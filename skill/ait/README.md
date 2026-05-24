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

No system-wide pip install needed. The first time `bin/ait` is invoked it creates an isolated `.venv` inside the skill directory and installs the bundled package + deps into it. Subsequent runs reuse the venv.

## Prerequisites

- Python ≥ 3.10 available as `python` or `python3` on PATH
- Internet access for the **first** invocation (pip fetches PyYAML / pydantic / click)
- ~30 MB disk for the per-skill venv

After the first install, the skill works offline.

## Usage

`bin/ait` is the entry point. Anything Claude does goes through it:

```bash
~/.claude/skills/ait/bin/ait --version
~/.claude/skills/ait/bin/ait prd create "需求标题"
```

Claude Code invokes this transparently when a user types `/ait prd ...`. See [SKILL.md](SKILL.md) for the command set.

## Uninstall

```bash
rm -rf ~/.claude/skills/ait
```

(Removes both the skill and its `.venv` — fully clean.)
