"""Publish both repositories — host artifacts and docs specs — to their remotes.

Per [TDD]-publisher: this is a *publish*, not a version transition. It creates
no commit, changes no chunk state and no version phase; it only pushes commits
that already exist.

Order is fixed host-then-docs: the docs repo's version metadata records the host
commit sha, so specs arriving at the remote before the artifact would reference
a commit that is not there. The reverse failure is merely "code published, specs
pending" and converges on a rerun.

Never rewrites remote history: no force/delete/mirror flags exist here, and the
only pushable refs are the current branch and `refs/tags/ait/*`. `publish()`
takes no branch/remote/refspec argument at all, so a caller cannot redirect it.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

# Artifact before spec. Not configurable — see the module docstring.
REPO_ORDER: tuple[str, ...] = ("host", "docs")

# Version anchor tags back the revert anchor of merged versions; without them a
# fresh clone loses those anchors. Scoped refspec: nothing else gets pushed.
ANCHOR_TAG_REFSPEC = "refs/tags/ait/*"

_MAX_COMMITS = 20
_MAX_STDERR = 500


@dataclass(frozen=True)
class RepoPublishResult:
    repo: str
    path: str
    branch: str | None = None
    upstream: str | None = None
    ahead: int = 0
    commits: list[str] = field(default_factory=list)
    outcome: str = "dry-run"
    dirty: bool = False
    error: str | None = None
    error_code: str | None = None


_OK_OUTCOMES = {"pushed", "nothing-to-push", "not-a-repo", "dry-run"}


class Publisher:
    def __init__(self, project_root: Path):
        # Host is derived from the docs root's parent: no config, no path input.
        self.docs = Path(project_root).resolve()
        self.host = self.docs.parent

    def _git(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        # Fixed argv list, never a shell. `args` only ever holds module
        # constants or values git itself produced.
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True
        )

    def _collect(self, name: str, repo: Path) -> RepoPublishResult:
        """Gather state without touching any remote."""
        base = RepoPublishResult(repo=name, path=str(repo))

        if not repo.exists() or self._git(repo, "rev-parse", "--git-dir").returncode != 0:
            return replace(base, outcome="not-a-repo")

        head = self._git(repo, "symbolic-ref", "--short", "HEAD")
        if head.returncode != 0:
            return replace(
                base,
                outcome="failed",
                error_code="PUSH_NO_UPSTREAM",
                error="detached HEAD: no branch to push",
            )
        branch = head.stdout.strip()

        if not self._git(repo, "remote").stdout.strip():
            return replace(
                base,
                branch=branch,
                outcome="failed",
                error_code="PUSH_NO_REMOTE",
                error="no git remote configured",
            )

        tracking = self._git(
            repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"
        )
        if tracking.returncode != 0:
            return replace(
                base,
                branch=branch,
                outcome="failed",
                error_code="PUSH_NO_UPSTREAM",
                error=f"branch {branch} has no upstream",
            )
        upstream = tracking.stdout.strip()

        dirty = bool(self._git(repo, "status", "--porcelain").stdout.strip())
        log = self._git(repo, "log", "--oneline", f"{upstream}..HEAD")
        commits = [line for line in log.stdout.splitlines() if line.strip()]

        return replace(
            base,
            branch=branch,
            upstream=upstream,
            ahead=len(commits),
            commits=commits[:_MAX_COMMITS],
            dirty=dirty,
            outcome="nothing-to-push" if not commits else "dry-run",
        )

    def _push(self, result: RepoPublishResult, repo: Path) -> RepoPublishResult:
        remote = (result.upstream or "").split("/", 1)[0]
        pushed = self._git(repo, "push", remote, result.branch)
        if pushed.returncode != 0:
            return replace(
                result,
                outcome="failed",
                error_code="PUSH_FAILED",
                error=(pushed.stderr or pushed.stdout).strip()[-_MAX_STDERR:],
            )

        if result.repo == "docs":
            tags = self._git(repo, "push", remote, ANCHOR_TAG_REFSPEC)
            if tags.returncode != 0:
                # The branch did reach the remote; report the tag problem
                # without lying about the push itself.
                return replace(
                    result,
                    outcome="pushed",
                    error="anchor tags not pushed: "
                    + (tags.stderr or tags.stdout).strip()[-_MAX_STDERR:],
                )
        return replace(result, outcome="pushed")

    def publish(self, dry_run: bool = False) -> dict:
        paths = {"host": self.host, "docs": self.docs}
        results = [self._collect(name, paths[name]) for name in REPO_ORDER]

        if not dry_run:
            blocked = False
            for index, result in enumerate(results):
                if blocked:
                    # Order precondition unmet: artifact must land before spec.
                    if result.outcome == "dry-run":
                        results[index] = replace(result, outcome="skipped")
                    continue
                if result.outcome == "dry-run":
                    results[index] = self._push(result, paths[result.repo])
                if results[index].outcome == "failed":
                    blocked = True

        return {
            "passed": all(item.outcome in _OK_OUTCOMES for item in results),
            "dry_run": dry_run,
            "repos": [asdict(item) for item in results],
        }
