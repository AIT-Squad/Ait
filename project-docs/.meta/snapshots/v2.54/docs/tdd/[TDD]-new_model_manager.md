<!-- @id:[TDD]-new_model_manager -->
## new_model_manager TDD

```yaml
target_file: skill/ait/ait/new_model_manager.py
```

### 技术栈
Python 3.10+；依赖 `chunk_parser`(parse_file/parse_text/Chunk)、`index_manager.IndexManager`、`specgraph`(combined_view/combined_specgraph/load_specgraph/resolve_chunk_uri/specgraph_path/sync_specgraph)、`new_model_validator`(check_edge_write/normalize_target_file/violations_to_details)、`validator`(ValidationError/ValidationIssue)、`version_manager.VersionManager`。

### 常量
`TARGET_FILE_RE = ^\s*target_file:\s*(\S+)\s*$`(MULTILINE)；`NEW_MODEL_RELS = {derives,decomposes,details,depends_on}`。

### 数据结构（@dataclass(frozen=True)）
`DocumentCreateResult{version,file,chunks:list[str],path}`、`EdgeCreateResult{version,src,dst,rel}`、`CodegenBundle{version,tdd_root,target_file,source_file,chunks:list[dict],upstream:list[dict],dependencies:list[dict]}`。

### 代码结构（FSD 依赖声明，v2.26）
- **依赖随内容申报、只入 specgraph（v2.31：文档正文零关系声明）**：FSD 冒号 split 的兄弟依赖在 split chunk 正文的 `depends_on: [...]` yaml 块里申报——这是**用完即走的建边输入指令**（不同于 `target_file` 的制品指向；depends_on 是 chunk↔chunk 关系，不得留在正文）。简写按同父解析（`store → {root_id}:store`），也接受完整 chunk_id 但须同父。**解析建边后，块从持久 markdown 剥离**——specgraph 是唯一权威存储，文档正文不承载任何关系声明。无独立 depend/link 命令。
- `_split_depends_on(chunk_content) -> list[str] | None`（**v2.32 语义细化**）：找含 `depends_on` 键的 yaml 围栏块；**无该块 → `None`（未申报,应保留现有边）;块存在但空/null → `[]`（显式清空）**;有项 → 列表。区分"未申报"与"显式清空"是 preserve 语义的基础。
- `_strip_depends_on_blocks(content) -> str`：从 markdown 正文删除含 `depends_on` 键的 yaml 围栏块（含分隔符与尾随空行；非 depends_on 的 yaml 块保留）。create_fsd 写盘前对内容执行，使持久 FSD 正文零关系声明。
- `_reconcile_sibling_depends_on(version, root_id, final_deps)`：把版本图中本文件全部兄弟 depends_on 边替换为 `final_deps`（删 src∈本文件 split 的旧边，按 `final_deps` 重建,metadata source="fsd-declaration",经 `_preserve_explicit_edges` 跨 reindex 存活）。**在 `_create_document` 的 sync_specgraph 之后执行**。`final_deps` 由 create_fsd 组装(见下),使版本图始终持有本文件的完整权威依赖集——combined_view 的 per-root 覆盖与 merge 对账逻辑因此零改动。
- 声明校验（写入前，拒绝＝零落盘）：声明指向文件内不存在的兄弟 → `DEPENDS_ON_UNKNOWN_SIBLING`；指向自己 → `DEPENDS_ON_SELF`；完整 id 跨父 → `DEPENDS_ON_CROSS_LEVEL`。

