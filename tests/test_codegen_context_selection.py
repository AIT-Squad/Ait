from __future__ import annotations

from pathlib import Path

from ait.index_manager import IndexManager
from ait.new_model_manager import NewModelManager
from ait.specgraph import load_specgraph, make_uri, specgraph_path, sync_specgraph
from ait.version_manager import VersionManager


def _write(root: Path, relative: str, content: str) -> None:
    path = root / "docs" / f"{relative}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _add_edge(graph, src: str, src_file: str, dst: str, dst_file: str, rel: str) -> None:
    graph.add_edge(
        make_uri(src, "baseline", src_file),
        make_uri(dst, "baseline", dst_file),
        rel,
        metadata={"source": "test"},
    )


def _manager(tmp_path: Path) -> NewModelManager:
    root = tmp_path / "project-docs"
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    _write(
        root,
        "prd/[PRD]-app",
        """<!-- @id:[PRD]-app -->
## App

<!-- @id:[PRD]-app:feature -->
## Feature requirement

<!-- @id:[PRD]-app:unrelated -->
## Unrelated requirement
""",
    )
    _write(
        root,
        "fsd/[FSD]-app",
        """<!-- @id:[FSD]-app -->
## App design

<!-- @id:[FSD]-app:feature -->
## Feature

<!-- @id:[FSD]-app:dependency -->
## Dependency

<!-- @id:[FSD]-app:unrelated -->
## Unrelated

<!-- @id:[FSD]-app:TEST -->
## Tests
""",
    )
    _write(
        root,
        "fsd/[FSD]-dependency",
        """<!-- @id:[FSD]-dependency -->
## Dependency design

<!-- @id:[FSD]-dependency:child -->
## Dependency child
""",
    )
    _write(
        root,
        "tdd/[TDD]-feature",
        """<!-- @id:[TDD]-feature -->
## Feature implementation

```yaml
target_file: app/feature.py
```
""",
    )
    _write(
        root,
        "tdd/[TDD]-dependency",
        """<!-- @id:[TDD]-dependency -->
## Dependency implementation

```yaml
target_file: app/dependency.py
```
""",
    )
    _write(
        root,
        "tdd/[TDD]-dependency-child",
        """<!-- @id:[TDD]-dependency-child -->
## Dependency child implementation

```yaml
target_file: app/dependency_child.py
```
""",
    )
    _write(
        root,
        "tdd/[TDD]-feature-tests",
        """<!-- @id:[TDD]-feature-tests -->
## Feature tests

```yaml
target_file: tests/test_feature.py
```
""",
    )

    IndexManager(root).rebuild_baseline()
    sync_specgraph(root)
    graph = load_specgraph(root)
    prd_file = "prd/[PRD]-app"
    fsd_file = "fsd/[FSD]-app"
    dependency_file = "fsd/[FSD]-dependency"
    feature_tdd_file = "tdd/[TDD]-feature"
    dependency_tdd_file = "tdd/[TDD]-dependency"
    child_tdd_file = "tdd/[TDD]-dependency-child"
    test_tdd_file = "tdd/[TDD]-feature-tests"
    _add_edge(graph, "[PRD]-app", prd_file, "[FSD]-app", fsd_file, "derives")
    _add_edge(graph, "[PRD]-app:feature", prd_file, "[FSD]-app:feature", fsd_file, "derives")
    _add_edge(graph, "[PRD]-app:unrelated", prd_file, "[FSD]-app:unrelated", fsd_file, "derives")
    _add_edge(graph, "[FSD]-app:feature", fsd_file, "[FSD]-app:dependency", fsd_file, "depends_on")
    _add_edge(graph, "[FSD]-app:dependency", fsd_file, "[FSD]-dependency", dependency_file, "decomposes")
    _add_edge(graph, "[FSD]-app:feature", fsd_file, "[TDD]-feature", feature_tdd_file, "details")
    _add_edge(graph, "[FSD]-app:dependency", fsd_file, "[TDD]-dependency", dependency_tdd_file, "details")
    _add_edge(graph, "[FSD]-dependency:child", dependency_file, "[TDD]-dependency-child", child_tdd_file, "details")
    _add_edge(graph, "[FSD]-app:TEST", fsd_file, "[TDD]-feature-tests", test_tdd_file, "details")
    graph.save(specgraph_path(root))

    versions = VersionManager(root)
    versions.create("v1.0")
    meta = versions.load_version_meta("v1.0")
    meta.phase = "tdd-confirm"
    versions.save_version_meta(meta)
    return NewModelManager(root)


def _reasons(items: list[dict]) -> dict[str, str]:
    return {item["id"]: item["selection_reason"] for item in items}


def test_codegen_includes_only_mapped_requirement_and_direct_dependency(tmp_path: Path):
    manager = _manager(tmp_path)

    bundle = manager.prepare_codegen("v1.0", "[TDD]-feature")

    assert _reasons(bundle.upstream) == {
        "[FSD]-app:feature": "parent_split",
        "[FSD]-app": "fsd_ancestor",
        "[PRD]-app": "prd_root",
        "[PRD]-app:feature": "prd_requirement",
    }
    assert _reasons(bundle.dependencies) == {"[FSD]-app:dependency": "depends_on_contract"}
    ids = {item["id"] for item in [*bundle.upstream, *bundle.dependencies]}
    assert "[PRD]-app:unrelated" not in ids
    assert "[FSD]-dependency" not in ids
    assert "[FSD]-dependency:child" not in ids
    assert "[TDD]-dependency-child" not in ids


def test_codegen_test_tdd_includes_covered_siblings_and_implementation_tdds(tmp_path: Path):
    manager = _manager(tmp_path)

    bundle = manager.prepare_codegen("v1.0", "[TDD]-feature-tests")

    reasons = _reasons(bundle.dependencies)
    assert reasons["[FSD]-app:feature"] == "test_covered_sibling"
    assert reasons["[TDD]-feature"] == "test_implementation_tdd"
    assert reasons["[FSD]-app:dependency"] == "test_covered_sibling"
    assert reasons["[TDD]-dependency"] == "test_implementation_tdd"
    assert "[FSD]-app:unrelated" not in reasons


def test_codegen_context_is_stable_for_active_version_and_baseline(tmp_path: Path):
    manager = _manager(tmp_path)

    active_first = manager.prepare_codegen("v1.0", "[TDD]-feature")
    active_second = manager.prepare_codegen("v1.0", "[TDD]-feature")
    baseline = manager.prepare_codegen(None, "[TDD]-feature")

    assert active_first.upstream == active_second.upstream == baseline.upstream
    assert active_first.dependencies == active_second.dependencies == baseline.dependencies
