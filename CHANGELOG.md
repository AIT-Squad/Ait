# Changelog

产品版本里程碑（v1.0、v2.0、…）记录功能范围；软件包版本见 [pyproject.toml](pyproject.toml)。

从 v2.0 起，AIT **完全由自身开发**：每个版本都走完整的
`version create → prd → fsd → tdd → codegen → confirm → merge` 闭环，chunk 级变更记录在
`project-docs/.meta/changes/`，版本元数据在 `project-docs/.meta/versions/`。本文件按主题聚合，
细节以那些记录为准。

---

## v2.86–v2.87 — 2026-08-06 — 版本可见性与写时拦截收口

- **v2.86 `ait --version` 动态化**：顶层 `--version` 从静态包版本改为显示当前项目的文档版本
  （承接 PRD 需求 `cli_version_reflects_docs`）——一眼确认当前迭代到哪个版本。
- **v2.87 `--content` 组装边界写时拦截**：`prd/fsd/tdd create` 在 `action=add` 且内容含
  baseline 已存在 chunk id 时，于任何写盘前报 `DUPLICATE_BASELINE_CHUNK`（零落盘可重试）——
  此前要到 merge 才被发现，此时 phase 已推进，只能整版 revert。同时明确 `--content` 只应包含
  根 chunk + 本次真正新增/变化的 chunk（正例 v2.81／反例 v2.86）。

## v2.83–v2.85 — 2026-08-04 — 受治理制品范围（artifact scopes）

- **v2.83 `artifact_scopes`**：`config.yaml` 新增治理配置——声明哪些制品范围（如测试文件）
  必须有 TDD 属主与验收覆盖。新增校验 `TEST_SPLIT_UNCOVERED`（`:TEST` split 无 details 子）、
  `UNCOVERED_ARTIFACT`（范围内制品无 TDD 属主）、`TARGET_FILE_SCOPE_ESCAPE`（target_file
  逃逸治理范围），每条可配 `warn`/`block`。违例新增 `enforcement` 字段，
  未配置时行为与之前完全一致。
- **v2.84 测试制品治理落地**：为既有测试文件批量补建属主 TDD（`tests/test_*.py` 全部纳入
  治理范围）。
- **v2.85 `exempt_paths`**：范围条目新增按归一化路径精确匹配的豁免清单。

## v2.80–v2.82 — 2026-08-03 — 交付形态、双仓发布与残留扫描

- **v2.80 codegen 交付形态改为渲染文本**：bundle 由 `codegen_brief.render` 产出 markdown
  （不再是 JSON——转义破坏可读性、字母序排键把 upstream 挤到源码之后）；临时文件扩展名
  `.json` → `.md`。`target_file` 状态三态化：`absent`（合法新文件）与 `unreadable`
  （存在但读不了）必须可区分，否则生成方会把既有代码当空白覆盖。
- **v2.81 `ait push` 双仓发布**：新顶层命令 `push`（`publisher` 模块）——先推宿主仓
  （代码制品），再推 docs 仓（规格 + `refs/tags/ait/*` 锚点 tag）。
- **v2.82 derives 声称一致性扫描 + 输出终止对称**：`validate-new-model` 新增
  `derives_residue` 字段（FSD 正文提及某 PRD 需求 id 但图上无对应 derives 边，报告不阻断）；
  `ok()` 末尾补 `sys.exit(0)`，与 `fail()` 对称，杜绝一条命令输出两段 JSON 的可能。

## v2.76–v2.79 — 2026-08-02 ~ 08-03 — 写作契约与演进纪律

- **v2.76 CLI 输出契约统一（G11）**：校验类命令统一为标准 `ok()`/`fail()` JSON 信封。
- **v2.77 PRD 需求契约写时门禁**：每个 `[PRD]-<root>:<slug>` 需求 chunk 必须含
  `**用户故事:**` 行与带编号条目的 `验收标准` 小节（EARS 形态），缺失报
  `PRD_REQUIREMENT_CONTRACT_VIOLATION`（零落盘）；`validate-new-model` 新增
  `prd_requirement_residue` 报告字段（只报告不阻断）。
- **v2.78 PRD 基线契约化**：把历史需求 chunk 全部补齐为用户故事 + EARS 验收标准形态，
  使基线自身通过 v2.77 门禁。
