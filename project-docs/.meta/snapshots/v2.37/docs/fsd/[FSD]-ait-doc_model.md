<!-- @id:[FSD]-ait-doc_model -->
## doc_model 内部分解

### 功能描述
doc_model 域的实现分解。该域是文档模型基础设施:把 markdown 解析成 chunk/ref/extract 结构,并定义全部持久化数据的 pydantic schema。被所有上层域依赖——它是"文档如何被解析"与"数据长什么样"这两件事的单一权威来源。实现拆为两个文件:chunk_parser(markdown→结构化 chunk 解析)与 schemas(全部 .meta YAML 的 pydantic 模型)。

### 反向要求
- 不管理索引或关系图(解析产物如何入索引归 indexing 域、如何建关系归 specgraph 域)。
- 不做文件 IO 的原子写与路径守卫(归 foundation 域的 io_utils)。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 doc_model 域块,本文件是内部实现分解)。

### 分解视图
- chunk_parser 叶(details → [TDD]-chunk_parser):markdown 的 chunk 级解析
- schemas 叶(details → [TDD]-schemas):全部持久化数据的 pydantic 模型

<!-- @id:[FSD]-ait-doc_model:chunk_parser -->
## chunk_parser
### 功能描述
chunk 级 markdown 解析器。chunk 边界由 `<!-- @id:xxx -->` 注释而非标题层级决定。识别五类标记:@id(chunk 起点)、@ref(chunk 间关系引用)、@extract(动态 global 提取块)、@summary(chunk 摘要)、@prd-no-impl(标记无需实现)。code-fence(``` 或 ~~~)内的内容被屏蔽以避免把示例里的 @id/@ref 误当真标记。file_header 是首个 @id 之前的内容;@ref 归属它所在的 chunk;@extract 成对解析,嵌套或未闭合报 ExtractError。chunk id 同时支持 legacy 命名与 [PRD]/[FSD]/[TDD] 前缀两类。产出冻结数据类 ParsedFile(file, file_header, chunks, refs),其中 Chunk 带 id/heading/level/content/行号范围/no_impl/summary,Ref 带 source_chunk_id/target_file/target_chunk_id/rel。

### 反向要求
- 不建立关系图(只抽出 @ref 原始数据,建边归 specgraph 域)。
- 不校验六不变式或图合法性(只做语法解析,语义校验归 new_model 域)。
- 不写文件(纯读入文本→结构,落盘归 foundation)。

<!-- @id:[FSD]-ait-doc_model:schemas -->
## schemas
### 功能描述
全部 .meta YAML 的 pydantic 模型定义。基类 StrictModel 统一约束 extra=forbid(拒未知字段)、populate_by_name。覆盖:ProjectConfig(项目配置)、BaselineIndex/BaselineChunkEntry(基线索引)、VersionIndex/VersionChunkEntry/CommitEntry/VersionIndexStats(版本索引)、VersionMeta/VersionDependencies(版本元数据,含 phase 阶段机字段与锁定/title 原子性字段)、RequirementMeta、ChangeRecord、TaskYaml/CodeRef 等。类型别名:Action(add/modify/delete)、State(working/staged/committed)、VersionPhase(阶段机全部合法值)、TaskStatus、ReqStatus、ChangeType。summary 字段有 ≤120 字符校验。

### 反向要求
- 不含业务逻辑(只定义数据形状与字段校验,行为归各业务域)。
- 不做 YAML 读写(序列化委托 foundation 的 yaml_io)。
- 不定义解析产物类型(Chunk/Ref/ParsedFile 归 chunk_parser,本文件只管持久化 schema)。

<!-- @id:[FSD]-ait-doc_model:TEST -->
## TEST 集成验收
doc_model 域所有部件(chunk_parser + schemas)合并到一起、作为整体的集成验收:
1. WHEN 解析含多个 @id 的 markdown THEN 得到 ParsedFile,chunks 按 @id 边界切分、file_header 为首个 @id 前内容、每个 @ref 归属其所在 chunk。
2. WHEN markdown 的 code-fence 内出现 @id/@ref 字样 THEN 这些被屏蔽不计入解析结果(不误当真标记)。
3. WHEN @extract 块嵌套或未闭合 THEN 抛 ExtractError;成对闭合则解析为 ExtractBlock 列表。
4. WHEN 用含未知字段的 dict 校验任一 schema THEN 因 extra=forbid 校验失败;summary 超过 120 字符校验失败。
5. WHEN 加载旧版本(无 phase 字段)的 VersionMeta THEN 因字段有默认值仍能加载(向后兼容)。
