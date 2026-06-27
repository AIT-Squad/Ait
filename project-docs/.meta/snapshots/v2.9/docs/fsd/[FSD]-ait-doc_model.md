<!-- @id:[FSD]-ait-doc_model -->
## doc_model FSD

### 功能范围

文档模型基础设施：把 markdown 解析成 chunk/ref/extract，定义全部持久化数据的 pydantic schema。被所有上层域依赖（解析与数据契约的单一来源）。

### 交互契约（对上层域提供）

- 解析：`parse_file/parse_text -> ParsedFile(chunks, refs, file_header)`；`parse_extract_blocks -> [ExtractBlock]`。
- 数据类型：`Chunk/Ref/ExtractBlock/ParsedFile`（解析产物）。
- Schema：`BaselineIndex/VersionIndex/VersionMeta/RequirementMeta/ChangeRecord/TaskYaml/ProjectConfig` 等 + 类型别名 `Action/State/VersionPhase/TaskStatus/ReqStatus/ChangeType`。

<!-- @id:[FSD]-ait-doc_model:chunk_parser -->
## chunk_parser
### 功能描述
chunk 级 markdown 解析（边界由 `<!-- @id -->` 而非标题层级决定）。识别 @id/@ref/@extract/@summary/@prd-no-impl；code-fence 内屏蔽避免误匹配；file_header=首个 @id 前内容；@ref 归属所在 chunk；@extract 块成对解析（嵌套/未闭合报错）。支持 legacy 与 `[PRD]/[FSD]/[TDD]` 两类 ID。

<!-- @id:[FSD]-ait-doc_model:schemas -->
## schemas
### 功能描述
全部 `.meta` YAML 的 pydantic 模型（StrictModel：extra=forbid、populate_by_name）。覆盖 config/baseline index/version index/version meta/requirement/change/task。summary ≤120 校验；version meta 含 phase/锁定/title 原子性字段。
