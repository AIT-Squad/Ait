"""AIT CLI — `ait prd ...`, `ait fsd ...`, `ait tdd ...`, `ait version ...`.

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
from typing import cast

import click

from . import config_store
from .chunk_parser import parse_file
from .deps import query_deps
from .impact import analyze_impact
from .index_manager import IndexManager, IndexSchemaViolation
from .init_manager import InitManager, InitManagerError
from .new_model_manager import NewModelManager
from .new_model_validator import (
    scan_baseline_prd_requirement_residue,
    scan_baseline_relation_residue,
    scan_derives_residue,
    validate_prd_fsd_tdd_graph,
    validate_target_file_existence,
    validate_target_file_uniqueness,
)
from .new_model_validator import violations_to_details as new_model_violations_to_details
from .root import NotAtProjectRoot, RootResolutionError, resolve_project_root
from .search import search_chunks
from .specgraph import combined_specgraph, combined_view, load_specgraph, resolve_chunk_uri, sync_specgraph
from .state import render_state, save_state
from .validation import ValidationError, ValidationIssue
from .version_manager import ConflictPolicy, VersionManager, VersionManagerError

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
    # v2.82: symmetric with fail()'s sys.exit — a command must not be able to
    # keep running (and possibly emit a second JSON line) after a successful
    # envelope, regardless of whether the call site remembers to `return`.
    sys.exit(0)


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



def _root(ctx: click.Context) -> Path:
    return ctx.obj["root"]


class JsonGroup(click.Group):
    """click Group whose usage errors keep the single-JSON stdout contract.

    Unknown command / missing argument / bad Choice → {"ok":false,
    code:"USAGE_ERROR"} + exit 2 (audit R3-05) instead of bare usage text.
    --help / normal exits are unchanged.
    """

    def main(self, *args, **kwargs):  # noqa: D102 — click entry override
        kwargs.setdefault("standalone_mode", False)
        try:
            return super().main(*args, **kwargs)
        except click.exceptions.Exit as exc:
            sys.exit(exc.exit_code)
        except click.UsageError as exc:
            click.echo(json.dumps(
                {"ok": False, "error": exc.format_message(), "code": "USAGE_ERROR"},
                ensure_ascii=False,
            ))
            sys.exit(2)
        except click.ClickException as exc:
            click.echo(json.dumps(
                {"ok": False, "error": exc.format_message(), "code": "CLI_ERROR"},
                ensure_ascii=False,
            ))
            sys.exit(exc.exit_code)
        except click.Abort:
            sys.exit(1)


def _print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Eager --version callback: print the project's current document
    version (numeric max of recorded vMAJOR.MINOR labels), not the package
    build version. Falls back to "unversioned" outside a project root or
    when no version has been recorded yet — never raises, exit code 0.
    """
    if not value or ctx.resilient_parsing:
        return
    try:
        resolved = resolve_project_root()
        label = VersionManager(resolved.root).latest_version_label()
    except RootResolutionError:
        label = None
    click.echo(f"ait, version {label or 'unversioned'}")
    ctx.exit()


