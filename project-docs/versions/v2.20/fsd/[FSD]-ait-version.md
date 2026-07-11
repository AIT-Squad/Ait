<!-- @id:[FSD]-ait-version -->
## version FSD

### 功能范围

版本生命周期与基线合并：版本创建/三态提交(working→staged→committed)/锁定/原子 confirm(两阶段+回退)/reset；chunk 级 merge。版本是「全有或全无」原子单元。**confirm 是新模型六不变式的全局权威闸口。**

### 交互契约

- 生命周期：`create/ensure/list_versions/current`；meta 读写。
- 三态：`add_chunk(upsert)/remove_chunk/stage/unstage/commit/status`。
- 锁定：`lock_prd/lock_impl/assert_*_writable/set_title`。
- 合并：`pre_merge_check/merge/confirm`（confirm 守卫 task 全 done + git 干净 + **新模型六不变式门禁（组合视图全量 validate_invariants，违例 INVARIANT_VIOLATION 拒于任何落盘之前，legacy 项目 vacuous 过）** → 合入基线 → 提取动态 global → 提升 specgraph → git commit；失败回退——docs 与 .meta 关键状态字节级还原）。
- 逃生：`reset(--confirm)` 物理清空版本。

<!-- @id:[FSD]-ait-version:version_manager -->
## version_manager
### 功能描述
VersionManager 编排版本全生命周期：三态流转、commit 锁定、原子 confirm（precheck〔task/git/去重/**六不变式门禁**〕→backup→merge→extract→specgraph 提升→git commit，失败 restore 字节级回退）、reset 物理删除。详见 [TDD]-version_manager。

<!-- @id:[FSD]-ait-version:merge_engine -->
## merge_engine
### 功能描述
纯 chunk 级合并：按 baseline 真实存在性逐 chunk 处理 add/modify/delete，modify=全替换、目标不存在则当 add、绝不丢 chunk。详见 [TDD]-merge_engine。
