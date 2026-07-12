---
name: ait
description: INVOKE THIS SKILL when the user types /ait followed by a subcommand. AIT 是 chunk 级文档版本控制系统，主线为新模型 prd→fsd→tdd→codegen 的 spec→code 流水线（旧模型 prdv1→impl→task 为 legacy），并路由到 sub-skills。命令含 init/prd/fsd/tdd/codegen/version/specgraph/state/search/context/reindex 与 legacy prdv1/impl/task。
---

# AIT — AI-Assisted Document Versioning

AIT (`/ait <subcommand>`) 是面向 AI 协作设计文档的 **chunk 级版本控制**系统。**主线模型**：`prd → fsd → tdd → codegen → code`——PRD 递归分解为 FSD 功能树，叶 FSD `details` 到 TDD（每个 TDD 唯一映射一个 `target_file`，可指向任意生成目标：源码/测试/SKILL.md 等），`codegen` 沿 specgraph 上溯组装聚焦上下文驱动 AI 编码。**legacy 模型** `prdv1 → impl → task → code` 仍可用但属遗留。主 skill 负责路由、全局契约与命令速查；具体讨论/面板/恢复由 `sub-skills/` 承担。

## Global Contract

- **入口命令**：项目根下统一用 `project-docs/.ait/ait-cli <subcmd>`（`init` 自动生成的项目本地 wrapper）；唯一例外是 `init` 自身——首次用 `~/.claude/skills/ait/bin/ait init`，路径变更后用 `... init --refresh-wrapper`。不要假设系统存在全局 `ait`。
- **运行目录**：必须从包含 `project-docs/` 的项目根运行；不要从 `project-docs/` 内部运行。
- **写入规则**：不要直接写 `project-docs/{docs,versions,.meta}/*`，所有持久化必须经 `project-docs/.ait/ait-cli`。
- **输出契约**：所有 CLI stdout 是单个 JSON：`{"ok": true, "data": {...}}` 或 `{"ok": false, "error": "...", "code": "..."}`。
- **术语约束**：用 `chunk` 表示 `<!-- @id:xxx -->` 标注的文档单元；不要恢复 `block`。

## 版本原子性（核心心智模型）

- **create 显式开版本**：`version create <v>` 建版本工作区（已存在则报错，杜绝幽灵版本）；**迭代入口也可直接 `prd create`——无活动版本时自动开下一版本（阶段机起点 phase→prd-creating）**。
- **commit 即锁定**：`version commit <v>` 把新模型 chunk working→committed 锁定；legacy `prdv1 commit`/`impl commit` 锁对应文档。锁定后本版本不可改。**层级冻结：`prd confirm` 锁 PRD 层（phase→prd-confirm），`prd revert` 成对返工解锁（phase→prd-creating）——每道门禁配返工。**
- **confirm＝纯门禁**：`version confirm <v>` 只做校验报告（task 全 done + 六不变式：PRD↔1FSD、TDD↔1FSD/1制品、制品↔1TDD、无孤儿、可追溯、树关系无环），**可重复跑、零落盘、不合入**。
- **merge＝唯一落盘点**：`version merge <v>` 原子合入基线（内部先过同一门禁）+ 一次 git commit，失败字节级回退（docs 与 .meta 同步还原）。
- **revert＝任意阶段退出**：不满意用 `version revert <vX.Y> --confirm` 整版清空（物理删除，未合入版本可用；无局部撤销）。merged 版本不可 revert。

## Pipeline（主线：新模型）

```text
/ait init --new-model --name <proj>   → 生成 docs/{prd,fsd,tdd} + [PRD]/[FSD] 根 + decomposes 边
/ait prd create <[PRD]-id> ...         → 新模型 PRD（无活动版本自动开版本；可 --action modify --overrides）
/ait prd confirm|revert                → PRD 层冻结 / 成对返工（phase 阶段机）
/ait fsd create <[FSD]-id> ...         → FSD 功能分解（根/内部 split；split 内 ```yaml depends_on: [兄弟]``` 声明依赖，随文件全量对账——文件＝兄弟依赖边的所有权边界）
/ait fsd decompose <parent> <child>   → 拆分即建边（原子写子 FSD + decomposes 边，取代 link）
/ait fsd confirm|revert               → FSD 层冻结 / 成对返工（phase fsd-*）
/ait tdd create <[TDD]-id> --parent <fsd_split> → 叶子 TDD（必含 target_file；--parent 原子建 details 边，创建即建边）
/ait tdd confirm|revert                → TDD 层冻结 / 成对返工（phase tdd-*）
/ait specgraph validate-new-model      → 图合法性 + target_file 唯一性（重复报 DUPLICATE_TARGET_FILE）
/ait version create <v>                → 显式开版本（已存在报错）
/ait version commit <v>                → 全部 working chunk → committed（锁定）
/ait version confirm <v>               → 纯门禁：六不变式+task 校验报告（可重复，不落盘）
/ait version merge <v>                 → 原子合入基线 + git commit（门禁前置，失败回退）
/ait version revert <v> --confirm      → 任意阶段整版退出（未合入）
/ait codegen prepare <[TDD]-id>        → 上溯 FSD/PRD + 旁取依赖 + target_file，输出聚焦上下文驱动编码
/ait acceptance set "<cmd>"            → 配置制品验收命令（写 config.yaml；未配则验收跳过）
/ait acceptance run                   → 跑验收命令回显 passed（version confirm/merge 前置自动跑）
```