- **v2.79 需求演进纪律**：写入 SKILL.md 与格式规范——新诉求先看能否与既有需求 chunk
  共用同一句用户故事（角色+价值相同），能则 `modify` 加验收标准，不能才新增；
  拆分上限用可观察信号；取代关系须双向标注。

## v2.74–v2.75 — 2026-08-02 — codegen 交付通道与子 agent 编排

- **v2.74 bundle 临时文件交付（G19）**：`codegen prepare` 不再 stdout 直出全 bundle
  （大 bundle 会被工具输出上限静默截断）。改为写入仓外临时文件（绝不被 git 追踪），
  stdout 只回指针 `{bundle_path, sha256, bytes, version, target_file, tdd_root, source_file}`，
  `target_file` 置顶层。编排层读文件、按 sha256 校验完整性后才注入 LLM。
- **v2.75 子 agent 生成编排（G24）写入 SKILL.md**：生成由 Skill 层派生的隔离子 agent
  完成——其全新 context window 仅注入该 bundle；AIT 不派生 agent、不调 LLM，
  只管可靠交付与事后收口（`version confirm` 绑制品 + acceptance 跑测试）。

## v2.72–v2.73 — 2026-08-01 — 回滚锚点韧性与 confirm 制品绑定

- **v2.72 回滚锚点韧性（G10）**：tag 只是防 GC 的优化，**提交 SHA 才是权威锚点**——
  tag 不可解析时回退到版本 meta 记录的 `docs_commit`/`code_result` 继续回滚；
  merge 建 tag 失败不再阻断（merge 仍成功、版本仍可回滚）；新增 `version backfill-tags`
  为历史版本幂等补建缺失 tag。
- **v2.73 confirm 提交制品仓（G25）**：`version confirm` 门禁通过后、persist plan 前，
  若宿主仓脏则 `git add -A` + 提交为 `AIT <v> artifacts` 并绑定 `code_result`；
  干净则绑定当前 HEAD；非 git 仓跳过。**原 HOST_DIRTY「脏则拒」语义被取代——
  脏不再是拒绝的理由，而是提交的理由**，与 merged 版本双仓回滚互为对称。
  注意：confirm 因此不再是"零写入"——它持久化合并计划并可能产生宿主仓提交。

## v2.71 — 2026-07-31 — 配置分层与 docs 仓治理收口

- **配置分层**：新增 `config_store` 模块。`.meta/config.yaml` 只放机器无关的共享设置
  （`initialized`、`auto_snapshot_on_merge`），机器特定字段（`skill_dir`、`cli_path`、
  `wrapper_path`、`acceptance_command`）迁到 `.meta/config.local.yaml` 并被 docs 仓 ignore。
  读取合并两层、本地层优先；写入按显式 `MACHINE_FIELDS` 表路由到所属层。
- **fail closed**：配置层存在但损坏时抛 `CONFIG_UNREADABLE`，不再降级成 `{}`——否则依赖配置的
  验收门禁会把"读不到"误判成"没配置"而放行。
- **治理迁移**：`init --migrate [--apply]` 把历史上被追踪的 `.meta/snapshots/`、`.ait/`
  移出 git 索引，并把共享层里的机器字段搬到本地层。默认只预览；单独给 `--apply` 报
  `USAGE_ERROR`。迁移顺序固定（先写目标层再删源层），中断可重入收敛。
- **`auto_snapshot_on_merge` 默认改为 `false`**：快照树写了却无读者——回滚依赖 `docs_commit`
  与持久 tag，不依赖这些拷贝。显式设 `true` 的项目不受影响。

## v2.70 — 2026-07-31 — codegen 上下文选择收紧

修正 `codegen prepare` 的上下文选择范围，避免拉入无关 chunk 稀释 bundle 信噪比。
新增 `[TDD]-new_model_manager_codegen_context_tests` 覆盖选择规则。

## v2.69 — 2026-07-31 — 保留 FSD 同文件覆盖

修复同一 FSD 文件多次写入时的覆盖语义，避免后续写入丢失先前 split 的内容。

## v2.67 — 2026-07-31 — 上下文令牌门禁

有正文的 PRD/FSD/TDD 写入必须携带 `--context-token`——该令牌由无内容的同名 `create`
调用（讨论背景）签发，绑定层级、目标、父锚点、最终 file、操作、action、overrides 与
**实际背景内容**的摘要。

