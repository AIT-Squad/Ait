<!-- @id:[TDD]-init_manager -->
## init_manager TDD

```yaml
target_file: skill/ait/ait/init_manager.py
```

### 技术栈
Python 3.10+；os/stat/re/pathlib、yaml；依赖 IndexManager、io_utils.atomic_write_text、VersionManager、specgraph.sync_specgraph。

### 数据结构
InitManagerError(RuntimeError){code}；@dataclass InitResult{created_files,chunks,specs,skill_dir,cli_path,wrapper_path,status(fresh/incomplete/ready),files,skipped}。常量 _STATIC_GLOBALS/_DYNAMIC_GLOBALS/GLOBAL_FILES/_GLOBAL_ID_RE。

### 代码结构（InitManager）
- run(*,check_only,skip,new_model,project_name)：new_model→_run_new_model_bootstrap；否则按 _scan_global_state(fresh/incomplete/ready) 选 _run_full_bootstrap/_run_incremental，ready 仅刷 wrapper。
- _run_full_bootstrap：写 static globals(overview/tech-stack)+dynamic 骨架(ddl/schema/api)+prd/impl README；rebuild_baseline+sync_specgraph；_mark_initialized+_write_project_wrapper。
- _run_new_model_bootstrap(project_name)：建 docs/{prd,fsd,tdd}；写 [PRD]-name(含 @ref decomposes 根 FSD)、[FSD]-name 根、tdd/README；rebuild+sync；幂等(已存在不覆盖)。
- _run_incremental：只补 missing/skeleton globals，honor skip 占位。
- refresh_wrapper / _mark_initialized(force_paths)(写 config.yaml skill_dir/cli_path) / _write_project_wrapper(cli_path) / _classify_global_file / _scan_global_state / has_any_version / _rel。

### 错误码 INIT_FAILED。

### 单元测试要求
tests/test_install_py.py 及 init/new-model 相关：fresh/incremental/new-model bootstrap、幂等、decomposes 边、refresh-wrapper。pytest。
