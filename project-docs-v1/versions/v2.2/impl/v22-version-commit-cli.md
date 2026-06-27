<!-- @id:impl-v22-new-model-version-commit-cli -->
## 新模型版本提交命令

<!-- @ref:prd/补全新模型版本生命周期-version-commit-版本-meta-自动创建-codegen-baseline-回退#prd-v22-new-model-version-commit rel:implements -->

<!-- @summary: 新增 ait version commit，stage 全部 working + commit 推进到 committed -->

### Change points

#### 1. version commit CLI

- 在 `version` 命令组新增 `commit <version> [-m message]`。
- 调用 `VersionManager.stage(version)`（暂存全部 working）再 `commit(version, message)`（提交全部 staged）。
- 输出提交的 chunk 列表与 commit_id（JSON 契约）。
- message 缺省给一个通用值（如 "new-model commit"）。

### Boundaries

- 不引入 task 层。
- 不改 `vm.stage`/`vm.commit` 内核语义（已存在、旧模型复用）。
- 不改旧模型 `prd/impl commit`。
