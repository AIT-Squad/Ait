"""v2.81: `ait push` publishes both repos ([TDD]-dual_repo_publish_tests).

No network: the "remotes" are local bare repos under tmp_path, so `git push`
runs for real while staying offline.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.publisher import ANCHOR_TAG_REFSPEC, REPO_ORDER, Publisher


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def _scaffold_docs(docs: Path) -> None:
    """A docs repo must look like a real project-docs/ for CLI root resolution."""
    for sub in ("docs", ".meta/versions", ".meta/changes"):
        (docs / sub).mkdir(parents=True, exist_ok=True)
        (docs / sub / ".gitkeep").write_text("", encoding="utf-8")


def _init(repo: Path, remote: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "a@b.c")
    _git(repo, "config", "user.name", "x")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")


@pytest.fixture
def repos(tmp_path: Path):
    """host/ + host/project-docs/, each tracking its own local bare remote."""
    host_remote = tmp_path / "remotes" / "host.git"
    docs_remote = tmp_path / "remotes" / "docs.git"
    for bare in (host_remote, docs_remote):
        bare.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], capture_output=True)

    host = tmp_path / "host"
    docs = host / "project-docs"
    _init(host, host_remote)
    _scaffold_docs(docs)
    _init(docs, docs_remote)
    return host, docs, host_remote, docs_remote


def _commit(repo: Path, msg: str) -> None:
    (repo / f"{msg}.txt").write_text(msg, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)


def _remote_log(bare: Path) -> list[str]:
    out = subprocess.run(
        ["git", f"--git-dir={bare}", "log", "--oneline"], capture_output=True, text=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _remote_tags(bare: Path) -> list[str]:
    out = subprocess.run(
        ["git", f"--git-dir={bare}", "tag", "-l"], capture_output=True, text=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _by_repo(result: dict) -> dict:
    return {item["repo"]: item for item in result["repos"]}


def test_publish_order_host_before_docs(repos):
    host, docs, host_remote, docs_remote = repos
    _commit(host, "code")
    _commit(docs, "spec")

    result = Publisher(docs).publish()

    assert REPO_ORDER == ("host", "docs")
    assert [item["repo"] for item in result["repos"]] == ["host", "docs"]
    assert result["passed"] is True
    assert all(item["outcome"] == "pushed" for item in result["repos"])
    assert any("code" in line for line in _remote_log(host_remote))
    assert any("spec" in line for line in _remote_log(docs_remote))


def test_anchor_tags_pushed_with_docs(repos):
    host, docs, _host_remote, docs_remote = repos
    _commit(docs, "spec")
    _git(docs, "tag", "ait/v9.9")
    _git(docs, "tag", "unrelated-tag")

    result = Publisher(docs).publish()

    assert result["passed"] is True
    tags = _remote_tags(docs_remote)
    assert "ait/v9.9" in tags
    # the refspec is scoped to refs/tags/ait/* — nothing else travels
    assert "unrelated-tag" not in tags
    assert ANCHOR_TAG_REFSPEC == "refs/tags/ait/*"


def test_host_failure_skips_docs_and_rolls_nothing_back(repos):
    host, docs, _host_remote, docs_remote = repos
    _commit(host, "code")
    _commit(docs, "spec")
    _git(host, "remote", "set-url", "origin", str(docs.parent / "nope.git"))

    before = _remote_log(docs_remote)
    result = Publisher(docs).publish()
    by = _by_repo(result)

    assert result["passed"] is False
    assert by["host"]["outcome"] == "failed"
    assert by["host"]["error_code"] == "PUSH_FAILED"
    # order precondition unmet → docs never pushed, remote untouched
    assert by["docs"]["outcome"] == "skipped"
    assert _remote_log(docs_remote) == before


def test_docs_failure_keeps_host_push_and_rerun_converges(repos):
    host, docs, host_remote, docs_remote = repos
    _commit(host, "code")
    _commit(docs, "spec")
    _git(docs, "remote", "set-url", "origin", str(docs.parent / "nope.git"))

    first = _by_repo(Publisher(docs).publish())
    assert first["host"]["outcome"] == "pushed"
    assert first["docs"]["outcome"] == "failed"
    # the successful host push is NOT undone
    assert any("code" in line for line in _remote_log(host_remote))

    # publishing is idempotent: fix docs, rerun, only docs remains to do
    _git(docs, "remote", "set-url", "origin", str(docs_remote))
    second_result = Publisher(docs).publish()
    second = _by_repo(second_result)
    assert second_result["passed"] is True
    assert second["host"]["outcome"] == "nothing-to-push"
    assert second["docs"]["outcome"] == "pushed"


@pytest.mark.parametrize("breakage", ["no-remote", "no-upstream"])
def test_missing_config_error_codes(repos, breakage):
    host, docs, _host_remote, _docs_remote = repos
    _commit(host, "code")
    if breakage == "no-remote":
        _git(host, "remote", "remove", "origin")
        expected = "PUSH_NO_REMOTE"
    else:
        _git(host, "checkout", "-q", "-b", "orphan")
        _commit(host, "on-orphan")
        expected = "PUSH_NO_UPSTREAM"

    by = _by_repo(Publisher(docs).publish())

    assert by["host"]["outcome"] == "failed"
    assert by["host"]["error_code"] == expected
    # nothing was auto-created / auto-set
    if breakage == "no-remote":
        assert not _git(host, "remote").stdout.strip()
    else:
        assert _git(host, "rev-parse", "--abbrev-ref", "orphan@{u}").returncode != 0


def test_dirty_reported_but_not_blocking(repos):
    host, docs, _host_remote, docs_remote = repos
    _commit(docs, "spec")
    (docs / "uncommitted.txt").write_text("wip", encoding="utf-8")

    by = _by_repo(Publisher(docs).publish())

    assert by["docs"]["outcome"] == "pushed"
    assert by["docs"]["dirty"] is True
    # the uncommitted file did not travel
    files = subprocess.run(
        ["git", f"--git-dir={docs_remote}", "ls-tree", "-r", "--name-only", "main"],
        capture_output=True, text=True,
    ).stdout
    assert "uncommitted.txt" not in files


def test_nothing_to_push_is_success(repos):
    _host, docs, _hr, _dr = repos
    result = Publisher(docs).publish()
    assert result["passed"] is True
    assert all(item["outcome"] == "nothing-to-push" for item in result["repos"])


def test_dry_run_touches_no_remote(repos):
    host, docs, host_remote, docs_remote = repos
    _commit(host, "code")
    _commit(docs, "spec")
    snapshot = (
        _remote_log(host_remote), _remote_log(docs_remote),
        _remote_tags(host_remote), _remote_tags(docs_remote),
    )

    result = Publisher(docs).publish(dry_run=True)
    by = _by_repo(result)

    assert result["dry_run"] is True and result["passed"] is True
    assert by["host"]["outcome"] == "dry-run" and by["host"]["commits"]
    assert by["docs"]["outcome"] == "dry-run" and by["docs"]["commits"]
    assert snapshot == (
        _remote_log(host_remote), _remote_log(docs_remote),
        _remote_tags(host_remote), _remote_tags(docs_remote),
    )


def test_host_not_a_repo(tmp_path: Path):
    docs_remote = tmp_path / "remotes" / "docs.git"
    docs_remote.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", str(docs_remote)], capture_output=True)
    host = tmp_path / "plain"          # no .git here
    docs = host / "project-docs"
    _scaffold_docs(docs)
    _init(docs, docs_remote)
    _commit(docs, "spec")

    result = Publisher(docs).publish()
    by = _by_repo(result)

    assert by["host"]["outcome"] == "not-a-repo"
    assert by["docs"]["outcome"] == "pushed"
    assert result["passed"] is True


def test_no_force_flags_in_source():
    """Guards the "never rewrites remote history" promise against future edits."""
    source = Path(__file__).resolve().parents[1] / "skill" / "ait" / "ait" / "publisher.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in ("--force", "--force-with-lease", "--delete", "--mirror", "shell=True"):
        assert forbidden not in text, f"publisher.py must not contain {forbidden}"


def test_cli_push_envelope(repos, monkeypatch):
    host, docs, _host_remote, _docs_remote = repos
    _commit(host, "code")
    _commit(docs, "spec")
    monkeypatch.chdir(host)
    runner = CliRunner()

    dry = json.loads(runner.invoke(main, ["push", "--dry-run"]).output.strip().splitlines()[-1])
    assert dry["ok"] is True and dry["data"]["dry_run"] is True

    live = json.loads(runner.invoke(main, ["push"]).output.strip().splitlines()[-1])
    assert live["ok"] is True
    assert {item["repo"]: item["outcome"] for item in live["data"]["repos"]} == {
        "host": "pushed", "docs": "pushed",
    }

    _commit(host, "more")
    _git(host, "remote", "remove", "origin")
    broken = json.loads(runner.invoke(main, ["push"]).output.strip().splitlines()[-1])
    assert broken["ok"] is False
    assert broken["code"] == "PUSH_NO_REMOTE"
