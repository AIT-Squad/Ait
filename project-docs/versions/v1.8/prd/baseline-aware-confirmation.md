<!-- @id:prd-prd-recursive-modify-discovery -->
<!-- @summary: Make prd create baseline-aware while requiring user-confirmed modify candidates -->
## prd-recursive-modify-discovery: prd create 时基于 baseline 讨论并确认 modify

### 概述

`/ait prd create "<title>"` 必须把当前 baseline PRD chunk 摘要作为讨论输入交给 AI，用于辅助识别本次需求可能涉及的旧 PRD chunk。AI 只能提出 add/modify 建议，不能直接把 modify 决议写入版本工作区；任何修改旧 chunk 的决议都必须先展示给用户确认。

### 业务规则

- ait-discuss 在 PRD 讨论开始时调用 `project-docs/.ait/ait-cli baseline-summary --scope prd --format yaml`，把 baseline 的 `id + heading + summary` 作为讨论上下文。
- AI 与用户完成需求讨论后，再根据最终 PRD 拆分结果标出每个 PRD chunk 是新增还是修改旧 chunk。
- 所有 `modify` 候选必须展示给用户确认，展示字段至少包含 `new_id`、`action`、`overrides`、`confidence`、`reason`。
- 用户确认前，skill 不得调用 `prd resolve-candidates`，也不得把 AI 原始判断写入 `.candidates.yaml`。
- 用户可以拒绝某个 modify，将其改为 add；也可以手工调整 `overrides` 指向的 baseline chunk。
- 用户确认后，skill 沿用现有 `prd resolve-candidates --from-file <file>` 落盘确认后的 candidates，不新增 change plan 文件、schema 或命令。
- 如果最终 PRD chunk 使用 baseline 已有 id，CLI 可按现有规则将其登记为 `action: modify, overrides: <same-id>`；如果使用新 id 修改旧 chunk，则必须通过确认后的 candidates 提供 `overrides`。
- `delete_candidates` 默认为空；删除旧 PRD chunk 仍要求用户显式声明，不由 AI 自动提出。

### 验收标准

- [ ] ait-discuss 的工作流明确要求先读取 baseline summary 并用于 PRD 讨论。
- [ ] ait-discuss 明确区分 AI 建议与用户确认后的 candidates。
- [ ] skill 文档中写明：未获得用户确认前不得调用 `prd resolve-candidates`。
- [ ] 用户确认后的 PRD modify 仍使用现有 `.candidates.yaml` / `action` / `overrides` 机制。
- [ ] 未新增 change plan 概念、文件或 CLI 命令。
- [ ] 既有 `prd resolve-candidates`、`prd save-draft`、`prd commit` 的校验语义保持兼容。

### 边界与非目标

- 不让 CLI 自行做语义判断；语义识别仍由 skill 侧 AI 讨论完成。
- 不把 AI 原始候选视为用户确认结果。
- 不新增独立的 change plan 抽象。
- 不做语义 diff 或 patch；modify 仍是 chunk 级完整替换。

<!-- @id:prd-prd-chunk-atomic-impl-merge -->
<!-- @summary: Require user confirmation for impl modify/inherit and add explicit impl overrides support -->
## prd-chunk-atomic-impl-merge: impl 侧基于 baseline 讨论并确认 modify/inherit

### 概述

impl 阶段必须遵循与 PRD 阶段一致的人机确认逻辑：`/ait impl create <prd-chunk-id>` 在生成实现设计前，应读取当前 PRD chunk、其覆盖的旧 PRD chunk（若存在）以及旧 PRD chunk 在 baseline 中对应的 impl chunks。AI 可以建议新增、修改或继承 impl，但任何修改旧 impl 或继承旧 impl 的动作都必须先由用户确认。

### 业务规则

- ait-impl-discuss 在 impl 讨论开始时调用 `context <prd-chunk-id> --scenario prd-to-impl` 获取当前 PRD 上下文。
- 如果当前 PRD chunk 是 `action: modify` 且有 `overrides`，skill 需要读取 `overrides` 指向的旧 PRD chunk，并通过 specgraph 找到 baseline 中实现该旧 PRD chunk 的 impl chunks。
- AI 与用户完成实现讨论后，再标出 impl chunk 的新增、修改或继承建议。
- 对 `modify` 旧 impl 的建议，skill 必须展示 `new_id`、`overrides`、`reason` 并获得用户确认后，才允许生成可落盘的 impl draft。
- 对 `inherit` 旧 impl 的建议，skill 必须展示将被继承的 baseline impl chunk 列表并获得用户确认后，才允许调用现有 `ait impl inherit <prd-chunk-id>`。
- `inherit` 仍是 skill/命令层的工效动作，不新增 `action: inherit`；底层版本索引仍登记为现有 `add/modify/delete` 语义。
- 为了让确认后的 impl modify 能确定性落盘，`ait impl create` 需要支持显式 `--action modify --overrides <baseline-impl-id>` 参数，并在 CLI 层校验 overrides 存在于 baseline。
- 未指定 `--action` 时，`impl create` 保持现有默认行为：创建新增 impl chunk，登记为 `action: add`。

### 验收标准

- [ ] ait-impl-discuss 的工作流明确读取当前 PRD、旧 PRD（若有）和旧 PRD 对应的 baseline impl chunks。
- [ ] 修改旧 impl 前，skill 必须向用户展示 `overrides` 候选并等待确认。
- [ ] 继承旧 impl 前，skill 必须向用户展示将继承的 impl 列表并等待确认。
- [ ] `ait impl create` 支持 `--action modify --overrides <impl-id>`，并把版本索引记录写为 `action: modify`、`overrides: <impl-id>`。
- [ ] `--action modify` 缺少 `--overrides` 时失败；`overrides` 不在 baseline 时失败。
- [ ] 现有 `ait impl inherit <prd-chunk-id>` 语义保持不变。
- [ ] 未新增 change plan 概念、文件或 CLI 命令。

### 边界与非目标

- 不引入 `action: inherit` 到版本索引 schema。
- 不让 `impl create` 自动猜测要覆盖哪个 baseline impl；覆盖目标必须来自用户确认后的显式参数。
- 不做 impl 级语义 diff；modify 仍是完整 chunk 替换。
- 不改变 PRD chunk 原子替换 impl 集合的既有 merge 规则。
