<!-- @id:[TDD]-new_model_manager -->
## new_model_manager TDD

```yaml
target_file: skill/ait/ait/new_model_manager.py
```

### 技术栈
Python 3.10+；依赖 `chunk_parser`(parse_file/parse_text/Chunk)、`index_manager.IndexManager`、`specgraph`(combined_view/combined_specgraph/load_specgraph/resolve_chunk_uri/specgraph_path/sync_specgraph)、`validator`(ValidationError/ValidationIssue)、`version_manager.VersionManager`。

### 常量
`TARGET_FILE_RE = ^\s*target_file:\s*(\S+)\s*$`(MULTILINE)；`NEW_MODEL_RELS = {decomposes,details,depends_on}`。

### 数据结构（@dataclass(frozen=True)）
`DocumentCreateResult{version,file,chunks:list[str],path}`、`EdgeCreateResult{version,src,dst,rel}`、`CodegenBundle{version,tdd_root,target_file,source_file,chunks:list[dict],upstream:list[dict],dependencies:list[dict]}`。

### 代码结构（NewModelManager）
- `__init__(project_root)`：self.root/versions(VersionManager)/indexes(IndexManager)。
- `create_fsd/create_tdd/create_prd(version,root_chunk_id,content,*,file=None,action="add",overrides=None)`：均委托 `_create_document(kind)`；`create_tdd` 先校验含 target_file（否则 `TDD_TARGET_FILE_REQUIRED`）。
- `add_edge(version,src,dst,rel)`：rel 不在 NEW_MODEL_RELS → `INVALID_NEW_MODEL_REL`；combined 图解析 src/dst URI；load 版本图 add_edge(metadata source="new-model-cli") save。
- `prepare_codegen(version,tdd_root)`：version=None 直接 baseline 解析；否则 query_version 缺则回退 baseline；读 target_file（root.content 或全文）缺→`TDD_TARGET_FILE_REQUIRED`；**view=combined_view(root,version)**（chunk_id 世界）→`_collect_upstream_context(view,tdd_root)`→`_collect_dependency_context(view, upstream)`（传整条上溯链）；返回 CodegenBundle。**被 modify 进版本的 TDD 保有 baseline 期全部关系——上溯链与依赖完整（v2.18 发现的 URI 二象性缺口在此消除）**。
- `_collect_upstream_context(view,tdd_chunk_id)`：view.edges_to(tdd_id,"details") 取父 split→append→父根(_parent_chunk_id)——父根仅在未访问过（不在 seen）时收集并下钻→`_walk_upstream_roots`。seen 为 chunk_id 集合。
- `_walk_upstream_roots(view,root_chunk_id,items,seen)`：沿 view.edges_to(root,"decomposes") 反向递归上溯 FSD/PRD；**seen 双职：去重收集＋递归门——src 或其父根已在 seen 则不再收集也不再下钻**；decomposes 环/自环下不抛 RecursionError，每个节点至多收集一次，上下文按首次访问序收敛。
- `_collect_dependency_context(view, upstream)`：从**上溯链里所有 fsd internal split**（含模块 split 与域 split [FSD]-ait:X）出发沿 view.edges_from(split,"depends_on") 收集 → 依赖的兄弟 split + 其 decomposes/details 子，去重。**关键：依赖边在域 split 层（同父约束），故须爬到域层而非只看父模块 split，否则依赖契约为空。**
- `_append_context_item(items,seen,node)`（seen 按 chunk_id 去重）/`_context_item_for_node`(按 ViewNode.version/file 读内容：version≠"baseline" 读 versions/{v}/{file}.md，否则 docs/{file}.md)/`_find_spec_by_chunk_id`(旧 URI 查询保留供 legacy 路径)。
- `collect_tdd_target_files(graph)`：遍历 type=tdd 且根(file stem==chunk id)，version 优先去重，读 target_file → list[(id,file,target_file)]；`_read_target_file_for_spec`。
- `_create_document(version,root_chunk_id,content,*,kind,file,action,overrides)`：file 缺省 `{kind}/{root_chunk_id}`；parse_text 校验含 root chunk（否则 `ROOT_CHUNK_REQUIRED`）；`self.versions.ensure(version)`；write_version_file；re-parse；逐 chunk add_chunk（overrides 仅给 root）；sync_specgraph。

### 模块函数
`_target_file(text)`(正则)、`_parent_chunk_id`(split ":" 前)、`_file_stem`(rsplit "/")、`_validation_error(code,message,chunk_id)`。

### 错误码
`TDD_TARGET_FILE_REQUIRED`、`INVALID_NEW_MODEL_REL`、`TDD_NOT_FOUND`、`ROOT_CHUNK_REQUIRED`。

### 边界条件
specgraph 中 decomposes 存在环（含自环 `X decomposes X` 与互指环）时，`prepare_codegen` 正常返回——环上节点各收集一次、不抛 RecursionError（修复前该场景递归爆栈，审计 R2-01）；上溯链断裂（details 缺失或父根不存在）时返回已收集部分，不报错；**对 modify 进版本的 TDD，upstream/dependencies 与该 chunk 在 baseline 时等同（内容来源换为版本文件）**。

### 单元测试要求
`tests/test_new_model_commands.py`、`test_new_model_merge.py`、`test_v21_toolchain.py`、`test_v22_new_model_lifecycle.py`：create_prd/fsd/tdd、add_edge 三关系、prepare_codegen 上溯+baseline 回退、collect_tdd_target_files；prepare_codegen 对 decomposes 环图与自环的上溯短路（不爆栈、每节点至多一次）；**回归：TDD 经 --action modify 进版本后 prepare_codegen(version) 的 upstream 为完整链、dependencies 非空（v2.18 缺口）**。pytest。
