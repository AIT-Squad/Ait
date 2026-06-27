# PRD: Global PRD Single-File + PRD-Chunk-Atomic Modify-Aware Planning + Format Enforcement

> Version: v1.6 / req-016
>
> 把 baseline 的 PRD 从"散落多文件"统一为"单文件 chunk 集合"，让 `/ait prd create`
> 在递归阅读 baseline PRD 时能用极低 token 成本识别"同一功能"，自动生成
> add / modify / delete 三态规划；version confirm 时以 PRD chunk 为原子单位整组
> 替换其绑定的 impl 集合；并把 v1.5 已规范的 PRD/impl 格式从"软告警"升级为"提交闸门"。

<!-- @id:prd-prd-global-single-file -->
## prd-global-single-file: Baseline PRD 单文件化

### 概述

把 baseline 的 PRD 物理布局从"`docs/prd/*.md` 多文件散落"统一为"`docs/prd/global.md` 单文件"，让 global PRD 在文件系统层就是一个清晰的实体；同时保留 chunk 作为唯一规划/合并单位的语义。impl 文件布局保持多文件不变，由 PRD chunk 通过 `@ref` 锚定关联。

### 业务规则

- 新基线契约：v1.6 起 baseline PRD 唯一文件为 `docs/prd/global.md`
- 一次性迁移（v1.6 内执行一次，作为本版本第一组 task 落地）：
  - 把现有 `docs/prd/` 下 14 个 PRD 文件的全部 chunk 按当前 chunks-index 顺序拼接到 `docs/prd/global.md`
  - 每个 chunk 内容、`@id`、`@ref`、`@extract` 全部保留不变（chunk_parser 自反性自检）
  - 物理删除迁移源文件
  - 调用 `ait reindex` 重建 baseline `chunks-index.yaml` + `specgraph.yaml`
  - 校验：迁移前后 chunk 数量、id 集合、`@ref` 关系全等
- CLI 路径写入策略调整：
  - `prd commit` 时对 `versions/{vX.Y}/prd/` 下任意 `*.md` 解析出的 chunk，merge 时全部合入 `docs/prd/global.md`，不再保留版本里的多文件物理结构到 baseline
  - 版本工作区仍可多文件（人写起来更舒服），但 baseline 永远单文件
- 历史版本兼容：
  - 已 merged 的 v1.1~v1.5 不动其 `versions/{vX.Y}/prd/` 历史快照
  - `chunks-index-{vX.Y}.yaml` 历史也不动
  - 仅 baseline `chunks-index.yaml` 在迁移后所有 chunk 的 `file` 字段统一为 `prd/global`

### 验收标准

- [ ] `docs/prd/global.md` 存在，包含原 14 个 PRD 文件的所有 chunk
- [ ] `docs/prd/` 下不再有其他 `.md` 文件（仅 `global.md`）
- [ ] `ait reindex` 后 `chunks-index.yaml` 中所有 PRD chunk 的 `file` 字段均为 `prd/global`
- [ ] 迁移前后 chunk id 集合相等、`@ref` 关系图同构（specgraph diff = 0）
- [ ] `chunk_parser.parse_file(global.md)` 解析出的 chunk 数 = 迁移前所有 PRD 文件 chunk 数之和
- [ ] 现有所有 `ait state` / `ait specgraph` / `ait deps` / `ait impact` 命令仍正常工作

### 边界与非目标

- 不改 impl 文件布局：`docs/impl/*.md` 仍可多文件
- 不改 chunk 的 `@id` / `@ref` / `@extract` 语法
- 不改版本工作区的写入路径：版本仍可在 `versions/{vX.Y}/prd/<file>.md` 下任意命名（CLI 在 confirm/merge 时把 chunk 缝合进 `global.md`）

<!-- @id:prd-prd-chunk-summary-index -->
## prd-chunk-summary-index: chunks-index 增加 summary 字段

### 概述

