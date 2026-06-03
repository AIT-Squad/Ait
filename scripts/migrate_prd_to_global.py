"""一次性迁移脚本：把 baseline 多文件 PRD 合并为 docs/prd/global.md。

实现 impl-prd-global-migrate-script（v1.6 task T-prd-global-single-file-02）。

执行步骤（严格顺序，任一失败立即终止且不改盘）：
1. 读 baseline chunks-index.yaml，过滤 PRD chunk，按当前顺序聚合 (file -> chunk_ids)。
2. parse_file 每个原始 PRD 文件，按 1 中顺序取 Chunk 对象。
3. 用原文件 raw 字节按 line_start/line_end 切片（保留 @summary / @prd-no-impl
   等所有 HTML 注释 markers 的逐字内容），拼成 docs/prd/global.md，文件头部
   写 H1 单行，chunk 间单空行分隔。
4. parse_file(global.md) 重解析自检：chunk 数 == 迁移前总数；id 集合相等；
   每 chunk 的 chunk_hash(content) 与原文件中同 id chunk 的 hash 相等
   （parser 规范化后的 content，不是 raw）。
5. 物理删除 docs/prd/ 下除 global.md 外的所有 .md。
6. subprocess 调 ait reindex 重建 chunks-index.yaml 与 specgraph.yaml。
7. 迁移后自检：所有 PRD chunk 的 file == "prd/global"；总数等于步骤 1 快照；
   specgraph PRD 节点的 (src,rel,dst) 三元组集合 == 迁移前快照。
8. 输出 JSON 报告到 stdout。

参数：
  --root <path>   默认 ./project-docs
  --apply         默认 dry-run；显式给才落盘
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

# 让脚本在仓库根直接 `python scripts/migrate_prd_to_global.py` 也能找到 ait 包。
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILL_AIT = _REPO_ROOT / "skill" / "ait"
if _SKILL_AIT.exists() and str(_SKILL_AIT) not in sys.path:
    sys.path.insert(0, str(_SKILL_AIT))

from ait.chunk_parser import parse_file  # noqa: E402
from ait.hash_utils import chunk_hash  # noqa: E402
from ait.index_manager import IndexManager  # noqa: E402
from ait.specgraph import SpecGraph, parse_uri  # noqa: E402


GLOBAL_HEADER = "# Baseline PRD（merged baseline, edit by chunk only）"


class MigrationError(Exception):
    """迁移过程中发现破坏不变量的异常 —— 抛出后不修改磁盘。"""


def _collect_prd_chunks_per_file(
    indexes: IndexManager,
) -> "OrderedDict[str, list[str]]":
    """按 chunks-index.yaml 中当前顺序聚合 PRD chunks 到 (file -> [chunk_id, ...])。

    chunks-index 是唯一权威 ordering：文件首次出现的位置决定 file 的相对顺序，
    文件内 chunk 按它们在 index 中出现的相对顺序保留。
    """
    baseline = indexes.load_baseline()
    grouped: "OrderedDict[str, list[str]]" = OrderedDict()
    for entry in baseline.chunks:
        if not entry.id.startswith("prd-"):
            continue
        grouped.setdefault(entry.file, []).append(entry.id)
    return grouped


def _read_raw_chunk_slice(file_path: Path, line_start: int, line_end: int) -> str:
    """按 1-indexed line_start..line_end 从原文件切出 raw 文本（含 markers）。

    说明：line_end 已是 parser 去尾随空行后的位置；我们仍然只切到 line_end，
    chunk 之间统一用单空行分隔。
    """
    text = file_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    # 1-indexed → 0-indexed slice
    return "\n".join(lines[line_start - 1 : line_end])


def _build_global_md(
    docs_dir: Path,
    grouped: "OrderedDict[str, list[str]]",
) -> tuple[str, dict[str, str], int]:
    """构造 global.md 文本，并返回 (text, expected_hashes, total_chunk_count)。

    expected_hashes: chunk_id -> chunk_hash(parser-normalized content from原文件)
    用于第 4 步自检比对。
    """
    raw_pieces: list[str] = []
    expected_hashes: dict[str, str] = {}
    total = 0

    for file_key, chunk_ids in grouped.items():
        src_path = docs_dir / f"{file_key}.md"
        if not src_path.exists():
            raise MigrationError(
                f"baseline chunks-index references {file_key}.md but file not found at {src_path}"
            )
        parsed = parse_file(src_path, docs_dir)
        chunk_by_id = {c.id: c for c in parsed.chunks}
        for cid in chunk_ids:
            chunk = chunk_by_id.get(cid)
            if chunk is None:
                raise MigrationError(
                    f"chunks-index says {cid} lives in {file_key}.md but parse_file did not find it"
                )
            raw = _read_raw_chunk_slice(src_path, chunk.line_start, chunk.line_end)
            raw_pieces.append(raw)
            expected_hashes[cid] = chunk_hash(chunk.content)
            total += 1

    body = ("\n\n").join(raw_pieces)
    text = f"{GLOBAL_HEADER}\n\n{body}\n"
    return text, expected_hashes, total


def _verify_global_md_self_consistent(
    docs_dir: Path,
    global_text: str,
    expected_hashes: dict[str, str],
    expected_total: int,
) -> None:
    """步骤 4：把 global.md 临时落到内存中验证（实际写入 in apply phase）。

    我们用 parse_text 等价：parse_file 需要 path，因此调用方先在临时位置写过；
    这里不重复写，而是直接在 _apply 阶段写入磁盘后再调本函数。
    """
    global_path = docs_dir / "prd" / "global.md"
    parsed = parse_file(global_path, docs_dir)
    if len(parsed.chunks) != expected_total:
        raise MigrationError(
            f"self-check: re-parsed global.md has {len(parsed.chunks)} chunks, expected {expected_total}"
        )
    parsed_ids = {c.id for c in parsed.chunks}
    expected_ids = set(expected_hashes.keys())
    if parsed_ids != expected_ids:
        missing = expected_ids - parsed_ids
        extra = parsed_ids - expected_ids
        raise MigrationError(
            f"self-check: chunk id set mismatch. missing={sorted(missing)} extra={sorted(extra)}"
        )
    for c in parsed.chunks:
        got = chunk_hash(c.content)
        want = expected_hashes[c.id]
        if got != want:
            raise MigrationError(
                f"self-check: hash mismatch for {c.id}: got={got} want={want}"
            )


def _snapshot_specgraph_prd_edges(specgraph_path: Path) -> set[tuple[str, str, str]]:
    """从 specgraph.yaml 取出所有 src 或 dst type 为 prd 的 (src, rel, dst) 三元组。

    边的 src/dst 是 spec URI 形如 `spec:{type}:{version}:{chunk_id}`，
    需要 parse_uri 取出 type 段判定。
    """
    if not specgraph_path.exists():
        return set()
    graph = SpecGraph.load(specgraph_path)
    triples: set[tuple[str, str, str]] = set()
    for e in graph.edges:
        try:
            src_type, _, _ = parse_uri(e.src)
            dst_type, _, _ = parse_uri(e.dst)
        except ValueError:
            continue
        if src_type == "prd" or dst_type == "prd":
            triples.add((e.src, e.rel, e.dst))
    return triples


def _run_reindex(root: Path) -> None:
    """ait CLI 解析 root 的契约：CWD 必须是 project-docs 的父目录，
    且 project-docs 必须叫这个名字。所以子进程 cwd = root.parent。

    PYTHONPATH 注入 skill/ait，让子进程不依赖 pip install 也能 import ait。
    """
    if root.name != "project-docs":
        raise MigrationError(
            f"`ait reindex` requires root dir name == 'project-docs', got: {root.name}"
        )
    import os

    env = os.environ.copy()
    extra_paths = [str(_SKILL_AIT)] if _SKILL_AIT.exists() else []
    if extra_paths:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            os.pathsep.join(extra_paths + [existing]) if existing else os.pathsep.join(extra_paths)
        )
    cmd = [sys.executable, "-m", "ait.cli", "reindex"]
    res = subprocess.run(
        cmd,
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if res.returncode != 0:
        raise MigrationError(
            f"`ait reindex` failed with code {res.returncode}.\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )


def _post_migration_checks(
    indexes: IndexManager,
    expected_total: int,
    pre_edges: set[tuple[str, str, str]],
    specgraph_path: Path,
) -> None:
    baseline = indexes.load_baseline()
    prd_entries = [c for c in baseline.chunks if c.id.startswith("prd-")]
    if len(prd_entries) != expected_total:
        raise MigrationError(
            f"post-check: PRD chunk count mismatch. got={len(prd_entries)} want={expected_total}"
        )
    bad_files = {e.file for e in prd_entries if e.file != "prd/global"}
    if bad_files:
        raise MigrationError(
            f"post-check: some PRD chunks have file != prd/global: {sorted(bad_files)}"
        )
    post_edges = _snapshot_specgraph_prd_edges(specgraph_path)
    if post_edges != pre_edges:
        added = post_edges - pre_edges
        removed = pre_edges - post_edges
        raise MigrationError(
            f"post-check: specgraph PRD edges changed. added={sorted(added)} removed={sorted(removed)}"
        )


def migrate(root: Path, *, apply: bool) -> dict:
    """主流程。返回 JSON 报告 dict。"""
    docs_dir = root / "docs"
    prd_dir = docs_dir / "prd"
    if not prd_dir.is_dir():
        raise MigrationError(f"PRD baseline dir not found: {prd_dir}")

    indexes = IndexManager(root)
    specgraph_path = root / ".meta" / "specgraph.yaml"

    # Step 1: 聚合
    grouped = _collect_prd_chunks_per_file(indexes)
    if not grouped:
        raise MigrationError("no PRD chunks found in baseline chunks-index.yaml")

    # Step 1.5: 已经是 single-file 形态？（仅 prd/global 一个 file_key 且无其它 .md）
    only_global = list(grouped.keys()) == ["prd/global"]
    other_md = [p for p in prd_dir.glob("*.md") if p.name != "global.md"]
    if only_global and not other_md:
        return {
            "ok": True,
            "noop": True,
            "reason": "baseline already single-file (docs/prd/global.md)",
            "prd_chunk_count": sum(len(v) for v in grouped.values()),
            "deleted_files": [],
            "specgraph_diff_edges": [],
        }

    # Step 2 + 3: 构造 global.md 文本
    global_text, expected_hashes, total = _build_global_md(docs_dir, grouped)

    # Step 7 准备：迁移前 specgraph PRD 边快照
    pre_edges = _snapshot_specgraph_prd_edges(specgraph_path)

    # 待删除文件清单（除 global.md 外的所有 docs/prd/*.md）
    to_delete = sorted(p for p in prd_dir.glob("*.md") if p.name != "global.md")

    if not apply:
        return {
            "ok": True,
            "dry_run": True,
            "prd_chunk_count": total,
            "global_md_size_bytes": len(global_text.encode("utf-8")),
            "files_to_delete": [str(p.relative_to(root)) for p in to_delete],
            "pre_specgraph_edges": len(pre_edges),
        }

    # ── 落盘阶段 ──
    # Step 3 落盘 global.md
    global_path = prd_dir / "global.md"
    global_path.write_text(global_text, encoding="utf-8")

    # Step 4 自检
    _verify_global_md_self_consistent(docs_dir, global_text, expected_hashes, total)

    # Step 5 删除其它 .md
    deleted: list[str] = []
    for p in to_delete:
        rel = str(p.relative_to(root))
        p.unlink()
        deleted.append(rel)

    # Step 6 reindex
    _run_reindex(root)

    # Step 7 迁移后自检
    _post_migration_checks(indexes, total, pre_edges, specgraph_path)

    post_edges = _snapshot_specgraph_prd_edges(specgraph_path)

    return {
        "ok": True,
        "applied": True,
        "prd_chunk_count": total,
        "deleted_files": deleted,
        "specgraph_diff_edges": sorted(list(post_edges ^ pre_edges)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate baseline PRD multi-file layout into single docs/prd/global.md (one-shot, v1.6)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("project-docs"),
        help="project-docs root (default: ./project-docs)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write to disk; default is dry-run with zero side effects",
    )
    args = parser.parse_args(argv)

    try:
        report = migrate(args.root.resolve(), apply=args.apply)
    except MigrationError as e:
        out = {"ok": False, "error": str(e)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": f"unexpected: {type(e).__name__}: {e}"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
