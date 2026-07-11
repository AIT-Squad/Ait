<!-- @id:[FSD]-ait-version -->
## version FSD

### 功能范围

版本生命周期与基线合并：版本创建/三态提交(working→staged→committed)/锁定/原子 confirm(两阶段+回退)/reset；chunk 级 merge。版本是「全有或全无」原子单元。**confirm 是新模型六不变式的全局权威闸口。新模型主线命令四件套 create/confirm/merge/revert。**

### 交互契约

- 生命周期：`create/ensure/list_versions/current`；meta 读写。**create/ensure 不预建 legacy prd/impl 子目录（工作区子目录按需创建）。**
- 三态：`add_chunk(upsert)/remove_chunk/stage/unstage/commit/status`。
- 锁定：`lock_prd/lock_impl/assert_*_writable/set_title`。
- 门禁：`gate(version)`——纯校验报告（merged 拒绝、task done、去重、六不变式），可重复跑、零落盘、不合入；CLI `version confirm` 映射之。
- 合并：`pre_merge_check/merge/confirm`（confirm 守卫 task 全 done + git 干净 + **新模型六不变式门禁（组合视图全量 validate_invariants，违例 INVARIANT_VIOLATION 拒于任何落盘之前，legacy 项目 vacuous 过）** → 合入基线 → 提取动态 global → 提升 specgraph → git commit；失败回退——docs 与 .meta 关键状态字节级还原）；CLI `version merge` 映射 confirm。
- 逃生：`reset(--confirm)` 物理清空版本；CLI `version revert` 映射之。

<!-- @id:[FSD]-ait-version:version_manager -->
## version_manager
### 功能描述
VersionManager 编排版本全生命周期：三态流转、commit 锁定、纯门禁 gate（可重复跑零落盘）、原子 confirm（precheck〔task/git/去重/**六不变式门禁**〕→backup→merge→extract→specgraph 提升→git commit，失败 restore 字节级回退）、reset 物理删除。create/ensure 只建 meta+index，工作区子目录按需创建。详见 [TDD]-version_manager。

<!-- @id:[FSD]-ait-version:merge_engine -->
## merge_engine
### 功能描述
纯 chunk 级合并：按 baseline 真实存在性逐 chunk 处理 add/modify/delete，modify=全替换、目标不存在则当 add、绝不丢 chunk。详见 [TDD]-merge_engine。