@click.group(cls=JsonGroup, help="AIT — AI-assisted document versioning.")
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    help="Show the current project document version and exit.",
)
@click.pass_context
def main(ctx: click.Context) -> None:
    ctx.ensure_object(dict)
    try:
        resolved = resolve_project_root()
    except NotAtProjectRoot as exc:
        # Bootstrap escape hatch: `ait init` on a blank directory (no
        # project-docs yet) must be able to run — it is the command that
        # CREATES project-docs. Point root at the to-be-created dir; InitManager
        # builds the skeleton. Any other command still hard-fails (need a root).
        if ctx.invoked_subcommand == "init":
            ctx.obj["root"] = Path.cwd().resolve() / "project-docs"
            return
        fail(str(exc), code=exc.code)
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
        env_skill_dir = os.environ.get("AIT_SKILL_DIR")
        cfg_skill_dir = None
        try:
            cfg_skill_dir = config_store.read_config(root / ".meta").get("skill_dir")
        except Exception:
            # Advisory read-only path: a corrupt config degrades to no hint
            # rather than breaking the CLI. Gate paths must NOT do this.
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
@click.option(
    "--migrate",
    "migrate",
    is_flag=True,
    default=False,
    help="docs 仓治理迁移子模式：把历史上被追踪的 .meta/snapshots/、.ait/ 移出 Git 索引，并把共享配置里的机器特定字段搬到机器本地层。默认只预览，不改动；需配合 --apply 才落地。此模式不执行常规初始化。",
)
@click.option(
    "--apply",
    "apply_migration",
    is_flag=True,
    default=False,
    help="与 --migrate 同用时表示落地执行（破坏性索引操作，必须显式指定）。单独给出报 USAGE_ERROR。",
)
@click.pass_context
def init_cmd(
    ctx,
    refresh_wrapper: bool,
    check_only: bool,
    skip_csv: str,
    new_model: bool,
    project_name: str,
    migrate: bool,
    apply_migration: bool,
) -> None:
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
    if apply_migration and not migrate:
        fail("--apply 仅在与 --migrate 同用时有效", code="USAGE_ERROR")
    try:
        if migrate:
            # Migration is a standalone sub-mode: it must not also mutate the
            # project skeleton, so `run()` is deliberately not called here.
            report = mgr.migrate_docs_repo_hygiene(dry_run=not apply_migration)
            ok(
                {
                    "removed_paths": report.removed_paths,
                    # Key names only — the values are local paths / command
                    # strings, i.e. machine-specific data that should not leak
                    # into command output or logs.
                    "moved_fields": sorted(report.moved_fields),
                    "dry_run": report.dry_run,
                    "applicable": report.applicable,
                }
            )
            return
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
    except config_store.ConfigError as exc:
        fail(str(exc), code=exc.code)


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
@click.option("--allow-dirty-git", is_flag=True, hidden=True)
@click.pass_context
def version_merge(ctx, version_name: str, allow_dirty_git: bool) -> None:
    """Atomically execute a confirmed plan, creating the default plan for legacy callers."""
    mgr = VersionManager(_root(ctx))
    try:
        if mgr.load_version_meta(version_name).confirmed_plan is None:
            report = mgr.gate(version_name, check_host=not allow_dirty_git)
            if not report["passed"]:
                violation = report["violations"][0]
                code = (
                    violation["code"]
                    if violation["code"] in {"ACCEPTANCE_FAILED", "TASK_NOT_DONE"}
                    else "INVARIANT_VIOLATION"
                )
                fail(violation["message"], code=code, details=report)
                return
        ok(mgr.merge_confirmed(version_name))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "MERGE_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "MERGE_FAILED"))


@version_group.command("confirm")
@click.argument("version_name")
@click.option(
    "--conflict-policy",
    type=click.Choice(["abort", "use-version", "use-baseline"]),
    default="use-version",
    show_default=True,
    help="Conflict policy frozen into the reconciliation plan.",
)
@click.pass_context
def version_confirm(ctx, version_name: str, conflict_policy: str) -> None:
    """Run gates and persist the reconciliation plan for a later merge."""
    mgr = VersionManager(_root(ctx))
    try:
        report = mgr.gate(version_name, conflict_policy=cast(ConflictPolicy, conflict_policy))
        if report["passed"]:
            ok(report)
        else:
            violation = report["violations"][0]
            code = (
                violation["code"]
                if violation["code"] in {"ACCEPTANCE_FAILED", "TASK_NOT_DONE"}
                else "INVARIANT_VIOLATION"
            )
            fail(violation["message"], code=code, details=report)
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "CONFIRM_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "CONFIRM_FAILED"))


