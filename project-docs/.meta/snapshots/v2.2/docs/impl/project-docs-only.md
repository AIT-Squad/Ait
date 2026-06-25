<!-- @id:impl-project-docs-only-root-resolver -->
## 项目根解析器（root-resolver）

把 PRD `prd-project-docs-only-{overview,rules,detection,errors,non-goals}` 全部落到一个新模块 `ait/cli/root.py` 上，配合 `ait/cli/errors.py` 的错误码扩展与一份测试文件即可完成。下分 5 个 H3 子节对应 PRD 的 5 个 block。

### 模块位置与接入点

- **新增模块**：`ait/cli/root.py`，封装解析、校验、锁定。
- **接入点**：所有 CLI 子命令（`prd` / `impl` / `version` / `reindex` / `context`）的入口装饰器在执行业务逻辑前调用 `resolve_project_root()` 一次；结果以不可变上下文对象注入到各业务模块，替代当前直接读取 `os.getcwd()` 的代码。
- **依赖**：仅标准库 `os` / `pathlib`，不引入新第三方包。
- **改造范围**：
  - `ait/cli/__init__.py` —— 改造命令入口装饰器，统一调用根解析
  - `ait/cli/errors.py` —— 注册 3 个新错误码
  - 所有 `ait/manager/*` 业务模块 —— 改为从注入的 root 上下文取路径

### 规则强制映射（R1–R6）

| 规则 | 强制方式 | 代码位置 |
|---|---|---|
| R1 唯一合法根 = CWD/project-docs/ | `resolve_project_root()` 内硬编路径拼接 | `ait/cli/root.py: resolve_project_root` |
| R2 目录名硬编 | 模块级常量 `DOCS_DIR_NAME = "project-docs"`，无对外 setter | `ait/cli/root.py: DOCS_DIR_NAME` |
| R3 不向上递归 | 只做一次拼接判断，不循环、不读 marker | 同上 |
| R4 无覆盖入口 | CLI 顶层不注册 `--root` / `-C` 选项；`AIT_ROOT` 不被读取 | `ait/cli/__init__.py` 参数表 |
| R5 必须含 docs/ + .meta/ | 锁定前 `is_dir()` 两个子目录 | `ait/cli/root.py` |
| R6 单次执行内锁定 | 解析结果存到 click `ctx.obj`，命令生命周期内只读 | `ait/cli/root.py: ProjectRoot` dataclass |

### `resolve_project_root` 算法

**公开 API**：

```python
from dataclasses import dataclass
from pathlib import Path

DOCS_DIR_NAME = "project-docs"

@dataclass(frozen=True)
class ProjectRoot:
    """Resolved project root. Immutable for the lifetime of one CLI invocation."""
    cwd: Path           # original CWD when CLI was invoked
    root: Path          # absolute path of <cwd>/project-docs/
    docs: Path          # root / "docs"
    meta: Path          # root / ".meta"

def resolve_project_root() -> ProjectRoot:
    """Resolve the AIT project root from os.getcwd(). Raises RootResolutionError on failure."""
```

**算法实现**：

```python
def resolve_project_root() -> ProjectRoot:
    cwd = Path.cwd().resolve()
    candidate = cwd / DOCS_DIR_NAME

    if cwd.name == DOCS_DIR_NAME or DOCS_DIR_NAME in cwd.parts:
        raise CwdInsideProjectDocs(cwd=str(cwd))

    if not candidate.is_dir():
        raise NotAtProjectRoot(cwd=str(cwd), expected=str(candidate))

    docs = candidate / "docs"
    meta = candidate / ".meta"
    missing = [name for name, p in [("docs", docs), (".meta", meta)] if not p.is_dir()]
    if missing:
        raise ProjectDocsMalformed(root=str(candidate), missing=missing)

    return ProjectRoot(cwd=cwd, root=candidate, docs=docs, meta=meta)
```

**接入装饰器**：

```python
# ait/cli/__init__.py
@click.group()
@click.pass_context
def cli(ctx):
    ctx.obj = resolve_project_root()   # 失败由顶层 click 错误处理器转 JSON
```

**关键不变量**：

- `cwd` 在 `resolve_project_root` 内部只读一次，写入 `ProjectRoot.cwd` 后冻结
- 所有业务 manager 的构造函数接受 `ProjectRoot` 参数，不再调用 `os.getcwd()`
- 同一进程多次调用 `resolve_project_root()` 必须返回值相等的对象（idempotent）

