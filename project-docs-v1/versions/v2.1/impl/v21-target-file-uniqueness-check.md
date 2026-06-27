<!-- @id:impl-v21-target-file-uniqueness-check -->
## target_file 唯一性校验

<!-- @ref:prd/补全新模型工具链-prd命令入口-init骨架-taskless-confirm-target-file唯一性#prd-v21-target-file-uniqueness rel:implements -->

<!-- @summary: new_model_validator 增加 target_file 唯一性检查，集成进 specgraph validate-new-model -->

### Change points

#### 1. 校验函数

- `new_model_validator` 新增 `validate_target_file_uniqueness(project_root, version)`。
- 遍历版本工作区 + baseline 的 TDD chunk，从 TDD markdown 正文读取 `target_file`（复用 `prepare_codegen` 的 `_target_file()` 读法，**markdown 为准**）。
- 同一 `target_file` 被多个 TDD 声明 → `NewModelViolation(code="DUPLICATE_TARGET_FILE")`，列出冲突的 TDD chunk id 与该 `target_file`。

#### 2. 集成

- `specgraph validate-new-model` 命令在现有图结构校验之后，追加调用 target_file 唯一性校验。
- 违规并入同一 `violations` 输出（机器可读 JSON，含 chunk id、target_file）。
- 与旧模型格式校验（`lint`）保持分离。

### Boundaries

- 不引入文件级 specgraph 图边（仍以 TDD→target_file 字段为准）。
- 不自动重写或修复冲突的 target_file。
- 不校验 target_file 指向的物理文件是否真实存在。