@version_group.command("commit")
@click.argument("version_name")
@click.option("-m", "--message", default="new-model commit", help="Commit message.")
@click.pass_context
def version_commit(ctx, version_name: str, message: str) -> None:
    """Stage all working chunks and commit them — the new-model lock step.

    New-model `fsd/tdd/prdv2 create` register chunks as `working`; `version
    confirm` only merges `committed` chunks. This bulk-commits the whole version
    (working → staged → committed) so a taskless new-model version can confirm.
    """
    mgr = VersionManager(_root(ctx))
    try:
        stage_result = mgr.stage(version_name)
        commit_result = mgr.commit(version_name, message)
        ok(
            {
                "version": version_name,
                "committed": stage_result.staged,
                "commit_id": commit_result.commit_id,
                "changes": commit_result.changes,
            }
        )
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "COMMIT_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "COMMIT_FAILED"))


@version_group.command("create")
@click.argument("version_name")
@click.option("--based-on", default=None, help="Optional parent version.")
@click.pass_context
def version_create(ctx, version_name: str, based_on: str | None) -> None:
    """Explicitly open a version workspace (meta + empty index).

    Erroring when the version already exists kills ghost versions: a typo'd
    --version elsewhere can no longer silently materialise a workspace.
    """
    mgr = VersionManager(_root(ctx))
    try:
        meta = mgr.create(version_name, based_on=based_on)
        ok({"version": version_name, "created_at": meta.created_at, "based_on": based_on})
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "CREATE_FAILED"))


@version_group.command("revert")
@click.argument("version_name")
@click.option("--confirm", is_flag=True, help="Confirm the irreversible revert.")
@click.pass_context
def version_revert(ctx, version_name: str, confirm: bool) -> None:
    """Wipe an unmerged version workspace — the any-stage exit (atomic-version escape hatch)."""
    mgr = VersionManager(_root(ctx))
    try:
        result = mgr.reset(version_name, confirmed=confirm)
        if not result.get("ok", True):
            fail(result["warning"], code=result["code"])
            return
        ok(result)
    except VersionManagerError as exc:
        fail(str(exc), code="REVERT_FAILED")


@version_group.command("backfill-tags")
@click.pass_context
def version_backfill_tags(ctx) -> None:
    """Re-create missing persistent revert tags from each version's docs_commit."""
    mgr = VersionManager(_root(ctx))
    try:
        ok(mgr.backfill_revert_tags())
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "BACKFILL_FAILED"))


@main.group("fsd")
def fsd_group() -> None:
    """Manage new-model FSD documents."""


@fsd_group.command("create")
@click.argument("root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.option("--parent", "parent_chunk_id", default=None,
              help="PRD root chunk to derive from (births the PRD→FSD derives edge).")
@click.option("--file", "file_opt", default=None, help="FSD file under fsd/ or explicit index path, no .md.")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--content", default=None)
@click.option("--action", type=click.Choice(["add", "modify"]), default="add")
@click.option("--overrides", default=None)
@click.option("--context-token", default=None)
@click.option("--skip-context", is_flag=True, default=False)
@click.pass_context
def fsd_create(
    ctx,
    root_chunk_id: str,
    version_opt: str | None,
    parent_chunk_id: str | None,
    file_opt: str | None,
    content_file: Path | None,
    content: str | None,
    action: str,
    overrides: str | None,
    context_token: str | None,
    skip_context: bool,
) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        if content is None and content_file is None:
            if skip_context:
                raise ValidationError([ValidationIssue(
                    severity="E1", code="CONTEXT_SKIP_NOT_ALLOWED",
                    message="--skip-context is only valid for content writes",
                )])
            ok(_json_safe(mgr.prepare_discussion(
                version, "fsd", root_chunk_id, parent_id=parent_chunk_id,
                file=file_opt, action=action, overrides=overrides,
            )))
            return
        result = mgr.create_fsd(
            version,
            root_chunk_id,
            _read_content(content_file, content),
            file=file_opt,
            action=action,
            overrides=overrides,
            parent_chunk_id=parent_chunk_id,
            context_token=context_token,
            skip_context=skip_context,
        )
        ok(_json_safe(result))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED",
             details=getattr(exc, "details", None))


