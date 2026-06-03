# AIT 用户使用文档

> AI-Assisted Document Versioning — 面向 AI 协作文档的块级版本控制系统，提供完整的 `prd → impl → task → code` AI 开发流水线。

## 目录

- [1. 快速开始](#1-快速开始)
- [2. 核心心智模型](#2-核心心智模型)
- [3. 项目初始化（init）](#3-项目初始化init)
- [4. 完整流水线总览](#4-完整流水线总览)
- [5. PRD 管理流程](#5-prd-管理流程)
- [6. 实现规划流程（impl）](#6-实现规划流程impl)
- [7. 任务开发流程（task）](#7-任务开发流程task)
- [8. 版本合并与重置](#8-版本合并与重置)
- [9. 索引与关系查询](#9-索引与关系查询)
- [10. 常见问题](#10-常见问题)
- [附录：命令速查表](#附录命令速查表)

---

## 1. 快速开始

### 1.1 安装 AIT（作为 Claude Code Skill）

AIT 推荐以 Skill 形式安装到 `~/.claude/skills/ait/`：

```bash
git clone <repo-url> ait
cd ait
python install.py            # 全新安装
# 或 python install.py update  （已有安装时升级，保留 .venv）
```

安装后重启 Claude Code，进入任意带 `project-docs/` 子目录的项目，使用 `/ait <subcmd>` 触发。

> **macOS 提示**：若 venv 加载原生 wheel 报 `dlopen ... different Team IDs`，改用 Homebrew Python 重建 venv（`/opt/homebrew/bin/python3.13 -m venv ...`），不要用带 hardened runtime 的 Python。

### 1.2 CLI 入口（v1.5+ 双轨制）

AIT 的 CLI 有两个入口，**用途严格区分**：

| 入口 | 何时用 | 例子 |
|------|--------|------|
| `~/.claude/skills/ait/bin/ait` | 仅 `init`（项目本地 wrapper 尚未生成时）和 `init --refresh-wrapper`（skill 重装到新路径时刷新本地 wrapper） | `~/.claude/skills/ait/bin/ait init` |
| `project-docs/.ait/ait-cli` | `init` 之后所有命令都走这里（由 `init` 自动生成的项目本地薄壳，会读 `.meta/config.yaml#skill_path` 跳到正确的 skill 安装位置） | `project-docs/.ait/ait-cli prd commit prd/foo -m "..."` |

**绝对不要**在项目根用相对路径 `bin/ait`——项目根没有这个文件，shell 会报 `no such file or directory: bin/ait`。AIT 文档把这种情况标记为 `ENOENT_BIN_AIT`（仅作为 pitfall 标识，不是 CLI 真实错误码）。

### 1.3 验证安装

```bash
# 验证 skill 入口可用
~/.claude/skills/ait/bin/ait --help

# 项目执行 init 后验证本地 wrapper
project-docs/.ait/ait-cli --help
```

### 1.4 项目布局

AIT 管理的文档位于项目根目录下的 `project-docs/`：

```
<cwd>/                              ← 项目根目录（在此运行 ait，不要进 project-docs/）
└── project-docs/
    ├── .ait/                       ← init 自动生成：本项目的 CLI 薄壳 wrapper
    │   └── ait-cli                 ← v1.5+ 项目侧统一入口
    ├── docs/                       ← 基线，合并后的真实状态
    │   ├── prd/
    │   ├── impl/
    │   └── global/                 ← init 生成：overview/tech-stack(静态) + ddl/schema/api(动态)
    ├── versions/{vX.Y}/            ← 每个版本的增量工作区
    │   ├── prd/  ├── impl/
    │   ├── tasks/T-*.yaml          ← v1.5：task YAML 与版本同位
    │   └── state.md
    └── .meta/                      ← 机器可读索引
        ├── chunks-index.yaml        ← 基线块台账（状态视角）
        ├── chunks-index-{vX.Y}.yaml ← 版本块台账
        ├── specgraph.yaml           ← 基线关系图（关系视角，替代 links-index）
        ├── specgraph-{vX.Y}.yaml    ← 每版本关系图（分文件）
        ├── versions/{vX.Y}.yaml      ← 版本 meta（phase/锁定/title/tasks_summary）
        ├── requirements/req-NNN.yaml
        └── changes/chg-NNN.yaml
```

> **重要**：必须从包含 `project-docs/` 的**项目根目录**运行 AIT，不要在 `project-docs/` 内部运行。
>
> **v1.5 变更提示**：task YAML 已从 `.meta/tasks/{vX.Y}/T-*.yaml` 迁移到 `versions/{vX.Y}/tasks/T-*.yaml`，与服务的版本同位。`.meta/versions/{vX.Y}.yaml` 增加 `tasks_summary` 字段汇总所有 task 状态。若 CLI 输出告警 `legacy task path detected: project-docs/.meta/tasks`，说明该目录仍存在历史 task，按提示手动清理（v1.5 已合并版本不影响）。

---

## 2. 核心心智模型

理解三件事，就理解了 AIT 的全部行为：

### 2.1 版本是原子单元

- **commit 即锁定**：`prd commit` 锁定 PRD，`impl commit` 锁定 impl。锁定后本版本**不可再改**。
- **无局部撤销**：要反悔只能 `ait version reset <vX.Y> --confirm` —— 物理删除整个版本工作区，回到空白重来（不保留快照）。
- 一个版本要么完整走完 `version confirm` 合入基线，要么整版重置。没有"只改一块"。

### 2.2 三态提交

```
working ──stage──► staged ──commit──► committed ──confirm/merge──► baseline
```

| 状态 | 可改？ | 参与合并？ |
|------|--------|-----------|
| working | 是 | 否 |
| staged | 是（可退回 working） | 否 |
| committed | 否（锁定 PRD/impl） | 是 |

### 2.3 两个索引各管一摊

| | `chunks-index` | `specgraph` |
|---|---|---|
| 管什么 | 块**自身的状态**（state/action/commit_id） | 块**之间的关系**（implements/depends-on） |
| 回答 | "这块到哪一步了？" | "这块跟谁有关？" |
| 谁用 | `version status` / `commit` / `merge` | `task create` / `deps` / `impact` / pre-merge 校验 |

> `links-index.yaml` 已废弃，所有关系查询走 specgraph。

---

## 3. 项目初始化（init）

新项目第一步是 `init`，生成或补齐全局基线。**v1.5 起 `init` 不再强行拒绝已纳管的项目**：CLI 自动判别项目状态并采取相应动作。

```
/ait init
```

或 CLI（首次 init 时项目侧 wrapper 还没生成，必须用 skill 入口）：

```bash
~/.claude/skills/ait/bin/ait init
```

### 3.1 三种状态自动识别

| 状态 | 触发条件 | 行为 |
|------|----------|------|
| **fresh** | 没有 `project-docs/` 或 `.meta/config.yaml#initialized != true` | 创建完整 `docs/global/*`、写 `config.yaml`、生成 `project-docs/.ait/ait-cli` wrapper |
| **incomplete** | 已 `initialized` 但 `docs/global/{overview,tech-stack,ddl,schema,api}.md` 中至少缺一个，或 wrapper 缺失 | **只补缺失的文件**，绝不覆盖已有内容；进入 `ait-init-guide` 子 skill 引导 |
| **ready** | 一切齐全 | no-op，仅返回当前状态 |

所有判别逻辑在 CLI 中完成，子 skill 只负责差异补全的对话。

### 3.2 init 生成的内容

- `docs/global/overview.md` / `tech-stack.md`（**静态** global，人工维护）
- `docs/global/ddl.md` / `schema.md` / `api.md`（**动态** global 空骨架，内容后续由 impl 的 `@extract` 自动填充）
- `docs/prd/README.md` / `docs/impl/README.md`（说明占位，不入索引）
- 重建基线索引 + specgraph
- `.meta/config.yaml`（含 `initialized: true` + `skill_path` 指向当前 skill 安装路径）
- `project-docs/.ait/ait-cli`（项目本地 CLI 入口 wrapper）

### 3.3 常用选项

| 选项 | 作用 |
|------|------|
| `--check` | dry-run：只输出差异报告，不写文件 |
| `--skip <file>` | 在 incomplete 模式下跳过特定文件（可重复，例如 `--skip overview --skip tech-stack`） |
| `--refresh-wrapper` | 强制重写 `project-docs/.ait/ait-cli` 与 `config.yaml#skill_path`，用于 skill 重装到新路径后同步本地 wrapper |

> 历史变更：旧版（≤ v1.4）init 在已纳管项目上会返回 `ALREADY_MANAGED`；v1.5 已废弃此强限制，改为差异补全。

---

## 4. 完整流水线总览

```
ait init                       引导生成全局基线
        │
        ▼
ait prd create "<title>"       讨论 → 写 PRD（四段结构）
ait prd confirm  ─────────────▶ 写入版本工作区
ait prd commit   ─────────────▶ 锁定 PRD
        │
        ▼
ait impl create <prd-chunk>    设计实现（1 PRD chunk → N impl，可带 @extract）
ait impl commit  ─────────────▶ pre-merge 校验（环 + 版本内重复）→ 锁定 impl
        │
        ▼
ait task create <prd-chunk>    从 specgraph 派生 task YAML（impl_refs/global_refs/deps）
ait task execute <id>          输出聚焦 context bundle → AI 编码
ait task complete <id>         自动收口：标 done + 绑定 code_refs（无 task confirm）
        │
        ▼
ait version confirm <vX.Y>     预检(全 done + git 干净) → 合入基线
                               → 从 impl @extract 提取动态 global → git commit(msg=title)
```

---

## 5. PRD 管理流程

### 5.1 创建 PRD（三阶段讨论）

```
/ait prd "用户登录功能"
```

AI 驱动 Clarify（澄清）→ Design（设计块结构）→ Generate（生成正文），底层调：

```bash
ait prd create "用户登录功能"                          # 创建需求，自动建版本
ait prd save-draft req-001 --content-file /tmp/draft.md  # 保存草稿
ait prd confirm req-001 --file prd/user-management       # 写入版本工作区（同时刷新 state.md）
```

### 5.2 PRD chunk 的四段固定结构

PRD 块用固定结构，便于后续拆 task：

```markdown
<!-- @id:prd-user-login -->
## 用户登录

### 概述
一句话功能定位 + 用户价值。

### 业务规则
- 规则1：支持账号密码 + 手机验证码
- 规则2：连续 5 次失败锁定 10 分钟

### 验收标准
- [ ] 正确凭证可登录并持久化会话
- [ ] 失败锁定生效

### 边界与非目标
- 不做第三方 OAuth（留后续版本）
```

- **业务规则** 是拆 task 的依据，**验收标准** 是 task 完成的判定，**边界** 防止 AI 过度发挥。

### 5.3 查看 PRD

```bash
ait prd show user-management              # 文件大纲
ait prd show user-management prd-user-login  # 单个块
```

### 5.4 提交并锁定 PRD

```bash
ait prd commit prd/user-management -m "用户登录 PRD"
```

**关键**：`prd commit` 不只是提交，它**锁定整个版本的 PRD**。锁定后再试图改会返回 `LOCKED`。只有 committed 的 PRD 块才能被 impl 引用。

---

## 6. 实现规划流程（impl）

### 6.1 从 PRD 生成实现设计

```
/ait impl prd-user-login
```

一个 PRD chunk 可派生**多个** impl chunk（1:N）。底层：

```bash
ait context prd-user-login --scenario prd-to-impl   # 组装上下文
ait impl create prd-user-login --content-file /tmp/impl.md
```

`impl create` 会自动注入 `<!-- @ref:prd/...#prd-user-login rel:implements -->`。

### 6.2 @extract 标记：impl 作为动态 global 的数据源

impl 里可以用 `@extract` 标记一段可提取到动态 global（DDL/schema/api）的片段：

```markdown
<!-- @id:impl-user-login-ddl -->
## 用户表数据模型

软删除 + 唯一索引（纯文本说明，不提取）。

<!-- @extract:dynamic/ddl#user -->
```sql
CREATE TABLE user (id BIGINT PRIMARY KEY, phone VARCHAR(20) UNIQUE);
```
<!-- @extract-end -->

<!-- @ref:prd/user-management#prd-user-login rel:implements -->
```

- `@extract:dynamic/{type}#{chunk}` 中 `{type}` 路由到 `docs/global/{type}.md`，`{chunk}` 是写入的 chunk id。
- 这段会在 `version confirm` 时自动提取进动态 global。**动态 global 内容只来自 impl @extract，不要手工编辑。**

### 6.3 提交并锁定 impl（含 pre-merge 校验）

```bash
ait impl commit impl-user-login-ddl -m "用户表数据模型"
```

`impl commit` 会跑 **pre-merge 校验**（把版本图试合并进全局图），检测两类问题：

1. **依赖成环**：impl 间 `depends-on` 形成环 → 拒绝（task 拆分无法拓扑排序）
2. **版本内重复**：同 `@id` 多处定义，或两个 impl 抢同一个 `@extract` 目标 → 拒绝

有问题返回 `PREMERGE_FAILED`，修正设计后重新 commit。其引用的 PRD 块必须已 committed。

### 6.4 继承基线 impl（可选）

```bash
ait impl inherit prd-user-login
```

将基线中某 PRD chunk 对应的 impl 复制到当前版本工作区。适用于**增量版本**中复用已有实现设计的场景，避免从零重写。

### 6.5 锁定 impl（可选）

```bash
ait impl lock
```

显式锁定本版本的 impl（将版本 phase 推进到 `impl_locked`）。`impl commit` 是逐块提交的，锁定是一个独立的后续步骤，表示"本版本所有 impl 块已完备，可以开始拆 task"。

> 锁定后 `ait task create` 才能基于 specgraph 派生 task YAML。

---

## 7. 任务开发流程（task）

这是新设计的核心——把锁定的 PRD+impl 变成可执行的 AI 编码任务。

### 7.1 派生 task

```bash
ait task create prd-user-login
```

- 从 **specgraph** 查该 PRD chunk 的所有 impl（`impl_refs`），派生出 1~N 个 task YAML。
- task 命名 `T-{源chunk}-NN`（如 `T-user-login-01`），自带血缘。
- 不带参数 → 列出所有"已 committed 且有 impl 覆盖但还没拆 task"的 PRD chunk。

**前置**：PRD 必须已锁定（`PRD_NOT_LOCKED`）；该 PRD chunk 必须有 impl 覆盖（`NO_IMPL`）。

**task YAML 示例**（`versions/v1.1/tasks/T-user-login-01.yaml` —— v1.5 起 task YAML 与版本同位）：

```yaml
id: T-user-login-01
title: 实现 impl-user-login-ddl
source_chunk: prd-user-login       # 血缘
impl_refs: [impl-user-login-ddl]   # 该读的 impl
global_refs: [global-tech-stack]   # 该遵守的全局约束
depends_on: []                     # 上游 task（拓扑序）
order_hint: 1
steps:
  - 按 impl-user-login-ddl 的设计实现对应代码并自检
status: created                    # created | executing | done | failed
code_refs: []                      # done 时回写：[{commit, paths, bound_at}]
```

### 7.2 执行 task（AI 编码）

```bash
ait task execute T-user-login-01
```

**重要——execute 不直接写代码**。它做两件事：

1. 把 task 标记为 `executing`
2. 输出一个 **token 聚焦的 context bundle**：只含该 task 的 `impl_refs ∪ global_refs`，**不读全树**

Skill 层据此驱动 AI 编码。依赖未满足（`depends_on` 有非 done）会被跳过并提示 `blocked`。不带参数 → 处理所有 pending（created/failed）task，按依赖序。

### 7.3 收口 task（无 task confirm）

AI 写完代码后：

```bash
ait task complete T-user-login-01 --commit <git-hash> --path src/user/login.py
# 失败则：
ait task fail T-user-login-01
```

- `complete` = 标 `done` + 绑定 `code_refs`（git commit + 文件路径）。这就是 execute 的自动收口，**没有单独的 task confirm**。
- 人工审核统一挪到 `version confirm`。

### 7.4 查看 task

```bash
ait task list                  # 列出所有 task + 状态 + 依赖
ait task show T-user-login-01  # 查看完整 YAML
```

---

## 8. 版本合并与重置

### 8.1 version confirm（合入基线）

当版本所有 task 都 `done` 后：

```bash
ait version confirm v1.1
```

**两阶段 + 失败回退**，保证原子性：

1. **预检**：所有 task 必须 `done`（否则 `TASK_NOT_DONE`）；git 工作区必须干净（否则 `GIT_DIRTY`，可加 `--allow-dirty-git` 跳过）
2. **合并**：版本 PRD/impl 按 chunk 合入基线 `docs/`（同名 chunk 替换）→ 从 impl `@extract` 提取动态 global → 版本 specgraph 并入全局
3. **git commit**：message = 版本 title

任何一步失败，`docs/` 自动回退到合并前（`MERGE_ROLLBACK`），要么全成要么全不动。

### 8.2 version reset（唯一逃生口）

```bash
ait version reset v1.1 --confirm
```

物理删除该版本的工作区 + 索引 + `specgraph-v1.1.yaml` + tasks，回到空白重来。**不保留快照**。已 merged 的版本不可 reset。

> 这是版本原子性模型下"反悔"的唯一方式——没有局部撤销。

### 8.3 查看版本状态

```bash
ait version status v1.1        # working/staged/committed 计数
ait state --version v1.1       # 完整进度面板（title/phase/锁定/覆盖率/task 进度）
ait state --version v1.1 --save  # 写入 versions/v1.1/state.md
```

---

## 9. 索引与关系查询

```bash
# 重建基线索引 + specgraph（扫描 docs/）
ait reindex

# 关系查询（全部走 specgraph）
ait deps prd-user-login            # 出向依赖（implements/depends-on）
ait impact prd-user-login          # 反向影响面（改它会波及谁）
ait specgraph query prd-user-login --implements   # 谁实现了它

# 上下文与搜索
ait context prd-user-login --scenario prd-to-impl
ait search "登录"

# 格式校验（lint）
ait lint --scope baseline          # 校验基线 PRD/impl 格式
ait lint --scope v1.6 --fix      # 校验版本 v1.6 并尝试自动修复 PRD 缺失段落
ait lint --scope version          # 校验所有未合并版本

# 基线摘要（用于 prompt 预算评估）
ait baseline-summary --scope all --format json   # 导出所有基线块摘要
```

### 9.1 SpecGraph 管理

```bash
ait specgraph sync                                   # 从 docs/ 重建 specgraph
ait specgraph add-edge src dst --rel implements      # 手动添加边
ait specgraph query prd-user-login                  # 查询关系
ait specgraph export --format dot                   # 导出 Graphviz DOT
```

---

## 10. 常见问题

### 10.1 错误码速查

| 错误码 | 含义 | 恢复方法 |
|--------|------|---------|
| `NOT_AT_PROJECT_ROOT` | 当前目录无 `project-docs/` | 切到项目根目录 |
| `CWD_INSIDE_PROJECT_DOCS` | 当前目录在 `project-docs/` 内 | 退出到项目根目录 |
| `PROJECT_DOCS_MALFORMED` | `project-docs/` 缺 `docs/` 或 `.meta/` | 检查目录结构 |
| `LOCKED` | 试图改已 commit 的 PRD/impl | 用 `version reset` 整版重来 |
| `ID_FORMAT` | 块 ID 含大写/下划线/非法字符 | 改为 `{type}-{domain}-{name}` 小写短横线 |
| `PRD_NOT_COMMITTED` | impl 引用的 PRD 块未提交 | 先 `prd commit` |
| `PREMERGE_FAILED` | impl commit 检出环或版本内重复 | 修正 impl 设计后重新 commit |
| `PRD_NOT_LOCKED` | task create 时 PRD 未锁定 | 先 `prd commit` |
| `NO_IMPL` | task create 的 PRD chunk 无 impl 覆盖 | 先设计 impl |
| `BLOCKED` | task execute 依赖未 done | 先执行上游 task |
| `TASK_NOT_DONE` | version confirm 时有 task 非 done | 跑完/修复所有 task |
| `GIT_DIRTY` | version confirm 时 git 不干净 | 先提交/暂存，或加 `--allow-dirty-git` |
| `MERGE_ROLLBACK` | confirm 合并阶段失败 | docs/ 已回退，查 error 修复后重试 |
| `FORMAT_VIOLATION` | PRD/impl 格式校验失败 | 运行 `ait lint --fix` 自动修复 |

> **shell 级 pitfall（非 CLI 错误码）**：若看到 `zsh:1: no such file or directory: bin/ait`，说明你在用相对路径 `bin/ait` 调 CLI——项目根并不存在该文件。改用 `project-docs/.ait/ait-cli <subcmd>`；若该 wrapper 不存在，先跑 `~/.claude/skills/ait/bin/ait init --refresh-wrapper`。AIT 文档把这种情况标记为 `ENOENT_BIN_AIT`（仅作为 pitfall 标识，**不**在 `ait/schemas.py` 注册，也**不**进入 `ait-resume` 处理链路）。
>
> **v1.4→v1.5 兼容性提醒**：旧版会返回 `ALREADY_MANAGED` 拒绝在已纳管项目上 init，v1.5 已废弃此错误码并改为差异补全模式。

### 10.2 如何修改已锁定的 PRD/impl？

锁定后**不能局部修改**。版本是原子单元，唯一方式是 `ait version reset <vX.Y> --confirm` 整版重置，回到空白 PRD 重新设计。这是刻意的设计——它消除了"局部回滚/失效检测"的全部复杂度。

### 10.3 如何回滚？

- **未 merged 的版本**：`ait version reset <vX.Y> --confirm`（物理删除整版）。
- **已 merged 的版本**：不可 reset。已合入基线的内容由 Git 管理（`version confirm` 已产生 git commit），用 Git 回退。

### 10.4 动态 global（ddl/schema/api）能手工改吗？

不能。动态 global 内容 100% 来自 impl 的 `@extract`，在 `version confirm` 时提取。要改 schema/DDL/API，改对应的 impl `@extract` 块，再走 version confirm。静态 global（overview/tech-stack）才是人工维护的。

### 10.5 `/ait` 和 `ait` 的区别？

| 格式 | 场景 | 说明 |
|------|------|------|
| `/ait <subcommand>` | AI 对话中触发 | AI 解析并执行相应流程（含多步讨论），底层最终调用 `project-docs/.ait/ait-cli` |
| `project-docs/.ait/ait-cli <subcommand>` | 终端 CLI（项目内推荐） | v1.5 起项目侧统一入口；由 init 自动生成 |
| `~/.claude/skills/ait/bin/ait <subcommand>` | 终端 CLI（仅 init / refresh-wrapper） | skill 安装位置；wrapper 尚未生成时使用 |

> 文档其余部分为简洁起见会写 `ait <subcmd>`，请按上下文替换为对应的真实入口。

---

## 附录：命令速查表

### 生命周期

| 命令 | 作用 |
|------|------|
| `ait init` | 三态自动识别：fresh 引导 / incomplete 差异补全 / ready no-op；支持 `--check`、`--skip`、`--refresh-wrapper` |
| `ait reindex` | 重建基线索引 + specgraph |
| `ait state [--version v] [--save]` | 版本进度面板 |
| `ait lint [--scope ...] [--fix]` | PRD/impl 格式校验（可选自动修复） |
| `ait baseline-summary [--scope ...] [--format ...]` | 基线块摘要（用于 prompt 预算） |

### PRD

| 命令 | 作用 |
|------|------|
| `/ait prd <title>` | 创建 PRD（三阶段讨论） |
| `ait prd create <title>` | 创建需求，自动建版本 |
| `ait prd save-draft <req-id> --content-file <file>` | 保存草稿 |
| `ait prd resolve-candidates --from-file <yaml>` | 持久化 AI 生成的 PRD 候选决策 |
| `ait prd confirm <req-id> --file prd/<slug>` | 写入版本工作区 |
| `ait prd show <prd-file> [chunk-id]` | 查看 PRD |
| `ait prd commit <prd-file> -m <msg>` | 提交 + **锁定 PRD** |

### impl

| 命令 | 作用 |
|------|------|
| `/ait impl <prd-chunk-id>` | 从 PRD 生成实现设计 |
| `ait impl create <prd-chunk-id> --content-file <file>` | 创建 impl 块（自动注入 @ref） |
| `ait impl show <impl-chunk-id>` | 查看 impl 块 |
| `ait impl commit <impl-chunk-id> -m <msg>` | 提交（pre-merge 校验）+ 锁定 impl |
| `ait impl inherit <prd-chunk-id>` | 继承基线 impl 到当前版本（增量复用） |
| `ait impl lock` | 显式锁定本版本 impl（推进 phase） |

### task

| 命令 | 作用 |
|------|------|
| `ait task create [prd-chunk]` | 派生 task YAML（无参列待拆分 chunk） |
| `ait task list [--version v]` | 列出 task |
| `ait task show <task-id>` | 查看 task YAML |
| `ait task execute [task-id\|chunk]` | 标 executing + 输出聚焦上下文 |
| `ait task complete <task-id> [--commit h] [--path p]` | 标 done + 绑定 code_refs |
| `ait task fail <task-id>` | 标 failed（可重跑） |

### version

| 命令 | 作用 |
|------|------|
| `ait version status <v>` | 版本状态计数 |
| `ait version confirm <v> [--allow-dirty-git]` | 原子合入基线 + 提取动态 global + git commit |
| `ait version merge <v>` | 底层合并（confirm 内部调用） |
| `ait version reset <v> --confirm` | 整版重置（逃生口，物理删除） |

### 查询 / 图

| 命令 | 作用 |
|------|------|
| `ait deps <chunk-id>` | 出向依赖 |
| `ait impact <chunk-id>` | 反向影响面 |
| `ait specgraph sync` | 重建 specgraph |
| `ait specgraph add-edge <src> <dst> --rel <rel>` | 手动添加边 |
| `ait specgraph query <chunk-id> [--deps\|--implements]` | 关系查询 |
| `ait specgraph export [--format dot]` | 导出图谱 |
| `ait context <chunk-id> [--scenario ...]` | 组装 AI 上下文 |
| `ait search <query>` | 全文搜索 |
| `ait baseline-summary [--scope ...] [--format ...]` | 基线块摘要 |

### 校验 / 维护

| 命令 | 作用 |
|------|------|
| `ait lint [--scope ...] [--fix]` | 格式校验（PRD 四段结构 / impl @ref 完整性） |
| `ait reindex` | 重建基线索引 + specgraph |
| `ait migrate-block-to-chunk [--dry-run]` | v1.1→v1.2 一次性数据迁移（重命名 block→chunk） |

---

> 本文档对应 AIT 截至 v1.6 的状态（`prd-impl-task` 三态流水线 + skill/CLI 双轨入口 + task 同位 + init 增量化 + sub-skills 治理）。详细设计见 `project-docs/docs/prd/` 与 `project-docs/docs/impl/`。
>
> **本指南示例中的 `ait <subcmd>` 是简写**：在终端实际使用时，请按下表替换：
> - `init` 首次 / `init --refresh-wrapper` → `~/.claude/skills/ait/bin/ait <subcmd>`
> - 其余所有命令 → `project-docs/.ait/ait-cli <subcmd>`
