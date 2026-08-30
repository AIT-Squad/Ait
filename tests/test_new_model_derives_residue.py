"""derives-mention residue scan (new_model_validator + validate-new-model wiring).

Covers [TDD]-new_model_validator (scan_derives_residue) and its exposure via
`specgraph validate-new-model`.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.new_model_validator import DERIVES_RESIDUE, scan_derives_residue
from ait.specgraph import load_specgraph, make_uri, specgraph_path, sync_specgraph


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


# ── v2.99: legal derives targets only ─────────────────────────────────────
#
# The scan used to judge every fsd/ chunk alike. A requirement can only derive
# to an FSD split — never to a root (that shape does not exist) and never to an
# acceptance node (traceability AC#2). Reporting those produced findings nobody
# could fix, which kept the count from ever reaching zero.

_MENTION = "承接 [PRD]-app:feat 的能力契约"


def test_fsd_root_chunk_is_not_a_derives_target():
    view = _StubView({})
    out = scan_derives_residue(view, [("fsd/[FSD]-app", "[FSD]-app", _MENTION)])
    assert out == []


def test_fsd_root_skipped_regardless_of_suffix_argument():
    view = _StubView({})
    contents = [("fsd/[FSD]-app", "[FSD]-app", _MENTION)]
    assert scan_derives_residue(view, contents, acceptance_suffixes=(":TEST",)) == []


def test_acceptance_node_skipped_when_suffix_supplied():
    view = _StubView({})
    contents = [("fsd/[FSD]-app", "[FSD]-app:TEST", _MENTION)]
    assert scan_derives_residue(view, contents, acceptance_suffixes=(":TEST",)) == []


def test_acceptance_node_still_judged_when_no_suffix_supplied():
    """The scan must not guess which suffixes are acceptance nodes."""
    view = _StubView({})
    contents = [("fsd/[FSD]-app", "[FSD]-app:TEST", _MENTION)]
    out = scan_derives_residue(view, contents)
    assert [v.chunk_id for v in out] == ["[FSD]-app:TEST"]


def test_multiple_suffixes_are_each_matched():
    view = _StubView({})
    contents = [
        ("fsd/[FSD]-app", "[FSD]-app:TEST", _MENTION),
        ("fsd/[FSD]-app", "[FSD]-app:ACCEPT", _MENTION),
        ("fsd/[FSD]-app", "[FSD]-app:feat", _MENTION),
    ]
    out = scan_derives_residue(view, contents, acceptance_suffixes=(":TEST", ":ACCEPT"))
    assert [v.chunk_id for v in out] == ["[FSD]-app:feat"]


def test_suffix_matches_on_end_not_substring():
    view = _StubView({})
    contents = [("fsd/[FSD]-app", "[FSD]-app:TESTING_helper", _MENTION)]
    out = scan_derives_residue(view, contents, acceptance_suffixes=(":TEST",))
    assert [v.chunk_id for v in out] == ["[FSD]-app:TESTING_helper"]


def test_ordinary_splits_are_still_judged():
    """Container splits and capability splits are both legal targets."""
    view = _StubView({})
    contents = [
        ("fsd/[FSD]-ait", "[FSD]-ait:new_model", _MENTION),      # container split
        ("fsd/[FSD]-app", "[FSD]-app:feat", _MENTION),           # capability split
    ]
    out = scan_derives_residue(view, contents, acceptance_suffixes=(":TEST",))
    assert {v.chunk_id for v in out} == {"[FSD]-ait:new_model", "[FSD]-app:feat"}


def test_narrowing_does_not_hide_a_real_missing_edge():
    view = _StubView({"[FSD]-app:other": ["[PRD]-app:feat"]})
    contents = [
        ("fsd/[FSD]-app", "[FSD]-app:feat", _MENTION),   # claims, no edge
        ("fsd/[FSD]-app", "[FSD]-app:other", _MENTION),  # claims, has edge
    ]
    out = scan_derives_residue(view, contents, acceptance_suffixes=(":TEST",))
    assert [v.chunk_id for v in out] == ["[FSD]-app:feat"]