@fsd_group.command("decompose")
@click.argument("parent_chunk_id")
@click.argument("child_root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.option("--file", "file_opt", default=None, help="Child FSD file under fsd/, no .md.")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--content", default=None)
@click.option("--context-token", default=None)
@click.option("--skip-context", is_flag=True, default=False)
@click.pass_context
def fsd_decompose(
    ctx,
    parent_chunk_id: str,
    child_root_chunk_id: str,
    version_opt: str | None,
    file_opt: str | None,
    content_file: Path | None,
    content: str | None,
    context_token: str | None,
    skip_context: bool,
) -> None:
    """Split-is-edge: atomically write the child FSD (if --content given) and
    create the parent→child decomposes edge. Replaces `fsd link`."""
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    child_content = None
    if content is not None or content_file is not None:
        child_content = _read_content(content_file, content)
    try:
        if child_content is None:
            if skip_context:
                raise ValidationError([ValidationIssue(
                    severity="E1", code="CONTEXT_SKIP_NOT_ALLOWED",
                    message="--skip-context is only valid for content writes",
                )])
            # v2.53: no content + child not yet in view → 锚定式讨论背景
            # (formerly a bare MISSING_ENDPOINT error path). Child exists →
            # link-only decompose, unchanged.
            from .specgraph import combined_view as _cv
            if _cv(_root(ctx), version).node(child_root_chunk_id) is None:
                ok(_json_safe(mgr.prepare_discussion(
                    version, "fsd", child_root_chunk_id, parent_id=parent_chunk_id,
                    file=file_opt, operation="decompose",
                )))
                return
        ok(_json_safe(mgr.decompose_fsd(
            version, parent_chunk_id, child_root_chunk_id,
            content=child_content, file=file_opt,
            context_token=context_token, skip_context=skip_context,
        )))
    except ValidationError as exc:
        code = exc.issues[0].code if exc.issues else "VALIDATION_FAILED"
        fail(str(exc), code=code, details=getattr(exc, "details", None))


@fsd_group.command("confirm")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def fsd_confirm(ctx, version_opt: str | None) -> None:
    """Freeze the FSD layer: lock [FSD]- chunks, phase → fsd-confirm."""
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(mgr.confirm_fsd_layer(version))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "CONFIRM_FAILED"))


@fsd_group.command("revert")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def fsd_revert(ctx, version_opt: str | None) -> None:
    """Rework pair of `fsd confirm`: unlock FSD chunks, phase → fsd-creating."""
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(mgr.revert_fsd_layer(version))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "REVERT_FAILED"))


@main.group("tdd")
def tdd_group() -> None:
    """Manage new-model TDD documents."""


@tdd_group.command("create")
@click.argument("root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.option("--parent", "parent_chunk_id", default=None,
              help="FSD leaf split; when given, atomically build the details edge.")
@click.option("--file", "file_opt", default=None, help="TDD file under tdd/ or explicit index path, no .md.")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--content", default=None)
@click.option("--action", type=click.Choice(["add", "modify"]), default="add")
@click.option("--overrides", default=None)
@click.option("--context-token", default=None)
@click.option("--skip-context", is_flag=True, default=False)
@click.pass_context
def tdd_create(
    ctx,
    root_chunk_id: str,
    version_opt: str | None,
    parent_chunk_id: str | None,
    file_opt: str | None,
    content_file: Path | None,
    content: str | None,
    action: str,
    overrides: str | None,
    context_token: str | None,
    skip_context: bool,
) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        if content is None and content_file is None:
            if skip_context:
                raise ValidationError([ValidationIssue(
                    severity="E1", code="CONTEXT_SKIP_NOT_ALLOWED",
                    message="--skip-context is only valid for content writes",
                )])
            ok(_json_safe(mgr.prepare_discussion(
                version, "tdd", root_chunk_id, parent_id=parent_chunk_id,
                file=file_opt, action=action, overrides=overrides,
            )))
            return
        result = mgr.create_tdd(
            version,
            root_chunk_id,
            _read_content(content_file, content),
            file=file_opt,
            action=action,
            overrides=overrides,
            parent_chunk_id=parent_chunk_id,
            context_token=context_token,
            skip_context=skip_context,
        )
        ok(_json_safe(result))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED",
             details=getattr(exc, "details", None))


