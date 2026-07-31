# AIT 用户使用文档

面向**使用者**的操作手册。设计原理见 [DESIGN.md](DESIGN.md)，格式规范权威源见
[skill/ait/references/new-model-format.md](skill/ait/references/new-model-format.md)。

## 目录

1. [快速开始](#1-快速开始)
2. [核心心智模型](#2-核心心智模型)
3. [项目初始化](#3-项目初始化)
4. [完整流水线](#4-完整流水线)
5. [PRD 层](#5-prd-层)
6. [FSD 层](#6-fsd-层)
7. [TDD 层](#7-tdd-层)
8. [codegen 与制品验收](#8-codegen-与制品验收)
9. [版本收口：commit / confirm / merge](#9-版本收口commit--confirm--merge)
10. [返工与回滚](#10-返工与回滚)
11. [查询与诊断命令](#11-查询与诊断命令)
12. [错误码与恢复](#12-错误码与恢复)
13. [Skill 与 sub-skills](#13-skill-与-sub-skills)
14. [legacy 流水线](#14-legacy-流水线)

---

## 1. 快速开始

### 1.1 安装

```bash
git clone <repo> && cd Ait
python install.py                      # 安装到 ~/.claude/skills/ait
python install.py update               # 升级（保留 .venv，快）
python install.py update --skip-venv   # 只更新文件
python install.py uninstall
python install.py --prefix /custom/path
```

首次运行 `bin/ait` 时会在 skill 目录内自建 `.venv` 并装依赖，无需手工处理。

### 1.2 两个入口，别混用

| 场景 | 入口 |
|---|---|
| 首次 `init`、路径变更后 `init --refresh-wrapper` | `~/.claude/skills/ait/bin/ait` |
| 其余**所有**命令 | `project-docs/.ait/ait-cli` |

`init` 会生成项目本地 wrapper `project-docs/.ait/ait-cli`（Windows 为 `ait-cli.cmd`），
它记住了 skill 路径。**不存在系统级全局 `ait` 命令**，不要假设 `ait` 在 PATH 里。

本文后续统一记作：

```bash
AIT="project-docs/.ait/ait-cli"
```

### 1.3 运行目录

必须在**包含 `project-docs/` 的目录**（项目根）下运行：

```bash
cd /path/to/my-project      # 这里有 project-docs/ 子目录
$AIT state
```

- 在 `project-docs/` 内部运行 → `CWD_INSIDE_PROJECT_DOCS`
- 当前目录没有 `project-docs/` → `NOT_AT_PROJECT_ROOT`（`init` 例外，它负责创建）
- `project-docs/` 存在但缺 `docs/` 或 `.meta/` → `PROJECT_DOCS_MALFORMED`

目录名 `project-docs` 硬编，没有 `--project`、没有 `AIT_ROOT`、不向上递归找 marker。

### 1.4 输出契约

所有命令 stdout 恒为**单个 JSON 对象**：

```json
{"ok": true,  "data": {...}}
{"ok": false, "error": "人类可读原因", "code": "STABLE_ERROR_CODE"}
```

提示信息一律走 stderr，不污染 stdout。写脚本时按 `code` 分支，不要解析 `error` 文本。

---

## 2. 核心心智模型

### 2.1 chunk 是最小单元

文档被 `<!-- @id:xxx -->` 切成 chunk。版本控制、关联、合并、锁定全部以 chunk 为单位，
不是以文件为单位。同一文件里的不同 chunk 可以处于不同状态。

### 2.2 文档正文零关系声明

PRD/FSD/TDD 的 markdown 正文**不写任何 chunk 间关系**。四种关系只存在于 SpecGraph，
由命令原子产生：

| 关系 | 含义 | 出生地 |
|---|---|---|
| `derives` | PRD 根 → 根 FSD（问题→方案） | `fsd create --parent <PRD根>` |
| `decomposes` | FSD split → 子 FSD 根（向下拆分） | `fsd decompose <parent> <child>` |
| `details` | 叶 FSD split → TDD 根（细化） | `tdd create --parent <split>` |
| `depends_on` | 同父兄弟 split 间依赖 | `fsd create` 内容里的 `depends_on:` yaml 块（建边后从磁盘剥离） |

没有 `link` 命令、没有 `depend` 命令。`target_file` 是 chunk→文件的属性（不是 chunk 间关系），
所以留在 TDD 正文。

### 2.3 一次只有一个开放版本

`version create` 是唯一开版本入口。已有未 merged 版本时报 `ACTIVE_VERSION_EXISTS`——
上一版必须先 merge 或 revert。版本名已存在也报错，杜绝"幽灵版本"。

### 2.4 三态锁定

chunk 在版本工作区经历 `working → staged → committed`：

- **working**：可反复改（同 id 就地替换）
- **committed**：本版本内冻结，再改报 `CHUNK_LOCKED`
- 层级 `confirm` 冻结该层，层级 `revert` 解锁返工

### 2.5 严格自顶向下（phase 状态机）

```
empty ──prd create──▶ prd-creating ──prd confirm──▶ prd-confirm
      ──fsd create/decompose──▶ fsd-creating ──fsd confirm──▶ fsd-confirm
      ──tdd create──▶ tdd-creating ──tdd confirm──▶ tdd-confirm
      ──version merge──▶ merged
```

每个写入口先校验 phase，不满足就拒绝且**零落盘**（可原地修正重试）。改任何一层都必须从
PRD 逐层往下走——`add` 与 `modify` 门禁完全相同，迭代也不例外。

### 2.6 confirm 与 merge 分离

- `version confirm` = **纯门禁**：跑六不变式 + 制品验收，持久化一份合并计划。可重复跑、
  零内容落盘、不合入。
- `version merge` = **唯一落盘点**：执行已确认的计划，失败字节级回退。

计划带输入指纹；confirm 之后版本内容再变，merge 会报 `CONFIRMATION_STALE`，要求重新 confirm。

### 2.7 docs 仓与代码仓隔离

`project-docs/` 是**独立 git 仓库**，被宿主仓 `.gitignore` 排除。AIT 的提交不碰你的代码历史。
`version merge` 记录跨仓绑定：`docs_commit`（docs 侧提交）、`code_base`（merge 时宿主 HEAD）、
`code_result`（验收后宿主 HEAD）、以及持久回滚锚 `refs/tags/ait/<v>`。

### 2.8 配置分层

| 层 | 文件 | 内容 | 是否入 git |
|---|---|---|---|
| 共享 | `.meta/config.yaml` | `initialized`、`auto_snapshot_on_merge` | 是（docs 仓） |
| 机器本地 | `.meta/config.local.yaml` | `skill_dir`、`cli_path`、`wrapper_path`、`acceptance_command` | 否（被 ignore） |

读取时合并两层、本地层优先。**某层存在但损坏时报 `CONFIG_UNREADABLE`，绝不降级成空配置**——
否则依赖配置的验收门禁会把"读不到"误判成"没配置"而放行。

---

## 3. 项目初始化

### 3.1 空目录起步

```bash
mkdir my-project && cd my-project
~/.claude/skills/ait/bin/ait init --new-model --name my_project
```

一条命令完成：

1. 创建 `project-docs/` 骨架（`docs/`、`.meta/versions/`、`.meta/changes/`）
2. `project-docs/` 内 `git init`；宿主根 `.gitignore` 追加 `project-docs/`；
   docs 仓 `.gitignore` 排除 `versions/*/state.md`、`.meta/snapshots/`、`.ait/`
3. 写入 `docs/prd/[PRD]-my_project.md` 与 `docs/fsd/[FSD]-my_project.md`
4. 在 SpecGraph 里建 PRD→FSD 的 `derives` 边
5. 落空 baseline 存储（`chunks-index.yaml`、`specgraph.yaml`）——初始＝现状为空的迭代
6. 生成 `project-docs/.ait/ait-cli` 并写入配置路径

`--name` 只接受小写字母数字下划线加短横分段（必须能构成合法 chunk id），
含大写/空格/中文/`/`/`..` 报 `INVALID_PROJECT_NAME`。已存在的用户文件永不覆盖（幂等）。

### 3.2 常用选项

| 选项 | 作用 |
|---|---|
| `--new-model --name N` | 新模型基线（PRD/FSD/TDD）——**推荐** |
| `--check` | 只诊断 `docs/global` 状态（fresh / incomplete / ready），不写文件 |
| `--refresh-wrapper` | 只刷新 skill 路径与本地 wrapper，不动文档 |
| `--skip a,b` | 增量模式下标记用户明确跳过的 global 项，避免反复追问 |
| `--migrate [--apply]` | docs 仓治理迁移：把历史被追踪的 `.meta/snapshots/`、`.ait/` 移出 git 索引，把机器特定配置搬到本地层。默认只预览 |

`--migrate` 单独给 `--apply` 会报 `USAGE_ERROR`；它是独立子模式，不执行常规初始化。

### 3.3 skill 路径变了怎么办

重装 skill 或换机器后：

```bash
~/.claude/skills/ait/bin/ait init --refresh-wrapper
```

wrapper 缺失或 `AIT_SKILL_DIR` 与配置漂移时，CLI 会在 stderr 给出 tip（不影响 JSON 输出）。

---

## 4. 完整流水线

```bash
AIT="project-docs/.ait/ait-cli"

$AIT version create v0.1                       # 开版本

$AIT prd create "[PRD]-app"                    # ① 无内容 → 取讨论背景 + context_token
#   ...与 AI 讨论收敛...
$AIT prd create "[PRD]-app" --action modify \
    --content-file prd.md --context-token ctx-v1.<digest>
$AIT prd confirm                               # 冻结 PRD 层

$AIT fsd create "[FSD]-app" --parent "[PRD]-app" \
    --content-file fsd.md --context-token ctx-v1.<digest>
$AIT fsd decompose "[FSD]-app:core" "[FSD]-core" \
    --content-file core.md --context-token ctx-v1.<digest>
$AIT fsd confirm                               # 冻结 FSD 层

$AIT tdd create "[TDD]-parser" --parent "[FSD]-core:parse" \
    --content-file tdd.md --context-token ctx-v1.<digest>
$AIT tdd confirm                               # 冻结 TDD 层

$AIT codegen prepare "[TDD]-parser"            # 取聚焦上下文 → AI 写代码

$AIT acceptance set "uv run pytest -q"         # 配置制品验收命令
$AIT version commit v0.1                       # working → committed
$AIT version confirm v0.1                      # 纯门禁 + 生成合并计划
$AIT version merge v0.1                        # 唯一落盘 + docs 仓提交
```

每层顺序固定：**讨论 → 写入 → 冻结**。跳层会被 phase 门禁拒绝。

---

## 5. PRD 层

### 5.1 先讨论，后写入

省略 `--content` / `--content-file` 时，命令**不写任何东西**，只返回讨论背景：

```bash
$AIT prd create "[PRD]-app"
```

返回 `mode: discussion-context`，含 baseline ∪ 当前版本的全部 PRD chunk 全文、目标 chunk 既有
内容，以及一个 `context_token`。空 baseline 返回空背景（初始迭代零分支）。

### 5.2 带 token 写入

```bash
$AIT prd create "[PRD]-app" --content-file prd.md \
    --action modify --context-token ctx-v1.<digest>
```

- `--action add`（默认）/ `--action modify`
- `--file <name>`：`prd/` 下的相对索引路径，不带 `.md`。越界（路径逃逸、跨 kind、带后缀）
  报 `INVALID_FILE_NAME`
- `--overrides`：改名/重定向映射；两条记录撞同一目标报 `DUPLICATE_OVERRIDES_TARGET`
- `--context-token`：必须与背景同一意图，否则 `CONTEXT_TOKEN_STALE` / `CONTEXT_TOKEN_CONFLICT`
- `--skip-context`：明确决定跳过讨论时使用，与 token 互斥，留审计痕迹

### 5.3 PRD 写什么

**零技术内容**。概述、范围（含 + **不含**）、用户角色、目标度量、风险，加上需求项
（用户故事 + 不做什么 + 用户级验收）。骨架见 `templates/TEMPLATE-PRD-AIT-DRAFT.md`。

### 5.4 冻结

```bash
$AIT prd confirm      # 锁 [PRD]- chunk，phase → prd-confirm，打 git 锚
$AIT prd revert       # 成对返工：解锁，phase → prd-creating
```

---

## 6. FSD 层

前置：phase 必须是 `prd-confirm` 或 `fsd-creating`，否则报 `PRD_NOT_CONFIRMED`。

### 6.1 从 PRD 派生根 FSD

```bash
$AIT fsd create "[FSD]-app" --parent "[PRD]-app" \
    --content-file fsd.md --context-token ctx-v1.<digest>
```

`--parent` 让 `derives` 边随创建原子出生。无 `--content` 时返回**发现式背景**：本版本被改动的
`[PRD]-` chunk 全文 + 每个锚点一跳关联的 chunk 全文。

### 6.2 向下拆分

```bash
$AIT fsd decompose "[FSD]-app:core" "[FSD]-core" \
    --content-file core.md --context-token ctx-v1.<digest>
```

原子完成"写子 FSD + 建 `decomposes` 边"。子 chunk 还不存在且未给内容时返回**锚定式背景**：
父块全文 + 全部邻接（含关系类型与方向）+ 上溯链到 PRD + 目标既有内容。

只有 FSD split 能做 `decompose` 的 parent；PRD 派生走 `fsd create --parent`
（用错报 `INVALID_DECOMPOSES_TYPES`）。

### 6.3 FSD 文件结构（递归同构）

每个 FSD 文件 = root + N 个功能 split + **恰 1 个 `:TEST`**：

- **root**：功能域职责边界（承接哪部分上游、负责/不负责）+ 分解视图（列子块结构，不列签名）
- **功能 split**：功能描述 + **能力契约（provide-only）**
- **`:TEST`**：本文件所有块合并的集成验收。`:TEST` 是唯一允许的大写 split 名，
  其余 split 名一律小写

**能力契约只写"本块对外提供什么"**：提供方式（HTTP 端点 / 模块函数 / CLI 命令 / 事件）、
接口（方法、参数名与类型、返回结构、错误语义）。

绝不写"需要/依赖什么"（那是 `depends_on` 关系，只在 SpecGraph）；绝不写函数内部实现（那是 TDD）。

### 6.4 声明兄弟依赖

在 split 正文里临时申报，`fsd create` 解析后建边并**从磁盘剥离**：

````markdown
<!-- @id:[FSD]-app:feat -->
## feat 模块
```yaml
depends_on: [store, config]
```
````

- 简写按同父解析（`store` → `[FSD]-app:store`）；完整 id 必须同父，跨父报
  `DEPENDS_ON_CROSS_LEVEL`
- 指向文件内不存在的兄弟报 `DEPENDS_ON_UNKNOWN_SIBLING`；指向自己报 `DEPENDS_ON_SELF`
- **preserve 语义**：不带 `depends_on` 块的 split **保留现有边**。改依赖＝带块 modify，
  清空＝显式 `depends_on: []`，不动＝不带块。所以重排正文不会误删依赖

一个 FSD 节点**不得混用** FSD 子（decomposes）与 TDD 子（details），报 `FSD_MIXED_CHILDREN`。

### 6.5 冻结

```bash
$AIT fsd confirm    # phase → fsd-confirm
$AIT fsd revert     # phase → fsd-creating
```

---

## 7. TDD 层

前置：phase 必须是 `fsd-confirm` 或 `tdd-creating`，否则报 `FSD_NOT_CONFIRMED`。

```bash
$AIT tdd create "[TDD]-parser" --parent "[FSD]-core:parse" \
    --content-file tdd.md --context-token ctx-v1.<digest>
$AIT tdd confirm
$AIT tdd revert
```

`--parent` 原子建 `details` 边，parent 必须是**叶子** FSD split。

### 7.1 target_file 是硬要求

每个 TDD 根 chunk 必须在 yaml 块里声明 `target_file`（缺失报 `TDD_TARGET_FILE_REQUIRED`）：

```markdown
<!-- @id:[TDD]-parser -->
## parser 技术设计
```yaml
target_file: src/parser.py
```
```

- **唯一性**：两个 TDD 不得声明同一个 `target_file`（报 `DUPLICATE_TARGET_FILE`），
  按归一化路径判重（分隔符、`./`、大小写变体视为同一制品）
- **可指任意生成目标**：源码、测试、模板、`SKILL.md`、脚本都行

### 7.2 TDD 写什么

`target_file`、技术栈约束、文件职责（负责 + **不负责**）、代码结构、核心实现逻辑、
错误边界、单元测试要求。一个 TDD 对应一个文件。

**FSD vs TDD 边界**：FSD 是黑盒对外接口（别人怎么调）；TDD 是白盒实现蓝图（这个文件内部怎么建）。

### 7.3 三条通用书写规约（PRD/FSD/TDD 都适用）

1. **详实自包含**：每块讲清自己，禁"参见 X"式甩锅
2. **反向要求必填**：每块明确"不实现什么/不负责什么（及归属）"
3. **术语就地展开**：总结性用语在使用处展开完整含义，不设集中术语表

---

## 8. codegen 与制品验收

### 8.1 取聚焦上下文

```bash
$AIT codegen prepare "[TDD]-parser"
```

返回 bundle：TDD 正文 chunks、沿 `details`/`decomposes`/`derives` 上溯到 PRD 的全链、
沿 `depends_on` 拉到的兄弟能力契约、`target_file` 及其**当前内容**（`target_file_content`）。

**`codegen prepare` 不写代码**——它只组装上下文，Skill 层据此驱动 AI 编码。

活动版本存在时要求 phase 为 `tdd-confirm`（否则 `TDD_NOT_CONFIRMED`）；无活动版本或版本已
merged 时按 baseline 解析、不设门禁。

### 8.2 制品验收

```bash
$AIT acceptance set "uv run pytest -q"   # 写入 .meta/config.local.yaml
$AIT acceptance set                      # 省略参数 = 清除
$AIT acceptance run                      # 手动跑一次，回显 passed
```

配置后，`version confirm` 与 `version merge` 在落盘前自动执行该命令（cwd = 项目根），
exit ≠ 0 → `ACCEPTANCE_FAILED`，拒于落盘前。未配置则跳过。

命令值存在机器本地层：它会被执行，且路径因机器而异，不该随共享历史传播。

---

## 9. 版本收口：commit / confirm / merge

### 9.1 commit — 锁定

```bash
$AIT version commit v0.1 -m "message"
```

把版本内全部 `working` chunk 一次性推到 `committed`。之后改动报 `CHUNK_LOCKED`。

### 9.2 confirm — 纯门禁 + 计划

```bash
$AIT version confirm v0.1 [--conflict-policy use-version|abort|use-baseline]
```

校验项：

1. legacy task 全部 `done`（无 task 时真空通过）
2. 重复 add / override 冲突
3. **六不变式**——在 `baseline ∪ version` 组合视图上全量校验
4. **制品验收**命令
5. 宿主仓干净（脏则 `HOST_DIRTY`——先提交你的代码）

通过则冻结一份**合并计划**（含所有规划输入的指纹）并返回；不通过返回违例明细，
`code` 为 `INVARIANT_VIOLATION` / `ACCEPTANCE_FAILED` / `TASK_NOT_DONE`。

可重复跑、零内容落盘、不合入。

### 9.3 merge — 唯一落盘

```bash
$AIT version merge v0.1
```

流程：校验计划仍有效（输入变了报 `CONFIRMATION_STALE`）→ 备份 → 执行计划逐块合入基线 →
重建 baseline 索引与 SpecGraph → 提升版本边到基线 → 写 merged 标记 → docs 仓 git 提交 →
记录 `docs_commit`/`code_base`/`code_result` 与回滚锚 tag。

任一步失败：**字节级回退**（docs 与 `.meta` 同步还原），报 `MERGE_ROLLBACK`，不残留 merged 标记。

### 9.4 合并语义（modify / add）

按每个 chunk 的**真实存在性**逐块处理：

- **modify = 整块全替换**：版本侧必须给出该 chunk 的完整最终内容（要保留的自带）
- **add = 仅新增** baseline 不存在的 chunk；命中已存在报 `DUPLICATE_BASELINE_CHUNK`
- modify 的目标不在 baseline → 自动当 add 追加。**merge 绝不静默丢 chunk**
- 前置拦截：modify 改名撞已存在 id → `MODIFY_RENAME_COLLISION`

### 9.5 git 提交三分语义

- 非 git 环境 / git 不可用 → 容忍，结果带 `git: "unavailable"`（不伪装成功）
- 无变更 → no-op，返回当前 HEAD
- 真实提交失败 → `GIT_COMMIT_FAILED`，进入回滚路径

---

## 10. 返工与回滚

### 10.1 层级返工

每层的 `confirm` 都配一个 `revert`——**每道门禁都有返工路径，没有终态陷阱**：

```bash
$AIT prd revert      # prd-confirm → prd-creating
$AIT fsd revert      # fsd-confirm → fsd-creating
$AIT tdd revert      # tdd-confirm → tdd-creating
```

解锁该层 chunk（committed → working）并回退 phase。merged 版本拒绝。

### 10.2 整版退出

```bash
$AIT version revert v0.1 --confirm
```

- **未合入版本**：物理清空版本工作区与索引（无局部撤销，这是原子版本模型的逃生口）
- **已合入版本**：把 docs 仓 `git reset --hard` 到该版本的锚点 tag，同时把宿主仓回滚到
  `code_result`，并删除其后的所有版本产物

不加 `--confirm` 返回 `NEED_CONFIRM` 与影响摘要（会删哪些版本），不执行。
锚点不可用报 `REVERT_PRECHECK_FAILED` / `REVERT_ANCHOR_INVALID`。

---

## 11. 查询与诊断命令

### 11.1 状态面板

```bash
$AIT state                        # 当前版本面板（markdown）
$AIT state --version v0.1
$AIT state --format json
$AIT state --save                 # 写入 versions/<v>/state.md
```

展示版本 phase、chunk 三态分布、PRD/FSD/TDD/impl 分类、下一步建议。

### 11.2 关系与影响

```bash
$AIT deps "[FSD]-app:core" --direction both|in|out
$AIT impact "[PRD]-app"                     # 传递影响闭包
$AIT specgraph query "[TDD]-parser" [--deps] [--implements]
$AIT specgraph export --format dot
$AIT specgraph graph-html [--version v0.1] [--prd-chunk "[PRD]-app:req1"]
$AIT specgraph sync
```

`graph-html` 生成文件级规格树：不带 `--version` 写 `docs/graph.html`，
带则写 `versions/<v>/graph.html`。

### 11.3 只读校验

```bash
$AIT specgraph validate-new-model [--version v0.1]
```

图合法性 + `target_file` 唯一性的只读诊断。**权威强制在 confirm/merge 门禁**，
这个命令只是提前发现问题。

### 11.4 检索与重建

```bash
$AIT search "关键词" [--scope prd|impl|all] [--regexp]
$AIT baseline-summary [--scope prd|impl|all] [--format yaml|json]
$AIT reindex                      # 扫 docs/ 重建 baseline 索引 + SpecGraph
$AIT context <chunk-id> [--scenario prd-to-impl|impl-edit] [--focus] [--deps]
$AIT lint [--scope baseline|version|v0.1] [--fix]
$AIT version status v0.1
```

`reindex` 会保留显式边（`source: new-model-cli`），不会因重扫而丢关系。

---

## 12. 错误码与恢复

### 12.1 运行环境

| Code | 原因 | 恢复 |
|---|---|---|
| `NOT_AT_PROJECT_ROOT` | 当前目录没有 `project-docs/` | cd 到项目根；新项目先 `init` |
| `CWD_INSIDE_PROJECT_DOCS` | 在 `project-docs/` 内部运行 | 退到父目录 |
| `PROJECT_DOCS_MALFORMED` | 缺 `docs/` 或 `.meta/` | 检查目录或重新 `init` |
| `USAGE_ERROR` | 命令/参数拼错 | 输出仍是 JSON，按 `error` 改命令 |
| `CONFIG_UNREADABLE` | 配置层存在但损坏 | 修复 `.meta/config*.yaml` YAML 语法 |

### 12.2 phase 门禁

| Code | 原因 | 恢复 |
|---|---|---|
| `NO_ACTIVE_VERSION` | 没有开放版本 | 先 `version create <v>` |
| `ACTIVE_VERSION_EXISTS` | 已有未 merged 版本 | 先 merge 或 revert 上一版 |
| `VERSION_NOT_FOUND` | 版本不存在 | `version create`（不自动创建） |
| `PRD_LAYER_CLOSED` | PRD 层已冻结还在 create | `prd revert` 重开 |
| `PRD_NOT_CONFIRMED` | 未 `prd confirm` 就写 FSD | 先 `prd confirm` |
| `FSD_NOT_CONFIRMED` | 未 `fsd confirm` 就写 TDD | 先 `fsd confirm` |
| `TDD_NOT_CONFIRMED` | 未 `tdd confirm` 就 codegen | 先 `tdd confirm` |

### 12.3 上下文令牌

| Code | 原因 | 恢复 |
|---|---|---|
| `CONTEXT_TOKEN_REQUIRED` | 有正文写入但没给 token | 先无内容调 create 取背景与 token |
| `CONTEXT_TOKEN_INVALID` | token 格式不对 | 用返回值原样传 |
| `CONTEXT_TOKEN_STALE` | 背景已变 | 重新取背景，重新讨论 |
| `CONTEXT_TOKEN_CONFLICT` | token 意图与本次调用不符 | 检查目标/父锚/file/action 是否改了 |
| `CONTEXT_SKIP_NOT_ALLOWED` | 无内容调用时给了 `--skip-context` | `--skip-context` 只用于有正文的写入 |

### 12.4 关系与不变式

| Code | 原因 | 恢复 |
|---|---|---|
| `DUPLICATE_TARGET_FILE` | 两个 TDD 抢同一文件 | 各自唯一文件 |
| `TDD_TARGET_FILE_REQUIRED` | TDD 缺 `target_file` | 补 yaml 声明 |
| `TDD_MULTI_PARENT` | TDD 有第二个 FSD 父 | 一个 TDD 只能有一个 details 入边 |
| `PRD_FSD_LINK_NOT_UNIQUE` | PRD 根关联了多个 FSD | 保留唯一 derives |
| `MISSING_ENDPOINT` | 边指向不存在的 chunk | 先创建端点 chunk |
| `FSD_MIXED_CHILDREN` | 一个 FSD 混了 FSD 子和 TDD 子 | 要么分解节点，要么叶子 |
| `DEPENDS_ON_CROSS_LEVEL` / `_UNKNOWN_SIBLING` / `_SELF` | 依赖申报越界 | 只能指同父兄弟 |
| `INVALID_DERIVES` / `INVALID_DECOMPOSES_TYPES` / `INVALID_DETAILS` | 关系端点类型不合法 | 见 §2.2 关系表 |
| `INVARIANT_VIOLATION` | confirm 六不变式违例 | 按 `details.violations` 补规格后复查 |
| `CHUNK_ID_PREFIX_REQUIRED` / `ID_FORMAT` | chunk id 不合规 | 用 `[PRD]`/`[FSD]`/`[TDD]` 前缀，名内 `_`、层级 `-` |

### 12.5 收口与落盘

| Code | 原因 | 恢复 |
|---|---|---|
| `CHUNK_LOCKED` | 改已 committed 的 chunk | 层级 `revert` 解锁，或整版 revert |
| `ACCEPTANCE_FAILED` | 验收命令返回非 0 | 修代码让测试转绿 |
| `HOST_DIRTY` | confirm 时宿主仓有未提交改动 | 先提交你的代码 |
| `CONFIRMATION_REQUIRED` | merge 前没 confirm | 先 `version confirm` |
| `CONFIRMATION_STALE` | confirm 后内容又变了 | 重新 `version confirm` |
| `MERGE_ROLLBACK` | merge 中途失败 | 已字节级回退，查 `error` 修复后重试 |
| `GIT_COMMIT_FAILED` | docs 仓提交失败 | 已回滚，修 git 状态后重试 |
| `DUPLICATE_BASELINE_CHUNK` | add 命中已存在 chunk | 改用 `--action modify` |
| `MODIFY_RENAME_COLLISION` / `DUPLICATE_OVERRIDES_TARGET` | 改名/override 撞车 | 零落盘，修 overrides 重试 |
| `INVALID_FILE_NAME` | `--file` 越界 | 只用本 kind 目录内的相对路径，不带 `.md` |
| `REVERT_PRECHECK_FAILED` / `REVERT_ANCHOR_INVALID` | 回滚锚不可用 | 检查 docs/宿主仓的 tag 与提交是否还在 |

---

## 13. Skill 与 sub-skills

在 Claude Code 里直接用 `/ait <subcommand>`（**不支持** `/ait:foo` 冒号命名空间）。
主 skill 负责路由、全局契约与命令速查，具体流程下沉到 sub-skills：

| Sub-skill | 触发 | 职责 |
|---|---|---|
| `ait-state` | 查看/刷新状态、版本进度 | 渲染状态面板，兼进度查询 |
| `ait-resume` | CLI 报错或要恢复中断流程 | 按 JSON `code` 给最短恢复路径 |
| `ait-init-guide` | `init` 返回 `status=incomplete` | 逐项确认 global 文件补齐 |
| `ait-discuss` (legacy) | `/ait prdv1 <title>` | Clarify → Design → Generate |
| `ait-impl-discuss` (legacy) | `/ait impl <prd-chunk>` | 生成 impl chunk |
| `ait-task-execute` (legacy) | `/ait task execute` | 驱动 AI 编码并收口 |

随 skill 分发的参考文档：`references/new-model-format.md`（**格式权威源**）、
`chunk-system.md`、`chunk-parser.md`、`index-system.md`、`version-manager.md`、
`merge-engine.md`、`overview.md`；模板在 `templates/`。

---

## 14. legacy 流水线

旧模型 `prdv1 → impl → task → code` 仍可运行但**已冻结，不再演进**。新项目请用主线模型。

```bash
$AIT prdv1 create "<title>"       # 四段结构 PRD
$AIT prdv1 save-draft <req-id> --content-file d.md
$AIT prdv1 confirm <req-id> --file <name>
$AIT prdv1 commit prd/<file> -m "msg" --req-id <req>

$AIT impl create <prd-chunk> --content-file impl.md --req-id <req>
$AIT impl commit <impl-chunk> -m "msg"
$AIT impl inherit | show | lock

$AIT task create <chunk-id>
$AIT task list | show | execute | complete | fail
```

常见 legacy 错误码：`PRD_NOT_COMMITTED`、`PRD_NOT_LOCKED`、`NO_IMPL`、`TASK_NOT_DONE`。

旧模型的 `docs/global/{ddl,schema,api}.md` 只能由 impl 的 `@extract` 生成，不接受人工编辑。
一次性迁移工具：`$AIT migrate-block-to-chunk`。
