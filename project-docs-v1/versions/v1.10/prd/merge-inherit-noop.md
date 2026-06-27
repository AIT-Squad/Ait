<!-- @id:prd-version-merge -->
## 版本合并

<!-- @summary: Enforce chunk action semantics during merge and prevent duplicate baseline writes -->

### 概述

`/ait version confirm` 是版本的终点：守卫检查 -> 合并版本 prd/impl 到全局 -> 从 impl 提取动态 global -> 一次 git commit。采用两阶段+失败回退保证原子性。

v1.10 明确合并动作的边界：merge 只按版本索引中的 `action` 语义处理完整 chunk，不做语义 diff 或局部 patch。`modify` 是完整替换，`add` 只能新增 baseline 中不存在的 chunk，`delete` 删除指定 baseline chunk。任何把已存在 baseline chunk 作为 `add` 写入的情况都必须在 merge 前阻断，避免同 ID chunk 被追加到 baseline。

### 业务规则

- 前置守卫：本版本所有 task 必须为 done，且 git 工作区干净；否则拦截并提示。
- 合并以 chunk 为维度：同名或 `overrides` 指向的 chunk 用本版本内容完整替换，其他 chunk 不动。
- `action=modify` 表示完整替换 `overrides` 指向的 baseline chunk。版本侧 markdown 中的该 chunk 必须已经包含最终希望保留的全部信息，merge 不从旧 chunk 自动搬运遗漏内容。
- `action=add` 只能用于 baseline 中不存在的新 chunk id。若 baseline 已存在同 ID chunk，merge 必须在写入前失败，错误码为 `DUPLICATE_BASELINE_CHUNK`，不得追加第二份同 ID chunk。
- `action=delete` 删除 `overrides` 指向的 baseline chunk。
- 继承来的 impl chunk 只用于当前版本的上下文、任务拆分和 impl 覆盖判断；不得作为 `add` 追加到 baseline。实现可以把 inherited chunk 表示为 no-op 记录，或表示为同 ID `modify` 替换，但最终 baseline 不得出现重复 chunk。
- 从本版本 impl 提取 `@extract` 标记的 DDL/schema/api 片段，按 chunk 合并进动态 global。
- 两阶段执行：1. 预检；2. merge 写入 docs/；3. git commit（message = state.md 的 title）。
- 失败回退：若 merge 或 git commit 失败，回退 merge（恢复 docs/ 到 merge 前），报错；要么全成要么全不动。

### 验收标准

- [ ] 有 task 非 done 时 version confirm 被拦截。
- [ ] 合并按 chunk 替换，不影响无关全局 chunk。
- [ ] `action=modify` 替换 `overrides` 指向的 baseline chunk，不追加同 ID chunk。
- [ ] `action=add` 且 baseline 已有同 ID chunk 时，merge 报 `DUPLICATE_BASELINE_CHUNK` 并且 baseline 不变。
- [ ] inherited impl chunk 在 version confirm 后不会向 baseline 追加重复 chunk。
- [ ] 动态 global 由 impl 的 @extract 片段提取生成。
- [ ] commit message 等于 title。
- [ ] commit 失败时 docs/ 回退到合并前状态。

### 边界与非目标

- 不在 version confirm 之外提供合并入口。
- 不做字段级、段落级或语义级 merge；modify 仍是 chunk 级完整替换。
- 不引入系统级全局 `ait` 命令或 PATH 注入。

<!-- @id:prd-prd-recursive-modify-discovery -->
## prd-recursive-modify-discovery: prd create 时基于 baseline 讨论并确认 modify

<!-- @summary: Require user-confirmed PRD modify chunks to be full replacement chunks -->

### 概述

`/ait prd create "<title>"` 必须把当前 baseline PRD chunk 摘要作为讨论输入交给 AI，用于辅助识别本次需求可能涉及的旧 PRD chunk。AI 只能提出 add/modify 建议，不能直接把 modify 决议写入版本工作区；任何修改旧 chunk 的决议都必须先展示给用户确认。