@tdd_group.command("confirm")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def tdd_confirm(ctx, version_opt: str | None) -> None:
    """Freeze the TDD layer: lock [TDD]- chunks, phase → tdd-confirm."""
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(mgr.confirm_tdd_layer(version))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "CONFIRM_FAILED"))


@tdd_group.command("revert")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def tdd_revert(ctx, version_opt: str | None) -> None:
    """Rework pair of `tdd confirm`: unlock TDD chunks, phase → tdd-creating."""
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(mgr.revert_tdd_layer(version))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED")
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "REVERT_FAILED"))


@main.group("codegen")
def codegen_group() -> None:
    """Prepare new-model TDD code generation context."""


@codegen_group.command("prepare")
@click.argument("tdd_root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def codegen_prepare(ctx, tdd_root_chunk_id: str, version_opt: str | None) -> None:
    import hashlib
    import re
    import tempfile

    from .codegen_brief import render as render_codegen_bundle
    from .io_utils import atomic_write_text

    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    try:
        # v2.74 (G19/G24): assemble the bundle, then deliver it via an ephemeral
        # temp file (never git-tracked) + a small stdout pointer. Dumping the full
        # ~100KB+ bundle to stdout risks silent mid-truncation by the orchestrator's
        # tool-output cap; a file channel + sha256 lets the caller inject the whole
        # context into an (sub)agent window and verify no truncation.
        # v2.80: the delivered artifact is the rendered text, not JSON — a JSON
        # payload escaped the spec (\n, \") and its alphabetical key order pushed
        # `upstream` behind the source code. Pointer field names are unchanged, so
        # the SKILL.md orchestration steps need no edit.
        bundle = mgr.prepare_codegen(version, tdd_root_chunk_id)
        payload = render_codegen_bundle(bundle)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        safe_v = re.sub(r"[^A-Za-z0-9_.-]", "_", str(version or "baseline"))
        safe_t = re.sub(r"[^A-Za-z0-9_.-]", "_", tdd_root_chunk_id)
        out_dir = Path(tempfile.gettempdir()) / "ait-codegen"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{safe_v}_{safe_t}.md"
        # v2.92: write via atomic_write_text (newline="\n") — Path.write_text's
        # text mode turns LF into CRLF on Windows, so the on-disk bytes differed
        # from the string the digest was taken over and the truncation check
        # below could never match.
        atomic_write_text(out_path, payload)
        ok({
            "bundle_path": str(out_path),
            "sha256": digest,
            "bytes": len(payload.encode("utf-8")),
            "version": bundle.version,
            "target_file": bundle.target_file,
            "tdd_root": bundle.tdd_root,
            "source_file": bundle.source_file,
        })
    except ValidationError as exc:
        # 领域错误码透传(契约见 [FSD]-ait:cli):不吞成笼统 VALIDATION_FAILED。
        fail(
            str(exc),
            code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED",
            details=exc.details,
        )


@main.command("push")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def push(ctx, dry_run: bool) -> None:
    """v2.81: publish both repos — host artifacts first, then docs specs.

    Deliberately exposes only --dry-run: no remote/branch/refspec option, so a
    mis-push cannot be requested through the interface.
    """
    from .publisher import Publisher

    # No phase gate: publishing changes no chunk state, so an in-flight version
    # does not block it.
    result = Publisher(_root(ctx)).publish(dry_run=dry_run)
    if result["passed"]:
        ok(result)
        return
    first_failed = next(
        (repo for repo in result["repos"] if repo["outcome"] == "failed"), None
    )
    fail(
        (first_failed or {}).get("error") or "push failed",
        code=(first_failed or {}).get("error_code") or "PUSH_FAILED",
        details=result,
    )


@main.group("acceptance")
def acceptance_group() -> None:
    """Artifact acceptance — the configured test command that gates merge."""


@acceptance_group.command("set")
@click.argument("command", required=False, default=None)
@click.pass_context
def acceptance_set(ctx, command: str | None) -> None:
    """Set (or clear, if omitted) the acceptance command.

    v2.71: stored in the machine-local config layer — the value is
    machine-specific and gets executed, so it must not travel in shared history.
    """
    mgr = VersionManager(_root(ctx))
    try:
        ok(mgr.set_acceptance_command(command))
    except VersionManagerError as exc:
        fail(str(exc), code=exc.code)


@acceptance_group.command("run")
@click.pass_context
def acceptance_run(ctx) -> None:
    """Run the configured acceptance command and report the result."""
    mgr = VersionManager(_root(ctx))
    try:
        ok(mgr.run_acceptance())
    except VersionManagerError as exc:
        # Keeps CONFIG_UNREADABLE / LEGACY_ACCEPTANCE_CONFIG as stable codes in
        # a single JSON payload instead of leaking a traceback.
        fail(str(exc), code=exc.code)


@main.group("prd")
def prdv2_group() -> None:
    """New-model PRD documents."""


@prdv2_group.command("create")
@click.argument("root_chunk_id")
@click.option("--version", "version_opt", default=None)
@click.option("--file", "file_opt", default=None, help="PRD file under prd/ or explicit index path, no .md.")
@click.option("--content-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--content", default=None)
@click.option("--action", type=click.Choice(["add", "modify"]), default="add")
@click.option("--overrides", default=None)
@click.option("--context-token", default=None)
@click.option("--skip-context", is_flag=True, default=False)
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
    context_token: str | None,
    skip_context: bool,
) -> None:
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    # P7 rule #2: prd create requires an already-created active version — no
    # auto-open. Run `version create` first.
    if not version:
        fail(
            "no active version — run `version create <v>` first",
            code="NO_ACTIVE_VERSION",
        )
        return
    try:
        if content is None and content_file is None:
            if skip_context:
                raise ValidationError([ValidationIssue(
                    severity="E1", code="CONTEXT_SKIP_NOT_ALLOWED",
                    message="--skip-context is only valid for content writes",
                )])
            ok(_json_safe(mgr.prepare_discussion(
                version, "prd", root_chunk_id,
                file=file_opt, action=action, overrides=overrides,
            )))
            return
        result = mgr.create_prd(
            version,
            root_chunk_id,
            _read_content(content_file, content),
            file=file_opt,
            action=action,
            overrides=overrides,
            context_token=context_token,
            skip_context=skip_context,
        )
        payload = _json_safe(result)
        ok(payload)
    except ValidationError as exc:
        # 领域错误码透传(与 fsd/tdd create 一致,契约见 [FSD]-ait:cli):
        # 不吞成笼统 VALIDATION_FAILED。
        fail(
            str(exc),
            code=exc.issues[0].code if exc.issues else "VALIDATION_FAILED",
            details=exc.details,
        )


