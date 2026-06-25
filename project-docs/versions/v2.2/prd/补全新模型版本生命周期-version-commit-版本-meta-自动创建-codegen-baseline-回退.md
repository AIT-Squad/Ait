<!-- @id:prd-v22-new-model-version-commit -->
## 新模型版本提交

<!-- @summary: 提供把新模型 fsd/tdd/prdv2 chunk 从 working 锁定为 committed 的 CLI，使 version confirm 能合并 -->

### 概述

新模型用 `fsd/tdd/prdv2 create` 把 chunk 注册进版本工作区，但注册态是 `working`。`version confirm` 只合并 `committed` 态 chunk，导致新模型版本 confirm 时报 `MERGE_NO_COMMITTED`（无可合并 chunk）。旧模型靠 `prd commit`/`impl commit` 把 chunk 推进到 committed，新模型缺少对应的提交/锁定入口。这是新模型 create→commit→confirm 生命周期断裂的核心缺口。

### 业务规则

- 提供一个新模型版本提交入口，把该版本所有 `working` 态 chunk 一次性推进到 `committed`。
- 提交后这些 chunk 在本版本内锁定，与旧模型 commit 语义一致（不可再改，要改走 version reset）。
- 提交是 taskless 流程的一部分：新模型不拆 task，提交即"准备好被 confirm 合并"。
- 提交入口与旧模型 `prd/impl commit` 并存，不改其行为。
- 提交后 `version confirm` 能正常合并这些 chunk 进 baseline。

### 验收标准

- [ ] 新模型版本（含 fsd/tdd/prdv2 chunk）执行提交后，chunk 全部变 committed。
- [ ] 提交后 `version confirm` 成功合并，不再报 `MERGE_NO_COMMITTED`。
- [ ] 提交后再次改动被拒（锁定生效）。
- [ ] 旧模型 `prd/impl commit` 现有测试继续通过。
- [ ] 新增测试覆盖新模型 create→提交→confirm 全链路。

### 边界与非目标

- 不为新模型引入 task 层。
- 不改旧模型 commit 的逐 chunk 语义。
- 不在本需求内做 codegen 或 init 相关改动。

<!-- @id:prd-v22-new-model-version-ensure -->
## 新模型版本元数据自动创建

<!-- @summary: 新模型 fsd/tdd/prdv2 create 在版本 meta 缺失时自动建 meta+index，避免半建状态 -->

### 概述

新模型 `fsd/tdd/prdv2 create` 通过 `write_version_file` 写文件时会建出版本目录，但不创建版本元数据（`.meta/versions/<v>.yaml`）与版本索引。结果是版本处于"有目录、无 meta"的半建状态，`version confirm` 报 `Version <v> has no metadata file`。旧模型靠 `prd create` 顺带建版本 meta，新模型路径缺这一步。

### 业务规则

- 新模型 create 在写文件前，确保目标版本的 meta 与索引存在；缺失则创建，已存在则不动（幂等）。
- 自动创建容忍版本目录已存在（不与现有 create 的"目录已存在即报错"冲突）。
- 版本号取自命令显式传入的 `--version`，不隐式臆测命名。
- 不改旧模型版本创建路径。

### 验收标准

- [ ] 对一个尚无 meta 的版本执行新模型 create 后，`.meta/versions/<v>.yaml` 与版本索引存在。
- [ ] 同版本重复 create 不报"已存在"错误（幂等）。
- [ ] 新模型版本随后可正常 `version confirm`。
- [ ] 旧模型版本创建的现有测试继续通过。

### 边界与非目标

- 不改旧模型 `prd create` 的自动建版本逻辑。
- 不引入新的版本号自动分配策略。

<!-- @id:prd-v22-codegen-baseline-fallback -->
## codegen 基线回退

<!-- @summary: 无活动版本时 codegen prepare 回退到 baseline 解析 TDD，而非报 NO_VERSION -->

### 概述

`codegen prepare <tdd>` 在未显式传 `--version` 且无活动未合并版本时，因 `versions.current()` 返回 None 而报 `NO_VERSION`。但 baseline 中已合并的 TDD 本应能直接出代码生成上下文——这正是迭代时"从已建基线追溯到代码文件"（目标 1）的常用场景。codegen 应在无活动版本时回退到 baseline 解析。

### 业务规则

- `codegen prepare` 未指定版本且无活动版本时，从 baseline 解析 TDD 根 chunk 与上游/依赖上下文。
- 有活动版本时维持现有行为（版本优先、回退 baseline）。
- 回退路径仍返回 `target_file` 与上游 FSD/PRD、依赖契约。

### 验收标准

- [ ] 已合并 baseline 后、无活动版本时，`codegen prepare <baseline-tdd>` 成功返回 target_file 与上游上下文。
- [ ] 有活动版本时行为不变，现有 codegen 测试继续通过。
- [ ] 新增测试覆盖无活动版本的 baseline 回退。

### 边界与非目标

- 不改 codegen 的上下文组装算法（上游遍历、依赖收集不变）。
- 不引入反向（代码→spec）查询。