### 代码结构（NewModelManager）
- `__init__(project_root)`：self.root/versions(VersionManager)/indexes(IndexManager)。
- `create_tdd(version,root_chunk_id,content,*,file=None,action="add",overrides=None,parent_chunk_id=None)`：**tdd 层"创建即建 details 边"**——必含 target_file（否则 TDD_TARGET_FILE_REQUIRED）＋归一化 target_file 唯一属主门禁；给 `parent_chunk_id` 则①`_precheck_details_parent(view,parent,tdd_root)`（parent 不在视图→MISSING_ENDPOINT；tdd_root 已有来自他者的 details 入边→TDD_MULTI_PARENT）前置于写入②写 TDD 文档③`add_edge(parent,tdd_root,"details")` 建边（两端点在视图，check_edge_write 完整过）④phase 若为 fsd-confirm 推进为 tdd-creating。details 边只由 tdd create 原子建立（fsd link 已退役）。
- `create_fsd(version,root_chunk_id,content,*,file=None,action="add",overrides=None,parent_chunk_id=None)` / `create_prd(...)`：均委托 `_create_document(kind)`；**create_prd 是流转入口：写入后若 meta.phase ∈ {None,empty} 置为 `prd-creating`（阶段机起点）**；**create_fsd 给 `parent_chunk_id`(PRD 根)则"派生即建边":`_precheck_derives_parent(view,parent,fsd_root)`（parent 须为 PRD 根、已有 derives 出边指向他者→PRD_FSD_LINK_NOT_UNIQUE、parent 不在视图→MISSING_ENDPOINT）前置于写入,写盘后 `add_edge(parent,fsd_root,"derives")`——PRD→FSD 派生边只由此出生（取代旧 decompose 的 PRD 分支）；create_fsd 写入后若 phase 为 prd-confirm 则推进为 `fsd-creating`;顺序＝①解析校验声明(`declared`={有块的 split→deps,含空块=显式清空}) → ②`_strip_depends_on_blocks` 得净正文 → ③写盘前从 combined_view(baseline∪版本)采集"未申报 split"的现有 depends_on 作 `hydrated`(preserve 地基) → ④`_create_document`(写净正文+sync) → ⑤`final_deps = {**hydrated, **declared}`(declared 覆盖)→`_reconcile_sibling_depends_on`。**
  **v2.32 preserve 语义(核心):无 depends_on 块的 split 保留其现有边(hydrate);有块的 split 权威覆盖(含空块=清空)。⇒ 重排 FSD 内容(不带块)不再 wipe 依赖边——修 v2.31 的 round-trip footgun,是文档格式迁移的关键地基。改依赖=带块 modify;清空=显式 `depends_on: []`;不动=不带块**；`create_tdd` 先校验含 target_file（否则 `TDD_TARGET_FILE_REQUIRED`），**再做写时唯一性门禁：normalize_target_file 后与组合视图内既有 TDD 属主比对（经 `collect_tdd_target_files`），撞车且属主不是本 chunk（modify 自身豁免）→ `DUPLICATE_TARGET_FILE` 拒绝，不写入、可改路径重试**。
