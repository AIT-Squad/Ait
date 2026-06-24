"""AIT CLI — `ait prd ...`, `ait impl ...`, `ait version ...`.

All commands emit a single JSON object per ait-system.md§prd-ait-cmd-output:

    Success: {"ok": true, "data": {...}}
    Failure: {"ok": false, "error": "...", "code": "..."}

This contract makes AI IDE integration straightforward — every Skill wrapper just
captures stdout and re-emits to the model.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import click

from . import __version__
from .context_assembler import ContextAssembler
from .deps import query_deps
from .format_validator import (
    fix_prd_text,
    is_version_scope,
    scan_impl_text,
    scan_prd_text,
    violations_to_details,
)
from .impact import analyze_impact
from .impl_manager import ImplManager
from .index_manager import IndexManager, IndexSchemaViolation
from .init_manager import InitManager, InitManagerError
from .new_model_validator import validate_prd_fsd_tdd_graph
from .new_model_validator import validate_target_file_uniqueness
from .new_model_validator import violations_to_details as new_model_violations_to_details
from .new_model_manager import NewModelManager
from .prd_manager import PrdManager
from .search import search_chunks
from .root import RootResolutionError, resolve_project_root
from .specgraph import add_edge as add_specgraph_edge
from .specgraph import combined_specgraph, load_specgraph, resolve_chunk_uri, sync_specgraph
from .state import render_state, save_state
from .task_manager import TaskManager, TaskManagerError
from .validator import ValidationError
from .version_manager import VersionManager, VersionManagerError

# Force UTF-8 stdout on Windows consoles so Chinese chars survive.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(by_alias=True))
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe({f: getattr(value, f) for f in value.__dataclass_fields__})
    return value


def ok(data) -> None:
    click.echo(json.dumps({"ok": True, "data": _json_safe(data)}, ensure_ascii=False))


def fail(message: str, code: str = "ERROR", exit_code: int = 1, details: dict | None = None) -> None:
    payload = {"ok": False, "error": message, "code": code}
    if details:
        payload["details"] = _json_safe(details)
    click.echo(json.dumps(payload, ensure_ascii=False))
    sys.exit(exit_code)


def _read_content(content_file: Path | None, content: str | None) -> str:
    if content is None and content_file is None:
        fail("Provide --content or --content-file", code="ARG_MISSING")
    if content is not None:
        return content
    assert content_file is not None
    if str(content_file) == "-":
        return sys.stdin.read()
    return content_file.read_text(encoding="utf-8")


def _scoped_filename(value: str | None, *, scope: str, option: str) -> str | None:
    if value is None:
        return None
    name = value.strip()
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or ":" in name
        or name.lower().endswith(".md")
    ):
        fail(
            f"{option} only accepts a file name without path or .md suffix",
            code="INVALID_FILE_NAME",
        )
    return f"{scope}/{name}"


def _root(ctx: click.Context) -> Path:
    return ctx.obj["root"]


@click.group(help="AIT — AI-assisted document versioning.")
@click.version_option(__version__, prog_name="ait")
@click.pass_context
def main(ctx: click.Context) -> None:
    ctx.ensure_object(dict)
    try:
        resolved = resolve_project_root()
    except RootResolutionError as exc:
        fail(str(exc), code=exc.code)
    ctx.obj["root"] = resolved.root
    _emit_wrapper_hints(resolved.root)


def _emit_wrapper_hints(root: Path) -> None:
    """Emit advisory tips on stderr when local wrapper is missing or skill_dir
    drifted. Never touches stdout (JSON contract) and never raises.
    """
    try:
        wrapper = root / ".ait" / ("ait-cli.cmd" if sys.platform == "win32" else "ait-cli")
        cfg_path = root / ".meta" / "config.yaml"
        env_skill_dir = os.environ.get("AIT_SKILL_DIR")
        cfg_skill_dir = None
        if cfg_path.exists():
            try:
                import yaml as _yaml

                loaded = _yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg_skill_dir = loaded.get("skill_dir")
            except Exception:
                cfg_skill_dir = None
        if not wrapper.exists() and env_skill_dir:
            click.echo(
                f"tip: project-local wrapper missing; run `{env_skill_dir}/bin/ait init --refresh-wrapper` to generate it",
                err=True,
            )
        if env_skill_dir and cfg_skill_dir and env_skill_dir != cfg_skill_dir:
            click.echo(
                "tip: skill_dir mismatch detected between AIT_SKILL_DIR and .meta/config.yaml; run `init --refresh-wrapper` to reconcile",
                err=True,
            )
        # v1.5: detect legacy `.meta/tasks/` path. Task YAML now lives in
        # `versions/<v>/tasks/`; warn (don't auto-migrate, don't auto-delete).
        # `root` points at `<cwd>/project-docs/`, so legacy lives directly under it.
        legacy = root / ".meta" / "tasks"
        if legacy.exists() and any(legacy.rglob("*.yaml")):
            try:
                rel = legacy.relative_to(root.parent)
            except ValueError:
                rel = legacy
            click.echo(
                f"⚠️  legacy task path detected: {rel} — task YAML 已迁至 "
                f"versions/<v>/tasks/，请手动删除旧目录",
                err=True,
            )
    except Exception:
        # Hints are advisory; never break the CLI.
        pass


# ═══════════════════════════════════════════════════════════
# /ait:init  (redesign — bootstrap the global baseline)
# ═══════════════════════════════════════════════════════════


@main.command("init")
@click.option(
    "--refresh-wrapper",
    is_flag=True,
    default=False,
    help="仅刷新 .meta/config.yaml 的 skill_dir/cli_path/wrapper_path 与 project-docs/.ait/ait-cli*；不动 docs/global/*。",
)
@click.option(
    "--check",
    "check_only",
    is_flag=True,
    default=False,
    help="仅诊断当前 docs/global 状态（fresh/incomplete/ready），不写文件。",
)
@click.option(
    "--skip",
    "skip_csv",
    type=str,
    default="",
    help="逗号分隔的 global 文件名列表（不含 .md），这些项写入 user-skipped 占位符。",
)
@click.option(
    "--new-model",
    "new_model",
    is_flag=True,
    default=False,
    help="引导新模型 PRD/FSD/TDD 基线（docs/prd,fsd,tdd + 根 chunk + decomposes 边），不影响旧 init。",
)
@click.option(
    "--name",
    "project_name",
    type=str,
    default="project",
    help="新模型基线的语义名（用于 [PRD]/[FSD] 根 chunk）。仅配合 --new-model。",
)
@click.pass_context
def init_cmd(ctx, refresh_wrapper: bool, check_only: bool, skip_csv: str, new_model: bool, project_name: str) -> None:
    """Bootstrap the global baseline (global PRD/impl overview + global skeletons).

    v1.5: incremental-aware. ``init`` always inspects ``docs/global/*`` first:

    \b
    - fresh      → no project-docs/docs-global yet → full bootstrap.
    - incomplete → some files missing/skeleton → fill only missing
                   (use ``--skip name1,name2`` to mark items the user declines;
                    those get a ``user-skipped`` placeholder so re-running won't
                    re-prompt).
    - ready      → all 5 globals present → no docs writes; wrapper still refreshed.

    Flags:
      --check            : diagnose only, no writes.
      --refresh-wrapper  : regenerate the project-local wrapper / config paths.
      --skip <names>     : honor user-declined items in incremental mode.

    ``--check`` takes precedence over ``--refresh-wrapper`` when both are set.
    """
    mgr = InitManager(_root(ctx))
    skip_list = [s.strip() for s in skip_csv.split(",") if s.strip()]
    try:
        if check_only:
            result = mgr.run(check_only=True)
            ok(
                {
                    "status": result.status,
                    "files": result.files,
                }
            )
            return
        if refresh_wrapper:
            result = mgr.refresh_wrapper()
            ok(
                {
                    "refreshed": True,
                    "skill_dir": result.skill_dir,
                    "cli_path": result.cli_path,
                    "wrapper": result.wrapper_path,
                }
            )
            return
        result = mgr.run(skip=skip_list, new_model=new_model, project_name=project_name)
        ok(
            {
                "created_files": result.created_files,
                "chunks": result.chunks,
                "specs": result.specs,
                "skill_dir": result.skill_dir,
                "cli_path": result.cli_path,
                "wrapper": result.wrapper_path,
                "status": result.status,
                "files": result.files,
                "skipped": result.skipped,
            }
        )
    except InitManagerError as exc:
        fail(str(exc), code=exc.code)


# ═══════════════════════════════════════════════════════════
# /ait:prd ...
# ═══════════════════════════════════════════════════════════


@main.group("prd")
def prd_group() -> None:
    """PRD-domain commands."""


@prd_group.command("create")
@click.argument("title")
@click.option("--author", default="system")
@click.option("--version", "version", default=None, help="Target version (auto if absent)")
@click.pass_context
def prd_create(ctx, title: str, author: str, version: str | None) -> None:
    mgr = PrdManager(_root(ctx))
    try:
        result = mgr.create(title, author=author, version=version)
        ok({"req_id": result.req_id, "version": result.version, "title": title})
    except (ValidationError, VersionManagerError) as exc:
        fail(str(exc), code=getattr(exc, "code", "ERROR"))


@prd_group.command("save-draft")
@click.argument("req_id")
@click.option(
    "--content-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File containing the PRD markdown draft (use - for stdin).",
)
@click.option("--content", default=None, help="Inline PRD markdown content")
@click.pass_context
def prd_save_draft(ctx, req_id: str, content_file: Path | None, content: str | None) -> None:
    if content is None and content_file is None:
        fail("Provide --content or --content-file", code="ARG_MISSING")
    if content is None:
        if str(content_file) == "-":
            content = sys.stdin.read()
        else:
            content = content_file.read_text(encoding="utf-8")
    mgr = PrdManager(_root(ctx))
    try:
        req = mgr.save_draft(req_id, content)
        ok(
            {
                "req_id": req.id,
                "status": req.status,
                "chunk_count": len(req.prd_chunks),
                "chunk_ids": [c.id for c in req.prd_chunks],
            }
        )
    except (FileNotFoundError, ValidationError) as exc:
        fail(str(exc), code="DRAFT_FAILED")


@prd_group.command("resolve-candidates")
@click.option(
    "--from-file",
    "from_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="YAML file containing PRD add/modify candidate decisions.",
)
@click.pass_context
def prd_resolve_candidates(ctx, from_file: Path) -> None:
    """Persist skill-produced PRD candidate decisions into the active version workspace."""
    mgr = PrdManager(_root(ctx))
    try:
        ok(mgr.resolve_candidates(from_file))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "CANDIDATES_INVALID")


@prd_group.command("confirm")
@click.argument("req_id")
@click.option("--file", "prd_file", default=None, help="PRD file name under prd/ (no path, no .md)")
@click.pass_context
def prd_confirm(ctx, req_id: str, prd_file: str | None) -> None:
    """Materialize the prd_draft into the version workspace."""
    mgr = PrdManager(_root(ctx))
    try:
        result = mgr.write_to_version(
            req_id,
            prd_file=_scoped_filename(prd_file, scope="prd", option="--file"),
        )
        ok(
            {
                "req_id": req_id,
                "version": result.version,
                "file": result.file,
                "chunk_ids": result.chunk_ids,
            }
        )
    except (FileNotFoundError, ValidationError) as exc:
        fail(str(exc), code="CONFIRM_FAILED")

@prd_group.command("show")
@click.argument("prd_file")
@click.argument("chunk_id", required=False)
@click.pass_context
def prd_show(ctx, prd_file: str, chunk_id: str | None) -> None:
    mgr = PrdManager(_root(ctx))
    try:
        ok(mgr.show(prd_file, chunk_id=chunk_id))
    except FileNotFoundError as exc:
        fail(str(exc), code="NOT_FOUND")


@prd_group.command("commit")
@click.argument("prd_file")
@click.option("-m", "--message", required=True)
@click.option("--req-id", default=None)
@click.pass_context
def prd_commit(ctx, prd_file: str, message: str, req_id: str | None) -> None:
    mgr = PrdManager(_root(ctx))
    try:
        ok(mgr.commit(prd_file, message, req_id=req_id))
    except ValidationError as exc:
        fail(
            str(exc),
            code=exc.issues[0].code if exc.issues else "COMMIT_FAILED",
            details=exc.details,
        )


# ═══════════════════════════════════════════════════════════
# /ait:impl ...
# ═══════════════════════════════════════════════════════════


@main.group("impl")
def impl_group() -> None:
    """Impl-domain commands."""


@impl_group.command("create")
@click.argument("prd_chunk_id")
@click.option(
    "--content-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File containing the impl markdown (use - for stdin).",
)
@click.option("--content", default=None, help="Inline impl markdown content.")
@click.option("--impl-file", default=None, help="Impl file name under impl/ (no path, no .md).")
@click.option("--req-id", default=None)
@click.option("--prd-file", default=None, help="PRD file name under prd/ (no path, no .md).")
@click.option(
    "--action",
    type=click.Choice(["add", "modify"]),
    default="add",
    show_default=True,
    help="Version index action for created impl chunk(s).",
)
@click.option("--overrides", default=None, help="Baseline impl chunk id when --action modify.")
@click.pass_context
def impl_create(
    ctx,
    prd_chunk_id: str,
    content_file: Path | None,
    content: str | None,
    impl_file: str | None,
    req_id: str | None,
    prd_file: str | None,
    action: str,
    overrides: str | None,
) -> None:
    if content is None and content_file is None:
        fail("Provide --content or --content-file", code="ARG_MISSING")
    if content is None:
        if str(content_file) == "-":
            content = sys.stdin.read()
        else:
            content = content_file.read_text(encoding="utf-8")
    mgr = ImplManager(_root(ctx))
    try:
        result = mgr.create(
            prd_chunk_id,
            content,
            impl_file=_scoped_filename(impl_file, scope="impl", option="--impl-file"),
            req_id=req_id,
            prd_file=_scoped_filename(prd_file, scope="prd", option="--prd-file"),
            action=action,  # type: ignore[arg-type]
            overrides=overrides,
        )
        ok(
            {
                "version": result.version,
                "file": result.file,
                "chunk_ids": result.chunk_ids,
            }
        )
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "IMPL_CREATE_FAILED")

@impl_group.command("show")
@click.argument("impl_chunk_id")
@click.pass_context
def impl_show(ctx, impl_chunk_id: str) -> None:
    mgr = ImplManager(_root(ctx))
    try:
        ok(mgr.show(impl_chunk_id))
    except FileNotFoundError as exc:
        fail(str(exc), code="NOT_FOUND")

@impl_group.command("commit")
@click.argument("impl_chunk_id")
@click.option("-m", "--message", required=True)
@click.option("--req-id", default=None)
@click.pass_context
def impl_commit(ctx, impl_chunk_id: str, message: str, req_id: str | None) -> None:
    mgr = ImplManager(_root(ctx))
    try:
        ok(mgr.commit(impl_chunk_id, message, req_id=req_id))
    except ValidationError as exc:
        fail(
            str(exc),
            code=exc.issues[0].code if exc.issues else "IMPL_COMMIT_FAILED",
            details=exc.details,
        )


@impl_group.command("inherit")
@click.argument("prd_chunk_id")
@click.pass_context
def impl_inherit(ctx, prd_chunk_id: str) -> None:
    """Copy baseline impl chunks for a PRD into the active version workspace."""
    mgr = ImplManager(_root(ctx))
    try:
        ok(mgr.inherit(prd_chunk_id))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "IMPL_INHERIT_FAILED")


@impl_group.command("lock")
@click.option(
    "--version",
    "version_name",
    default=None,
    help="Version to lock; defaults to the current (non-merged) version.",
)
@click.pass_context
def impl_lock(ctx, version_name: str | None) -> None:
    """Lock impl for the version, advancing phase to ``impl_locked``.

    Symmetric to PRD: ``prd commit`` auto-locks because PRD is committed
    file-at-a-time, while impl is committed chunk-by-chunk so locking is an
    explicit follow-up step (run after all impl chunks are committed).
    """
    mgr = ImplManager(_root(ctx))
    try:
        ok(mgr.lock(version=version_name))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "IMPL_LOCK_FAILED")


# ═══════════════════════════════════════════════════════════
# /ait:version ...
# ═══════════════════════════════════════════════════════════


@main.group("version")
def version_group() -> None:
    """Version-domain commands."""


@version_group.command("status")
@click.argument("version_name")
@click.pass_context
def version_status(ctx, version_name: str) -> None:
    mgr = VersionManager(_root(ctx))
    ok(mgr.status(version_name))


@version_group.command("merge")
@click.argument("version_name")
@click.option(
    "--conflict-policy",
    type=click.Choice(["abort", "use-version", "use-baseline"]),
    default="abort",
)
@click.pass_context
def version_merge(ctx, version_name: str, conflict_policy: str) -> None:
    mgr = VersionManager(_root(ctx))
    try:
        result = mgr.merge(version_name, conflict_policy=conflict_policy)
        ok(result)
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "MERGE_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code="MERGE_FAILED")


@version_group.command("confirm")
@click.argument("version_name")
@click.option("--allow-dirty-git", is_flag=True, help="Skip the git-clean precheck.")
@click.pass_context
def version_confirm(ctx, version_name: str, allow_dirty_git: bool) -> None:
    """Atomic version confirm: precheck (all tasks done + git clean) → merge to
    baseline → extract dynamic global from impl @extract → promote specgraph →
    git commit (message = version title). Rolls back docs/ if anything fails.
    """
    mgr = VersionManager(_root(ctx))
    try:
        result = mgr.confirm(version_name, allow_dirty_git=allow_dirty_git)
        ok(result)
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "CONFIRM_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "CONFIRM_FAILED"))


@version_group.command("reset")
@click.argument("version_name")
@click.option("--confirm", is_flag=True, help="Confirm the irreversible reset.")
@click.pass_context
def version_reset(ctx, version_name: str, confirm: bool) -> None:
    """Wipe a version workspace and return to a blank state (atomic-version escape hatch)."""
    mgr = VersionManager(_root(ctx))
    try:
        result = mgr.reset(version_name, confirmed=confirm)
        if not result.get("ok", True):
            fail(result["warning"], code=result["code"])
            return
        ok(result)
    except VersionManagerError as exc:
        fail(str(exc), code="RESET_FAILED")


# ═══════════════════════════════════════════════════════════
# /ait:task ...  (redesign — AI coding task lifecycle)
# ═══════════════════════════════════════════════════════════


@main.group("task")
def task_group() -> None:
    """Task-domain commands (AI coding units derived from PRD+impl)."""


@task_group.command("create")
@click.argument("chunk_id", required=False)
@click.pass_context
def task_create(ctx, chunk_id: str | None) -> None:
    """Derive task YAML(s) from a committed PRD chunk's impl coverage.

    No chunk_id → list PRD chunks still pending task split (interactive driver).
    """
    mgr = TaskManager(_root(ctx))
    try:
        version = mgr.versions.current()
        if not version:
            fail("No active version", code="NO_VERSION")
            return
        if chunk_id is None:
            pending = mgr.pending_prd_chunks(version)
            ok({"version": version, "pending_chunks": pending, "interactive": True})
            return
        result = mgr.create(chunk_id, version=version)
        ok(
            {
                "version": result.version,
                "source_chunk": result.source_chunk,
                "task_ids": result.task_ids,
                "files": result.files,
            }
        )
    except TaskManagerError as exc:
        fail(str(exc), code=exc.code)


@task_group.command("list")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def task_list(ctx, version_opt: str | None) -> None:
    mgr = TaskManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
        return
    tasks = mgr.list_tasks(version)
    ok(
        {
            "version": version,
            "tasks": [
                {
                    "id": t.id,
                    "status": t.status,
                    "source_chunk": t.source_chunk,
                    "impl_refs": t.impl_refs,
                    "depends_on": t.depends_on,
                    "order_hint": t.order_hint,
                }
                for t in sorted(tasks, key=lambda x: x.order_hint)
            ],
        }
    )


@task_group.command("show")
@click.argument("task_id")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def task_show(ctx, task_id: str, version_opt: str | None) -> None:
    mgr = TaskManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
        return
    try:
        task = mgr.load_task(version, task_id)
        ok(_json_safe(task))
    except TaskManagerError as exc:
        fail(str(exc), code=exc.code)


@task_group.command("execute")
@click.argument("task_or_chunk", required=False)
@click.option("--version", "version_opt", default=None)
@click.pass_context
def task_execute(ctx, task_or_chunk: str | None, version_opt: str | None) -> None:
    """Prepare task(s) for AI coding: mark executing + emit the focused context bundle.

    This command does NOT itself write code — it hands the Skill layer a
    minimal, token-focused context (impl_refs ∪ global_refs only) plus the
    task steps. The Skill drives the AI, then calls `task complete`/`task fail`
    to self-close. No separate `task confirm`.

    No selector → all pending (created/failed) tasks, dependency-ordered.
    """
    mgr = TaskManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
        return
    try:
        tasks = mgr.resolve_tasks(version, task_or_chunk)
        prepared = []
        skipped = []
        for t in tasks:
            if t.status == "done":
                skipped.append({"id": t.id, "reason": "already done"})
                continue
            if not mgr.deps_satisfied(version, t):
                skipped.append({"id": t.id, "reason": f"blocked by {t.depends_on}"})
                continue
            mgr.begin_execute(version, t.id)
            prepared.append(mgr.assemble_context(version, t))
        ok(
            {
                "version": version,
                "prepared": prepared,
                "skipped": skipped,
                "note": "Skill drives AI coding over each prepared task, then calls"
                " `ait task complete <id>` / `ait task fail <id>`.",
            }
        )
    except TaskManagerError as exc:
        fail(str(exc), code=exc.code)


@task_group.command("complete")
@click.argument("task_id")
@click.option("--commit", default=None, help="git commit hash to bind.")
@click.option("--path", "paths", multiple=True, help="code file path(s) to bind.")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def task_complete(ctx, task_id: str, commit: str | None, paths: tuple, version_opt: str | None) -> None:
    """Mark a task done and bind its code refs (execute's self-close step)."""
    mgr = TaskManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
        return
    try:
        task = mgr.complete(version, task_id, commit=commit, paths=list(paths))
        ok(_json_safe(task))
    except TaskManagerError as exc:
        fail(str(exc), code=exc.code)


@task_group.command("fail")
@click.argument("task_id")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def task_fail(ctx, task_id: str, version_opt: str | None) -> None:
    mgr = TaskManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
        return
    try:
        task = mgr.fail(version, task_id)
        ok(_json_safe(task))
    except TaskManagerError as exc:
        fail(str(exc), code=exc.code)


# ═══════════════════════════════════════════════════════════
# /ait:context ... (AI plumbing — not in the user-facing 7 but useful for Skills)
# ═══════════════════════════════════════════════════════════


@main.group("fsd")
def fsd_group() -> None:
    """Manage new-model FSD documents."""


@fsd_group.command("create")
@click.argument("root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.option("--file", "file_opt", default=None, help="FSD file under fsd/ or explicit index path, no .md.")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--content", default=None)
@click.option("--action", type=click.Choice(["add", "modify"]), default="add")
@click.option("--overrides", default=None)
@click.pass_context
def fsd_create(
    ctx,
    root_chunk_id: str,
    version_opt: str | None,
    file_opt: str | None,
    content_file: Path | None,
    content: str | None,
    action: str,
    overrides: str | None,
) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        result = mgr.create_fsd(
            version,
            root_chunk_id,
            _read_content(content_file, content),
            file=file_opt,
            action=action,
            overrides=overrides,
        )
        ok(_json_safe(result))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)


@fsd_group.command("link")
@click.argument("src_chunk_id")
@click.argument("dst_chunk_id")
@click.option("--rel", type=click.Choice(["decomposes", "details", "depends_on"]), required=True)
@click.option("--version", "version_opt", default=None)
@click.pass_context
def fsd_link(ctx, src_chunk_id: str, dst_chunk_id: str, rel: str, version_opt: str | None) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(_json_safe(mgr.add_edge(version, src_chunk_id, dst_chunk_id, rel)))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)


@main.group("tdd")
def tdd_group() -> None:
    """Manage new-model TDD documents."""


@tdd_group.command("create")
@click.argument("root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.option("--file", "file_opt", default=None, help="TDD file under tdd/ or explicit index path, no .md.")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--content", default=None)
@click.option("--action", type=click.Choice(["add", "modify"]), default="add")
@click.option("--overrides", default=None)
@click.pass_context
def tdd_create(
    ctx,
    root_chunk_id: str,
    version_opt: str | None,
    file_opt: str | None,
    content_file: Path | None,
    content: str | None,
    action: str,
    overrides: str | None,
) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        result = mgr.create_tdd(
            version,
            root_chunk_id,
            _read_content(content_file, content),
            file=file_opt,
            action=action,
            overrides=overrides,
        )
        ok(_json_safe(result))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)


@main.group("codegen")
def codegen_group() -> None:
    """Prepare new-model TDD code generation context."""


@codegen_group.command("prepare")
@click.argument("tdd_root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def codegen_prepare(ctx, tdd_root_chunk_id: str, version_opt: str | None) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(_json_safe(mgr.prepare_codegen(version, tdd_root_chunk_id)))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)


@main.group("prdv2")
def prdv2_group() -> None:
    """Manage new-model PRD documents (parallel to legacy `prd`)."""


@prdv2_group.command("create")
@click.argument("root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.option("--file", "file_opt", default=None, help="PRD file under prd/ or explicit index path, no .md.")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--content", default=None)
@click.option("--action", type=click.Choice(["add", "modify"]), default="add")
@click.option("--overrides", default=None)
@click.pass_context
def prdv2_create(
    ctx,
    root_chunk_id: str,
    version_opt: str | None,
    file_opt: str | None,
    content_file: Path | None,
    content: str | None,
    action: str,
    overrides: str | None,
) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        result = mgr.create_prd(
            version,
            root_chunk_id,
            _read_content(content_file, content),
            file=file_opt,
            action=action,
            overrides=overrides,
        )
        ok(_json_safe(result))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)


@prdv2_group.command("link")
@click.argument("src_chunk_id")
@click.argument("dst_chunk_id")
@click.option("--rel", type=click.Choice(["decomposes", "details", "depends_on"]), required=True)
@click.option("--version", "version_opt", default=None)
@click.pass_context
def prdv2_link(ctx, src_chunk_id: str, dst_chunk_id: str, rel: str, version_opt: str | None) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(_json_safe(mgr.add_edge(version, src_chunk_id, dst_chunk_id, rel)))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)


@main.command("context")
@click.argument("target_id")
@click.option(
    "--scenario",
    type=click.Choice(["prd-to-impl", "impl-edit"]),
    default="prd-to-impl",
)
@click.option("--focus", is_flag=True, help="Return only L1 target chunk.")
@click.option("--deps", "include_deps", is_flag=True, help="Populate L2 from SpecGraph dependencies.")
@click.pass_context
def context_cmd(ctx, target_id: str, scenario: str, focus: bool, include_deps: bool) -> None:
    """Assemble L1+L2 context for AI prompting."""
    asm = ContextAssembler(_root(ctx))
    try:
        ok(asm.assemble(target_id, scenario=scenario, focus=focus, include_deps=include_deps).to_dict())
    except FileNotFoundError as exc:
        fail(str(exc), code="NOT_FOUND")

# ════════════════════════════════════════════════════════════
# /ait:state
# ════════════════════════════════════════════════════════════

@main.command("state")
@click.option("--version", "version_name", default=None)
@click.option("--save", "save", is_flag=True)
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
@click.pass_context
def state_cmd(ctx, version_name: str | None, save: bool, fmt: str) -> None:
    root = _root(ctx)
    try:
        if save:
            path = save_state(root, version_name)
            ok({"saved": str(path.relative_to(root)).replace("\\", "/")})
            return
        ok(render_state(root, version_name, fmt=fmt))
    except VersionManagerError as exc:
        fail(str(exc), code="NO_VERSION")


@main.command("lint")
@click.option(
    "--scope",
    type=str,
    default="baseline",
    help="baseline, version, or a concrete version such as v1.6.",
)
@click.option("--fix", is_flag=True, default=False, help="Apply mechanical PRD section fixes.")
@click.pass_context
def lint_cmd(ctx, scope: str, fix: bool) -> None:
    """Validate PRD/impl formatting rules without changing version state."""
    root = _root(ctx)
    try:
        payload, exit_code = _run_lint(root, scope=scope, fix=fix)
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "NO_VERSION"))
        return
    click.echo(json.dumps(_json_safe(payload), ensure_ascii=False))
    sys.exit(exit_code)


def _run_lint(root: Path, *, scope: str, fix: bool) -> tuple[dict, int]:
    idx = IndexManager(root)
    vm = VersionManager(root)
    baseline_ids = {c.id for c in idx.load_baseline().chunks}
    files = _lint_files(root, scope, vm)
    fixed_files: list[str] = []

    if fix:
        for path, base_dir, kind in files:
            if kind != "prd":
                continue
            original = path.read_text(encoding="utf-8")
            fixed, changed = fix_prd_text(original)
            if changed:
                path.write_text(fixed, encoding="utf-8")
                fixed_files.append(str(path.relative_to(root)).replace("\\", "/"))

    violations = []
    for path, base_dir, kind in files:
        file_rel = _lint_file_rel(path, base_dir)
        text = path.read_text(encoding="utf-8")
        if kind == "prd":
            violations.extend(scan_prd_text(text, file_rel))
        elif kind == "impl":
            version_ids = _version_ids_for_lint(root, idx, path, scope)
            violations.extend(
                scan_impl_text(
                    text,
                    file_rel,
                    baseline_ids=baseline_ids,
                    version_ids=version_ids,
                )
            )

    data = {
        "ok": not violations,
        "violations": violations_to_details(violations),
        "fixed_files": fixed_files,
    }
    return data, 0 if not violations else 1


def _lint_files(root: Path, scope: str, vm: VersionManager) -> list[tuple[Path, Path, str]]:
    if scope == "baseline":
        base = root / "docs"
        return _collect_markdown_files(base, base)
    versions: list[str]
    if scope == "version":
        versions = [m.version for m in vm.list_versions() if not m.merged_at]
    elif is_version_scope(scope):
        if not (root / "versions" / scope).exists():
            raise VersionManagerError(f"Version {scope} not found", code="VERSION_NOT_FOUND")
        versions = [scope]
    else:
        raise VersionManagerError(f"Unknown lint scope {scope}", code="INVALID_SCOPE")
    files: list[tuple[Path, Path, str]] = []
    for version in versions:
        base = root / "versions" / version
        files.extend(_collect_markdown_files(base, base))
    return files


def _collect_markdown_files(base: Path, base_dir: Path) -> list[tuple[Path, Path, str]]:
    files: list[tuple[Path, Path, str]] = []
    for kind in ("prd", "impl"):
        folder = base / kind
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*.md")):
            files.append((path, base_dir, kind))
    return files


def _lint_file_rel(path: Path, base_dir: Path) -> str:
    rel = path.relative_to(base_dir).with_suffix("")
    return str(rel).replace("\\", "/")


def _version_ids_for_lint(root: Path, idx: IndexManager, path: Path, scope: str) -> set[str]:
    if scope == "baseline":
        return set()
    parts = path.relative_to(root).parts
    version = parts[1] if len(parts) > 2 and parts[0] == "versions" else None
    if not version:
        return set()
    return {c.id for c in idx.load_version_index(version).chunks}

# ════════════════════════════════════════════════════════════
# /ait:search / deps / impact
# ════════════════════════════════════════════════════════════

@main.command("search")
@click.argument("query")
@click.option("--scope", type=click.Choice(["prd", "impl", "all"]), default="all")
@click.option("--regexp", is_flag=True)
@click.pass_context
def search_cmd(ctx, query: str, scope: str, regexp: bool) -> None:
    hits = search_chunks(_root(ctx), query, scope=scope, regexp=regexp)
    ok({"query": query, "scope": scope, "count": len(hits), "hits": [_json_safe(hit) for hit in hits]})


@main.command("deps")
@click.argument("target")
@click.option("--direction", type=click.Choice(["in", "out", "both"]), default="both")
@click.pass_context
def deps_cmd(ctx, target: str, direction: str) -> None:
    ok(query_deps(_root(ctx), target, direction=direction))


@main.command("impact")
@click.argument("target")
@click.pass_context
def impact_cmd(ctx, target: str) -> None:
    ok(analyze_impact(_root(ctx), target))

# ════════════════════════════════════════════════════════════
# /ait:reindex — rebuild baseline indexes from docs/
# ════════════════════════════════════════════════════════════

@main.command("reindex")
@click.pass_context
def reindex_cmd(ctx) -> None:
    """Rebuild baseline chunks-index.yaml + specgraph (split files) by scanning docs/.

    Also re-saves every version index to refresh derived stats
    (e.g. ``tasks_summary``).

    links-index is deprecated; all relations now live in specgraph.
    """
    root = _root(ctx)
    mgr = IndexManager(root)
    baseline, _links = mgr.rebuild_baseline()
    graph = sync_specgraph(root)

    # v1.5: refresh every version index so tasks_summary stays current.
    versions_dir = root / ".meta" / "versions"
    versions_reindexed: list[str] = []
    if versions_dir.is_dir():
        for vp in sorted(versions_dir.glob("*.yaml")):
            v = vp.stem
            try:
                vi = mgr.load_version_index(v)
                mgr.save_version_index(vi)
                versions_reindexed.append(v)
            except Exception:
                # per-version failure shouldn't break the whole reindex.
                continue

    ok(
        {
            "chunks": len(baseline.chunks),
            "specs": len(graph.specs),
            "edges": len(graph.edges),
            "baseline_index": str(mgr.baseline_index_path().relative_to(root)).replace(
                "\\", "/"
            ),
            "specgraph_index": ".meta/specgraph.yaml",
            "versions_reindexed": versions_reindexed,
        }
    )


@main.command("baseline-summary")
@click.option("--scope", type=click.Choice(["prd", "impl", "all"]), default="all")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml")
@click.pass_context
def baseline_summary_cmd(ctx, scope: str, fmt: str) -> None:
    """List baseline chunk summaries for prompt budgeting and review."""
    try:
        chunks = IndexManager(_root(ctx)).load_baseline().chunks
    except IndexSchemaViolation as exc:
        fail(str(exc), code=exc.code)
        return
    if scope == "prd":
        chunks = [c for c in chunks if c.id.startswith("prd-")]
    elif scope == "impl":
        chunks = [c for c in chunks if c.id.startswith("impl-")]
    data = [
        {"id": c.id, "heading": c.heading, "summary": c.summary}
        for c in chunks
    ]
    if fmt == "json":
        ok(data)
        return
    import yaml

    click.echo(yaml.safe_dump(_json_safe(data), allow_unicode=True, sort_keys=False))

# ═══════════════════════════════════════════════════════════
# /ait:specgraph ...
# ═══════════════════════════════════════════════════════════

@main.group("specgraph")
def specgraph_group() -> None:
    """SpecGraph index commands."""


@specgraph_group.command("sync")
@click.pass_context
def specgraph_sync(ctx) -> None:
    graph = sync_specgraph(_root(ctx))
    ok({"specs": len(graph.specs), "edges": len(graph.edges), "file": ".meta/specgraph.yaml"})


@specgraph_group.command("add-edge")
@click.argument("src")
@click.argument("dst")
@click.option("--rel", required=True)
@click.pass_context
def specgraph_add_edge(ctx, src: str, dst: str, rel: str) -> None:
    graph = add_specgraph_edge(_root(ctx), src, dst, rel)
    ok({"src": src, "dst": dst, "rel": rel, "edges": len(graph.edges)})


@specgraph_group.command("query")
@click.argument("target")
@click.option("--deps", is_flag=True)
@click.option("--implements", "implements_", is_flag=True)
@click.pass_context
def specgraph_query(ctx, target: str, deps: bool, implements_: bool) -> None:
    root = _root(ctx)
    version = VersionManager(root).current()
    graph = combined_specgraph(root, version)
    uri = resolve_chunk_uri(root, target, version, graph=graph)
    if deps:
        edges = graph.dependencies(uri)
    elif implements_:
        edges = graph.implementations(uri)
    else:
        edges = graph.query(uri, direction="both")
    ok({"target": uri, "edges": [_json_safe(edge) for edge in edges]})


@specgraph_group.command("export")
@click.option("--format", "fmt", type=click.Choice(["dot"]), default="dot")
@click.pass_context
def specgraph_export(ctx, fmt: str) -> None:
    root = _root(ctx)
    graph = combined_specgraph(root, VersionManager(root).current())
    if fmt == "dot":
        ok({"format": "dot", "content": graph.export_dot()})


@specgraph_group.command("validate-new-model")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def specgraph_validate_new_model(ctx, version_opt: str | None) -> None:
    """Validate PRD/FSD/TDD specgraph rules without applying rewrites."""
    root = _root(ctx)
    version = version_opt
    if version is None:
        try:
            version = VersionManager(root).current()
        except VersionManagerError:
            version = None
    graph = combined_specgraph(root, version) if version else load_specgraph(root, "baseline")
    violations = validate_prd_fsd_tdd_graph(graph)
    violations += validate_target_file_uniqueness(
        NewModelManager(root).collect_tdd_target_files(graph)
    )
    payload = {
        "ok": not violations,
        "version": version or "baseline",
        "violations": new_model_violations_to_details(violations),
    }
    click.echo(json.dumps(_json_safe(payload), ensure_ascii=False))
    sys.exit(0 if not violations else 1)

# ═══════════════════════════════════════════════════════════
# /ait:migrate-block-to-chunk — v1.1 → v1.2 one-shot data migration
# ═══════════════════════════════════════════════════════════

@main.command("migrate-block-to-chunk")
@click.option("--dry-run", is_flag=True, help="Show what would change, don't write.")
@click.pass_context
def migrate_block_to_chunk_cmd(ctx, dry_run: bool) -> None:
    """One-time migration: rename `block` to `chunk` in all .meta/*.yaml files."""
    from .migrations import MigrationError, migrate_block_to_chunk

    root = _root(ctx)
    meta_dir = root / ".meta"
    try:
        report = migrate_block_to_chunk(meta_dir, dry_run=dry_run)
    except MigrationError as exc:
        fail(str(exc), code="MIGRATION_FAILED")
        return
    ok(
        {
            "skipped": report.skipped_reason is not None,
            "skipped_reason": report.skipped_reason,
            "dry_run": dry_run,
            "yaml_rewritten": [
                str(p.relative_to(root)).replace("\\", "/")
                for p in report.yaml_files_rewritten
            ],
            "files_renamed": [
                [
                    str(o.relative_to(root)).replace("\\", "/"),
                    str(n.relative_to(root)).replace("\\", "/"),
                ]
                for o, n in report.files_renamed
            ],
            "fields_renamed_count": report.fields_renamed_count,
        }
    )

if __name__ == "__main__":
    main()
