"""Task manager — AI-coding task lifecycle (redesign).

Tasks are the executable unit derived from a locked PRD+impl pair. One PRD chunk
may yield 1..N tasks. A task is a YAML file at
`versions/{version}/tasks/T-{src-chunk}-NN.yaml` consumed by the AI coding step.

Pipeline:
    task create [chunk]   → derive task YAML(s) from specgraph (version dim)
    task execute [id]     → run AI coding; success auto-marks done + code_refs
                            (no separate `task confirm` — execute self-closes)

State machine:  created → executing → done | failed (re-runnable)

Single source of truth = the task YAML `status`; state.md aggregates for display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .chunk_parser import parse_file
from .format_validator import DERIVED_NAME_VIOLATION, validate_task_id
from .index_manager import IndexManager
from .schemas import TaskYaml
from .specgraph import combined_specgraph, make_uri, resolve_chunk_uri
from .version_manager import VersionManager


class TaskManagerError(RuntimeError):
    """Raised on task-domain failures (with a stable error code)."""

    def __init__(self, message: str, code: str = "TASK_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class TaskBuildResult:
    version: str
    source_chunk: str
    task_ids: list[str]
    files: list[str]


# Project-level default global constraint every task should honor.
_DEFAULT_GLOBAL_REFS = ["global-tech-stack"]


def _src_slug(prd_chunk_id: str) -> str:
    """`prd-pet-archive` → `pet-archive` (strip the leading `prd-`)."""
    return prd_chunk_id[4:] if prd_chunk_id.startswith("prd-") else prd_chunk_id


class TaskManager:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()
        self.indexes = IndexManager(self.root)
        self.versions = VersionManager(self.root)

    # ──────────────────────────────────────────────────
    # paths
    # ──────────────────────────────────────────────────

    def tasks_dir(self, version: str) -> Path:
        return self.root / "versions" / version / "tasks"

    def task_path(self, version: str, task_id: str) -> Path:
        return self.tasks_dir(version) / f"{task_id}.yaml"

    # ──────────────────────────────────────────────────
    # load / save
    # ──────────────────────────────────────────────────

    def load_task(self, version: str, task_id: str) -> TaskYaml:
        path = self.task_path(version, task_id)
        if not path.exists():
            raise TaskManagerError(f"task {task_id} not found in {version}", code="NOT_FOUND")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return TaskYaml.model_validate(raw)

    def save_task(self, version: str, task: TaskYaml) -> Path:
        from .io_utils import atomic_write_text

        violations = validate_task_id(task.id)
        if violations:
            raise TaskManagerError(violations[0].message, code=DERIVED_NAME_VIOLATION)
        path = self.task_path(version, task.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = task.model_dump(mode="json", exclude_none=False)
        atomic_write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
        return path

    def list_tasks(self, version: str) -> list[TaskYaml]:
        d = self.tasks_dir(version)
        if not d.exists():
            return []
        out: list[TaskYaml] = []
        for path in sorted(d.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                out.append(TaskYaml.model_validate(raw))
            except Exception:
                continue
        return out

    # ──────────────────────────────────────────────────
    # create — derive tasks from specgraph (version dim)
    # ──────────────────────────────────────────────────

    def create(self, prd_chunk_id: str, *, version: str | None = None) -> TaskBuildResult:
        version = version or self.versions.current()
        if not version:
            raise TaskManagerError("No active version", code="NO_VERSION")

        # Precondition: PRD must be locked/committed before tasks can be split.
        meta = self.versions.load_version_meta(version)
        if not meta.prd_locked:
            raise TaskManagerError(
                f"PRD must be committed/locked before task split in {version}",
                code="PRD_NOT_LOCKED",
            )

        # Resolve PRD chunk + its impl_refs from specgraph (version dimension).
        graph = combined_specgraph(self.root, version)
        impl_refs = graph.implements_of(prd_chunk_id, version)
        if not impl_refs:
            raise TaskManagerError(
                f"no impl chunks implement {prd_chunk_id}; design impl first",
                code="NO_IMPL",
            )

        # global_refs: globals referenced by the impl chunks + project default.
        global_refs = self._collect_global_refs(graph, impl_refs, version)

        # Derive ordered tasks from impl chunks. Heuristic: one task per impl
        # chunk (clean 1:1 unless an impl is large enough to warrant splitting;
        # we keep 1:1 here and let humans split further if needed).
        slug = _src_slug(prd_chunk_id)
        existing = {t.id for t in self.list_tasks(version)}
        task_ids: list[str] = []
        files: list[str] = []
        seq = self._next_seq(version, slug)
        prev_id: str | None = None
        for impl_id in impl_refs:
            task_id = f"T-{slug}-{seq:02d}"
            while task_id in existing:
                seq += 1
                task_id = f"T-{slug}-{seq:02d}"
            task = TaskYaml(
                id=task_id,
                title=f"实现 {impl_id}",
                source_chunk=prd_chunk_id,
                impl_refs=[impl_id],
                global_refs=global_refs,
                depends_on=[prev_id] if prev_id else [],
                order_hint=seq,
                steps=[f"按 {impl_id} 的设计实现对应代码并自检"],
                status="created",
            )
            path = self.save_task(version, task)
            existing.add(task_id)
            task_ids.append(task_id)
            files.append(str(path.relative_to(self.root)).replace("\\", "/"))
            prev_id = task_id
            seq += 1

        self._refresh_state(version)
        return TaskBuildResult(
            version=version, source_chunk=prd_chunk_id, task_ids=task_ids, files=files
        )

    def pending_prd_chunks(self, version: str) -> list[str]:
        """committed PRD chunks in this version that have no task yet."""
        graph = combined_specgraph(self.root, version)
        covered = {t.source_chunk for t in self.list_tasks(version)}
        out: list[str] = []
        idx = self.indexes.load_version_index(version)
        for entry in idx.chunks:
            if not entry.id.startswith("prd-"):
                continue
            if entry.state != "committed":
                continue
            if entry.id in covered:
                continue
            # only those that actually have impl coverage
            if graph.implements_of(entry.id, version):
                out.append(entry.id)
        return out

    # ──────────────────────────────────────────────────
    # execute — run AI coding, self-close on success
    # ──────────────────────────────────────────────────

    def resolve_tasks(self, version: str, task_or_chunk: str | None) -> list[TaskYaml]:
        """Resolve a selector into a concrete ordered task list.

        - None        → all tasks not yet done (created/failed), order_hint asc
        - T-xxx-NN    → that single task
        - prd-chunk   → all tasks whose source_chunk == that chunk
        """
        tasks = self.list_tasks(version)
        if task_or_chunk is None:
            pend = [t for t in tasks if t.status in ("created", "failed")]
            return sorted(pend, key=lambda t: t.order_hint)
        if task_or_chunk.startswith("T-"):
            one = [t for t in tasks if t.id == task_or_chunk]
            if not one:
                raise TaskManagerError(f"task {task_or_chunk} not found", code="NOT_FOUND")
            return one
        # treat as source chunk id
        grp = [t for t in tasks if t.source_chunk == task_or_chunk]
        if not grp:
            raise TaskManagerError(
                f"no tasks for chunk {task_or_chunk}", code="NOT_FOUND"
            )
        return sorted(grp, key=lambda t: t.order_hint)

    def deps_satisfied(self, version: str, task: TaskYaml) -> bool:
        if not task.depends_on:
            return True
        by_id = {t.id: t for t in self.list_tasks(version)}
        for dep in task.depends_on:
            d = by_id.get(dep)
            if d is None or d.status != "done":
                return False
        return True

    def begin_execute(self, version: str, task_id: str) -> TaskYaml:
        """Mark a task executing (after dep check). Returns the task."""
        task = self.load_task(version, task_id)
        if not self.deps_satisfied(version, task):
            raise TaskManagerError(
                f"task {task_id} has unsatisfied dependencies: {task.depends_on}",
                code="BLOCKED",
            )
        task.status = "executing"
        self.save_task(version, task)
        self._refresh_state(version)
        return task

    def complete(
        self, version: str, task_id: str, *, commit: str | None = None,
        paths: list[str] | None = None,
    ) -> TaskYaml:
        """Mark a task done and bind code refs. Called after AI coding succeeds."""
        from .schemas import CodeRef

        task = self.load_task(version, task_id)
        task.status = "done"
        task.code_refs = [
            CodeRef(commit=commit, paths=paths or [], bound_at=datetime.now(timezone.utc))
        ]
        self.save_task(version, task)
        self._refresh_state(version)
        return task

    def fail(self, version: str, task_id: str) -> TaskYaml:
        task = self.load_task(version, task_id)
        task.status = "failed"
        self.save_task(version, task)
        self._refresh_state(version)
        return task

    def assemble_context(self, version: str, task: TaskYaml) -> dict:
        """Gather the minimal context bundle for AI coding (token-focused).

        Only the task's impl_refs ∪ global_refs are loaded — never the whole
        project tree. Returns chunk_id → markdown content.
        """
        slices: dict[str, str] = {}
        for chunk_id in [*task.impl_refs, *task.global_refs]:
            content = self._locate_chunk_content(version, chunk_id)
            if content:
                slices[chunk_id] = content
        return {
            "task": task.model_dump(mode="json"),
            "context": slices,
        }

    # ──────────────────────────────────────────────────
    # internals
    # ──────────────────────────────────────────────────

    def _next_seq(self, version: str, slug: str) -> int:
        prefix = f"T-{slug}-"
        nums = [
            int(t.id[len(prefix):])
            for t in self.list_tasks(version)
            if t.id.startswith(prefix) and t.id[len(prefix):].isdigit()
        ]
        return (max(nums) + 1) if nums else 1

    def _collect_global_refs(self, graph, impl_refs: list[str], version: str) -> list[str]:
        refs: list[str] = []
        for impl_id in impl_refs:
            uri = resolve_chunk_uri(self.root, impl_id, version, graph=graph)
            for edge in graph.query(uri, direction="out"):
                dst_chunk = edge.dst.split(":")[-1]
                if dst_chunk.startswith("global-") and dst_chunk not in refs:
                    refs.append(dst_chunk)
        for g in _DEFAULT_GLOBAL_REFS:
            if g not in refs:
                refs.append(g)
        return refs

    def _locate_chunk_content(self, version: str, chunk_id: str) -> str | None:
        """Find a chunk's markdown in the version workspace, then baseline."""
        # version workspace first
        version_dir = self.versions_dir(version)
        for base in (version_dir, self.root / "docs"):
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.md")):
                pf = parse_file(path, base)
                for chunk in pf.chunks:
                    if chunk.id == chunk_id:
                        return chunk.content
        return None

    def versions_dir(self, version: str) -> Path:
        return self.root / "versions" / version

    def _refresh_state(self, version: str) -> None:
        try:
            from .state import save_state

            save_state(self.root, version)
        except Exception:
            pass