- `add_edge(version,src,dst,rel)`：**底层建边原语（不再直接暴露为 CLI；decomposes 归 `decompose_fsd`，link 命令退役）**。rel 不在 NEW_MODEL_RELS → `INVALID_NEW_MODEL_REL`；**写时局部门禁：view=combined_view(root,version)，`check_edge_write(view,src,dst,rel)` 有违例 → 以首条违例 code 抛 ValidationError（幽灵端点 `MISSING_ENDPOINT`／TDD 第二父 `TDD_MULTI_PARENT`／PRD 第二派生 FSD `PRD_FSD_LINK_NOT_UNIQUE`(rel=derives)），不落盘、修正后可重试**；通过后 combined 图解析 src/dst URI；load 版本图 add_edge(metadata source="new-model-cli") save。全局完整性（孤儿/断链/环）不在写时查，归 version confirm 门禁。
- `decompose_fsd(version, parent_chunk_id, child_root_chunk_id, *, content=None, file=None) -> EdgeCreateResult`：**FSD 层"拆分即建边"统一入口，取代 fsd link 的 decomposes 用法**。①`_precheck_decompose_parent(view,parent,child)`——parent 不在组合视图 → `MISSING_ENDPOINT`；parent 须为 FSD internal split（PRD 不再经 decompose——PRD→FSD 走 create_fsd --parent 的 derives；parent 为 PRD → `INVALID_DECOMPOSES_TYPES`）（父侧门禁前置于任何写入，保拒绝＝零落盘）；②content 非空 → `create_fsd(version, child_root, content, file=file)` 原子写子 FSD（走 create 全校验）；③`add_edge(version, parent, child_root, "decomposes")` 建边（此时两端点在视图，check_edge_write 完整过）；④phase 若为 prd-confirm 推进为 fsd-creating。rel 恒 decomposes 且仅限 FSD split→FSD 根（PRD 派生走 derives、details 归 tdd 层）。返回 EdgeCreateResult。
- `confirm_fsd_layer(version)`／`revert_fsd_layer(version)`：与 prd 层同构的冻结-返工对——confirm 锁全部 working 态 `[FSD]-` chunk（stage→commit）＋phase→fsd-confirm（无 FSD chunk→`NO_FSD_CHUNKS`）；revert 经 `versions.uncommit` 解锁 committed 态 `[FSD]-` chunk 回 working＋phase→fsd-creating（merged 拒）。
- `prepare_codegen(version,tdd_root)`：version=None 直接 baseline 解析；否则 query_version 缺则回退 baseline；读 target_file（root.content 或全文）缺→`TDD_TARGET_FILE_REQUIRED`；**view=combined_view(root,version)**（chunk_id 世界）→`_collect_upstream_context(view,tdd_root)`→`_collect_dependency_context(view, upstream)`（传整条上溯链）；返回 CodegenBundle。**被 modify 进版本的 TDD 保有 baseline 期全部关系——上溯链与依赖完整（v2.18 发现的 URI 二象性缺口在此消除）**。
- `_collect_upstream_context(view,tdd_chunk_id)`：view.edges_to(tdd_id,"details") 取父 split→append→父根(_parent_chunk_id)——父根仅在未访问过（不在 seen）时收集并下钻→`_walk_upstream_roots`。seen 为 chunk_id 集合。
- `_walk_upstream_roots(view,root_chunk_id,items,seen)`：沿 view.edges_to(root,"decomposes") 与 view.edges_to(root,"derives") 反向递归上溯 FSD/PRD（**FSD 根经 derives 入边上溯到 PRD、经 decomposes 入边上溯到父 FSD split**）；**seen 双职：去重收集＋递归门——src 或其父根已在 seen 则不再收集也不再下钻**；decomposes 环/自环下不抛 RecursionError，每个节点至多收集一次，上下文按首次访问序收敛。
- `_collect_dependency_context(view, upstream)`：从**上溯链里所有 fsd internal split**（含模块 split 与域 split [FSD]-ait:X）出发沿 view.edges_from(split,"depends_on") 收集 → 依赖的兄弟 split + 其 derives/decomposes/details 子，去重。**关键：依赖边在域 split 层（同父约束），故须爬到域层而非只看父模块 split，否则依赖契约为空。**
- `_append_context_item(items,seen,node)`（seen 按 chunk_id 去重）/`_context_item_for_node`(按 ViewNode.version/file 读内容：version≠"baseline" 读 versions/{v}/{file}.md，否则 docs/{file}.md)/`_find_spec_by_chunk_id`(旧 URI 查询保留供 legacy 路径)。
- `collect_tdd_target_files(graph)`：遍历 type=tdd 且根(file stem==chunk id)，version 优先去重，读 target_file → list[(id,file,target_file)]；`_read_target_file_for_spec`。
- `_create_document(version,root_chunk_id,content,*,kind,file,action,overrides)`：file 缺省 `{kind}/{root_chunk_id}`；parse_text 校验含 root chunk（否则 `ROOT_CHUNK_REQUIRED`）；**gap-4 收口:kind→前缀映射(prd→`[PRD]-`/fsd→`[FSD]-`/tdd→`[TDD]-`),root_chunk_id 与内容中每个 chunk id 必须以该前缀开头,否则 `CHUNK_ID_PREFIX_REQUIRED`(写盘前全量拦,零落盘可重试)——无前缀 chunk 会占 target_file/节点却逃六不变式取样(校验器 `_is_new_model_spec` 按前缀判新模型);****P7 全严格：所有层(含 prd)都要求版本 meta 已存在(无 auto-create、无幽灵)，缺→`VERSION_NOT_FOUND`。`version create` 是唯一版本入口**；**--file 路径清洗（审计 R3-02）：`_validated_index_path(file,kind)`——反斜杠→posix；拒绝空值/绝对路径/盘符/含 `..` 段/`.md` 后缀/以 `.` 开头 → `INVALID_FILE_NAME`；无斜杠简名补 `{kind}/` 前缀；必须落在自己 kind 目录下（跨 kind 拒），零落盘可重试**；write_version_file；re-parse；逐 chunk add_chunk（overrides 仅给 root）；sync_specgraph。

