<!-- @id:[FSD]-ait-doc_model -->
## doc_model FSD

### 功能范围

chunk 解析 + 数据模型；被所有域依赖。

<!-- @id:[FSD]-ait-doc_model:chunk_parser -->
## chunk_parser

### 功能描述

parse_file/parse_text：@id/@ref/@extract 解析、代码围栏屏蔽、[PRD]/[FSD]/[TDD] bracket 前缀、内部 split `:`、summary 提取。

<!-- @id:[FSD]-ait-doc_model:schemas -->
## schemas

### 功能描述

pydantic 数据模型：VersionMeta/VersionIndex/VersionChunkEntry/ChangeRecord/CommitEntry/State 等 + 错误码集合。
