<!-- @id:[TDD]-new_model_validator -->
## new_model_validator TDD

```yaml
target_file: skill/ait/ait/new_model_validator.py
```

### 技术栈
Python 3.10+；依赖 `specgraph`(Edge/Spec/SpecGraph/CombinedView)。纯函数校验（不读盘、不写盘）。

### 常量
`ALLOWED_RELS={decomposes,details,depends_on}`；`NEW_MODEL_TYPES={prd,fsd,tdd}`；`NEW_MODEL_PREFIXES=("[PRD]-","[FSD]-","[TDD]-")`。

### 数据结构
`@dataclass(frozen=True) NewModelViolation{code,message,chunk_id?,file?,rel?,src?,dst?}`。

### 代码结构
- `validate_prd_fsd_tdd_graph(graph)->list[NewModelViolation]`：遍历 edges；端点缺失且 rel∈ALLOWED→`MISSING_ENDPOINT`；非新模型 spec 跳过；rel 不在 ALLOWED→`UNSUPPORTED_RELATION`；按 rel 分派 `_validate_decomposes/_validate_details/_validate_depends_on`；累积 `child_kinds_by_parent`（internal split 的 fsd/tdd 子类型）；最后 `{fsd,tdd}` 同父 → `FSD_MIXED_CHILDREN`。
- **`validate_invariants(view: CombinedView, target_files: list[tuple[str,str|None]]) -> list[NewModelViolation]`——六不变式全局门禁（confirm 前对 baseline∪版本组合视图全量执行）**：
  - ①每个 PRD 节点沿 decomposes 出边恰关联 1 个 FSD，≠1（含 0）→ `PRD_FSD_LINK_NOT_UNIQUE`；
  - ②每个 TDD 节点 details 入边 >1 → `TDD_MULTI_PARENT`（0 的情形由⑥ `TRACE_BROKEN` 覆盖）；
  - ③target_files 归一化后同一制品路径多属主 → `DUPLICATE_TARGET_FILE`；缺 target_file 的 TDD → `TDD_TARGET_FILE_REQUIRED`；
  - ④关联经 chunk：增量悬空由写时 `check_edge_write` 拦；**存量悬空不经视图（CombinedView 按契约丢弃悬空边）——由 confirm 门禁并行执行 `validate_prd_fsd_tdd_graph`(原始合并图) 的 `MISSING_ENDPOINT` 兜底**；
  - ⑤从全部 PRD 根出发沿 decomposes/details 边＋id 结构子下行，不可达的新模型节点 → `ORPHAN_CHUNK`；
  - ⑥每个 TDD 沿 details 入边→split→结构根→decomposes 入边上溯，不达任一 PRD → `TRACE_BROKEN`；
  - 另：**树关系环检测在合成下行图上做——decomposes/details 边 ∪ id 结构通道（根→冒号 split）**，Kahn 残差非空 → `SPEC_CYCLE`（环节点入 message）；纯边视角看不见穿过结构通道的环（audit R2-01 的崩溃图 `top:a→mid`+`mid:b→top` 即此形态）；**depends_on 环不作门禁**——侧向依赖在域级聚合下现实互指（本项目基线即含 version↔task↔indexing 互依，源自真实 import 导出）、六不变式不含其无环性、且当前无删边命令，硬拦即终态陷阱；depends_on 环经 view.detect_cycle 保持可诊断（R2-02 能力仍在）；
  - **视图中无新模型节点时返回空（vacuous pass，legacy 项目不受影响）**。
- **`check_edge_write(view, src, dst, rel) -> list[NewModelViolation]`——写时局部门禁（add_edge 落盘前）**：只拦"永远不该合法存在"的增量——src/dst 不在视图 → `MISSING_ENDPOINT`；rel=details 且 dst 已有来自其他 src 的 details 入边 → `TDD_MULTI_PARENT`；rel=decomposes 且 src 为 PRD 且已有 decomposes 出边指向其他 FSD → `PRD_FSD_LINK_NOT_UNIQUE`。全局完整性（孤儿/断链/环）**不在写时查**——构建期图暂不完整是合法态，归 confirm 门禁。
- **`normalize_target_file(path) -> str`**：反斜杠→posix、去 `./` 前缀、折叠 `..` 段、casefold——`./src\X.py` 与 `src/x.py` 判同一制品。
- `validate_target_file_uniqueness(entries:list[(chunk_id,file,target_file)])`：按 **normalize_target_file 后**的 target_file 分组，>1 owner → `DUPLICATE_TARGET_FILE`（列冲突 chunk id）。
- `violations_to_details(violations)->list[dict]`。
- 判定辅助：`_is_new_model_spec`(type∈NEW_MODEL_TYPES 且 chunk_id 前缀)、`_is_root_chunk`(无 ":" 且 file_stem==chunk_id)、`_is_internal_split`(fsd 且含 ":" 且 parent==file_stem)、`_parent_chunk_id/_file_stem/_find_spec_by_chunk_id/_violation`。

### 错误码
`MISSING_ENDPOINT`、`UNSUPPORTED_RELATION`、`INVALID_PRD_DECOMPOSES`、`INVALID_FSD_DECOMPOSES`、`INVALID_DECOMPOSES_TYPES`、`INVALID_DETAILS`、`INVALID_DEPENDS_ON_TYPES`、`DEPENDS_ON_ROOT_CHUNK`、`DEPENDS_ON_CROSS_LEVEL`、`FSD_MIXED_CHILDREN`、`DUPLICATE_TARGET_FILE`、`TDD_TARGET_FILE_REQUIRED`、**`PRD_FSD_LINK_NOT_UNIQUE`、`TDD_MULTI_PARENT`、`ORPHAN_CHUNK`、`TRACE_BROKEN`、`SPEC_CYCLE`**。

### 边界条件
六不变式与错误码的映射：①PRD↔1FSD=`PRD_FSD_LINK_NOT_UNIQUE`；②TDD 上=1FSD=`TDD_MULTI_PARENT`+`TRACE_BROKEN`(0父)，下=1制品=`TDD_TARGET_FILE_REQUIRED`；③制品↔1TDD=`DUPLICATE_TARGET_FILE`；④关联经 chunk=`MISSING_ENDPOINT`；⑤无孤儿=`ORPHAN_CHUNK`；⑥可追溯=`TRACE_BROKEN`。冒号 split 与其根的隶属是 id 结构关系（无显式边），⑤⑥遍历必须含结构通道。

### 单元测试要求
`tests/test_new_model_validator.py`：各关系合法/非法、FSD 混子、depends_on 跨级、target_file 重复与不重复；**六不变式各一正一反（合规图空违例/违例图报对应码）；归一化查重（分隔符/./大小写变体判重）；check_edge_write 三种拒绝；空新模型图 vacuous pass；SPEC_CYCLE 对合并后才成环（R2-02）报出**。pytest。
