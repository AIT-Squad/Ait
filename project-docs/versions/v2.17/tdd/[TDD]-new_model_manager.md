<!-- @id:[TDD]-new_model_manager -->
## new_model_manager TDD

```yaml
target_file: skill/ait/ait/new_model_manager.py
```

### 技术栈
Python 3.10+；依赖 `chunk_parser`(parse_file/parse_text/Chunk)、`index_manager.IndexManager`、`specgraph`(combined_specgraph/load_specgraph/resolve_chunk_uri/specgraph_path/sync_specgraph)、`validator`(ValidationError/ValidationIssue)、`version_manager.VersionManager`。

### 常量
`TARGET_FILE_RE = ^\s*target_file:\s*(\S+)\s*$`(MULTILINE)；`NEW_MODEL_RELS = {decomposes,details,depends_on}`。

### 数据结构（@dataclass(frozen=True)）
`DocumentCreateResult{version,file,chunks:list[str],path}`、`EdgeCreateResult{version,src,dst,rel}`、`CodegenBundle{version,tdd_root,target_file,source_file,chunks:list[dict],upstream:list[dict],dependencies:list[dict]}`。

### 代码结构（NewModelManager）
- `__init__(project_root)`：self.root/versions(VersionManager)/indexes(IndexManager)。
- `create_fsd/create_tdd/create_prd(version,root_chunk_id,content,*,file=None,action="add",overrides=None)`：均委托 `_create_document(kind)`；`create_tdd` 先校验含 target_file（否则 `TDD_TARGET_FILE_REQUIRED`）。
- `add_edge(version,src,dst,rel)`：rel 不在 NEW_MODEL_RELS → `INVALID_NEW_MODEL_REL`；combined 图解析 src/dst URI；load 版本图 add_edge(metadata source="new-model-cli") save。
- `prepare_codegen(version,tdd_root)`：version=None 直接 baseline 解析；否则 query_version 缺则回退 baseline；读 target_file（root.content 或全文）缺→`TDD_TARGET_FILE_REQUIRED`；combined 图解析 tdd_uri→`_collect_upstream_context`→`_collect_dependency_context(graph, upstream)`（传整条上溯链）；返回 CodegenBundle。
- `_collect_upstream_context(graph,tdd_uri)`：找 incoming details 的 src(父 split)→append→父根(_parent_chunk_id)→`_walk_upstream_roots`(沿 decomposes 反向递归上溯 FSD/PRD)。
- `_collect_dependency_context(graph, upstream)`：从**上溯链里所有 fsd internal split**（含模块 split 与域 split [FSD]-ait:X）出发收集 depends_on 边 → 依赖的兄弟 split + 其 decomposes/details 子，去重。**关键：依赖边在域 split 层（同父约束），故须爬到域层而非只看父模块 split，否则依赖契约为空。**
- `_append_context_item/_context_item_for_spec`(读文件取 chunk 内容)/`_find_spec_by_chunk_id`(优先 version 再 baseline)。
- `collect_tdd_target_files(graph)`：遍历 type=tdd 且根(file stem==chunk id)，version 优先去重，读 target_file → list[(id,file,target_file)]；`_read_target_file_for_spec`。
- `_create_document(version,root_chunk_id,content,*,kind,file,action,overrides)`：file 缺省 `{kind}/{root_chunk_id}`；parse_text 校验含 root chunk（否则 `ROOT_CHUNK_REQUIRED`）；`self.versions.ensure(version)`；write_version_file；re-parse；逐 chunk add_chunk（overrides 仅给 root）；sync_specgraph。

### 模块函数
`_target_file(text)`(正则)、`_parent_chunk_id`(split ":" 前)、`_file_stem`(rsplit "/")、`_validation_error(code,message,chunk_id)`。

### 错误码
`TDD_TARGET_FILE_REQUIRED`、`INVALID_NEW_MODEL_REL`、`TDD_NOT_FOUND`、`ROOT_CHUNK_REQUIRED`。

### 单元测试要求
`tests/test_new_model_commands.py`、`test_new_model_merge.py`、`test_v21_toolchain.py`、`test_v22_new_model_lifecycle.py`：create_prd/fsd/tdd、add_edge 三关系、prepare_codegen 上溯+baseline 回退、collect_tdd_target_files。pytest。