- 背景或意图变化后旧令牌失效：`CONTEXT_TOKEN_STALE` / `CONTEXT_TOKEN_CONFLICT`；
  格式非法 `CONTEXT_TOKEN_INVALID`；缺失 `CONTEXT_TOKEN_REQUIRED`
- `--skip-context` 是明确的退出通道，与令牌互斥，留最小审计痕迹；纯关系分解无需令牌
- 令牌**只证明上下文连续性**，不代表身份认证、授权或所有权

## v2.66 — 2026-07-31 — 讨论背景连续性修复

修复讨论背景在迭代中丢失连续性的问题（背景组装未正确覆盖版本内在制品改动）。

## v2.65 — 2026-07-30 — 关系出生边界收口

四种关系的出生地收敛到唯一入口，杜绝旁路建边。

## v2.64 — 2026-07-30 — docs 仓治理 + 基线/状态持久化纯净性

docs 仓 `.gitignore` 明确排除 `versions/*/state.md`、`.meta/snapshots/`、`.ait/`——
运行时产物与机器本地文件不进共享历史。

## v2.61–v2.63 — 2026-07-22 ~ 07-27 — confirm/merge 分离与图可视化

- **v2.61 计划与执行分离**：`version confirm` 生成并持久化**合并计划**
  （`ReconciliationPlan`，含所有规划输入的 SHA-256 指纹）；`version merge` 只执行已确认的
  计划。confirm 后内容再变，merge 报 `CONFIRMATION_STALE`；无计划报 `CONFIRMATION_REQUIRED`。
  同时引入 `RevertAnchor`（持久 tag `refs/tags/ait/<v>`，规避 SHA 自引用陷阱）与
  `RecoveryJournal`（回滚过程的可恢复日志）。
- **v2.62**：`derives` 恢复 1:1 映射语义；`graph-html` 支持 `--prd-chunk` 子树范围；状态面板瘦身。
- **v2.63**：SpecGraph HTML 渲染器改为总线路由布局；`derives` 支持 M:N；方向修正。

## v2.55–v2.60 — 2026-07-18 ~ 07-19 — docs/代码 git 隔离与跨仓绑定

- **v2.55 隔离**：`project-docs/` 成为独立 git 仓库（`init` 建 docs 仓 `.git`、宿主根
  `.gitignore` 追加 `project-docs/`、docs 仓 `.gitignore` 排除 state.md）。
  confirm 取消 docs 侧 `GIT_DIRTY` 预检（版本生命周期中 docs 仓本就应该是脏的）；
  merge 在版本 meta 记录 `docs_commit` 与 `code_base`。
- **v2.56/v2.57 可视化**：`specgraph graph-md` 生成 Mermaid 子图；`graph-html` 生成文件级
  Reingold-Tilford 规格树（同深度共 y、`depends_on` 虚线弧、白底点阵 SVG）。
- **v2.58 加固**：三层 confirm 打 git 锚；`version confirm` 增 `HOST_DIRTY` 检查与
  `code_result` 绑定；`version revert` 前置收集 + git clean。
- **v2.59**：`version revert` 同步把宿主仓回滚到 `code_result`。
- **v2.60**：codegen bundle 增 `target_file_content`——规格与现有代码一起交给 AI。

## v2.46–v2.54 — 2026-07-15 ~ 07-17 — 治理收口与空目录起步

- **v2.47 不变式修正**：不变式 ①（PRD↔1FSD）只约束 PRD **根** chunk；PRD 需求 split 豁免。
  由 PRD chunk 化的 dogfood 暴露。
- **v2.48**：`[PRD]-ait` 迁移到分化格式（5 个需求 split + 反向要求 + 六不变式就地展开）。
- **v2.49**：新模型 create 强制 `[PRD]`/`[FSD]`/`[TDD]` 前缀（`CHUNK_ID_PREFIX_REQUIRED`，零落盘）。
- **v2.50 退役 `specgraph add-edge`**：它能绕过写时边检查与六不变式门禁直写 baseline。
  边此后只经受门禁的内容创建路径产生。
- **v2.51 P7 严格自顶向下**：所有 create/confirm/codegen 入口加 phase 门禁；
  `version create` 加活动版本守卫（`ACTIVE_VERSION_EXISTS`）；`prd create` 不再自动开版本
  （`NO_ACTIVE_VERSION`）。
