"""AIT CLI — `ait prd ...`, `ait impl ...`, `ait version ...`.

All commands emit a single JSON object per ait-system.md§prd-ait-cmd-output:

    Success: {"ok": true, "data": {...}}
    Failure: {"ok": false, "error": "...", "code": "..."}

This contract makes AI IDE integration straightforward — every Skill wrapper just
captures stdout and re-emits to the model.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import click

from . import __version__
from .context_assembler import ContextAssembler
from .impl_manager import ImplManager
from .index_manager import IndexManager
from .prd_manager import PrdManager
from .root import RootResolutionError, resolve_project_root
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


def fail(message: str, code: str = "ERROR", exit_code: int = 1) -> None:
    click.echo(
        json.dumps({"ok": False, "error": message, "code": code}, ensure_ascii=False)
    )
    sys.exit(exit_code)


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
                "block_count": len(req.prd_blocks),
                "block_ids": [b.id for b in req.prd_blocks],
            }
        )
    except (FileNotFoundError, ValidationError) as exc:
        fail(str(exc), code="DRAFT_FAILED")


@prd_group.command("confirm")
@click.argument("req_id")
@click.option("--file", "prd_file", default=None, help="prd/{name} path (no .md)")
@click.pass_context
def prd_confirm(ctx, req_id: str, prd_file: str | None) -> None:
    """Materialize the prd_draft into the version workspace."""
    mgr = PrdManager(_root(ctx))
    try:
        result = mgr.write_to_version(req_id, prd_file=prd_file)
        ok(
            {
                "req_id": req_id,
                "version": result.version,
                "file": result.file,
                "block_ids": result.block_ids,
            }
        )
    except (FileNotFoundError, ValidationError) as exc:
        fail(str(exc), code="CONFIRM_FAILED")


@prd_group.command("show")
@click.argument("prd_file")
@click.argument("block_id", required=False)
@click.pass_context
def prd_show(ctx, prd_file: str, block_id: str | None) -> None:
    mgr = PrdManager(_root(ctx))
    try:
        ok(mgr.show(prd_file, block_id=block_id))
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
        fail(str(exc), code=exc.issues[0].code if exc.issues else "COMMIT_FAILED")


# ═══════════════════════════════════════════════════════════
# /ait:impl ...
# ═══════════════════════════════════════════════════════════


@main.group("impl")
def impl_group() -> None:
    """Impl-domain commands."""


@impl_group.command("create")
@click.argument("prd_block_id")
@click.option(
    "--content-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File containing the impl markdown (use - for stdin).",
)
@click.option("--content", default=None, help="Inline impl markdown content.")
@click.option("--impl-file", default=None, help="impl/{name} target file (auto-detected if absent).")
@click.option("--req-id", default=None)
@click.option("--prd-file", default=None)
@click.pass_context
def impl_create(
    ctx,
    prd_block_id: str,
    content_file: Path | None,
    content: str | None,
    impl_file: str | None,
    req_id: str | None,
    prd_file: str | None,
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
            prd_block_id,
            content,
            impl_file=impl_file,
            req_id=req_id,
            prd_file=prd_file,
        )
        ok(
            {
                "version": result.version,
                "file": result.file,
                "block_ids": result.block_ids,
            }
        )
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "IMPL_CREATE_FAILED")


@impl_group.command("show")
@click.argument("impl_block_id")
@click.pass_context
def impl_show(ctx, impl_block_id: str) -> None:
    mgr = ImplManager(_root(ctx))
    try:
        ok(mgr.show(impl_block_id))
    except FileNotFoundError as exc:
        fail(str(exc), code="NOT_FOUND")


@impl_group.command("commit")
@click.argument("impl_block_id")
@click.option("-m", "--message", required=True)
@click.option("--req-id", default=None)
@click.pass_context
def impl_commit(ctx, impl_block_id: str, message: str, req_id: str | None) -> None:
    mgr = ImplManager(_root(ctx))
    try:
        ok(mgr.commit(impl_block_id, message, req_id=req_id))
    except ValidationError as exc:
        fail(str(exc), code=exc.issues[0].code if exc.issues else "IMPL_COMMIT_FAILED")


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


# ═══════════════════════════════════════════════════════════
# /ait:context ... (AI plumbing — not in the user-facing 7 but useful for Skills)
# ═══════════════════════════════════════════════════════════


@main.command("context")
@click.argument("target_id")
@click.option(
    "--scenario",
    type=click.Choice(["prd-to-impl", "impl-edit"]),
    default="prd-to-impl",
)
@click.pass_context
def context_cmd(ctx, target_id: str, scenario: str) -> None:
    """Assemble L1+L2 context for AI prompting."""
    asm = ContextAssembler(_root(ctx))
    try:
        ok(asm.assemble(target_id, scenario=scenario).to_dict())
    except FileNotFoundError as exc:
        fail(str(exc), code="NOT_FOUND")


# ═══════════════════════════════════════════════════════════
# /ait:reindex — rebuild baseline indexes from docs/
# ═══════════════════════════════════════════════════════════


@main.command("reindex")
@click.pass_context
def reindex_cmd(ctx) -> None:
    """Rebuild baseline blocks-index.yaml and links-index.yaml by scanning docs/."""
    root = _root(ctx)
    mgr = IndexManager(root)
    baseline, links = mgr.rebuild_baseline()
    ok(
        {
            "blocks": len(baseline.blocks),
            "links": len(links.links),
            "baseline_index": str(mgr.baseline_index_path().relative_to(root)).replace(
                "\\", "/"
            ),
            "links_index": str(mgr.links_index_path().relative_to(root)).replace(
                "\\", "/"
            ),
        }
    )


if __name__ == "__main__":
    main()
