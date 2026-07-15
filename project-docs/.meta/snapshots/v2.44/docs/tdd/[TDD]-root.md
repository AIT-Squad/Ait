<!-- @id:[TDD]-root -->
## root TDD

```yaml
target_file: skill/ait/ait/root.py
```

### 技术栈
Python 3.10+；`pathlib`、`dataclasses`。无第三方依赖。

### 实现约束
**不接受任何覆盖配置**：不读 `--root`/`-C`/`AIT_ROOT`，不向上递归找 marker（.git/pyproject），目录名 `project-docs` 硬编（常量 `DOCS_DIR_NAME`）。

### 代码结构
- `DOCS_DIR_NAME = "project-docs"`
- `RootResolutionError(Exception)`：`code="ROOT_RESOLUTION_ERROR"`；`__init__(message, **data)` 存 `self.data`。
- `NotAtProjectRoot`（code `NOT_AT_PROJECT_ROOT`，`(cwd, expected)`）
- `ProjectDocsMalformed`（code `PROJECT_DOCS_MALFORMED`，`(root, missing: list[str])`）
- `CwdInsideProjectDocs`（code `CWD_INSIDE_PROJECT_DOCS`，`(cwd)`）
- `@dataclass(frozen=True) ProjectRoot{cwd, root, docs, meta: Path}`
- `resolve_project_root() -> ProjectRoot`

### 核心逻辑 / 算法
`resolve_project_root`：`cwd=Path.cwd().resolve()`；若 `cwd.name==DOCS_DIR_NAME or DOCS_DIR_NAME in cwd.parts` → 抛 `CwdInsideProjectDocs`；`candidate=cwd/DOCS_DIR_NAME`，非目录 → `NotAtProjectRoot`；检查 `candidate/docs`、`candidate/.meta` 均为目录，缺者收集进 `missing` → `ProjectDocsMalformed`；否则返回 `ProjectRoot(cwd, candidate, docs, meta)`。

### 边界条件
project-docs 大小写敏感按 Path 语义；`in cwd.parts` 防止从子目录误判。

### 单元测试要求
`tests/test_root_resolution.py`：正常解析、E1/E2/E3 三类错误、从 project-docs 内部运行被拒。pytest，独立可跑。