为每个 chunk 在 `chunks-index.yaml` 中增加一个短摘要字段，让 `/ait prd create` 在递归读 baseline 时只读 index 不读全文，把基线扫描的 token 消耗压到原来的 1/20 量级。summary 仅在 index 里维护，不写进 markdown 正文，纯辅助元数据。

### 业务规则

- schema 扩展（向后兼容），index 中每个 chunk 增加可选字段：
  ```yaml
  chunks:
    - id: prd-task-relocation
      file: prd/global
      heading: task relocation
      level: 2
      summary: "Move task YAML from .meta/tasks to versions/{vX}/tasks; add legacy warn"
  ```
- summary 约束：≤ 120 字符的中文/英文一句话摘要；字段可缺省；旧数据 reindex 时 summary 为 `null`，由后续 commit/手动补齐
- 生成时机：
  - `prd commit` / `impl commit` 锁定时，CLI 调用 ait-discuss skill 钩子让 LLM 生成 summary，写入 chunks-index
  - 也允许在 markdown 里用 `<!-- @summary: ... -->` 元注释直接声明（优先级高于 LLM 生成）
- 新命令 `ait baseline-summary [--scope prd|impl|all] [--format yaml|json]`：输出 baseline 所有 chunk 的 `id + heading + summary` 列表，供 ait-discuss skill 在 `/ait prd create` 时一次性读入
- `ait reindex` 兼容性：保留已有 summary 字段，仅刷新 `id` / `file` / `heading` / `level`

### 验收标准

- [ ] `chunks-index.yaml` 新增的 `summary` 字段被现有解析代码忽略时不报错（向后兼容）
- [ ] `ait baseline-summary --scope prd` 输出当前 baseline 所有 PRD chunk 的 `id + summary`
- [ ] `prd commit` 后该 commit 涉及的所有 chunk 在 baseline `chunks-index.yaml` 中都有非空 summary（commit 时若 LLM 钩子失败必须报错而非静默写空）
- [ ] markdown 里 `<!-- @summary: xxx -->` 注释能正确被读取并写入 index（优先级覆盖 LLM 生成值）
- [ ] `ait reindex` 不丢失已存在的 summary 字段

### 边界与非目标

- 不用 embedding / 向量库（保留为 v1.7+ 可选增强）
- 不改 chunk 内文档语法（summary 只在 index 里，不写进 markdown 正文）
- summary 不参与合并冲突检测，不参与 `@id` / `@ref` 解析

<!-- @id:prd-prd-recursive-modify-discovery -->
## prd-recursive-modify-discovery: prd create 时递归识别 modify 候选

### 概述

让 `/ait prd create "<title>"` 在 ait-discuss 阶段自动一次性读入 baseline PRD chunks 的 `id+heading+summary` 列表（约几 KB），对用户的新需求给出 modify 候选清单（结构化 yaml）；高置信度自动用 `action: modify, overrides: <id>`；低置信度回到 `ait context <id>` 拉全文做精判；用户在 `prd confirm` 前看到一份清晰的 add / modify 决议表。

### 业务规则

- ait-discuss skill 流程加阶段 0：scan-baseline
  - skill 先调用 `ait baseline-summary --scope prd` 拿 baseline 摘要列表
  - 把"用户原始需求 + summary 列表"喂给 LLM，输出结构化 candidates：
    ```yaml
    modify_candidates:
      - new_id: prd-prd-global-single-file
        overrides: prd-overview
        confidence: 0.92
        reason: "both define how baseline PRD is organized"
    adds:
      - new_id: prd-prd-chunk-summary-index
        reason: "no baseline chunk covers chunks-index summary semantics"
    ```
- 低置信度二次精判：任一 candidate 的 `confidence < 0.8` → skill 自动调 `ait context <overrides>` 拉该 baseline chunk 全文 + 让 LLM 重判（最多 3 个候选，避免成本爆炸）
- 用户审阅闸门（在 `prd confirm` 之前）：skill 把 candidates 渲染成 markdown 表格供用户阅读；用户可在表中手动改 `overrides` / 拒绝某条 modify（降级为 add）
- 写入 chunks-index 的版本视图：`prd save-draft` / `prd confirm` 时把 candidates 决议落到 `chunks-index-{vX.Y}.yaml` 的 `action` 字段：
  ```yaml
  - id: prd-prd-global-single-file
    file: prd/global
    state: working
    action: modify
    overrides: prd-overview
  ```
  merge_engine 已经原生支持 add/modify/delete + overrides，无需改它