@prdv2_group.command("confirm")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def prdv2_confirm(ctx, version_opt: str | None) -> None:
    """Freeze the PRD layer: lock [PRD]- chunks, phase → prd-confirm."""
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(mgr.confirm_prd_layer(version))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "CONFIRM_FAILED"))


@prdv2_group.command("revert")
@click.option("--version", "version_opt", default=None)
@click.pass_context
def prdv2_revert(ctx, version_opt: str | None) -> None:
    """Rework pair of `prd confirm`: unlock PRD chunks, phase → prd-creating."""
    mgr = NewModelManager(_root(ctx))
    version = version_opt or mgr.versions.current()
    if not version:
        fail("No active version", code="NO_VERSION")
    try:
        ok(mgr.revert_prd_layer(version))
    except ValidationError as exc:
        fail(str(exc), code="VALIDATION_FAILED", details=exc.details)
    except VersionManagerError as exc:
        fail(str(exc), code=getattr(exc, "code", "REVERT_FAILED"))


# v2.26: `prd link` retired — the last link command. All three relations are
# born with content creation: depends_on via fsd create's in-split yaml
# declarations, decomposes via fsd decompose, details via tdd create --parent.


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


# ════════════════════════════════════════════════════════════
# /ait:search / deps / impact
# ════════════════════════════════════════════════════════════

