<!-- @id:prd-project-docs-only-overview -->
## 概述

**背景**：当前 AIT CLI 在任意 CWD 下都会启动——如果该目录已具备 `docs/` + `.meta/` 布局就直接接管，否则按提示 scaffold 出一份新的。这导致两类风险：

1. **目录歧义**：同一仓库里可以存在多份 AIT-managed 目录（如本仓库的 `project-demo/` 与 `project-docs/`），CLI 是否"对该项目生效"完全取决于 CWD，使用者难以一眼判断当前命令作用于哪一份元数据。
2. **误 scaffold**：在错误的目录下执行 `/ait prd` 之类的命令会无声地 scaffold 出一份空的 AIT 项目，污染目录结构。

**目标**：把 AIT 的"项目根"语义收紧到唯一约定——`<CWD>/project-docs/`，并在不满足时立即拒绝执行，不再 scaffold、不再自动推断。

**非范围声明**：本需求只调整 root 解析行为，不改变 PRD/impl/版本/合并等业务规则。已有的 `project-demo/` 不在治理范围内（仅作样例保留）。

<!-- @id:prd-project-docs-only-rules -->
## 业务规则

| 编号 | 规则 |
|---|---|
| R1 | 唯一合法的 AIT 工作根 = `<CWD>/project-docs/`（CWD 的直接子目录，名称严格匹配） |
| R2 | 目录名 `project-docs` **硬编**，不读取任何配置项、环境变量、CLI flag 来改名 |
| R3 | 不向上递归查找项目根 marker（`.git`、`pyproject.toml`、`.ait-root` 等一概不参与判定） |
| R4 | 不提供 `--root` / `-C` / `AIT_ROOT` 之类的覆盖入口 |
| R5 | `project-docs/` 内必须同时存在 `docs/` 和 `.meta/` 子目录才被视为合法工作根 |
| R6 | 一次命令执行内 root 解析结果**锁定**：命令运行期间不重新探测、不切换 |

<!-- @id:prd-project-docs-only-detection -->
## 目录定位

**触发时机**：所有 `bin/ait` 子命令（`prd`、`impl`、`version`、`reindex`、`context`）在解析子命令参数之前、加载任何元数据之前，先调用统一的 root 解析逻辑。

**算法**：

```
1. cwd ← os.getcwd()
2. candidate ← cwd / "project-docs"
3. 若 candidate 不是已存在的目录 → 抛 NOT_AT_PROJECT_ROOT（见错误场景 E1）
4. 若 (candidate / "docs") 或 (candidate / ".meta") 不是已存在的目录 → 抛 PROJECT_DOCS_MALFORMED（E2）
5. 若 cwd 本身位于 candidate 内部（即 cwd == candidate 或 cwd 是 candidate 的后代）→ 抛 CWD_INSIDE_PROJECT_DOCS（E3）
6. 否则 root ← candidate，写入命令上下文，后续路径解析全部基于 root
```

**不变量**：

- 解析完成后，CLI 内部不再使用 `os.getcwd()`，全部以解析得到的 root 为基准。
- 同一进程生命周期内 root 不变。
- 任何相对路径（`docs/prd/...`、`.meta/blocks-index.yaml`、`versions/v1.0/...`）都相对 root 解析。

<!-- @id:prd-project-docs-only-errors -->
## 错误场景

所有错误遵循统一的 JSON 输出契约：`{"ok": false, "error": "<人类可读>", "code": "<机器码>"}`，并以 exit code 1 退出。

| 编号 | code | 触发条件 | 提示文案（中文） |
|---|---|---|---|
| E1 | `NOT_AT_PROJECT_ROOT` | CWD 下没有 `project-docs/` 子目录 | 当前目录不是 AIT 项目根。请 cd 到包含 `project-docs/` 子目录的项目根目录后重试。 |
| E2 | `PROJECT_DOCS_MALFORMED` | `project-docs/` 存在，但缺 `docs/` 或 `.meta/` | `project-docs/` 结构不完整：缺少 `docs/` 或 `.meta/`。请检查目录或重新初始化。 |
| E3 | `CWD_INSIDE_PROJECT_DOCS` | CWD 本身就是 `project-docs/` 或其后代 | 请退出 `project-docs/`，从其父目录（项目根）运行命令。 |

**辅助信息**：错误 JSON 的 `data` 字段允许携带诊断信息（如解析过的 CWD 绝对路径、缺失的子目录名），便于排障，但 `code` + `error` 两个字段是稳定 API。

<!-- @id:prd-project-docs-only-non-goals -->
## 非目标

明确**不做**的事项，避免范围蔓延：

- ❌ 不实现 `--root` / `-C` / `AIT_ROOT` 等任何覆盖入口
- ❌ 不支持自定义目录名（`docs/`、`site/`、`project_docs` 一律不接受）
- ❌ 不向上递归查找项目根 marker（`.git`、`pyproject.toml`、`.ait-root` 等不参与判定）
- ❌ 不为 `project-demo/` 提供兼容性 shim——它仅作演示样例保留，本需求生效后将不再被 CLI 视为合法工作根
- ❌ 不处理 multi-root 工作区场景（一个项目内放多套独立 AIT 元数据）
- ❌ 不引入 scaffold 行为变化以外的命令语义改动；仅在 root 解析失败时拒绝执行