- CLI 校验（`prd commit` 阶段）：
  - 所有 `action: modify/delete` 的 `overrides` 必须在 baseline 存在
  - 同一 `overrides` 不能被本版本内多个新 chunk 同时覆盖

### 验收标准

- [ ] `/ait prd create` 时 skill 自动调用 `ait baseline-summary` 并把列表注入 LLM 上下文
- [ ] LLM 输出的 candidates 是合法 yaml（schema 校验通过）
- [ ] 用户能在 `prd confirm` 前看到一份 add / modify 决议表
- [ ] `chunks-index-{vX.Y}.yaml` 中每个版本 chunk 都带 `action` 字段；modify/delete 都带合法 `overrides`
- [ ] `prd commit` 阶段对非法 `overrides`（baseline 不存在 / 重复覆盖）报错并阻断
- [ ] 单次 baseline 扫描的 LLM 输入 token ≤ 5 KB（30 chunk × 120 char summary 量级）

### 边界与非目标

- 不让 LLM 自动生成 chunk id（id 一律来自人/skill 设计，CLI 校验唯一）
- 不自动产生 delete 候选（删除是更重的语义，需用户显式声明）
- 不做语义合并——modify 永远是完整替换 chunk content，不做 diff/patch

<!-- @id:prd-prd-chunk-atomic-impl-merge -->
## prd-chunk-atomic-impl-merge: PRD chunk 原子规则与 impl 整组替换

### 概述

明确 PRD chunk 是规划的原子单位这一核心契约，并把它落到三处可执行规则上：(1) `version confirm` merge 时按 PRD chunk 为分组键整组替换其 impl 集合；(2) `impl commit` pre-merge 强制校验 impl 覆盖完整性；(3) 提供 `ait impl inherit` 工效命令，让"原样继承 baseline impl 集合"成为一行命令。

### 业务规则

- 核心 merge 规则（`version confirm` 阶段，伪码）：
  ```
  for prd_chunk_id in version.changed_prd_chunks:
      baseline_impls = specgraph.baseline.impls_of(prd_chunk_id)
      version_impls  = specgraph.version.impls_of(prd_chunk_id)
      baseline.remove_chunks(baseline_impls)
      baseline.add_chunks(version_impls)
  ```
  纯查询 + 纯替换，零 LLM、零猜测；复用现有 merge_engine 的 add/delete 操作能力
- `impl commit` 的 pre-merge 校验扩展：
  ```
  for prd_chunk_id in version.changed_prd_chunks:
      if action in (add, modify):
          assert (版本工作区有 >= 1 个 impl chunk @ref -> prd_chunk_id)
                 or (PRD chunk 内含 <!-- @prd-no-impl --> 标记)
      if action == delete:
          assert (版本工作区无 impl chunk @ref -> prd_chunk_id)
  ```
  失败时报错码 `IMPL_COVERAGE_INCOMPLETE`，列出未覆盖的 PRD chunk id
- 新命令 `ait impl inherit <prd-chunk-id>`（工效命令）：
  - 把 baseline 中所有 `@ref -> <prd-chunk-id>` 的 impl chunks 原样 clone 到当前版本工作区
  - 适用场景：PRD chunk 改的是叙述层、impl 一字不动 → 一行命令完成 impl 集合"形式上重新声明"
  - 实现：读 specgraph + 复制原 chunk content 到 `versions/{vX.Y}/impl/` 下（文件名沿用 baseline）