@main.command("search")
@click.argument("query")
@click.option("--scope", type=click.Choice(["prd", "all"]), default="all")
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
    baseline = mgr.rebuild_baseline()
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
@click.option("--scope", type=click.Choice(["prd", "all"]), default="all")
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


@specgraph_group.command("graph-html")
@click.option("--prd-chunk", default=None,
              help="Scope to this PRD requirement chunk's subtree.")
@click.option("--version", "version_opt", default=None,
              help="Generate from combined_view of this version; omit for baseline.")
@click.pass_context
def specgraph_graph_html(ctx, prd_chunk: str | None, version_opt: str | None) -> None:
    """Generate an HTML spec-tree from the specgraph.

    Without --version writes docs/graph.html (baseline).
    With --version writes versions/<v>/graph.html (combined view).
    With --prd-chunk scopes to that PRD requirement chunk's FSD/TDD subtree.
    """
    from .graph_md import write_graph_html
    root = _root(ctx)
    try:
        result = write_graph_html(root, version_opt, prd_chunk)
        ok(result)
    except ValueError as exc:
        fail(str(exc), code="PRD_CHUNK_INVALID")
    except Exception as exc:
        fail(str(exc), code="GRAPH_HTML_FAILED")


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
    tdd_targets = NewModelManager(root).collect_tdd_target_files(graph)
    violations += validate_target_file_uniqueness(tdd_targets)
    # relation birth boundary closure: one-shot baseline sweep for residual
    # @ref/@extract/depends_on-derives declarations left in new-model docs
    # bodies. Report-only — never gates `ok`/exit code.
    contents = []
    for kind in ("prd", "fsd", "tdd"):
        kind_dir = root / "docs" / kind
        if not kind_dir.exists():
            continue
        for path in sorted(kind_dir.rglob("*.md")):
            parsed = parse_file(path, root / "docs")
            for chunk in parsed.chunks:
                contents.append((parsed.file, chunk.id, chunk.content))
    residue = scan_baseline_relation_residue(contents)
    # v2.77: same already-read contents feed the PRD requirement contract sweep
    # (report-only, independent field — does not touch `passed`/exit code).
    prd_residue = scan_baseline_prd_requirement_residue(contents)
    # v2.82: same contents (filtered to fsd/) feed the derives-mention sweep;
    # needs edge lookups, so it takes the combined_view rather than the graph
    # object already built above (report-only, independent field).
    fsd_contents = [item for item in contents if item[0].startswith("fsd/")]
    # v2.99: which suffixes mark acceptance nodes is project config, not a
    # constant in the validator — read it here and pass it in (derives_mapping
    # AC#6). Unconfigured means an empty set, never a guessed ":TEST".
    scopes = config_store.read_config(root / ".meta").get("artifact_scopes", {}) or {}
    acceptance_suffixes = tuple(sorted(
        {s["parent_suffix"] for s in scopes.values() if s.get("parent_suffix")}
    ))
    derives_residue = scan_derives_residue(
        combined_view(root, version), fsd_contents,
        acceptance_suffixes=acceptance_suffixes,
    )
    # v2.96: the same collected entries answer the mirror question — does the
    # artifact each TDD claims still exist. Report-only like the fields above;
    # applying warn/block is the confirm gate's job, so no enforcement here.
    target_file_missing = validate_target_file_existence(
        tdd_targets, exists=lambda p: (root.parent / p).exists()
    )
    ok(
        {
            "version": version or "baseline",
            "passed": not violations,
            "violations": new_model_violations_to_details(violations),
            "relation_residue": new_model_violations_to_details(residue),
            "prd_requirement_residue": new_model_violations_to_details(prd_residue),
            "derives_residue": new_model_violations_to_details(derives_residue),
            "target_file_missing": new_model_violations_to_details(target_file_missing),
        }
    )

if __name__ == "__main__":
    main()