### 代码结构（TDD 层流转）
- `create_tdd(...,parent_chunk_id)`：见上（创建即建 details 边 + phase→tdd-creating）；`_precheck_details_parent(view,parent,tdd_root)`：父侧门禁前置（MISSING_ENDPOINT/TDD_MULTI_PARENT），拒绝＝零落盘。
- `confirm_tdd_layer(version)`/`revert_tdd_layer(version)`：与 prd/fsd 同构冻结-返工对——confirm 锁全部 working 态 `[TDD]-` chunk＋phase→tdd-confirm（无 TDD chunk→`NO_TDD_CHUNKS`）；revert 经 uncommit 解锁 committed 态 `[TDD]-` chunk＋phase→tdd-creating（merged 拒）。

### 代码结构（FSD 层流转）
- `decompose_fsd`/`confirm_fsd_layer`/`revert_fsd_layer`/`_precheck_decompose_parent`：见上（拆分即建边 + 层级冻结-返工对，phase 值 fsd-creating/fsd-confirm）。

### 代码结构（PRD 层流转）
- `confirm_prd_layer(version) -> dict`：版本内无 `[PRD]-` chunk → `NO_PRD_CHUNKS` 拒；把全部 working 态 PRD chunk stage→commit（锁定），meta.phase → `prd-confirm`；返回 {version, confirmed:[ids], phase}；幂等（已 committed 的 PRD 不重复处理，仍推进 phase）。
- `revert_prd_layer(version) -> dict`：**confirm 的成对返工**——committed 态 PRD chunk 经 `versions.uncommit` 回 working，meta.phase → `prd-creating`；merged 版本拒（`VERSION_ERROR`）；返回 {version, reverted:[ids], phase}。
- `next_version_name()`：扫描全部版本名 `v{major}.{minor}` 取最大后 minor+1；无任何版本 → `v0.1`。仍供计算下一版本名;**P7 后 CLI `prd create` 不再自动开版本——无活动版本报 `NO_ACTIVE_VERSION`，须先 `version create`**。

### 模块函数
`_target_file(text)`(正则)、`_parent_chunk_id`(split ":" 前)、`_file_stem`(rsplit "/")、`_validation_error(code,message,chunk_id)`。

- **P7 收(全严格)自顶向下门禁——每入口写盘前 `_require_phase(version, allowed, code, op)` 校验 `meta.phase`，不在 `allowed` 则拒(零落盘可重试)；版本不存在→`VERSION_NOT_FOUND`(无 auto-create)。add 与 modify 同等门禁**：
  - `create_prd` 需 phase∈{empty, prd-creating}，否则 `PRD_LAYER_CLOSED`(PRD 层已越过，先 `prd revert` 重开)；
  - `create_fsd`/`decompose_fsd` 需 phase∈{prd-confirm, fsd-creating}，否则 `PRD_NOT_CONFIRMED`；
  - `create_tdd` 需 phase∈{fsd-confirm, tdd-creating}，否则 `FSD_NOT_CONFIRMED`；
  - `prepare_codegen` 对活动版本需 phase==tdd-confirm，否则 `TDD_NOT_CONFIRMED`(version=None 或已 merged/不存在=baseline codegen，不门禁)；
  - `confirm_prd_layer`/`confirm_fsd_layer`/`confirm_tdd_layer` 分别需 phase==prd-creating/fsd-creating/tdd-creating，否则 `PRD_LAYER_NOT_OPEN`/`FSD_LAYER_NOT_OPEN`/`TDD_LAYER_NOT_OPEN`。
  死锁逃生：各层 revert(confirm→creating 回退) + `version revert`(整版清空)。迭代亦每版从 prd create 逐层向下。

