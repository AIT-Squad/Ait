<!-- @id:[TDD]-version_manager -->
## version_manager TDD

```yaml
target_file: skill/ait/ait/version_manager.py
```

### 技术栈
Python 3.10+；依赖 `schemas`(VersionMeta/VersionIndex/VersionChunkEntry/CommitEntry/ChangeRecord 等)、`yaml_io.save_model`、`merge_engine`(merge_file/merge_new_file/VersionChunkOp/MergedFile)、`chunk_parser`(parse_file/parse_text/Chunk)、`hash_utils.chunk_hash`、`index_manager.IndexManager`、`io_utils.atomic_write_text`、`git`(subprocess)。

### 实现约束
三态 working→staged→committed；commit 即锁定（本版本不可改）；版本原子（confirm 全有或全无，失败回退）；reset 物理删除不留快照。

### 数据结构（@dataclass）
`StageResult{staged,skipped:list[(id,reason)]}`、`UnstageResult{unstaged,not_found}`、`CommitResult{commit_id,changes:list[chg]}`、`StatusReport{version,working,staged,committed,by_action}`、`ConflictReport{chunk_id,reason,recorded_hash,current_hash}`、`MergeResult{merged_chunks,conflicts,skipped,status}`。`VersionManagerError(Exception){code="VERSION_ERROR"}`。

### 代码结构（VersionManager 方法，按职责）
- **生命周期**：`version_meta_path/load_version_meta/save_version_meta`；`create(version,based_on)`（建 prd/impl 目录+meta+空 index，目录已存在则报错）；`ensure(version)`（meta 存在则 no-op，否则建——容忍目录已存在，新模型 create 用）；`list_versions`；`current`（最新未 merged）。
- **chunk 变更**：`add_chunk(chunk,action,overrides,insert_after,base_hash,source_req)` upsert——同 id 在 working 则就地替换、在 staged/committed 则抛 `CHUNK_LOCKED`、否则尾插；写 summary（≤120）；`remove_chunk`。
- **三态**：`stage(version,chunk_ids=None)`（None=全部 working→staged）；`unstage`；`commit(version,message,req_id)`（staged→committed，建 CommitEntry + ChangeRecord，无 staged 报错）；`status`。
- **锁定**：`lock_prd/lock_impl`（置 phase/标志）；`assert_prd_writable/assert_impl_writable`（锁后抛 LOCKED）；`set_title`。
- **reset**：`reset(version,*,confirmed)`（二次确认，rmtree 版本目录 + 删 meta/index，merged 不可 reset）。
- **校验**：`pre_merge_check`、`_detect_intra_version_dup`（同 @id / 同 @extract 目标重复）。
- **合并**：`merge(version,conflict_policy)`——读 committed records，按 file_key 分组，legacy PRD 路由到 docs/prd/global（`_should_route_legacy_prd_to_global`），每文件构造 `VersionChunkOp` 调 merge_file/merge_new_file 写回；`_merge_one_file`、`_with_atomic_impl_deletes`。
- **confirm**：`confirm(version,*,allow_dirty_git=False)`——**phase1 precheck**：所有 task done 否则 `TASK_NOT_DONE`；git 干净否则 `GIT_DIRTY`；`_assert_no_duplicate_adds`。**phase2 merge（可逆）**：`_backup_docs`→`merge`→`_extract_dynamic_global`（变了则 rebuild_baseline+sync_specgraph）→`_merge_specgraph_to_baseline`→`_assert_no_orphan_impl_refs`。**phase3**：`_git_commit(title or "AIT v.. merge")`。任一步失败 `_restore_docs(backup)` 并抛 `MERGE_ROLLBACK`。成功写 merged 状态进同一 commit。
- **内部**：`_backup_docs/_restore_docs`（docs/ 快照与还原）、`_extract_dynamic_global`(+`_upsert_global_chunk`，从 impl @extract 提取 ddl/schema/api)、`_merge_specgraph_to_baseline`(提升 decomposes/details/depends_on 边)、`_assert_no_orphan_impl_refs`、`_assert_no_duplicate_adds`(同 id add 两次→`DUPLICATE_BASELINE_CHUNK`)、`_git_clean/_git_commit`、`_create_snapshot`、`_next_chg_id/_build_change_record`、`write_version_file/read_version_file/chunk_hash_in_version`。

### 错误码
`TASK_NOT_DONE`、`GIT_DIRTY`、`MERGE_ROLLBACK`、`CHUNK_LOCKED`、`LOCKED`、`DUPLICATE_BASELINE_CHUNK`、`VERSION_ERROR`。

### 边界条件
merged 版本不可再 confirm/reset；confirm 成功后 git 无脏尾（merged 状态文件并入同一 merge commit）；零 task 时 precheck 通过（taskless 新模型）。

### 单元测试要求
`tests/test_version_manager.py`、`test_version_confirm*.py`、`test_merge_workflow.py`、`test_v22_new_model_lifecycle.py`：三态/锁定、confirm 两阶段成功与回退、reset、duplicate add 拦截、taskless confirm。pytest。
