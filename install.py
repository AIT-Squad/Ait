#!/usr/bin/env python3
"""AIT installer — install / update / uninstall the Claude Code Skill.

Usage:
    python install.py                  # install (or update if already present)
    python install.py install          # full install: removes existing including .venv
    python install.py update           # update files, then refresh installed .venv
    python install.py update --skip-venv  # update files only, leave .venv untouched
    python install.py uninstall        # remove the installed skill

Common options:
    --prefix PATH                      # custom install location
    --force                            # skip confirmation prompts
    --no-venv-warmup                   # (install only) skip first-run pip install
    --skip-venv                        # (update only) skip refreshing .venv
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 on Windows consoles so dashes / non-ASCII chars don't mojibake.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

DEFAULT_PREFIX = Path.home() / ".claude" / "skills" / "ait"

IGNORE_PATTERNS = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
    ".venv",
    ".pytest_cache",
    ".coverage",
    "*.tmp",
    "build",
)


def log(msg: str) -> None:
    print(f"[ait] {msg}", file=sys.stderr)


def find_skill_source() -> Path:
    here = Path(__file__).resolve().parent
    src = here / "skill" / "ait"
    if not (src / "SKILL.md").exists():
        sys.exit(
            f"error: cannot find skill/ait/SKILL.md relative to {here} — run this "
            "script from the repository root."
        )
    return src


def confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def is_ait_skill(path: Path) -> bool:
    """Refuse to touch a directory that doesn't look like an AIT skill install."""
    return (path / "SKILL.md").exists() and (path / "bin").exists()


def warmup_venv(dest: Path) -> None:
    """Trigger first-run pip install by invoking bin/ait --version once."""
    ait_bin = (
        dest / "bin" / "ait.cmd" if sys.platform == "win32" else dest / "bin" / "ait"
    )
    if not ait_bin.exists():
        log(f"warning: {ait_bin} not found, skipping venv warmup")
        return

    log("warming up venv (first install may take ~30s)...")
    try:
        result = subprocess.run(
            [str(ait_bin), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        log(f"warning: could not run {ait_bin}: {exc}")
        return

    if result.returncode == 0:
        log(f"ready: {result.stdout.strip()}")
    else:
        log(
            f"warning: venv warmup exited with code {result.returncode}. "
            f"Run `{ait_bin}` later to retry."
        )
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)


def find_venv_python(dest: Path) -> Path | None:
    """Return the installed skill venv Python if it exists."""
    candidates = (
        [
            dest / ".venv" / "Scripts" / "python.exe",
            dest / ".venv" / "bin" / "python",
        ]
        if sys.platform == "win32"
        else [
            dest / ".venv" / "bin" / "python",
            dest / ".venv" / "Scripts" / "python.exe",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def refresh_venv(dest: Path) -> None:
    """Refresh the ait package installed in the target skill venv."""
    venv_py = find_venv_python(dest)
    if venv_py is None:
        log("no venv python found; warming up venv via wrapper...")
        warmup_venv(dest)
        return

    log("refreshing venv package...")
    try:
        result = subprocess.run(
            [
                str(venv_py),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "--upgrade",
                str(dest),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        sys.exit(f"error: could not refresh venv with {venv_py}: {exc}")

    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(
            "error: venv refresh failed. Re-run `python install.py update --skip-venv` "
            "to update files without touching the venv."
        )
    log("venv refreshed")


def do_install(source: Path, dest: Path, force: bool, warmup: bool) -> None:
    """Full install: wipes the entire dest (including .venv) and copies fresh."""
    log(f"source: {source}")
    log(f"target: {dest}")

    if dest.exists():
        if not force and not confirm(
            f"{dest} already exists. Remove (including .venv) and reinstall?"
        ):
            sys.exit("aborted (use `update` to preserve .venv)")
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, ignore=IGNORE_PATTERNS)
    log(f"installed to {dest}")

    if warmup:
        warmup_venv(dest)

    print(file=sys.stderr)
    log("done. Restart Claude Code, then type /ait <subcommand> in any project.")


def do_update(source: Path, dest: Path, skip_venv: bool = False) -> None:
    """In-place update: overwrites code & docs, then refreshes .venv by default."""
    log(f"source: {source}")
    log(f"target: {dest}")

    if not dest.exists():
        sys.exit(
            f"error: no installation at {dest}. Run `python install.py install` first."
        )
    if not is_ait_skill(dest):
        sys.exit(
            f"error: {dest} does not look like an AIT skill "
            "(missing SKILL.md or bin/). Refusing to overwrite."
        )

    venv_preserved = (dest / ".venv").exists()

    for child in source.iterdir():
        if child.name in {".venv", "__pycache__", "build"} or child.name.endswith(
            ".egg-info"
        ):
            continue
        target = dest / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target, ignore=IGNORE_PATTERNS)
        else:
            shutil.copy2(child, target)

    log(f"updated {dest}" + (" (kept .venv)" if venv_preserved else ""))
    if skip_venv:
        log("skipped venv refresh (--skip-venv)")
        return

    refresh_venv(dest)


def do_uninstall(dest: Path, force: bool) -> None:
    if not dest.exists():
        log(f"{dest} does not exist — nothing to uninstall")
        return
    if not is_ait_skill(dest):
        sys.exit(
            f"error: {dest} does not look like an AIT skill. Refusing to delete."
        )
    if not force and not confirm(f"Remove {dest}?"):
        sys.exit("aborted")
    shutil.rmtree(dest)
    log(f"removed {dest}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install / update / uninstall the AIT Claude Code Skill.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python install.py                  # install (default)\n"
            "  python install.py install --force  # full reinstall, no prompts\n"
            "  python install.py update           # upgrade files and refresh .venv\n"
            "  python install.py update --skip-venv  # upgrade files only\n"
            "  python install.py uninstall        # remove\n"
        ),
    )
    parser.add_argument(
        "--prefix",
        type=Path,
        default=DEFAULT_PREFIX,
        help=f"Skill install directory (default: {DEFAULT_PREFIX})",
    )

    sub = parser.add_subparsers(dest="action", metavar="{install,update,uninstall}")

    p_install = sub.add_parser(
        "install",
        help="Full install — removes existing target (including .venv) and copies fresh.",
    )
    p_install.add_argument("--force", action="store_true", help="No prompts.")
    p_install.add_argument(
        "--no-venv-warmup",
        action="store_true",
        help="Skip first-run pip install (runs on first /ait call instead).",
    )

    p_update = sub.add_parser(
        "update",
        help="Upgrade in place — overwrites files and refreshes .venv by default.",
    )
    p_update.add_argument(
        "--skip-venv",
        action="store_true",
        help="Copy files only; do not refresh the installed .venv.",
    )

    p_uninstall = sub.add_parser("uninstall", help="Remove the installed skill.")
    p_uninstall.add_argument("--force", action="store_true", help="No prompts.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        sys.exit(
            f"error: Python 3.10+ required (you have "
            f"{sys.version_info.major}.{sys.version_info.minor})"
        )

    dest = args.prefix.expanduser().resolve()
    action = args.action or "install"

    if action == "install":
        source = find_skill_source()
        do_install(
            source,
            dest,
            force=getattr(args, "force", False),
            warmup=not getattr(args, "no_venv_warmup", False),
        )
    elif action == "update":
        source = find_skill_source()
        do_update(source, dest, skip_venv=getattr(args, "skip_venv", False))
    elif action == "uninstall":
        do_uninstall(dest, force=getattr(args, "force", False))
    else:
        parser.error(f"unknown action: {action}")


if __name__ == "__main__":
    main()