- **`prepare_discussion(version, layer, target_id, parent_id=None) -> dict`(v2.53 迭代连续性)**:create 无内容时的讨论背景组装,零写入。发现式(layer∈{fsd,tdd},无 parent):anchors=版本 index 中上层前缀(fsd→`[PRD]-`、tdd→`[FSD]-`)的 add/modify chunk 全文;related=每锚点在 combined_view 上 edges_from+edges_to 一跳对端 chunk 全文(id 去重,含 rel 与方向);target=target_id 在视图中的既有全文(exists 标志)。锚定式(parent_id 给定,tdd --parent / decompose child 缺失):anchor=parent 全文;linked=parent 全部邻接对端全文;upstream=parent 沿 derives/decomposes/details 入边+结构根上溯至 PRD 的链全文;target 同上。prd 层:related=视图中全部 `[PRD]-` chunk 全文。chunk 内容提取:视图节点 file+version 定位文档,parse 后取该 chunk content(版本被 modify 的 chunk 自动取版本内容);整文件级 target 取该 file 全部 chunk 拼接。返回 {mode:'discussion-context', layer, anchors, related|linked+upstream, target}。CLI 三 create 无 --content/--content-file 时调用之(过同层 `_require_phase` 后、不写盘不动 phase);`fsd decompose` 无 content 且 child 不在视图时改走 prepare_discussion(原 MISSING_ENDPOINT 错误路径转有用;child 存在保持 link-only)。

### 错误码
`TDD_TARGET_FILE_REQUIRED`、`INVALID_NEW_MODEL_REL`、`TDD_NOT_FOUND`、`ROOT_CHUNK_REQUIRED`、`NO_PRD_CHUNKS`、`NO_FSD_CHUNKS`、`NO_TDD_CHUNKS`、**`VERSION_NOT_FOUND`、`DEPENDS_ON_UNKNOWN_SIBLING`、`DEPENDS_ON_SELF`、`INVALID_FILE_NAME`、`CHUNK_ID_PREFIX_REQUIRED`、`PRD_LAYER_CLOSED`、`PRD_NOT_CONFIRMED`、`FSD_NOT_CONFIRMED`、`TDD_NOT_CONFIRMED`、`PRD_LAYER_NOT_OPEN`、`FSD_LAYER_NOT_OPEN`、`TDD_LAYER_NOT_OPEN`**；写时门禁转发校验器码：`MISSING_ENDPOINT`、`TDD_MULTI_PARENT`、`PRD_FSD_LINK_NOT_UNIQUE`、`DUPLICATE_TARGET_FILE`、`DEPENDS_ON_CROSS_LEVEL`。

### 边界条件
specgraph 中 decomposes 存在环（含自环 `X decomposes X` 与互指环）时，`prepare_codegen` 正常返回——环上节点各收集一次、不抛 RecursionError（修复前该场景递归爆栈，审计 R2-01）；上溯链断裂（details 缺失或父根不存在）时返回已收集部分，不报错；**对 modify 进版本的 TDD，upstream/dependencies 与该 chunk 在 baseline 时等同（内容来源换为版本文件）**；**写时门禁拒绝＝零落盘（文档、索引、图均不写），修正入参即可重试，无终态陷阱**。

