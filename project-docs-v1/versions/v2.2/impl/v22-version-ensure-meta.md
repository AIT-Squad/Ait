<!-- @id:impl-v22-new-model-version-ensure-meta -->
## 新模型版本元数据自动创建

<!-- @ref:prd/补全新模型版本生命周期-version-commit-版本-meta-自动创建-codegen-baseline-回退#prd-v22-new-model-version-ensure rel:implements -->

<!-- @summary: VersionManager.ensure 幂等建 meta+index；新模型 create 写文件前调用 -->

### Change points

#### 1. VersionManager.ensure

- 新增 `ensure(version, based_on=None)`：meta 文件存在则 no-op 返回；不存在则建 `prd`/`impl` 目录（`exist_ok=True`）、写 meta、建空 version index、刷 state。
- 与 `create` 的区别：**容忍版本目录已存在**（不抛 "already exists"）。

#### 2. 新模型 create 调用 ensure

- `NewModelManager._create_document` 在 `write_version_file` 之前调用 `self.versions.ensure(version)`，确保后续 confirm 能加载版本 meta。

### Boundaries

- 不改旧模型 `create` 与 `prd_manager` 的自动建版本逻辑。
- 不引入新的版本号自动分配。
