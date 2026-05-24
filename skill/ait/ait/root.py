"""Project root resolution for AIT.

实现 PRD `prd-project-docs-only-*`：AIT 的唯一合法工作根 = `<CWD>/project-docs/`。

**本模块刻意不接受任何形式的覆盖配置**：

- 不读 `--root` / `-C` / `AIT_ROOT` 等命令行/环境变量
- 不向上递归查找 marker 文件（.git / pyproject.toml / .ait-root）
- 目录名 `project-docs` 硬编，不可由配置改名

如需调整，请先修订 PRD `prd-project-docs-only-non-goals`，再动这里的代码。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DOCS_DIR_NAME = "project-docs"


class RootResolutionError(Exception):
    """Base for project root resolution failures (E1/E2/E3 per PRD `prd-project-docs-only-errors`)."""

    code: str = "ROOT_RESOLUTION_ERROR"

    def __init__(self, message: str, **data) -> None:
        super().__init__(message)
        self.data = data


class NotAtProjectRoot(RootResolutionError):
    code = "NOT_AT_PROJECT_ROOT"

    def __init__(self, cwd: str, expected: str) -> None:
        super().__init__(
            "当前目录不是 AIT 项目根。请 cd 到包含 `project-docs/` 子目录的项目根目录后重试。",
            cwd=cwd,
            expected_path=expected,
        )


class ProjectDocsMalformed(RootResolutionError):
    code = "PROJECT_DOCS_MALFORMED"

    def __init__(self, root: str, missing: list[str]) -> None:
        super().__init__(
            f"`project-docs/` 结构不完整：缺少 {', '.join(missing)}。请检查目录或重新初始化。",
            root=root,
            missing=list(missing),
        )


class CwdInsideProjectDocs(RootResolutionError):
    code = "CWD_INSIDE_PROJECT_DOCS"

    def __init__(self, cwd: str) -> None:
        super().__init__(
            "请退出 `project-docs/`，从其父目录（项目根）运行命令。",
            cwd=cwd,
        )


@dataclass(frozen=True)
class ProjectRoot:
    """Resolved project root. Immutable for the lifetime of one CLI invocation."""

    cwd: Path
    root: Path
    docs: Path
    meta: Path


def resolve_project_root() -> ProjectRoot:
    """Resolve `<CWD>/project-docs/` as the AIT project root.

    Raises:
        CwdInsideProjectDocs: CWD 本身位于 project-docs/ 内部（E3）
        NotAtProjectRoot: CWD 下不存在 project-docs/ 子目录（E1）
        ProjectDocsMalformed: project-docs/ 存在但缺 docs/ 或 .meta/（E2）
    """
    cwd = Path.cwd().resolve()

    if cwd.name == DOCS_DIR_NAME or DOCS_DIR_NAME in cwd.parts:
        raise CwdInsideProjectDocs(cwd=str(cwd))

    candidate = cwd / DOCS_DIR_NAME

    if not candidate.is_dir():
        raise NotAtProjectRoot(cwd=str(cwd), expected=str(candidate))

    docs = candidate / "docs"
    meta = candidate / ".meta"
    missing = [
        name for name, p in [("docs", docs), (".meta", meta)] if not p.is_dir()
    ]
    if missing:
        raise ProjectDocsMalformed(root=str(candidate), missing=missing)

    return ProjectRoot(cwd=cwd, root=candidate, docs=docs, meta=meta)
