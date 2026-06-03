from __future__ import annotations

from pathlib import Path

from ait.index_manager import IndexManager
from ait.schemas import BaselineChunkEntry, BaselineIndex
from ait.yaml_io import save_model


def _init(root: Path) -> IndexManager:
    (root / "docs" / "prd").mkdir(parents=True)
    (root / ".meta").mkdir()
    return IndexManager(root)


def test_rebuild_preserves_existing_summary(tmp_path: Path):
    mgr = _init(tmp_path)
    (tmp_path / "docs" / "prd" / "feature.md").write_text(
        "<!-- @id:prd-summary-demo -->\n## Demo\n\nBody\n",
        encoding="utf-8",
    )
    save_model(
        mgr.baseline_index_path(),
        BaselineIndex(
            chunks=[
                BaselineChunkEntry(
                    id="prd-summary-demo",
                    file="prd/feature",
                    heading="Old",
                    level=2,
                    summary="旧摘要",
                )
            ]
        ),
    )

    baseline, _ = mgr.rebuild_baseline()

    assert baseline.chunks[0].summary == "旧摘要"


def test_rebuild_picks_markdown_over_index(tmp_path: Path):
    mgr = _init(tmp_path)
    (tmp_path / "docs" / "prd" / "feature.md").write_text(
        "<!-- @id:prd-summary-demo -->\n## Demo\n\n<!-- @summary: 新摘要 -->\n\nBody\n",
        encoding="utf-8",
    )
    save_model(
        mgr.baseline_index_path(),
        BaselineIndex(
            chunks=[
                BaselineChunkEntry(
                    id="prd-summary-demo",
                    file="prd/feature",
                    heading="Old",
                    level=2,
                    summary="旧摘要",
                )
            ]
        ),
    )

    baseline, _ = mgr.rebuild_baseline()

    assert baseline.chunks[0].summary == "新摘要"