- **v2.52 `derives` 独立成关系**：PRD→FSD 从 `decomposes` 拆出为专用 `derives`（派生，1:1），
  `decomposes` 收窄为 FSD 内部。四关系四出生地成型。
- **v2.53 讨论背景**：create 省略内容即返回该层讨论背景（现状式/发现式/锚定式），
  零写入、受同层 phase 门禁。`init` 保证空 baseline 存储落盘——初始＝现状为空的迭代，零分支。
- **v2.54 空目录起步**：`ait init` 可在全新空目录自建 `project-docs/` 骨架
  （`init` 经 `NotAtProjectRoot` 逃生口豁免根解析）。从零跑通完整流水线。

## v2.31–v2.45 — 2026-07-13 ~ 07-15 — 格式收敛与全域迁移

- **v2.31 文档正文零关系声明**：`depends_on` 块从 FSD 正文剥离（临时输入，SpecGraph 唯一存储）；
  PRD 的 `@ref` 关系改为显式 SpecGraph 边。
- **v2.32 preserve 语义**：chunk id 允许保留标记 `:TEST`；`depends_on` 对账改为
  **省略即保留**（清空须显式 `depends_on: []`）——修掉 v2.31 引入的"重排正文即清空依赖"脚枪。
- **v2.33 FSD 三类分化**：root（分解视图）+ 功能 split（provide-only 能力契约）+
  `:TEST`（集成验收节点）；功能 split 上不写验收标准也不写签名。
  新模型格式规范新增 §5b（FSD 结构、能力契约、所有权分层、codegen 契约）。
- **v2.35 三条通用书写规约**：详实自包含（禁"参见 X"）、反向要求必填、术语就地展开。
- **v2.34、v2.36–v2.45**：按域逐个迁移到分化格式（version / foundation / doc_model /
  indexing / specgraph / new_model / cli / init），顶层 FSD 分三批补齐 + 系统级 `:TEST`。
  迁移过程中域间边净零变化（对账保证不丢关系）。

## v2.22–v2.30 — 2026-07-11 ~ 07-13 — 四层命令面与加固

- **v2.22 PRD 层**：create/confirm/revert 冻结-返工对 + `uncommit` 原语 + phase 机启动。
- **v2.23 FSD 层**：`fsd decompose`（拆分即建边）取代 `fsd link`；confirm/revert 对；phase `fsd-*`。
- **v2.24 TDD 层**：`tdd create --parent`（创建即建 details 边）+ confirm/revert。
  四层命令面（prd/fsd/tdd/codegen）成型。
- **v2.25 制品验收门禁**：配置化测试命令把守 confirm/merge（验证＝confirm 门禁）；
  本项目启用 pytest 作为验收命令。
- **v2.26 兄弟依赖申报**：`fsd create` 内容里的 yaml 块申报 `depends_on`，经视图 + merge 做
  owned-scope 对账；回填 69 条基线边；`prd link` 退役；`VERSION_NOT_FOUND` 关闭幽灵版本。
- **v2.27 merge 与 JSON 契约加固**：git 提交三分语义（不可用/无变更/真实失败）；
  override 冲突前置拦截；`--file` 路径净化（`INVALID_FILE_NAME`）；
  click 参数错误也包装成 JSON（`USAGE_ERROR`）。
- **v2.28 init 加固**：`--name` 校验杀掉幽灵空基线与路径逃逸（`INVALID_PROJECT_NAME`）+
  `BOOTSTRAP_FAILED` 防御性收口。
- **v2.29/v2.30 分发对齐**：`new-model-format.md` 按当前形态重写（六不变式、申报机制、
  四层生命周期、完整错误码表）；6 篇 reference 纳入 TDD 治理。

## v2.18–v2.21 — 2026-07-11 — 不变式强制与 version 四件套

- **v2.18**：confirm 全状态回滚 + codegen 上溯环守卫。
- **v2.19 组合视图**：`baseline ∪ version` 折叠到 chunk_id 身份空间——在制品 chunk 的 codegen
  上下文与全树影响分析（URI 二元性修正）。
- **v2.20 六不变式强制**：写时边/制品门禁 + confirm 全局门禁双层。
- **v2.21 version 四件套**：`create` / `confirm`（纯门禁）/ `merge`（唯一落盘）/
  `revert`（任意阶段退出）；移除 legacy impl 目录预建。