### 单元测试要求
`tests/test_new_model_commands.py`、`test_new_model_merge.py`、`test_v21_toolchain.py`、`test_v22_new_model_lifecycle.py`：create_prd/fsd/tdd、add_edge 三关系、prepare_codegen 上溯+baseline 回退、collect_tdd_target_files；prepare_codegen 对 decomposes 环图与自环的上溯短路（不爆栈、每节点至多一次）；回归：TDD 经 --action modify 进版本后 prepare_codegen(version) 的 upstream 为完整链、dependencies 非空（v2.18 缺口）；**写时门禁：add_edge 幽灵端点/TDD 第二 details 父/PRD 第二 derives 派生各拒绝且零落盘;PRD 走 decompose 报 INVALID_DECOMPOSES_TYPES、FSD split 走 create_fsd --parent(derives)报 INVALID_DERIVES、修正后重试成功；create_tdd 归一化撞车（`./`、反斜杠、大小写变体）拒绝、换路径重试成功、modify 自身同 target 豁免**；**PRD 层流转：create_prd 置 phase 起点、confirm_prd_layer 锁 PRD chunk+phase、revert_prd_layer 解锁回 working+phase 回退、merged 拒 revert、next_version_name 递增与空库缺省**；**FSD 层：decompose_fsd 原子写子 FSD+建 decomposes 边、父侧预检拒绝时零落盘、confirm/revert 冻结-返工、NO_FSD_CHUNKS**；**TDD 层：create_tdd --parent 原子建 details 边、TDD 第二父拒绝零落盘、幽灵 parent 拒绝、confirm_tdd_layer 锁 TDD chunk+phase→tdd-confirm、revert_tdd_layer 解锁+phase→tdd-creating、NO_TDD_CHUNKS；端到端 prd→fsd create --parent(derives)→fsd decompose→tdd create --parent→codegen prepare 上溯链非空(含 derives 上溯到 PRD)**；**依赖声明（v2.26）：声明→版本图生边（简写解析+完整 id）、未知兄弟/自依赖/跨父各拒且零落盘、modify 改声明→对账后新增边在删除边亡、同声明幂等、fsd/tdd create 对不存在版本报 VERSION_NOT_FOUND（prd 保留 ensure）**；**v2.32 preserve：modify 不带块→依赖边保留(不 wipe)、带块只覆盖该 split、显式 `[]` 清空该 split、`:TEST` 等新 split 无块=无边;含 `:TEST` chunk 的 FSD 过门禁(非孤儿、不误判)**；**--file 清洗：`../../x`、绝对路径、`x.md`、跨 kind（tdd create --file fsd/x）各拒且零落盘,简名补 kind 前缀成功**；**v2.31 文档正文零关系：create_fsd 传含 depends_on 块内容 → 持久 markdown 正文不含 `depends_on:`、但 specgraph 有对应边（声明→建边→剥离全链）；_strip_depends_on_blocks 只删 depends_on 块保留其它 yaml；改声明经重 modify 仍对账正确**；**gap-4 前缀强制:prd/fsd/tdd create 传无前缀 root id(如 `myfsd`)或内容含无前缀 chunk → `CHUNK_ID_PREFIX_REQUIRED` 零落盘,补前缀重试成功**;**讨论背景(v2.53):各层 create 无内容返回 mode=discussion-context 且零写入、phase 不动;fsd 发现式含 PRD 改动锚+一跳关联+target 现状;tdd --parent 锚定式含 parent/linked/upstream;decompose child 缺失返回背景、child 存在仍 link-only;空基线返回空背景(初始=空现状迭代)**；**P7 收全严格门禁:各层缺上层 confirm 时 create 被拒(PRD_NOT_CONFIRMED/FSD_NOT_CONFIRMED)、codegen 未 tdd-confirm 拒(TDD_NOT_CONFIRMED)、越层 prd create 拒(PRD_LAYER_CLOSED)、confirm 越相拒(*_LAYER_NOT_OPEN)、补齐分层后重试成功;prd create 无版本→NO_ACTIVE_VERSION、create_prd 不存在版本→VERSION_NOT_FOUND(无 auto-create)**。pytest。
