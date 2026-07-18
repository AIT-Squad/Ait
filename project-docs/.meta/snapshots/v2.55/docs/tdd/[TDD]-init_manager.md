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
- `_validate_project_name(name)`(v2.28,R3-01/R3-03)：project_name 必须整体匹配 `[a-z0-9_]+(-[a-z0-9_]+)*`(小写字母/数字/下划线,短横分段;`[PRD]-{name}` 须落在 NEW_MODEL_CHUNK_ID 内),否则抛 `INVALID_PROJECT_NAME`——同时封堵 `/`、`..`、空格、大写、中文(既是幽灵空基线根因,也是路径穿越入口)。
- _run_new_model_bootstrap(project_name)：**先 _validate_project_name**；建 docs/{prd,fsd,tdd}；写 **[PRD]-name(正文零关系声明,不含 @ref)**、[FSD]-name 根、tdd/README；rebuild+sync；**v2.52：PRD→FSD 派生边 rel=derives（v2.31 起 sync 后在 baseline 图显式建边(按 chunk_id 查实际 URI，metadata source="new-model-cli"，经 _preserve_explicit_edges 跨 reindex 存活)——文档正文不再承载关系**；**兜底:rebuild 后基线必须含 [PRD]-name 与 [FSD]-name 两个根 chunk,否则抛 `BOOTSTRAP_FAILED`**;幂等(已存在不覆盖)。
- _run_incremental：只补 missing/skeleton globals，honor skip 占位。
- refresh_wrapper / _mark_initialized(force_paths)(写 config.yaml skill_dir/cli_path) / _write_project_wrapper(cli_path) / _classify_global_file / _scan_global_state / has_any_version / _rel。

### 错误码 INIT_FAILED、**INVALID_PROJECT_NAME、BOOTSTRAP_FAILED**。

- **白板 bootstrap(v2.54)**:run() 非 check_only 时先调 `_ensure_project_docs_skeleton()`——self.root(=<cwd>/project-docs)下 mkdir docs/ 与 .meta/{versions,changes}(exist_ok 幂等),再 `_ensure_empty_baseline_stores()` 与既有引导。使空目录 init 自建骨架、全流程从零可推进。
- **空基线保证(v2.53)**:run()(全部模式)结束前确保 .meta/chunks-index.yaml 与 .meta/specgraph.yaml 存在(缺则写空结构,已存在不动)——初始=现状为空的迭代,背景检索零分支。

- **`_ensure_docs_git_repo()(v2.55)`**:若 project-docs/.git 不存在执行 `git init`(cwd=self.root,subprocess);在宿主根 `.gitignore` 追加 `project-docs/`(先读现有内容,仅当行不存在才追加,原子写,若宿主无 .gitignore 则新建);在 project-docs/.gitignore 确保含 `versions/*/state.md` 行(同样幂等追加)。run() 调用顺序:_ensure_project_docs_skeleton → _ensure_docs_git_repo → _ensure_empty_baseline_stores。全部幂等。

### 单元测试要求
tests/test_install_py.py 及 init/new-model 相关：fresh/incremental/new-model bootstrap、幂等、derives 派生边、refresh-wrapper；**非法 name(大写/空格/中文/含 `/`/`..`)→INVALID_PROJECT_NAME、合法 name→chunks≥2 且根 chunk 落地、假 chunks==0 场景→BOOTSTRAP_FAILED；**v2.52：new-model bootstrap 后 PRD 正文不含 @ref、baseline 有 PRD→FSD **derives** 边(source=new-model-cli)**。pytest。