> 关系三种：`decomposes`(PRD/FSD→FSD)、`details`(叶 FSD→TDD)、`depends_on`(同父兄弟 split)。
> ID：`[PRD]/[FSD]/[TDD]` 前缀、名内 `_`、层级 `-`、内部 split 用 `<父根id>:<split名>`。

### legacy Pipeline（旧模型，遗留）

```text
/ait prdv1 create "<title>"   → 四段结构 PRD（req 草稿）→ confirm → commit 锁定
/ait impl create <prd-chunk>  → 1 PRD→N impl（可 @extract）→ commit（pre-merge）锁定
/ait task create/execute/complete → 派生 task、聚焦上下文、回写 code_refs → version confirm
```

## Project Layout

```text
<cwd>/project-docs/
├── docs/{prd,fsd,tdd}/        # 新模型基线（confirm 合入）；legacy: docs/{impl,global}/
├── versions/{vX.Y}/{prd,fsd,tdd,impl,tasks}/ + state.md
└── .meta/  chunks-index[-vX.Y].yaml（块状态）· specgraph[-vX.Y].yaml（块关系）·
           versions/{vX.Y}.yaml · changes/chg-NNN.yaml · requirements/req-NNN.yaml
```

> chunks-index 管「块自身状态」，specgraph 管「块之间关系」；均 baseline + per-version 分文件。`links-index.yaml` 已废弃。

## Command Quick Reference

| User trigger | CLI | Routed skill |
|---|---|---|
| `/ait init [--new-model --name]` | `~/.claude/skills/ait/bin/ait init`（首次） | `ait-init-guide` |
| `/ait prd create\|confirm\|revert ...` | `project-docs/.ait/ait-cli prd ...`（新模型 PRD；create 自动开版本；link 已退役） | main |
| `/ait fsd create\|decompose\|confirm\|revert ...` | `project-docs/.ait/ait-cli fsd ...`（decompose=拆分即建边；link 退役） | main |
| `/ait tdd create\|confirm\|revert ...` | `project-docs/.ait/ait-cli tdd ...`（create --parent=创建即建 details 边） | main |
| `/ait codegen prepare <[TDD]-id>` | `project-docs/.ait/ait-cli codegen prepare ...` → 驱动 AI 编码 | main |
| `/ait specgraph validate-new-model` | `project-docs/.ait/ait-cli specgraph validate-new-model` | main |
| `/ait version create\|commit\|confirm\|merge\|revert\|status <v>` | `project-docs/.ait/ait-cli version ...` | `ait-resume`（revert/错误） |
| `/ait state [--version v]` | `project-docs/.ait/ait-cli state ...` | `ait-state` |
| `/ait search\|context\|specgraph\|deps\|impact ...` | `project-docs/.ait/ait-cli ...` | main |
| **legacy** `/ait prdv1 <title>` | `project-docs/.ait/ait-cli prdv1 create/save-draft/confirm/commit` | `ait-discuss` |
| **legacy** `/ait impl <prd-chunk>` | `project-docs/.ait/ait-cli impl create/commit` | `ait-impl-discuss` |
| **legacy** `/ait task create\|execute\|complete` | `project-docs/.ait/ait-cli task ...` | `ait-task-execute` |
| CLI error recovery | inspect `code` / `error` | `ait-resume` |

## codegen 的职责边界（重要）

`codegen prepare` **不写代码**。它解析 TDD 根 chunk 的 `target_file`，沿 specgraph 上溯父 FSD split→FSD 根→PRD、旁取 `depends_on` 兄弟契约，输出 token 聚焦的 context bundle（无活动版本时回退 baseline 解析）。Skill 层据此驱动 AI 编码。legacy `task execute` 同理输出 `impl_refs ∪ global_refs` bundle，完成调 `task complete/fail` 收口（无 task confirm）。

## Sub-skills 索引