### 错误码扩展

扩展 `ait/cli/errors.py`，3 个新错误继承统一基类 `AitError`，由顶层 click 错误处理器转为 `{"ok": false, "error", "code", "data"}` 契约，exit code 1。

```python
class RootResolutionError(AitError):
    """Base for project root resolution failures (E1/E2/E3)."""

class NotAtProjectRoot(RootResolutionError):
    code = "NOT_AT_PROJECT_ROOT"
    message_template = "当前目录不是 AIT 项目根。请 cd 到包含 `project-docs/` 子目录的项目根目录后重试。"
    def __init__(self, cwd: str, expected: str):
        super().__init__(self.message_template)
        self.data = {"cwd": cwd, "expected_path": expected}

class ProjectDocsMalformed(RootResolutionError):
    code = "PROJECT_DOCS_MALFORMED"
    def __init__(self, root: str, missing: list[str]):
        super().__init__(f"`project-docs/` 结构不完整：缺少 {', '.join(missing)}。请检查目录或重新初始化。")
        self.data = {"root": root, "missing": missing}

class CwdInsideProjectDocs(RootResolutionError):
    code = "CWD_INSIDE_PROJECT_DOCS"
    message_template = "请退出 `project-docs/`，从其父目录（项目根）运行命令。"
    def __init__(self, cwd: str):
        super().__init__(self.message_template)
        self.data = {"cwd": cwd}
```

**JSON 输出示例**（E1）：

```json
{
  "ok": false,
  "error": "当前目录不是 AIT 项目根。请 cd 到包含 `project-docs/` 子目录的项目根目录后重试。",
  "code": "NOT_AT_PROJECT_ROOT",
  "data": {"cwd": "/Users/foo/random-dir", "expected_path": "/Users/foo/random-dir/project-docs"}
}
```

**测试矩阵**（最小覆盖，落到 `tests/cli/test_root_resolution.py`）：

| 场景 | 期望 code | exit code |
|---|---|---|
| CWD 下无 project-docs/ | `NOT_AT_PROJECT_ROOT` | 1 |
| project-docs/ 缺 docs/ | `PROJECT_DOCS_MALFORMED` | 1 |
| project-docs/ 缺 .meta/ | `PROJECT_DOCS_MALFORMED` | 1 |
| CWD 是 project-docs/ 本身 | `CWD_INSIDE_PROJECT_DOCS` | 1 |
| CWD 是 project-docs/ 后代 | `CWD_INSIDE_PROJECT_DOCS` | 1 |
| 完整合法布局 | （正常返回） | 0 |

### 非目标的实现约束

非目标不引入新模块，而是通过**测试断言**与**代码缺失证据**保证后续 PR 不"顺手"加回这些能力。

| 非目标 | 约束方式 |
|---|---|
| 不实现 `--root` / `-C` / `AIT_ROOT` | 测试：注入 `AIT_ROOT=...` 后 `resolve_project_root()` 行为不变；CLI 顶层 click 参数表不含 `--root` / `-C` |
| 不支持自定义目录名 | 测试：CWD 下放 `site/` / `docs/` 等非约定名目录而非 `project-docs/`，CLI 仍抛 `NOT_AT_PROJECT_ROOT` |
| 不向上递归 | 测试：CWD=`/foo/bar/baz/`，`/foo/project-docs/` 存在但 `/foo/bar/baz/project-docs/` 不存在，CLI 必须抛 `NOT_AT_PROJECT_ROOT` |
| 不为 project-demo/ 兼容 | 不做事——`project-demo/` 不在 CWD 直接子目录时自然走 E1 路径 |
| 不处理 multi-root | 实现上只读取一个 `<cwd>/project-docs/`；不引入"工作区"概念 |
| 不引入命令语义改动 | 现有所有 manager 模块仅改造构造函数接收 `ProjectRoot`，业务方法签名不变 |

**反向告警**：在 `ait/cli/root.py` 顶部加注释明确"本模块刻意不接受任何形式的覆盖配置"，劝阻未来 PR 加回这些能力。

<!-- @ref:prd/project-docs-only#prd-project-docs-only-detection rel:implements -->
