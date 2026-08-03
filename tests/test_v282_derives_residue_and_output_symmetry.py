"""v2.82: derives-mention residue scan + ok()/fail() output symmetry.

Covers [TDD]-new_model_validator (derives residue) and [TDD]-cli (ok() exits,
derives_residue field wired into validate-new-model).
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.new_model_validator import DERIVES_RESIDUE, scan_derives_residue
from ait.specgraph import load_specgraph, make_uri, specgraph_path, sync_specgraph
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _write(root: Path, relative: str, content: str) -> None:
    path = root / "docs" / f"{relative}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _add_edge(graph, src, src_file, dst, dst_file, rel):
    graph.add_edge(
        make_uri(src, "baseline", src_file), make_uri(dst, "baseline", dst_file), rel,
        metadata={"source": "test"},
    )


class _StubEdge:
    def __init__(self, src):
        self.src = src


class _StubView:
    """Just enough of CombinedView.edges_to for scan_derives_residue."""

    def __init__(self, derives_by_dst: dict[str, list[str]]):
        self._map = derives_by_dst

    def edges_to(self, chunk_id, rel=None):
        assert rel == "derives"
        return [_StubEdge(src) for src in self._map.get(chunk_id, [])]


def test_no_residue_when_edge_exists():
    view = _StubView({"[FSD]-app:feat": ["[PRD]-app:feat"]})
    fsd_contents = [("fsd/[FSD]-app", "[FSD]-app:feat", "承接 [PRD]-app:feat 的能力契约")]
    assert scan_derives_residue(view, fsd_contents) == []


def test_residue_when_mentioned_without_edge():
    view = _StubView({})
    fsd_contents = [("fsd/[FSD]-app", "[FSD]-app:feat", "承接 [PRD]-app:feat 的能力契约")]
    out = scan_derives_residue(view, fsd_contents)
    assert len(out) == 1
    assert out[0].code == DERIVES_RESIDUE
    assert "[PRD]-app:feat" in out[0].message
    assert out[0].chunk_id == "[FSD]-app:feat"
    assert out[0].file == "fsd/[FSD]-app"


def test_multiple_unmentioned_ids_each_become_a_violation():
    view = _StubView({})
    content = "承接 [PRD]-app:feat 与 [PRD]-app:other 两条需求"
    out = scan_derives_residue(view, [("fsd/[FSD]-app", "[FSD]-app:feat", content)])
    assert {v.message for v in out} != set()  # each id gets its own message
    assert len(out) == 2
    mentioned_ids = {"[PRD]-app:feat", "[PRD]-app:other"}
    assert {pid for v in out for pid in mentioned_ids if pid in v.message} == mentioned_ids


def test_non_fsd_files_and_no_mention_are_skipped():
    view = _StubView({})
    fsd_contents = [
        ("tdd/[TDD]-app-feat", "[TDD]-app-feat", "提及 [PRD]-app:feat 但不是 fsd 文件"),
        ("fsd/[FSD]-app", "[FSD]-app", "没有提及任何需求 id"),
    ]
    assert scan_derives_residue(view, fsd_contents) == []


def _project(root: Path) -> None:
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    _write(root, "prd/[PRD]-app", "<!-- @id:[PRD]-app -->\n## App\n\n<!-- @id:[PRD]-app:feat -->\n## Feat requirement\n")
    _write(
        root, "fsd/[FSD]-app",
        "<!-- @id:[FSD]-app -->\n## App design\n\n<!-- @id:[FSD]-app:feat -->\n"
        "## Feat\n\n承接 [PRD]-app:feat 的能力契约\n\n<!-- @id:[FSD]-app:TEST -->\n## Tests\n",
    )
    NewModelManager(root).indexes.rebuild_baseline()
    sync_specgraph(root)


def test_cli_reports_derives_residue_without_edge(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    _project(root)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    r = runner.invoke(main, ["specgraph", "validate-new-model"])
    data = _payload(r)["data"]

    assert data["passed"] is True  # residue is report-only, does not gate `passed`
    assert any(v["code"] == "DERIVES_RESIDUE" and v["chunk_id"] == "[FSD]-app:feat"
               for v in data["derives_residue"])


def test_cli_no_residue_when_edge_present(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    _project(root)
    graph = load_specgraph(root, "baseline")
    _add_edge(graph, "[PRD]-app:feat", "prd/[PRD]-app", "[FSD]-app:feat", "fsd/[FSD]-app", "derives")
    graph.save(specgraph_path(root, "baseline"))
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    data = _payload(runner.invoke(main, ["specgraph", "validate-new-model"]))["data"]
    assert data["derives_residue"] == []


def test_ok_terminates_process(capsys):
    """ok() must exit(0) by itself — a call site relying on fall-through must
    never emit a second line."""
    import pytest
    from ait.cli import ok

    with pytest.raises(SystemExit) as exc:
        ok({"x": 1})
        # unreachable: proves ok() itself stops execution, not the test
        click_echo_marker = "should never run"
        raise AssertionError(click_echo_marker)
    assert exc.value.code == 0

    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0]) == {"ok": True, "data": {"x": 1}}
