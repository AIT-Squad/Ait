<!-- @id:impl-v21-taskless-confirm-test -->
## 无 task confirm 端到端验证

<!-- @ref:prd/补全新模型工具链-prd命令入口-init骨架-taskless-confirm-target-file唯一性#prd-v21-taskless-confirm rel:implements -->

<!-- @summary: confirm 守卫零 task 时已自然通过；本 impl 只补端到端测试，不改生产逻辑 -->

### Change points

#### 1. 现状确认（不改生产代码）

- `version_manager.confirm` 守卫为 `not_done = [t for t in tasks if t.status != "done"]`；**零 task 时 `not_done` 为空 → 守卫通过**。
- `merge` 已支持 FSD/TDD chunk 路由（v2.0 `test_new_model_merge` 已覆盖）。
- 故本需求**不改** confirm/merge 任何生产逻辑。

#### 2. 端到端测试

- 新增 `tests/test_version_confirm_taskless.py`：构造一个只含 `[PRD]`/`[FSD]`/`[TDD]`、**零 task** 的版本。
- 走 `version confirm`，断言：
  - confirm 成功返回；
  - FSD chunk 合入 `docs/fsd/`、TDD chunk 合入 `docs/tdd/`，**未被塞进 `docs/prd/global.md`**；
  - baseline specgraph 保留 `decomposes`/`details`/`depends_on` 三种边；
  - git commit 成功（必要时 `allow_dirty_git=True`）。

### Boundaries

- 不改 confirm 守卫与 merge 逻辑。
- 不删除 task 元数据。
- 不强制项目切换新模型 confirm 规则。