v1.10 明确 PRD modify 的内容契约：版本侧 modify chunk 是完整替换块，不是 patch。用户确认某个 baseline chunk 被 modify 后，写入 `versions/<v>/prd/*.md` 的新 chunk 必须包含该 chunk 合并后的完整内容，包括旧 chunk 中仍然有效的全部信息和本次新增/修改的信息。merge 时直接用该完整 chunk 替换 `overrides` 指向的 baseline chunk。

### 业务规则

- ait-discuss 在 PRD 讨论开始时调用 `project-docs/.ait/ait-cli baseline-summary --scope prd --format yaml`，把 baseline 的 `id + heading + summary` 作为讨论上下文。
- AI 与用户完成需求讨论后，再根据最终 PRD 拆分结果标出每个 PRD chunk 是新增还是修改旧 chunk。
- 所有 `modify` 候选必须展示给用户确认，展示字段至少包含 `new_id`、`action`、`overrides`、`confidence`、`reason`。
- 对每个被确认的 `modify` 候选，ait-discuss 必须读取 `overrides` 指向的旧 chunk 全文，并在生成新 PRD chunk 时保留旧 chunk 中仍然有效的信息。
- 用户确认后的版本侧 modify chunk 必须是完整替换块。它不能只写新增段落、差异片段、补丁说明或“沿用旧内容”的引用。
- merge 层不做旧内容补全；若版本侧 modify chunk 缺少应保留的信息，merge 后这些信息会丢失，责任在 PRD 讨论/确认阶段完成。
- 用户确认前，skill 不得调用 `prd resolve-candidates`，也不得把 AI 原始判断写入 `.candidates.yaml`。
- 用户可以拒绝某个 modify，将其改为 add；也可以手工调整 `overrides` 指向的 baseline chunk。
- 用户确认后，skill 沿用现有 `prd resolve-candidates --from-file <file>` 落盘确认后的 candidates，不新增 change plan 文件、schema 或命令。
- 如果最终 PRD chunk 使用 baseline 已有 id，CLI 可按现有规则将其登记为 `action: modify, overrides: <same-id>`；如果使用新 id 修改旧 chunk，则必须通过确认后的 candidates 提供 `overrides`。
- `delete_candidates` 默认为空；删除旧 PRD chunk 仍要求用户显式声明，不由 AI 自动提出。

### 验收标准

- [ ] ait-discuss 的工作流明确要求先读取 baseline summary 并用于 PRD 讨论。
- [ ] ait-discuss 明确区分 AI 建议与用户确认后的 candidates。
- [ ] skill 文档中写明：未获得用户确认前不得调用 `prd resolve-candidates`。
- [ ] skill 文档中写明：PRD modify chunk 必须包含旧 chunk 中仍然有效的全部信息，是完整替换块。
- [ ] 用户确认后的 PRD modify 仍使用现有 `.candidates.yaml` / `action` / `overrides` 机制。
- [ ] 未新增 change plan 概念、文件或 CLI 命令。
- [ ] 既有 `prd resolve-candidates`、`prd save-draft`、`prd commit` 的校验语义保持兼容。

### 边界与非目标

- 不让 CLI 自行做语义判断；语义识别仍由 skill 侧 AI 讨论完成。
- 不把 AI 原始候选视为用户确认结果。
- 不新增独立的 change plan 抽象。
- 不做语义 diff 或 patch；modify 仍是 chunk 级完整替换。
- 不要求 merge 层从旧 chunk 自动补全缺失内容。

<!-- @id:prd-prd-chunk-atomic-impl-merge -->
## prd-chunk-atomic-impl-merge: impl 侧基于 baseline 讨论并确认 modify/inherit

<!-- @summary: Make inherited impl chunks no-op for baseline merge while preserving coverage context -->

### 概述

