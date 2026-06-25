<!-- @id:impl-v22-codegen-baseline-fallback-resolve -->
## codegen 基线回退

<!-- @ref:prd/补全新模型版本生命周期-version-commit-版本-meta-自动创建-codegen-baseline-回退#prd-v22-codegen-baseline-fallback rel:implements -->

### Change points

#### 1. CLI 不再硬性要求版本

- `codegen prepare`：`version = version_opt or versions.current()`；当两者皆 None 时**不再 fail NO_VERSION**，把 None 传给 `prepare_codegen`。

#### 2. prepare_codegen baseline-only 路径

- `version` 为 None 时：跳过版本索引查询，直接 `query_baseline` 解析 TDD；`base_dir` 用 `docs/`；specgraph 用 `load_specgraph(baseline)` 而非 `combined`。
- 有 `version` 时维持现有"版本优先、回退 baseline"行为不变。

### Boundaries

- 不改上游遍历 / 依赖收集算法。
- 不引入反向（代码→spec）查询。
