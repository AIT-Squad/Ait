<!-- @id:[FSD]-ait-new_model -->
## new_model 内部分解

### 功能描述
new_model 域的实现分解。该域是新模型主线(PRD→FSD→TDD→codegen)的引擎:创建三类文档、在写内容时原子建立关系边、校验图合法性与六不变式、为 codegen 组装上溯上下文。它把"文档如何被创建、关系如何出生、规格如何被校验、代码生成需要什么上下文"这四件事统一在一处。实现拆为两个文件:new_model_manager(文档创建与流转编排)与 new_model_validator(纯函数校验器)。

### 反向要求
- 不存储关系图(建边委托 specgraph 域的 add_edge 与 sync;本域只决定"何时建什么边")。
- 不解析 markdown 语法(委托 doc_model 域的 chunk_parser)、不做版本合并与门禁落盘(委托 version 域)。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 new_model 域块,本文件是内部实现分解)。

### 分解视图
- new_model_manager 叶(details → [TDD]-new_model_manager):文档创建、层级流转、codegen 上下文组装
- new_model_validator 叶(details → [TDD]-new_model_validator):纯函数图校验与写时门禁

<!-- @id:[FSD]-ait-new_model:new_model_manager -->
## new_model_manager
### 功能描述
NewModelManager 类,新模型三类文档的创建者与四层流转(PRD/FSD/TDD/codegen)的编排者。职责:create_prd/create_fsd/create_tdd 把文档写入版本工作区(解析→ensure 版本→写文件→注册 chunk→同步关系图);create_prd 是流转入口,置阶段机起点(phase→prd-creating),CLI 无活动版本时经 next_version_name 自动开版本;create_fsd 可带 parent_chunk_id(PRD 根):创建即建 derives 派生边(父侧预检:parent 须为 PRD 根且尚无 derives 出边,否则拒且零落盘),并解析 split 内 `depends_on` 声明块,建兄弟依赖边后从正文剥离(owned-scope 全量对账:该文件的兄弟依赖边完全由声明决定);create_tdd 可带 parent_chunk_id,创建即建 details 边(父侧预检:parent 不在视图报 MISSING_ENDPOINT、TDD 已有他者 details 入边报 TDD_MULTI_PARENT),且写入前按归一化路径做制品唯一属主门禁(撞车报 DUPLICATE_TARGET_FILE);decompose_fsd 拆分即建 decomposes 边(仅限 FSD split 为 parent——PRD→FSD 走 derives 不走 decompose;父侧预检后原子写子 FSD);三层各有 confirm_*_layer/revert_*_layer 冻结-返工对(锁定/解锁 chunk + 推进/回退 phase);add_edge 是底层建边原语,落盘前经 check_edge_write 局部门禁;prepare_codegen 在组合视图上溯 TDD→FSD→PRD 全链、旁取路径上的 depends_on 兄弟契约,组装 CodegenBundle(无活动版本回退 baseline)。fsd/tdd create 对不存在的版本报 VERSION_NOT_FOUND(prd create 保留自动开版本)。

**讨论背景组装(v2.53,迭代连续性原则的工具化)**:create_prd/create_fsd/create_tdd 在未提供内容时走 prepare_discussion 路径——沿组合视图(baseline∪活动版本)提取:上层在本版本的改动 chunk 全文(anchors,修改方向的载体)、每个锚点经边一跳关联的 chunk 全文(related,受波及现状)、目标 chunk 既有全文(target,演进而非新建);锚定式变体(tdd --parent / decompose child 缺失)以命名父块为中心:父块全文+全部邻接+上溯链+既有子。结构完整性(六不变式)是检索可靠性的前提;零写入、不动 phase、过同层相位门禁。

### 反向要求
- 不自己存关系边(委托 specgraph 的 add_edge/sync)、不自己算六不变式细节(委托 new_model_validator,本类只在写时/流转点调用并按结果拒绝)。
- 不做版本 commit/merge/门禁落盘(委托 version 域;本类只写版本工作区与推进 phase)。
- 不生成代码(prepare_codegen 只组装上下文包,实际编码由 skill 层驱动 AI 完成)。