## v2.0–v2.17 — 2026-06-27 — 新模型立骨

- **v2.0–v2.3**：PRD/FSD/TDD 三层模型落地并迁移基线；merge 改为按 baseline 存在性逐 chunk
  决定 action（v2.4）。
- **v2.5**：`prd` 归新模型，旧模型改名 `prdv1`。
- **v2.6/v2.7**：SKILL.md 重写为新模型主线；格式规范与 PRD/FSD/TDD 模板随 skill 分发。
- **v2.8–v2.15 生成式自举**：把自身各域（foundation / doc_model / version / new_model /
  specgraph / indexing / lint-search-state-context / init-prd-impl-task-cli）逐个补齐
  FSD + TDD，使每个源文件都有唯一 TDD 归属。
- **v2.16/v2.17**：PRD 与根 FSD 补充角色/目标/域依赖；codegen 依赖上溯到域级 `depends_on`。

---

## v1.x — 2026-05-24 ~ 06-03 — legacy 模型（已冻结）

旧模型 `prdv1 → impl → task → code` 仍可运行但不再演进。归档基线在 `project-docs-v1/`。

### v1.6 — 2026-06-03 — Baseline PRD 单文件化 + 格式硬约束

baseline PRD 从 `docs/prd/*.md` 多文件统一为 `docs/prd/global.md`（迁移前后 chunk 数 / id 集合 /
`@ref` 关系图全等校验）；merge 路由收敛；格式硬约束 + `ait lint --fix`；
新增 `baseline-summary`、`@summary` 注释、`impl inherit`、impl 覆盖率守卫。
（chg-080~091）

### v1.5 — 2026-06-02 — task 归位 + init 增量化 + wrapper 解析

task YAML 从 `.meta/tasks/{v}/` 迁到 `versions/{v}/tasks/`；init 三态检测（fresh/incomplete/ready）
+ `--check`；init 注入 `skill_dir` 并生成项目本地 wrapper `project-docs/.ait/ait-cli`；
新增 `ait-task-execute` sub-skill，`ait-progress` 并入 `ait-state`。（chg-063~079）

### v1.4 — 2026-06-01 — prd → impl → task 三态流水线

确立三核心态与**版本原子性**：任一 confirm 后内容在本版本内冻结；唯一逃生口是整版 reset。
明确取消局部回滚、单 chunk 放弃、checksum 失效检测、增量版本继承——这些被版本原子性取代。
（chg-039~062）

### v1.3 — 2026-05-30 — SpecGraph + sub-skill 体系

`links-index.yaml` → SpecGraph 关系图（baseline + per-version 分文件）；主 SKILL.md 改造为
router，落地 sub-skill 体系；新增 `search` / `deps` / `impact` / `state`。（chg-017~038）

### v1.2 — 2026-05-25 — micro-skill 拆分 + block → chunk 术语重构

单体 SKILL.md 按"用户所处阶段"拆为 router + micro-skill；全局术语 `block` → `chunk`
（代码符号 + 文档 + schema + 索引常量），配一次性迁移脚本与双验证脚本
（防术语泄漏 / 回归）。（chg-007~016）

### v1.1 — 2026-05-24 — 工作根锁定为 `<CWD>/project-docs/`

新增 `root.py`：`resolve_project_root()` + 三个错误码
（`NOT_AT_PROJECT_ROOT` / `PROJECT_DOCS_MALFORMED` / `CWD_INSIDE_PROJECT_DOCS`）。

**Breaking**：移除 `--project / -p`。不读 `AIT_ROOT`、不向上递归找 marker、目录名硬编。
迁移方式是机械的——运行前 `cd` 到 `project-docs/` 的父目录。

### v1.0 — 2026-05-24 (frozen)

MVP：单用户、文档侧 chunk 级版本控制、Claude Code Skill 就绪。
11 个命令（`prd` 5 / `impl` 3 / `version` 2 / `reindex` / `context`）、
13 个模块约 2700 行、三态提交模型、带 `base_hash` 冲突检测的块级合并。

已知限制：`/ait:foo` 冒号命名空间不路由到 skill（Claude Code 保留给插件系统），
只支持 `/ait foo`；无代码生成、无代码↔文档同步检测、无多用户协作。