impl 阶段必须遵循与 PRD 阶段一致的人机确认逻辑：`/ait impl create <prd-chunk-id>` 在生成实现设计前，应读取当前 PRD chunk、其覆盖的旧 PRD chunk（若存在）以及旧 PRD chunk 在 baseline 中对应的 impl chunks。AI 可以建议新增、修改或继承 impl，但任何修改旧 impl 或继承旧 impl 的动作都必须先由用户确认。

v1.10 修正 inherit 的 merge 语义：继承旧 impl 表示该 baseline impl 对当前版本仍然有效，它可以参与当前版本的上下文、覆盖判断和 task 拆分，但不得作为新增 chunk 再写入 baseline。baseline 中已经存在的 inherited impl 不应被追加第二份。

### 业务规则

- ait-impl-discuss 在 impl 讨论开始时调用 `context <prd-chunk-id> --scenario prd-to-impl` 获取当前 PRD 上下文。
- 如果当前 PRD chunk 是 `action: modify` 且有 `overrides`，skill 需要读取 `overrides` 指向的旧 PRD chunk，并通过 specgraph 找到 baseline 中实现该旧 PRD chunk 的 impl chunks。
- AI 与用户完成实现讨论后，再标出 impl chunk 的新增、修改或继承建议。
- 对 `modify` 旧 impl 的建议，skill 必须展示 `new_id`、`overrides`、`reason` 并获得用户确认后，才允许生成可落盘的 impl draft。
- 对 `inherit` 旧 impl 的建议，skill 必须展示将被继承的 baseline impl chunk 列表并获得用户确认后，才允许调用现有 `ait impl inherit <prd-chunk-id>`。
- `inherit` 是 skill/命令层的工效动作，用于把 baseline impl 带入当前版本上下文。它不得在 merge 阶段表现为 `action=add` 写入 baseline。
- 不新增 `action: inherit` 到 schema。实现可以用同 ID `action=modify, overrides=<impl-id>` 表示“保留该 baseline impl”，或在 merge 前过滤 inherited/no-op 记录；无论采用哪种内部表示，version confirm 后 baseline 不得出现重复 chunk。
- 为了让确认后的 impl modify 能确定性落盘，`ait impl create` 需要支持显式 `--action modify --overrides <baseline-impl-id>` 参数，并在 CLI 层校验 overrides 存在于 baseline。
- 未指定 `--action` 时，`impl create` 保持现有默认行为：创建新增 impl chunk，登记为 `action: add`。
- merge 前必须阻断任何 `action=add` 且 chunk id 已存在于 baseline 的 impl 记录，避免把继承或误分类的旧 impl 追加进 baseline。

### 验收标准

- [ ] ait-impl-discuss 的工作流明确读取当前 PRD、旧 PRD（若有）和旧 PRD 对应的 baseline impl chunks。
- [ ] 修改旧 impl 前，skill 必须向用户展示 `overrides` 候选并等待确认。
- [ ] 继承旧 impl 前，skill 必须向用户展示将继承的 impl 列表并等待确认。
- [ ] `ait impl create` 支持 `--action modify --overrides <impl-id>`，并把版本索引记录写为 `action: modify`、`overrides: <impl-id>`。
- [ ] `--action modify` 缺少 `--overrides` 时失败；`overrides` 不在 baseline 时失败。
- [ ] `ait impl inherit <prd-chunk-id>` 后执行 version confirm，不会向 baseline 追加重复 inherited impl chunk。
- [ ] merge 前发现 `action=add` 且 baseline 已有同 ID chunk 时会阻断。
- [ ] 未新增 change plan 概念、文件或 CLI 命令。

### 边界与非目标

- 不引入 `action: inherit` 到版本索引 schema。
- 不让 `impl create` 自动猜测要覆盖哪个 baseline impl；覆盖目标必须来自用户确认后的显式参数。
- 不做 impl 级语义 diff；modify 仍是完整 chunk 替换。
- 不改变 PRD chunk 原子替换 impl 集合的既有 merge 规则，只修正 inherited impl 的 baseline 写入语义。
