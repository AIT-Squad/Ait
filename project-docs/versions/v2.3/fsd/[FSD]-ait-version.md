<!-- @id:[FSD]-ait-version -->
## version FSD

<!-- @summary: 版本生命周期与合并域。details 到对应 TDD（一文件一映射）。 -->

### 功能范围

ait version：三态提交、原子 confirm（两阶段+回退）、chunk 级合并、reset。

<!-- @id:[FSD]-ait-version:version_manager -->
## version_manager

<!-- @summary: VersionManager：create/ensure/stage/commit/lock/confirm/reset；三态流转；confirm 两阶段（pr details [TDD]-version_manager。 -->

### 功能描述

VersionManager：create/ensure/stage/commit/lock/confirm/reset；三态流转；confirm 两阶段（precheck→merge→extract→specgraph 提升→git commit）失败回退。

<!-- @id:[FSD]-ait-version:merge_engine -->
## merge_engine

<!-- @summary: merge_file/merge_new_file：按 action 把版本 chunk 合并进 baseline——modify 全替换 overrides  details [TDD]-merge_engine。 -->

### 功能描述

merge_file/merge_new_file：按 action 把版本 chunk 合并进 baseline——modify 全替换 overrides 目标、add 仅新增、delete 删除；保留文件容器。