<!-- @id:[FSD]-ait-new_model:new_model_validator -->
## new_model_validator
### 功能描述
纯函数校验器(不读盘、不写盘,输入图/视图输出违例列表),new_model 域的规则内核。提供:validate_prd_fsd_tdd_graph(图合法性——decomposes/details/depends_on 的类型与根-split 规则、FSD 不得混用 FSD 子与 TDD 子);normalize_target_file(路径归一化——分隔符/前导 ./ /大小写,用于制品判重);validate_target_file_uniqueness(归一化后同一制品被多 TDD 持有报 DUPLICATE_TARGET_FILE);check_edge_write(写时局部门禁——幽灵端点 MISSING_ENDPOINT、TDD 第二 details 父 TDD_MULTI_PARENT、PRD 第二 decomposes FSD PRD_FSD_LINK_NOT_UNIQUE);validate_invariants(六不变式全量校验,吃组合视图:①PRD↔恰1FSD(沿 derives 派生边判定) ②TDD 向上恰1FSD 入边且向下恰1制品 ③每制品恰1TDD 持有 ④关联经真实存在的 chunk ⑤除树根外无孤儿 chunk(下行遍历含 derives/decomposes/details 边+id 结构通道)⑥每制品沿 TDD→FSD→…→PRD 可追溯(上溯含 derives),违例分别 PRD_FSD_LINK_NOT_UNIQUE/TDD_MULTI_PARENT/DUPLICATE_TARGET_FILE/MISSING_ENDPOINT/ORPHAN_CHUNK/TRACE_BROKEN;另检 derives/decomposes/details 树关系环 SPEC_CYCLE);violations_to_details(违例转 CLI 输出结构)。孤儿与追溯遍历含 id 结构通道(冒号 split 隶属其根 chunk);视图无新模型节点时全部 vacuous 通过(legacy 项目零影响)。

### 反向要求
- 不读写磁盘、不改任何状态(纯函数,输入图/视图,输出违例列表;调用与拒绝由 manager/version 编排)。
- depends_on 环只诊断不作门禁(同父兄弟互依在现实中合法,只有 decomposes/details 树关系环才是 SPEC_CYCLE 硬违例)。
- 不建边、不创建文档(只判定,不产出制品)。

<!-- @id:[FSD]-ait-new_model:TEST -->
## TEST 集成验收
new_model 域所有部件(new_model_manager + new_model_validator)合并到一起、作为整体的集成验收:
1. WHEN 从空版本依次 create_prd → create_fsd --parent(派生)→ decompose_fsd(拆分)→ create_tdd --parent(细化)THEN 三类文档写入版本工作区,derives/decomposes/details 边各随其创建命令原子建立,phase 依次推进 prd-creating→fsd-creating→tdd-creating。
2. WHEN create_tdd 声明的 target_file 归一化后与既有 TDD 撞车 THEN 报 DUPLICATE_TARGET_FILE 拒于落盘前(改路径可重试);TDD 已有他者 details 父再挂一个报 TDD_MULTI_PARENT。
3. WHEN create_fsd 的 split 内声明 `depends_on: [兄弟]` THEN 建 depends_on 边并从正文剥离;改声明后重跑,该文件兄弟依赖边按新声明全量对账(旧边删、新边增)。
4. WHEN add_edge 的端点不存在 THEN 报 MISSING_ENDPOINT 零落盘;PRD 已 derives 一个 FSD 再派生第二个报 PRD_FSD_LINK_NOT_UNIQUE;decompose 以 PRD 为 parent 被拒(PRD→FSD 只走 derives)。
5. WHEN fsd/tdd create 指定不存在的版本 THEN 报 VERSION_NOT_FOUND;prd create 无活动版本则自动开版本。
6. WHEN 版本含孤儿 chunk 或断裂追溯链 THEN validate_invariants 报 ORPHAN_CHUNK/TRACE_BROKEN;合规则零违例(供 version confirm 全局门禁消费)。
7. WHEN prepare_codegen 指定一个 TDD THEN 返回 CodegenBundle,含该 TDD 内容 + 上溯 FSD/PRD 全链 + 路径上 depends_on 兄弟的契约(被 modify 进版本的 TDD 上下文完整)。
8. WHEN 任一层 create 未提供内容 THEN 返回该层讨论背景(anchors/related/target 全文)且零写入、phase 不动;基线为空时背景为空(初始=现状为空的迭代);锚定式(tdd --parent/decompose child 缺失)返回父块中心邻域。

