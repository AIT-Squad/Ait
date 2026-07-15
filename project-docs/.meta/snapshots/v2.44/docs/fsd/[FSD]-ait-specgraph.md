<!-- @id:[FSD]-ait-specgraph -->
## specgraph 内部分解

### 功能描述
specgraph 域的实现分解。该域是块间关系的权威存储与查询层(取代早期 links-index):以 spec/edge 模型记录 PRD/FSD/TDD chunk 之间的 decomposes/details/depends_on/implements 关系,提供从 markdown @ref 重建、保留命令建的显式边、依赖/影响/成环查询、组合视图(把 baseline∪版本坍缩到 chunk_id 世界供跨版本统一查询)。它是 codegen 上溯、deps/impact 查询、六不变式校验的关系数据来源。实现拆为三个文件:specgraph(图模型与组合视图内核)、deps(依赖查询命令)、impact(影响分析命令)。

### 反向要求
- 不记录 chunk 自身状态(action/state/统计归 indexing 域,本域只管块间关系)。
- 不强制六不变式(校验归 new_model 域的校验器,本域只提供查询能力供其消费)。
- 不解析 markdown 语法(委托 doc_model)、不做原子写(委托 foundation)。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 specgraph 域块,本文件是内部实现分解)。

### 分解视图
- specgraph 叶(details → [TDD]-specgraph):图模型、URI 体系、组合视图内核
- deps 叶(details → [TDD]-deps):依赖关系查询命令
- impact 叶(details → [TDD]-impact):下游影响分析命令

<!-- @id:[FSD]-ait-specgraph:specgraph -->
## specgraph
### 功能描述
关系图核心。SpecGraph 持有 specs(节点)与 edges(边),节点 URI 形如 spec:{type}:{version}:{chunk_id}。sync_specgraph 从所有 docs/version markdown 的 @ref 重建图,并经 _preserve_explicit_edges 保留命令写入的显式边(source 标记的 decomposes/details/depends_on),使 reindex 不丢关系。CombinedView 在读取时把 baseline∪版本坍缩到 chunk_id 世界(存储格式不变、无数据迁移):同一 chunk_id 版本覆盖 baseline(modify 换内容来源)、边端点坍缩为 chunk_id 并去重;depends_on 按 owned-scope 覆盖(版本内出现的 FSD 根,其兄弟依赖边以版本为准,声明删除立即生效);消除 URI 二象性使被 modify 的 chunk 保有其 baseline 期全部关系。成环检测在坍缩视图上做,合并后才成环的图在合并前即可报出。公开面:load_specgraph/combined_specgraph/combined_view/sync_specgraph/resolve_chunk_uri/add_edge,以及 SpecGraph 的 query/dependencies/implementations/impacted/detect_cycle/implements_of/dry_run_merge/merge_into_baseline 与 CombinedView 的 edges_from/edges_to/impacted/detect_cycle。

### 反向要求
- 不判定关系是否合法(六不变式/基数约束归 new_model 校验器,本层只忠实存取)。
- 不写业务文档(只维护 .meta 下的关系图文件)。

<!-- @id:[FSD]-ait-specgraph:deps -->
## deps
### 功能描述
依赖关系查询。`query_deps(project_root, target, *, direction="both") -> dict`:在当前版本的组合视图上,按 chunk_id 解析 target,返回其关系边——direction=out 取出边、in 取入边、both 取两者并去重;返回 {target, direction, edges}(每条边含 src/dst/rel,端点均为 chunk_id)。被 modify 进版本的 chunk 也能查到其全部既有关系(组合视图消除 URI 二象性)。

### 反向要求
- 不建边、不改图(只读查询)。
- 不做传递闭包(单跳邻接边;下游闭包归 impact)。

<!-- @id:[FSD]-ait-specgraph:impact -->
## impact
### 功能描述
下游影响分析。`analyze_impact(project_root, target) -> dict`:在当前版本组合视图上求 target 的影响传递闭包——正向 decomposes/details 边 ＋ id 结构子(冒号 split 隶属其根)＋ 反向 depends_on/implements(依赖方),供迭代流转"沿关联逐层向下改"定位波及面。target 不在图中返回 {found: false, impacted: [], count: 0};在图中返回 {found: true, impacted, count}。

### 反向要求
- 不建边、不改图(只读查询)。
- 不做修改编排(只报影响面,改哪些 chunk 由使用者决定)。

<!-- @id:[FSD]-ait-specgraph:TEST -->
## TEST 集成验收
specgraph 域所有部件(specgraph + deps + impact)合并到一起、作为整体的集成验收:
1. WHEN 从含 @ref 与命令显式边的 docs/ 调 sync_specgraph THEN 图被重建且显式边(decomposes/details/depends_on)经 _preserve_explicit_edges 保留不丢。
2. WHEN 某 chunk 被 modify 进一个版本、再在该版本的 combined_view 上查 THEN 该 chunk 保有其 baseline 期建立的全部关系(URI 二象性消除);删除了 depends_on 声明的 FSD 根,其兄弟依赖边在视图中立即消失。
3. WHEN 对某 chunk 调 query_deps(direction=out/in/both)THEN 返回对应方向的关系边、both 去重,端点均为 chunk_id。
4. WHEN 对某 PRD/FSD 调 analyze_impact THEN 返回沿 decomposes/details 正向 + id 结构子 + depends_on 反向的传递闭包;target 不在图返回 found:false。
5. WHEN baseline 与版本合并后才成环 THEN detect_cycle 在坍缩视图上报出该环(合并前即可发现)。
