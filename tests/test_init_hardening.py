"""v2.28 init --new-model 加固:R3-01 幽灵空基线 + R3-03 路径穿越。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.init_manager import InitManager, InitManagerError


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _fresh(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    root.mkdir(parents=True)
    return root


@pytest.mark.parametrize("bad", ["MyApp", "my app", "项目", "a/b", "../x", "x.y", "UPPER-case"])
def test_invalid_name_rejected(tmp_path: Path, bad: str):
    root = _fresh(tmp_path)
    with pytest.raises(InitManagerError) as exc:
        InitManager(root).run(project_name=bad)
    assert exc.value.code == "INVALID_PROJECT_NAME"
    # 拒绝 = 不产半成品文档
    assert not (root / "docs" / "prd").exists() or not any((root / "docs" / "prd").glob("*.md"))


@pytest.mark.parametrize("good", ["proj", "my_app", "book-shop", "a1_b2-c3"])
def test_valid_name_materializes_roots(tmp_path: Path, good: str):
    root = _fresh(tmp_path)
    result = InitManager(root).run(project_name=good)
    assert result.chunks >= 2, f"根 chunk 应落地,得到 chunks={result.chunks}"
    baseline = InitManager(root).indexes.load_baseline()
    ids = {c.id for c in baseline.chunks}
    assert f"[PRD]-{good}" in ids and f"[FSD]-{good}" in ids
    # derives 边建立(PRD→FSD)
    from ait.specgraph import load_specgraph
    g = load_specgraph(root)
    def cid(uri):
        s = g.specs.get(uri); return s.chunk_id if s else uri
    dec = {(cid(e.src), cid(e.dst)) for e in g.edges if e.rel == "derives"}
    assert (f"[PRD]-{good}", f"[FSD]-{good}") in dec


def test_path_traversal_name_rejected_no_escape(tmp_path: Path):
    root = _fresh(tmp_path)
    with pytest.raises(InitManagerError) as exc:
        InitManager(root).run(project_name="x/../../../ESCAPED")
    assert exc.value.code == "INVALID_PROJECT_NAME"
    assert not list(tmp_path.rglob("ESCAPED*")), "禁止穿越落盘"


def test_cli_invalid_name_returns_json(tmp_path: Path, monkeypatch):
    root = _fresh(tmp_path)
    (root / ".meta").mkdir()
    (root / "docs").mkdir()
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(main, ["init", "--name", "MyApp"],
                           catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "INVALID_PROJECT_NAME"


def test_bootstrap_failed_when_roots_missing(tmp_path: Path, monkeypatch):
    """兜底:即便校验放过,若根 chunk 未落地也报 BOOTSTRAP_FAILED(不假成功)。"""
    root = _fresh(tmp_path)
    mgr = InitManager(root)
    # 让 rebuild_baseline 返回空基线,模拟解析失败
    empty = mgr.indexes.load_baseline()
    empty.chunks = []
    monkeypatch.setattr(mgr.indexes, "rebuild_baseline", lambda: empty)
    with pytest.raises(InitManagerError) as exc:
        mgr.run(project_name="proj")
    assert exc.value.code == "BOOTSTRAP_FAILED"


def test_new_model_bootstrap_relation_free_prd_body(tmp_path: Path):
    """v2.31: PRD 正文不含 @ref,derives 边在 specgraph(source=new-model-cli)。"""
    root = _fresh(tmp_path)
    InitManager(root).run(project_name="proj")
    prd_body = (root / "docs" / "prd" / "[PRD]-proj.md").read_text(encoding="utf-8")
    assert "@ref" not in prd_body, "PRD 正文不得承载关系声明"

    from ait.specgraph import load_specgraph
    g = load_specgraph(root)
    def cid(uri):
        s = g.specs.get(uri); return s.chunk_id if s else uri
    dec = {(cid(e.src), cid(e.dst)) for e in g.edges if e.rel == "derives"}
    assert ("[PRD]-proj", "[FSD]-proj") in dec, "derives 边应在 specgraph"


# ── v3.1: new-model bootstrap is init's only path ───────────────────────────


def test_default_init_produces_no_legacy_skeleton(tmp_path: Path):
    """Retired: docs/global/*, docs/impl/ and the global-* chunks they carried."""
    root = _fresh(tmp_path)
    InitManager(root).run(project_name="demo")

    assert not (root / "docs" / "global").exists()
    assert not (root / "docs" / "impl").exists()
    ids = [e.id for e in InitManager(root).indexes.load_baseline().chunks]
    assert not any(i.startswith("global-") for i in ids)
    assert set(ids) == {"[PRD]-demo", "[FSD]-demo"}


def test_deprecated_new_model_flag_is_a_no_op(tmp_path: Path, monkeypatch):
    """Accepted so old invocations don't hit USAGE_ERROR; changes nothing."""
    runner = CliRunner()
    outputs = []
    for label, args in (
        ("without", ["init", "--name", "demo"]),
        ("with", ["init", "--new-model", "--name", "demo"]),
    ):
        work = tmp_path / label
        work.mkdir()
        monkeypatch.chdir(work)
        r = runner.invoke(main, args, catch_exceptions=False)
        assert r.exit_code == 0, r.output
        data = _payload(r)["data"]
        outputs.append((sorted(data["created_files"]), data["chunks"], data["specs"]))

    assert outputs[0] == outputs[1]
    assert "docs/prd/[PRD]-demo.md" in outputs[0][0]


def test_skip_option_is_gone(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(main, ["init", "--skip", "api"])
    assert r.exit_code == 2
    assert _payload(r)["code"] == "USAGE_ERROR"


def test_check_reports_baseline_presence_without_writing(tmp_path: Path):
    root = _fresh(tmp_path)
    before = InitManager(root).run(check_only=True)
    assert before.status == "fresh"
    assert before.files == {}
    assert not (root / "docs").exists()

    InitManager(root).run(project_name="demo")
    after = InitManager(root).run(check_only=True)
    assert after.status == "ready"
    assert after.files == {}
