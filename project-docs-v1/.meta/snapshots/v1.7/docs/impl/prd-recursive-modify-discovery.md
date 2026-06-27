<!-- @id:impl-prd-recursive-modify-discovery-pipeline -->
## prd create 递归扫描 baseline + skill 侧 candidates 决议

<!-- @ref:prd/v1-6-roadmap#prd-prd-recursive-modify-discovery rel:implements -->

### 改动点

本 chunk 的核心改动在 **skill 侧**（ait-discuss）+ **CLI 校验侧**（prd commit）。LLM 调度由 skill 主导，CLI 只承担"决议落盘 + 静态校验"。

#### 1. `skill/ait/sub-skills/ait-discuss/SKILL.md` — 流程加阶段 0：scan-baseline

在 ait-discuss 的现有"理解需求 → 拆 chunk"流程之前，插入 **Phase 0: scan-baseline**：

1. 调 `ait baseline-summary --scope prd --format yaml` 拿 baseline PRD chunk 摘要列表（依赖 `impl-prd-chunk-summary-field` 已落地）
2. 把"用户原始需求 + 摘要列表"喂给 LLM，提示词要求输出严格 yaml（schema 见 PRD 第 3 节示例），三段：`modify_candidates` / `delete_candidates`（始终为空，PRD 已声明不自动产 delete）/`adds`
3. 解析 LLM 输出 → 对 `modify_candidates` 中 `confidence < 0.8` 的项（最多 3 个），逐个调 `ait context <overrides>` 拉全文，让 LLM 二次精判，把 confidence 重写或降级为 add
4. 把最终 candidates 渲染成 markdown 表格输出给用户：四列 `new_id` / `action` / `overrides` / `confidence` / `reason`
5. 用户在 confirm 闸门前可以手动改表格（编辑成 `action: add` 即拒绝该 modify）；skill 解析最终用户确认后的表格→产 `chunks-index-{vX.Y}.yaml` 草稿条目（带 `action`/`overrides`）

skill 文档需明确：**LLM 输入限制 ≤ 5 KB**（与 PRD 验收对齐），若 baseline PRD chunk 数 × 平均 summary 长度 > 5 KB，则只挑与用户需求关键词最相关的前 N 个（关键词由用户原始需求 tokenize 后取实词，N 自适应直至总长 ≤ 5 KB）。

#### 2. `ait/cli.py` — 新增 `ait prd resolve-candidates` 命令（只做静态落盘）

在 prd 子命令组（约 290~330 行）增加 `@prd_group.command("resolve-candidates")`，参数 `--from-file`（必选，LLM 产出的 candidates yaml 路径）。

实现：读 candidates yaml → 写入 `versions/{vX.Y}/.candidates.yaml`（草稿态、不进 chunks-index），同时为每条 candidate 校验：
- `new_id` 命名合法（`prd-{domain}-{name}`，全小写短横线，由 format_validator 复用）
- `overrides`（若 action=modify）必须在 baseline `chunks-index.yaml` 存在
- 同一 `overrides` 不能被多个 candidate 同时 modify → 报 `DUPLICATE_OVERRIDES_TARGET`
- candidate `new_id` 不能与 baseline 已有 chunk id 撞 → 报 `CHUNK_ID_COLLISION`

`prd save-draft`（已有命令）扩展：保存草稿时若工作区存在 `.candidates.yaml` → 把每个 candidate 的 `action` / `overrides` 字段同步到 `chunks-index-{vX.Y}.yaml` 对应 chunk 上；不动 chunk 内容。

#### 3. `ait/prd_manager.py` — `commit` 阶段增校验

`PrdManager.commit()`（约第 304 行）在 stage 之前、`target_ids` 计算之后追加 modify-aware 校验段：

- 加载 baseline index 拿 `baseline_ids` 集合
- 对 `target_ids` 中 `action ∈ {modify, delete}` 的每个 chunk：
  - 若 `overrides` 为空 → `OVERRIDES_REQUIRED`
  - 若 `overrides` 不在 `baseline_ids` → `OVERRIDES_NOT_IN_BASELINE`
  - 同一 `overrides` 在本次 commit 被多个新 chunk 重复声明 → `DUPLICATE_OVERRIDES_TARGET`

不改 stage / commit 后续链路。

#### 4. 不得改动

- merge_engine（add/modify/delete + overrides 已原生支持，验证它就够）
- specgraph 任何代码（合规 candidates 写入 chunks-index 后 reindex 自然刷出新 specgraph）
- chunks-index schema —— `action` / `overrides` 字段已在 `VersionChunkEntry` 中，不新增字段

### 单元测试

- `tests/test_prd_commit_modify.py::test_modify_overrides_must_exist` — chunks-index 中有 `action: modify, overrides: prd-not-exist`，prd commit 报 `OVERRIDES_NOT_IN_BASELINE` 并阻断。
- `tests/test_prd_commit_modify.py::test_modify_requires_overrides` — `action: modify` 但 `overrides` 缺失 → `OVERRIDES_REQUIRED`。
- `tests/test_prd_commit_modify.py::test_duplicate_overrides_target` — 两个新 chunk 都 `overrides: prd-foo` → `DUPLICATE_OVERRIDES_TARGET`。
- `tests/test_prd_commit_modify.py::test_delete_overrides_validated_too` — `action: delete, overrides: prd-not-exist` 同样 `OVERRIDES_NOT_IN_BASELINE`。
- `tests/test_prd_commit_modify.py::test_legitimate_modify_passes` — overrides 命中 baseline、唯一覆盖 → commit 成功，stage/commit_id 正常返回。
- `tests/test_prd_resolve_candidates.py::test_candidates_written_to_workspace` — `ait prd resolve-candidates --from-file ...` 写出 `.candidates.yaml`、内容 == 输入。
- `tests/test_prd_resolve_candidates.py::test_chunk_id_collision_baseline` — candidate.new_id 与 baseline chunk id 撞 → `CHUNK_ID_COLLISION`。
- `tests/test_prd_save_draft_sync.py::test_save_draft_propagates_action_overrides` — 工作区有 `.candidates.yaml` 时，save-draft 把 action/overrides 同步进 `chunks-index-{vX.Y}.yaml` 对应 chunk。