| Sub-skill | Trigger | Purpose |
|---|---|---|
| `ait-state` | 查看/刷新 `state.md`、版本进度、chunk 三态、task 状态 | 调 `state [--save]` 渲染面板，兼进度查询。 |
| `ait-resume` | CLI 返回错误或要求恢复中断流程 | 据 JSON `code` 给恢复步骤（含 version revert）。 |
| `ait-init-guide` | `/ait init` 进入差异补全模式 | 逐项确认 global 文件是否补齐。 |
| `ait-discuss` (legacy) | `/ait prdv1 <title>` 创建/讨论 legacy PRD | Clarify → Design → Generate，CLI 存草稿/确认。 |
| `ait-impl-discuss` (legacy) | `/ait impl <prd-chunk-id>` 规划/生成 impl | 读上下文、生成 impl chunk（含 @extract）、注册。 |
| `ait-task-execute` (legacy) | `/ait task execute` 驱动 AI 编码 | 据聚焦 bundle 编码，完成调 task complete/fail。 |

## Required Knowledge

- **新模型格式权威源**：`references/new-model-format.md` —— PRD/FSD/TDD 的 ID 格式、三关系及合法性、target_file 唯一性、章节结构、`validate-new-model` 校验项与错误码、modify/add 合并语义。**任意项目使用 AIT 时以此为准。**
- **文档模板**（章节骨架，随 skill 分发）：`templates/TEMPLATE-{PRD,FSD,TDD}-AIT-DRAFT.md`。
- 其余参考（`references/`）：`chunk-system.md`（@id/@ref/@extract）·`chunk-parser.md`（解析边界）·`index-system.md`（index/specgraph 语义）·`version-manager.md`（三态/gate/merge/revert）·`merge-engine.md`（按存在性逐 chunk merge，绝不丢 chunk）·`overview.md`（设计边界）。

## Common Pitfalls

| Code / symptom | Likely cause | Recovery |
|---|---|---|
| `DUPLICATE_TARGET_FILE` | 两个 TDD 声明同一 `target_file` | 改为各自唯一文件（目标2：不撞同一文件）。 |
| `TDD_TARGET_FILE_REQUIRED` | TDD 缺 `target_file` | TDD 必须含 `target_file`。 |
| 新模型图非法（FSD_MIXED_CHILDREN / DEPENDS_ON_*） | FSD 混 FSD/TDD 子、depends_on 跨级 | 见 `validate-new-model` 违规说明修正。 |
| `MERGE_NO_COMMITTED` / `no metadata` | 新模型版本未 `version commit` / 未经 CLI 建版本 | 先 `version commit <v>`；版本 meta 由新模型 create 自动建。 |
| `LOCKED` | 改已 commit 的 chunk | 锁定后不可改；用 `version revert <v> --confirm`。 |
| `ID_FORMAT` | chunk ID 非法字符 | 新模型用 `[PRD]/[FSD]/[TDD]` 前缀；legacy 用 `{type}-{domain}-{name}` 小写短横线。 |
| `INVARIANT_VIOLATION` | 六不变式违例（孤儿/断链/多属主/多父/幽灵端点/树环） | 按 violations 明细补规格（PRD/边/target_file），confirm 复查后再 merge。 |
| `GIT_DIRTY` | merge 时 git 不干净 | 先提交/暂存，或 `--allow-dirty-git`。 |
| `MERGE_ROLLBACK` | merge 中途失败 | docs/ 与 .meta 已字节级回退；查 error 修复后重试。 |
| `NOT_AT_PROJECT_ROOT` / `CWD_INSIDE_PROJECT_DOCS` | 运行目录不对 | 切到包含 `project-docs/` 的父目录。 |
| **legacy** `PRD_NOT_COMMITTED`/`PRD_NOT_LOCKED`/`NO_IMPL`/`TASK_NOT_DONE` | 旧流水线前置未满足 | 先 `prdv1 commit` / 补 impl / 跑完 task。 |

## Scope Boundaries

- AI 编码由 Skill 层驱动；CLI 只派生上下文、记录绑定，不直接生成业务代码。
- 不提供多用户协作锁；不提供系统级全局 `ait`；不支持 `/ait:foo` colon 命名空间（用 `/ait foo`）。
- 不绕过 CLI 直接改 AIT 管理文档或 `.meta`。
- 新模型关系不从命名推断，三种关系全部随内容创建原子出生：depends_on 随 `fsd create` 的 split 内 yaml 声明、decomposes 随 `fsd decompose`、details 随 `tdd create --parent`；无任何 link/depend 命令；每个 TDD 唯一映射一个 `target_file`。fsd/tdd create 对不存在的版本报 VERSION_NOT_FOUND。
- legacy：动态 global（ddl/schema/api）只来自 impl 的 `@extract`，不接受人工直接编辑。
