"""Init manager — `/ait init` project bootstrapping (redesign).

`init` generates the global baseline (global PRD/impl overview + global static/
dynamic skeletons) directly into `docs/`. It does NOT consume a version number;
the first feature version (v1.0) is created later by `prd create`.

v1.5 update: `init` is now incremental.
- `fresh`      → no docs/global yet, run full bootstrap
- `incomplete` → docs/global exists but some files missing/skeleton-only
                 (write only what's missing; honor `skip` list with placeholders)
- `ready`      → all 5 globals present (no-op)
- `--check`    → diagnose only, no writes
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from .index_manager import IndexManager
from .io_utils import atomic_write_text
from .version_manager import VersionManager


class InitManagerError(RuntimeError):
    def __init__(self, message: str, code: str = "INIT_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class InitResult:
    created_files: list[str] = field(default_factory=list)
    chunks: int = 0
    specs: int = 0
    skill_dir: str = ""
    cli_path: str = ""
    wrapper_path: str = ""
    status: Literal["fresh", "incomplete", "ready"] = "fresh"
    files: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


# Static global skeletons (human-maintained). chunk_id → (filename, heading, body)
_STATIC_GLOBALS = {
    "global-overview": ("overview", "项目概述", "<!-- 项目定位、目标用户、核心价值。init 时讨论填充。 -->"),
    "global-tech-stack": ("tech-stack", "技术栈", "<!-- 语言/框架/存储/部署等技术选型。init 时讨论填充。 -->"),
}
# Dynamic global skeletons (sourced ONLY from impl @extract at version confirm).
_DYNAMIC_GLOBALS = {
    "ddl": "数据库 DDL",
    "schema": "数据结构 Schema",
    "api": "API 契约",
}

# All global filenames in canonical scan order. Used by `_scan_global_state`.
GLOBAL_FILES = ["overview", "tech-stack", "ddl", "schema", "api"]

# Regex to detect a `<!-- @id:global-* -->` chunk marker in a global file.
_GLOBAL_ID_RE = re.compile(r"<!--\s*@id:global-[\w-]+\s*-->")


class InitManager:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()
        self.indexes = IndexManager(self.root)
        self.versions = VersionManager(self.root)

    def has_any_version(self) -> bool:
        """True if the project is already managed (any version dir or meta).

        v1.5: kept for diagnostic use only — no longer hard-blocks `init`.
        """
        versions_dir = self.root / "versions"
        if versions_dir.exists() and any(versions_dir.iterdir()):
            return True
        meta_versions = self.root / ".meta" / "versions"
        if meta_versions.exists() and any(meta_versions.glob("*.yaml")):
            return True
        return False

    # ──────────────────────────────────────────────────
    # state detection
    # ──────────────────────────────────────────────────

    def _classify_global_file(self, path: Path) -> str:
        """Return one of: 'present' | 'skeleton' | 'missing'.

        - missing  : file does not exist or is empty.
        - skeleton : file exists with content but lacks `<!-- @id:global-* -->`.
        - present  : file exists and carries a chunk id marker (whether
                     auto-generated or user-customized).

        For the caller (`_run_incremental`), `skeleton` and `missing` are
        treated equivalently (both trigger fill); they're reported separately
        so `ait-init-guide` can show the user a meaningful diagnosis.
        """
        try:
            if not path.exists() or path.stat().st_size == 0:
                return "missing"
            text = path.read_text(encoding="utf-8")
        except Exception:
            return "missing"
        if not _GLOBAL_ID_RE.search(text):
            return "skeleton"
        return "present"

    def _scan_global_state(self) -> dict:
        """Return ``{"overall": str, "files": {name: status}}``.

        overall:
          - 'ready'      → all 5 files are 'present'
          - 'incomplete' → docs/global exists OR project-docs exists, but
                           ≥1 file is missing/skeleton
          - 'fresh'      → no project-docs and no docs/global yet
        """
        g = self.root / "docs" / "global"
        per_file: dict[str, str] = {}
        for name in GLOBAL_FILES:
            per_file[name] = self._classify_global_file(g / f"{name}.md")
        if all(s == "present" for s in per_file.values()):
            overall = "ready"
        elif (self.root / "project-docs").exists() or g.exists():
            overall = "incomplete"
        else:
            overall = "fresh"
        return {"overall": overall, "files": per_file}

    # ──────────────────────────────────────────────────
    # entrypoint
    # ──────────────────────────────────────────────────

    def run(
        self,
        *,
        check_only: bool = False,
        skip: Iterable[str] | None = None,
        new_model: bool = False,
        project_name: str = "project",
    ) -> InitResult:
        """Bootstrap or incrementally fill the global baseline.

        Args:
            check_only: diagnose only, no writes. Returns status + files dict.
            skip:       names (without `.md`) the user explicitly declined to
                        fill. Each gets a `<!-- @id ... user-skipped -->`
                        placeholder so subsequent `init` runs don't re-prompt.
            new_model:  bootstrap a PRD/FSD/TDD new-model baseline instead of the
                        legacy global baseline. Idempotent: existing user files
                        are never overwritten.
            project_name: semantic name used for the `[PRD]`/`[FSD]` root chunks.
        """
        if new_model and not check_only:
            return self._run_new_model_bootstrap(project_name)

        skip_set = {s.strip() for s in (skip or []) if s and s.strip()}
        state = self._scan_global_state()

        if check_only:
            return InitResult(status=state["overall"], files=state["files"])

        if state["overall"] == "ready":
            # All present — still refresh wrapper paths so re-running init on
            # an already-ready project is useful (config drift recovery).
            skill_dir, cli_path = self._mark_initialized()
            wrapper_path = self._write_project_wrapper(cli_path)
            return InitResult(
                status="ready",
                files=state["files"],
                skill_dir=skill_dir,
                cli_path=cli_path,
                wrapper_path=self._rel(wrapper_path) if wrapper_path else "",
            )

        if state["overall"] == "fresh":
            return self._run_full_bootstrap()

        # incomplete
        return self._run_incremental(state["files"], skip_set)

    # ──────────────────────────────────────────────────
    # bootstrap modes
    # ──────────────────────────────────────────────────

    def _run_full_bootstrap(self) -> InitResult:
        """Original full bootstrap — extracted from the legacy `run()` body."""
        created: list[str] = []
        global_dir = self.root / "docs" / "global"
        global_dir.mkdir(parents=True, exist_ok=True)

        # 1. Static globals (each its own file + @id chunk).
        for chunk_id, (fname, heading, body) in _STATIC_GLOBALS.items():
            path = global_dir / f"{fname}.md"
            content = f"<!-- @id:{chunk_id} -->\n## {heading}\n\n{body}\n"
            atomic_write_text(path, content)
            created.append(self._rel(path))

        # 2. Dynamic global skeletons (empty bodies; filled by version confirm).
        for ftype, heading in _DYNAMIC_GLOBALS.items():
            path = global_dir / f"{ftype}.md"
            chunk_id = f"global-{ftype}"
            content = (
                f"<!-- @id:{chunk_id} -->\n## {heading}\n\n"
                f"<!-- 动态 global：内容由 version confirm 从 impl @extract 提取，请勿手工编辑。 -->\n"
            )
            atomic_write_text(path, content)
            created.append(self._rel(path))

        # 3. README placeholders for prd/ and impl/ (NOT indexed — no @id).
        for sub in ("prd", "impl"):
            d = self.root / "docs" / sub
            d.mkdir(parents=True, exist_ok=True)
            readme = d / "README.md"
            if not readme.exists():
                atomic_write_text(
                    readme,
                    f"# {sub.upper()} baseline\n\n"
                    f"由各版本 `version confirm` 合入。init 仅建占位说明。\n",
                )
                created.append(self._rel(readme))

        # 4. Rebuild baseline index + baseline specgraph (global chunks get category).
        baseline, _links = self.indexes.rebuild_baseline()
        from .specgraph import sync_specgraph

        graph = sync_specgraph(self.root)

        # 5. Mark initialized in config.yaml (best-effort, append flag).
        skill_dir, cli_path = self._mark_initialized()

        # 6. Generate project-local thin wrapper.
        wrapper_path = self._write_project_wrapper(cli_path)
        if wrapper_path and self._rel(wrapper_path) not in created:
            created.append(self._rel(wrapper_path))

        return InitResult(
            created_files=created,
            chunks=len(baseline.chunks),
            specs=len(graph.specs),
            skill_dir=skill_dir,
            cli_path=cli_path,
            wrapper_path=self._rel(wrapper_path) if wrapper_path else "",
            status="fresh",
            files={n: "present" for n in GLOBAL_FILES},
        )

    def _validate_project_name(self, name: str) -> None:
        """Reject names that can't form a valid new-model root chunk id.

        ``[PRD]-{name}`` must land inside NEW_MODEL_CHUNK_ID (``[a-z0-9_]``
        segments joined by ``-``). This is the R3-01 fix (uppercase/space/CJK
        names silently yielded a chunkless "success") and simultaneously the
        R3-03 fix (``/`` and ``..`` can't appear, so no path traversal).
        """
        if not re.fullmatch(r"[a-z0-9_]+(?:-[a-z0-9_]+)*", name or ""):
            raise InitManagerError(
                f"invalid --name {name!r}: only lowercase letters, digits, '_' "
                "and '-' separators are allowed (must form a valid chunk id)",
                code="INVALID_PROJECT_NAME",
            )

    def _run_new_model_bootstrap(self, project_name: str) -> InitResult:
        """Bootstrap a PRD/FSD/TDD new-model baseline under ``docs/``.

        Creates ``docs/prd``, ``docs/fsd``, ``docs/tdd`` with one ``[PRD]`` root
        document and one ``[FSD]`` root document, wired by a ``derives`` edge
        (carried as an ``@ref`` in the PRD root so ``sync_specgraph`` materializes
        it). Idempotent: existing files are left untouched.
        """
        self._validate_project_name(project_name)
        created: list[str] = []
        docs = self.root / "docs"
        prd_id = f"[PRD]-{project_name}"
        fsd_id = f"[FSD]-{project_name}"

        # 1. PRD root — relation-free body (v2.31: docs carry no relations; the
        #    PRD→FSD derives edge is built directly in specgraph in step 4).
        prd_path = docs / "prd" / f"{prd_id}.md"
        if not prd_path.exists():
            prd_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                prd_path,
                f"<!-- @id:{prd_id} -->\n"
                f"## {project_name} PRD\n\n"
                f"<!-- @summary: {project_name} 根 PRD：描述需求意图（why/what），derives 根 FSD。 -->\n\n"
                "### 概述\n\n<!-- 项目需求概述，init 后由 ait prdv2 增量补充。 -->\n",
            )
            created.append(self._rel(prd_path))

        # 2. Root FSD.
        fsd_path = docs / "fsd" / f"{fsd_id}.md"
        if not fsd_path.exists():
            fsd_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                fsd_path,
                f"<!-- @id:{fsd_id} -->\n"
                f"## {project_name} FSD\n\n"
                f"<!-- @summary: {project_name} 根 FSD：功能分解与交互契约入口。 -->\n\n"
                "### 功能范围\n\n<!-- 根 FSD 功能总览，init 后由 ait fsd 递归分解。 -->\n",
            )
            created.append(self._rel(fsd_path))

        # 3. TDD placeholder dir (TDD docs are derived from leaf FSDs later).
        tdd_dir = docs / "tdd"
        tdd_dir.mkdir(parents=True, exist_ok=True)
        tdd_readme = tdd_dir / "README.md"
        if not tdd_readme.exists():
            atomic_write_text(
                tdd_readme,
                "# TDD baseline\n\n"
                "TDD 文档由叶子 FSD 派生，每个 TDD 唯一映射一个 target_file。\n",
            )
            created.append(self._rel(tdd_readme))

        # 4. Rebuild baseline index + specgraph, then build the PRD→FSD
        #    derives edge as an explicit specgraph edge (v2.31: no @ref in
        #    doc body). source="new-model-cli" so _preserve_explicit_edges keeps
        #    it across every reindex, exactly like fsd decompose edges.
        baseline, _links = self.indexes.rebuild_baseline()
        from .specgraph import load_specgraph, specgraph_path, sync_specgraph

        sync_specgraph(self.root)
        base = load_specgraph(self.root, "baseline")
        uri_by_chunk = {spec.chunk_id: uri for uri, spec in base.specs.items()}
        prd_uri = uri_by_chunk.get(prd_id)
        fsd_uri = uri_by_chunk.get(fsd_id)
        if prd_uri and fsd_uri:
            base.add_edge(prd_uri, fsd_uri, "derives", metadata={"source": "new-model-cli"})
            base.save(specgraph_path(self.root, "baseline"))
        graph = base

        skill_dir, cli_path = self._mark_initialized()
        wrapper_path = self._write_project_wrapper(cli_path)
        if wrapper_path and self._rel(wrapper_path) not in created:
            created.append(self._rel(wrapper_path))

        # v2.28 defensive close (R3-01): the roots must actually be in baseline.
        # Guards against a silent chunks==0 "success" if the ids ever fail to
        # parse (the very failure mode an unvalidated name produced).
        baseline_ids = {c.id for c in baseline.chunks}
        missing = [cid for cid in (prd_id, fsd_id) if cid not in baseline_ids]
        if missing:
            raise InitManagerError(
                f"new-model bootstrap produced no root chunks for {missing}; "
                "baseline was not materialized",
                code="BOOTSTRAP_FAILED",
            )

        return InitResult(
            created_files=created,
            chunks=len(baseline.chunks),
            specs=len(graph.specs),
            skill_dir=skill_dir,
            cli_path=cli_path,
            wrapper_path=self._rel(wrapper_path) if wrapper_path else "",
            status="fresh",
        )

    def _run_incremental(
        self, files_state: dict[str, str], skip_set: set[str]
    ) -> InitResult:
        """Fill only missing/skeleton globals; honor user-skip placeholders."""
        created: list[str] = []
        skipped: list[str] = []
        global_dir = self.root / "docs" / "global"
        global_dir.mkdir(parents=True, exist_ok=True)

        # Build name → (chunk_id, heading, body) lookup unifying static + dynamic.
        name_to_meta: dict[str, tuple[str, str, str]] = {}
        for chunk_id, (fname, heading, body) in _STATIC_GLOBALS.items():
            name_to_meta[fname] = (chunk_id, heading, body)
        for ftype, heading in _DYNAMIC_GLOBALS.items():
            chunk_id = f"global-{ftype}"
            name_to_meta[ftype] = (
                chunk_id,
                heading,
                "<!-- 动态 global：内容由 version confirm 从 impl @extract 提取，请勿手工编辑。 -->",
            )

        for name in GLOBAL_FILES:
            if files_state.get(name) == "present":
                continue
            chunk_id, heading, body = name_to_meta[name]
            path = global_dir / f"{name}.md"
            if name in skip_set:
                # User-skip placeholder. Carries @id (so `_classify_global_file`
                # treats it as `present` next run, no re-prompt) plus a marker
                # comment so future readers understand why it's empty.
                content = (
                    f"<!-- @id:{chunk_id} -->\n## {heading}\n\n"
                    f"<!-- ait-init-guide: user-skipped, will not be touched by init -->\n"
                )
                atomic_write_text(path, content)
                skipped.append(self._rel(path))
            else:
                content = f"<!-- @id:{chunk_id} -->\n## {heading}\n\n{body}\n"
                atomic_write_text(path, content)
                created.append(self._rel(path))

        # README placeholders if missing (idempotent).
        for sub in ("prd", "impl"):
            d = self.root / "docs" / sub
            d.mkdir(parents=True, exist_ok=True)
            readme = d / "README.md"
            if not readme.exists():
                atomic_write_text(
                    readme,
                    f"# {sub.upper()} baseline\n\n"
                    f"由各版本 `version confirm` 合入。init 仅建占位说明。\n",
                )
                created.append(self._rel(readme))

        # Refresh indexes + specgraph after writing new globals.
        baseline, _links = self.indexes.rebuild_baseline()
        from .specgraph import sync_specgraph

        graph = sync_specgraph(self.root)

        skill_dir, cli_path = self._mark_initialized()
        wrapper_path = self._write_project_wrapper(cli_path)
        if wrapper_path and self._rel(wrapper_path) not in created:
            created.append(self._rel(wrapper_path))

        # Re-scan to report final per-file status to the caller (sub-skill).
        final_state = self._scan_global_state()
        return InitResult(
            created_files=created,
            chunks=len(baseline.chunks),
            specs=len(graph.specs),
            skill_dir=skill_dir,
            cli_path=cli_path,
            wrapper_path=self._rel(wrapper_path) if wrapper_path else "",
            status="incomplete",
            files=final_state["files"],
            skipped=skipped,
        )

    def refresh_wrapper(self) -> InitResult:
        """Refresh `.meta/config.yaml` skill_dir/cli_path/wrapper_path and
        regenerate `project-docs/.ait/ait-cli*`. Does NOT touch docs/global/*.

        Idempotent. Use after machine change / skill reinstallation.
        """
        skill_dir, cli_path = self._mark_initialized(force_paths=True)
        wrapper_path = self._write_project_wrapper(cli_path)
        return InitResult(
            created_files=[self._rel(wrapper_path)] if wrapper_path else [],
            chunks=0,
            specs=0,
            skill_dir=skill_dir,
            cli_path=cli_path,
            wrapper_path=self._rel(wrapper_path) if wrapper_path else "",
        )

    # ──────────────────────────────────────────────────
    # internals
    # ──────────────────────────────────────────────────

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)).replace("\\", "/")

    def _mark_initialized(self, force_paths: bool = False) -> tuple[str, str]:
        """Write `.meta/config.yaml` with init flag and skill paths.

        Returns `(skill_dir, cli_path)`. New path fields are written
        independently of the `initialized` flag so that running on an already
        initialized project (e.g. via `init --refresh-wrapper`) still updates
        them. Best-effort: never raises.
        """
        import yaml

        # Resolve canonical paths.
        skill_dir = os.environ.get(
            "AIT_SKILL_DIR",
            str(Path.home() / ".claude" / "skills" / "ait"),
        )
        wrapper_basename = "ait.cmd" if os.name == "nt" else "ait"
        cli_path = str(Path(skill_dir) / "bin" / wrapper_basename)
        wrapper_rel = (
            "project-docs/.ait/ait-cli.cmd"
            if os.name == "nt"
            else "project-docs/.ait/ait-cli"
        )

        cfg_path = self.root / ".meta" / "config.yaml"
        try:
            data: dict = {}
            if cfg_path.exists():
                loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded

            # Set the init flag once.
            if data.get("initialized") is not True:
                data["initialized"] = True

            # Path fields: write on first init, or when force_paths=True
            # (refresh-wrapper). Never silently overwrite user customizations
            # otherwise — users may relocate skill_dir manually.
            if force_paths or "skill_dir" not in data:
                data["skill_dir"] = skill_dir
            if force_paths or "cli_path" not in data:
                data["cli_path"] = cli_path
            if force_paths or "wrapper_path" not in data:
                data["wrapper_path"] = wrapper_rel

            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                cfg_path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            )
            # Echo back what we ended up with (may differ from env if user pre-
            # configured the file).
            return (
                str(data.get("skill_dir") or skill_dir),
                str(data.get("cli_path") or cli_path),
            )
        except Exception:
            # config is advisory; never fail init on it.
            return (skill_dir, cli_path)

    def _write_project_wrapper(self, cli_path: str) -> Path | None:
        """Generate `project-docs/.ait/ait-cli` (or `.cmd`) thin wrapper.

        Best-effort; returns the written path or None on failure.
        """
        try:
            ait_dir = self.root / ".ait"
            ait_dir.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                wrapper = ait_dir / "ait-cli.cmd"
                content = (
                    "@echo off\r\n"
                    "rem AIT project-local wrapper -- generated by `ait init`. Do not edit manually.\r\n"
                    f'"{cli_path}" %*\r\n'
                )
                atomic_write_text(wrapper, content)
            else:
                wrapper = ait_dir / "ait-cli"
                content = (
                    "#!/usr/bin/env bash\n"
                    "# AIT project-local wrapper -- generated by `ait init`. Do not edit manually.\n"
                    f'exec "{cli_path}" "$@"\n'
                )
                atomic_write_text(wrapper, content)
                # chmod 0755
                try:
                    mode = wrapper.stat().st_mode
                    wrapper.chmod(
                        mode
                        | stat.S_IXUSR
                        | stat.S_IXGRP
                        | stat.S_IXOTH
                        | stat.S_IRUSR
                        | stat.S_IRGRP
                        | stat.S_IROTH
                    )
                except Exception:
                    pass
            return wrapper
        except Exception:
            return None
