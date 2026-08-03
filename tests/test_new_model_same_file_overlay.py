"""G17: FSD 同文件局部 Overlay 回归。"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.chunk_parser import parse_file
from ait.cli import main
from ait.index_manager import IndexManager
from ait.specgraph import combined_view, load_specgraph
from ait.version_manager import VersionManager


PRD = "<!-- @id:[PRD]-app -->\n## App PRD\n"
FSD_BASE = """<!-- @id:[FSD]-app -->
## App FSD

<!-- @id:[FSD]-app:feat -->
## feat baseline
```yaml
depends_on: [store]
```

<!-- @id:[FSD]-app:store -->
## store baseline
```yaml
depends_on: [feat]
```
"""
FSD_FEAT_PARTIAL = """<!-- @id:[FSD]-app:feat -->
## feat changed
```yaml
depends_on: [store]
```
"""
FSD_STORE_PARTIAL = """<!-- @id:[FSD]-app:store -->
## store changed
```yaml
depends_on: [feat]
```
"""
FSD_FULL_REPLAY = """<!-- @id:[FSD]-app -->
## App FSD

<!-- @id:[FSD]-app:feat -->
## feat changed
```yaml
depends_on: [store]
```

<!-- @id:[FSD]-app:store -->
## store changed
```yaml
depends_on: [feat]
```
"""


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _run(runner: CliRunner, *args: str) -> dict:
    return _payload(runner.invoke(main, list(args), catch_exceptions=False))


def _project(workspace: Path) -> Path:
    root = workspace / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def _merged_baseline(runner: CliRunner) -> None:
    assert _run(runner, "version", "create", "v0.1")["ok"]
    assert _run(runner, "prd", "create", "[PRD]-app", "--skip-context", "--content", PRD)["ok"]
    assert _run(runner, "prd", "confirm")["ok"]
    assert _run(
        runner,
        "fsd",
        "create",
        "[FSD]-app",
        "--parent",
        "[PRD]-app",
        "--skip-context",
        "--content",
        FSD_BASE,
    )["ok"]
    assert _run(runner, "version", "commit", "v0.1")["ok"]
    assert _run(runner, "version", "merge", "v0.1")["ok"]


def _open_iteration(runner: CliRunner) -> None:
    assert _run(runner, "version", "create", "v0.2")["ok"]
    assert _run(
        runner,
        "prd",
        "create",
        "[PRD]-app",
        "--action",
        "modify",
        "--overrides",
        "[PRD]-app",
        "--skip-context",
        "--content",
        PRD,
    )["ok"]
    assert _run(runner, "prd", "confirm")["ok"]


def _modify_split(runner: CliRunner, split_id: str, content: str) -> dict:
    return _run(
        runner,
        "fsd",
        "create",
        split_id,
        "--version",
        "v0.2",
        "--file",
        "fsd/[FSD]-app",
        "--action",
        "modify",
        "--overrides",
        split_id,
        "--skip-context",
        "--content",
        content,
    )


def test_partial_modify_resolves_baseline_sibling_and_records_only_target(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _merged_baseline(runner)
    _open_iteration(runner)

    result = _modify_split(runner, "[FSD]-app:feat", FSD_FEAT_PARTIAL)

    assert result["ok"], result
    assert result["data"]["chunks"] == ["[FSD]-app:feat"]
    index = IndexManager(root).load_version_index("v0.2")
    assert [chunk.id for chunk in index.chunks if chunk.id.startswith("[FSD]-")] == ["[FSD]-app:feat"]
    view = combined_view(root, "v0.2")
    assert [edge.dst for edge in view.edges_from("[FSD]-app:feat", "depends_on")] == ["[FSD]-app:store"]

    graph = load_specgraph(root, "v0.2")
    preserved = [edge for edge in graph.edges if edge.rel == "depends_on" and ":baseline:[FSD]-app:store" in edge.src]
    assert preserved, "未改 sibling 的保留边必须继续使用 baseline 端点"


def test_sequential_partial_modifies_preserve_both_chunks_in_version_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _merged_baseline(runner)
    _open_iteration(runner)

    assert _modify_split(runner, "[FSD]-app:feat", FSD_FEAT_PARTIAL)["ok"]
    assert _modify_split(runner, "[FSD]-app:store", FSD_STORE_PARTIAL)["ok"]

    version_file = root / "versions" / "v0.2" / "fsd" / "[FSD]-app.md"
    parsed = parse_file(version_file, root / "versions" / "v0.2")
    assert {chunk.id for chunk in parsed.chunks} == {"[FSD]-app", "[FSD]-app:feat", "[FSD]-app:store"}
    assert "feat changed" in version_file.read_text(encoding="utf-8")
    assert "store changed" in version_file.read_text(encoding="utf-8")
    index = IndexManager(root).load_version_index("v0.2")
    assert {chunk.id for chunk in index.chunks if chunk.id.startswith("[FSD]-")} == {
        "[FSD]-app:feat",
        "[FSD]-app:store",
    }


def test_partial_and_full_replay_have_equivalent_combined_graphs(tmp_path: Path, monkeypatch):
    partial_workspace = tmp_path / "partial"
    partial_root = _project(partial_workspace)
    monkeypatch.chdir(partial_workspace)
    partial_runner = CliRunner()
    _merged_baseline(partial_runner)
    _open_iteration(partial_runner)
    assert _modify_split(partial_runner, "[FSD]-app:feat", FSD_FEAT_PARTIAL)["ok"]
    assert _modify_split(partial_runner, "[FSD]-app:store", FSD_STORE_PARTIAL)["ok"]

    full_workspace = tmp_path / "full"
    full_root = _project(full_workspace)
    monkeypatch.chdir(full_workspace)
    full_runner = CliRunner()
    _merged_baseline(full_runner)
    _open_iteration(full_runner)
    replay = _run(
        full_runner,
        "fsd",
        "create",
        "[FSD]-app",
        "--version",
        "v0.2",
        "--file",
        "fsd/[FSD]-app",
        "--action",
        "modify",
        "--overrides",
        "[FSD]-app",
        "--skip-context",
        "--content",
        FSD_FULL_REPLAY,
    )
    assert replay["ok"], replay

    partial_view = combined_view(partial_root, "v0.2")
    full_view = combined_view(full_root, "v0.2")
    assert set(partial_view.nodes) == set(full_view.nodes)
    assert {(edge.src, edge.dst, edge.rel) for edge in partial_view.edges} == {
        (edge.src, edge.dst, edge.rel) for edge in full_view.edges
    }


def test_fsd_confirm_rejects_index_entry_missing_from_version_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _merged_baseline(runner)
    _open_iteration(runner)
    assert _modify_split(runner, "[FSD]-app:feat", FSD_FEAT_PARTIAL)["ok"]

    version_file = root / "versions" / "v0.2" / "fsd" / "[FSD]-app.md"
    version_file.write_text(
        "<!-- @id:[FSD]-app -->\n## App FSD\n\n"
        "<!-- @id:[FSD]-app:store -->\n## store baseline\n",
        encoding="utf-8",
    )
    meta_before = (root / ".meta" / "versions" / "v0.2.yaml").read_bytes()
    index_before = (root / ".meta" / "chunks-index-v0.2.yaml").read_bytes()
    graph_before = (root / ".meta" / "specgraph-v0.2.yaml").read_bytes()

    result = _run(runner, "fsd", "confirm", "--version", "v0.2")

    assert result["ok"] is False and result["code"] == "VERSION_INDEX_SOURCE_MISSING"
    assert (root / ".meta" / "versions" / "v0.2.yaml").read_bytes() == meta_before
    assert (root / ".meta" / "chunks-index-v0.2.yaml").read_bytes() == index_before
    assert (root / ".meta" / "specgraph-v0.2.yaml").read_bytes() == graph_before
    assert VersionManager(root).load_version_meta("v0.2").phase == "fsd-creating"
