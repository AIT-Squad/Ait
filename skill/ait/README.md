# AIT Skill — Distributable Bundle

> This directory IS the Claude Code Skill. Copy it to `~/.claude/skills/ait/` to install.

```
skill/ait/
├── SKILL.md             # Entry point Claude reads
├── pyproject.toml       # Distribution metadata + deps
├── README.md            # This file
├── ait/                 # Python package (the actual implementation)
├── bin/
│   ├── ait              # POSIX/Git-Bash wrapper (self-installing)
│   └── ait.cmd          # Windows CMD wrapper (self-installing)
├── references/          # Bundled docs (replaces external links)
└── templates/           # YAML templates used by the CLI
```

## Install

From the repository root:

```bash
python install.py             # fresh install (default)
python install.py install     # same, explicit
python install.py update      # in-place upgrade (preserves .venv, <1s)
python install.py uninstall   # remove
```

`install` copies the contents of `skill/ait/` (this directory) into `~/.claude/skills/ait/` and pre-warms the bundled venv. `update` is what you want after `git pull` — it overwrites code/docs but keeps the warmed-up venv. See [`install.py --help`](../../install.py) for `--prefix`, `--force`, and `--no-venv-warmup`.

### Manual install (no installer)

```bash
# Linux / macOS / Git Bash
cp -r skill/ait ~/.claude/skills/

# Windows (PowerShell)
Copy-Item -Recurse skill\ait $env:USERPROFILE\.claude\skills\
```

No system-wide pip install needed. The first time the skill wrapper is invoked it creates an isolated `.venv` inside the skill directory and installs the bundled package + deps into it. Subsequent runs reuse the venv.

## Prerequisites

- Python ≥ 3.10 available as `python` or `python3` on PATH
- Internet access for the **first** invocation (pip fetches PyYAML / pydantic / click)
- ~30 MB disk for the per-skill venv

After the first install, the skill works offline.

## Usage

After a one-time bootstrap, all commands run via the project-local wrapper that `init` generates inside your project:

```bash
# 1. One-time bootstrap (wrapper not yet generated, use the absolute skill path):
~/.claude/skills/ait/bin/ait init

# 2. From now on, run from your project root via the generated wrapper:
project-docs/.ait/ait-cli --version
project-docs/.ait/ait-cli prd create "需求标题"
```

If you reinstall the skill or move it on disk, run `~/.claude/skills/ait/bin/ait init --refresh-wrapper` to regenerate `project-docs/.ait/ait-cli` and refresh `.meta/config.yaml`. Claude Code invokes the wrapper transparently when a user types `/ait prd ...`. See [SKILL.md](SKILL.md) for the full command set.

## Uninstall

```bash
rm -rf ~/.claude/skills/ait
```

(Removes both the skill and its `.venv` — fully clean.)