- `<!-- @prd-no-impl -->` 标记：在 PRD chunk content 里加这一行注释，CLI 把它视为该 chunk 不需要 impl 覆盖；仅用于 PRD overview / non-goals / 项目愿景这类纯叙述 chunk
- 错误码补充：
  - `IMPL_COVERAGE_INCOMPLETE`：PRD chunk 缺 impl 覆盖
  - `IMPL_ON_DELETED_PRD`：被 delete 的 PRD chunk 仍有 impl `@ref`
- specgraph 一致性：merge 完成后 `ait specgraph` 自动 rebuild，断言无 orphan impl（`@ref` 指向已不存在的 PRD）

### 验收标准

- [ ] `version confirm` merge 时，对每个版本变动的 PRD chunk，其 baseline impl 集合被版本工作区 impl 集合整组替换
- [ ] `impl commit` 在 PRD chunk add/modify 但版本工作区未提供任何 impl `@ref` 时报 `IMPL_COVERAGE_INCOMPLETE` 并阻断
- [ ] `impl commit` 在 PRD chunk delete 但版本工作区仍有 impl `@ref` 时报 `IMPL_ON_DELETED_PRD`
- [ ] `ait impl inherit prd-xxx` 把 baseline 该 PRD chunk 下所有 impl chunk 原样 clone 到版本工作区
- [ ] PRD chunk 内 `<!-- @prd-no-impl -->` 标记能让 pre-merge 跳过该 chunk 的 impl 覆盖检查
- [ ] merge 完成后 specgraph 无 orphan impl（reindex 自检通过）
- [ ] 现有 v1.5 已 merged 数据不受迁移影响（兼容性回归测试通过）

### 边界与非目标

- 不做 impl 级别的 keep/modify/delete 三选一决议（保持极简语义）
- 不做惰性继承（PRD chunk 进入版本变动 ⟺ 其 impl 集合在该版本被原子重写，是清晰契约）
- 不改 specgraph 的 `@ref rel:implements` 语义

<!-- @id:prd-prd-format-enforcement -->
## prd-format-enforcement: PRD/impl 格式规范强制化

### 概述

v1.5 已通过 `prd-formats` chunk 规范了 PRD 四段（`概述` / `业务规则` / `验收标准` / `边界与非目标`）、impl chunk `@extract` 标记、task YAML 字段、派生命名（`impl-{源chunk}-{名}` / `T-{源chunk}-NN`）、chunk id 命名（`{type}-{domain}-{name}` 小写短横线）。但当前 `impl-formats-parser` 仅给出告警、不阻断 commit，导致 v1.6 PRD 草稿曾用英文四段（Goal/Non-Goals/Approach/Acceptance）也通过了 `prd save-draft` / `prd confirm`。本期把规范从"软提示"升级为"硬约束"：在 commit 闸门强制阻断违规，并提供 `ait lint` 离线扫描+机械修复命令；同时 v1.6 的本期重写已自纠为合规（dogfood）。

### 业务规则

- **`prd commit` 闸门**：所有 PRD chunk 必须包含且仅包含中文四段三级标题：`### 概述` / `### 业务规则` / `### 验收标准` / `### 边界与非目标`；缺段、英文段名、段名顺序错乱 → 报错码 `PRD_FORMAT_VIOLATION`，错误体含违规 chunk id 与缺段/错段清单，阻断提交
- **`impl commit` 闸门**：impl chunk 含代码块（` ``` ` 围栏）时必须用 `<!-- @extract:dynamic/{type}#{chunk} -->` ... `<!-- @extract-end -->` 包裹该代码块；纯说明性 impl chunk（无代码块）不强制要求 @extract；违规 → `IMPL_FORMAT_VIOLATION`
- **chunk id 命名校验**：`{type}-{domain}-{name}`，`type ∈ {prd, impl, task, global}`，全小写短横线（仅允许 `[a-z0-9-]`）；违规 → `CHUNK_ID_FORMAT_VIOLATION`
- **派生命名校验**：
  - impl chunk id 必须形如 `impl-{源 PRD chunk 去掉 prd- 前缀}-{名}`，且其 `@ref ... rel:implements` 指向的 PRD chunk id 必须存在
  - task YAML id 必须形如 `T-{源 chunk}-NN`（NN 为 2 位数字）
  - 违规 → `DERIVED_NAME_VIOLATION`
