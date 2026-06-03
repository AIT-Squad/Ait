"""Baseline PRD 单文件化 — 一次性自检脚本。

实现 impl-prd-global-parser-compat-check #3 (T-prd-global-single-file-03)。

迁移完成后的人工触发自检：`python scripts/verify_prd_global_invariants.py`。

打印项：
  - docs/prd/ 是否仅有 global.md 一个 .md 文件
  - baseline chunks-index 中 PRD chunk 总数 + file 字段唯一值集合
  - specgraph 中 PRD 类型 spec 节点 + 边数
  - 调用 `ait state` / `ait specgraph` / `ait deps prd-prd-global-single-file` /
    `ait impact prd-prd-global-single-file` 的 returncode == 0

退出码：
  0 = 所有不变量通过
  1 = 存在违反不变量的项
  2 = 脚本自身异常
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILL_AIT = _REPO_ROOT / "skill" / "ait"
if _SKILL_AIT.exists() and str(_SKILL_AIT) not in sys.path:
    sys.path.insert(0, str(_SKILL_AIT))

from ait.index_manager import IndexManager  # noqa: E402
from ait.specgraph import SpecGraph, parse_uri  # noqa: E402


_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def _ok_line(label: str, detail: str = "") -> None:
    msg = f"{_GREEN}✓{_RESET} {label}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


def _fail_line(label: str, detail: str) -> None:
    print(f"{_RED}✗{_RESET} {label}  ({detail})")


def _check_prd_single_file(root: Path) -> bool:
    prd_dir = root / "docs" / "prd"
    md_files = sorted(p.name for p in prd_dir.glob("*.md"))
    if md_files == ["global.md"]:
        _ok_line("docs/prd/ 只有 global.md", f"{md_files}")
        return True
    _fail_line("docs/prd/ 应只含 global.md", f"actual={md_files}")
    return False


def _check_baseline_chunks_index(root: Path) -> bool:
    indexes = IndexManager(root)
    baseline = indexes.load_baseline()
    prd_entries = [c for c in baseline.chunks if c.id.startswith("prd-")]
    files = {e.file for e in prd_entries}
    ok_total = len(prd_entries) >= 1
    ok_files = files == {"prd/global"}
    if ok_total and ok_files:
        _ok_line(
            "baseline chunks-index PRD 不变量",
            f"total={len(prd_entries)} files={files}",
        )
        return True
    _fail_line(
        "baseline chunks-index PRD 不变量违反",
        f"total={len(prd_entries)} files={files}",
    )
    return False


def _check_specgraph_prd(root: Path) -> bool:
    graph_path = root / ".meta" / "specgraph.yaml"
    if not graph_path.exists():
        _fail_line("specgraph.yaml 缺失", str(graph_path))
        return False
    graph = SpecGraph.load(graph_path)
    prd_specs = [s for s in graph.specs.values() if s.type == "prd"]
    prd_edges = []
    for e in graph.edges:
        try:
            src_t, _, _ = parse_uri(e.src)
            dst_t, _, _ = parse_uri(e.dst)
        except ValueError:
            continue
        if src_t == "prd" or dst_t == "prd":
            prd_edges.append(e)
    _ok_line(
        "specgraph PRD 节点/边",
        f"specs={len(prd_specs)} edges={len(prd_edges)}",
    )
    return True


def _run_ait_cmd(root: Path, *args: str) -> tuple[int, str, str]:
    if root.name != "project-docs":
        return 2, "", f"root dir name != 'project-docs': {root.name}"
    env = os.environ.copy()
    if _SKILL_AIT.exists():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            os.pathsep.join([str(_SKILL_AIT), existing]) if existing else str(_SKILL_AIT)
        )
    cmd = [sys.executable, "-m", "ait.cli", *args]
    res = subprocess.run(
        cmd,
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return res.returncode, res.stdout, res.stderr


def _check_cli_commands(root: Path) -> bool:
    """ait state / ait specgraph / ait deps / ait impact 都应 returncode == 0。"""
    targets = [
        ("state",),
        ("specgraph", "sync"),
        ("deps", "prd-prd-global-single-file"),
        ("impact", "prd-prd-global-single-file"),
    ]
    all_ok = True
    for argv in targets:
        rc, out, err = _run_ait_cmd(root, *argv)
        label = "ait " + " ".join(argv)
        if rc == 0:
            _ok_line(label, "returncode=0")
        else:
            _fail_line(label, f"returncode={rc} stderr={err.strip()[:200]}")
            all_ok = False
    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify PRD single-file baseline invariants after migration."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("project-docs"),
        help="project-docs root (default: ./project-docs)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if not (root / "docs" / "prd" / "global.md").exists():
        print(
            f"{_RED}docs/prd/global.md not found under {root} —— "
            f"请先跑 scripts/migrate_prd_to_global.py --apply 完成迁移。{_RESET}"
        )
        return 1

    print(f"verifying PRD single-file invariants under: {root}\n")
    results = [
        _check_prd_single_file(root),
        _check_baseline_chunks_index(root),
        _check_specgraph_prd(root),
        _check_cli_commands(root),
    ]
    print()
    if all(results):
        print(f"{_GREEN}ALL OK{_RESET} — invariants hold.")
        return 0
    print(f"{_RED}FAILED{_RESET} — see above.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        raise SystemExit(2)