- **新命令 `ait lint [--scope baseline|version|<vX.Y>] [--fix]`**：
  - 离线扫描指定 scope 内所有 chunk，输出违规清单（JSON 数组，含 `chunk_id` / `code` / `message` / `fixable`）
  - `--fix` 仅修可机械修复的项：四段标题英文 → 中文映射（Goal→概述、Non-Goals→边界与非目标、Approach→业务规则、Acceptance→验收标准）、缺段填空骨架（`### <段名>\n\n_TODO_\n`）；不可机械修复的违规仅报告不修改
  - 默认 scope 为 `baseline`；`--scope version` 等价于扫描所有未 merged 版本工作区
- **错误码退出策略**：违规时 CLI 退出码非零；stdout 仍输出 `{"ok": false, "error": {...}}` 契约 JSON；错误体包含违规清单数组，每项含 `chunk_id` / `file` / `line` / `code` / `message`
- **v1.6 自我修复（dogfood）**：本版本 PRD 重写时 4 个原 chunk 已手工改为中文四段并保持 chunk id 不变；不再依赖 `--fix`（避免鸡生蛋）；新增的 `prd-prd-format-enforcement` 也以中文四段交付
- **闸门生效时机**：`prd commit` / `impl commit` 闸门在本期 impl 落地后立即生效，对 v1.6 自身及后续所有版本均强制；baseline 的存量历史 chunk 不做回溯校验（仅在 `ait lint --scope baseline` 主动扫描时报告）

### 验收标准

- [ ] `ait prd commit` 在含英文四段（Goal/Non-Goals/Approach/Acceptance）的 PRD chunk 上报 `PRD_FORMAT_VIOLATION` 并阻断
- [ ] `ait prd commit` 在缺任一中文四段时报 `PRD_FORMAT_VIOLATION` 并列出缺段名
- [ ] `ait impl commit` 在 impl chunk 含裸代码块（无 `@extract` 包裹）时报 `IMPL_FORMAT_VIOLATION`
- [ ] `ait lint --scope v1.6` 列出 v1.6 所有 5 个 chunk 的格式违规（重写后应为 0 条违规）
- [ ] `ait lint --scope baseline --fix` 在 baseline 历史 chunk 上能机械修复英文四段（若存在），且修复后 `ait lint --scope baseline` 通过
- [ ] 派生命名违规（如出现 `impl-foo-bar` 但 baseline 与所有版本都不存在 `prd-foo`）报 `DERIVED_NAME_VIOLATION`
- [ ] chunk id 含大写、下划线、空格时报 `CHUNK_ID_FORMAT_VIOLATION`
- [ ] task YAML id 不符合 `T-{源 chunk}-NN` 格式时报 `DERIVED_NAME_VIOLATION`
- [ ] 所有违规错误码退出非零，stdout 输出合法 `{"ok": false, "error": {...}}` JSON
- [ ] v1.6 本身 5 个 chunk 在本版本 impl 落地后跑 `ait prd commit` 不触发任何格式违规（dogfood 自洽）

### 边界与非目标

- 不做语义级 lint（不判断"验收标准"是否覆盖"概述"目标、不查"边界与非目标"是否合理）
- 不自动改写 chunk 正文内容；`--fix` 仅做机械的标题映射 / 缺段空骨架填充
- 不改 chunk id 命名规则本身（沿用 v1.5 `prd-formats` 已定的派生式 + 三段式）
- 不强制 task YAML 字段级 lint（task 由 `task create/execute` 内置 schema 校验，已足够）
- 不对历史已 merged 版本（v1.1 ~ v1.5）做强制回溯阻断（仅 `ait lint --scope baseline` 主动扫描时报告，不阻断任何写操作）
- 不引入新的格式（如 YAML frontmatter、JSON Schema 文件），保持 HTML 注释元数据哲学

<!-- @ref:prd/ait-redesign#prd-formats rel:refines -->
