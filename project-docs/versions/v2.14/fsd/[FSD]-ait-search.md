<!-- @id:[FSD]-ait-search -->
## search FSD
### 功能范围
跨 baseline/version chunk 的全文关键词检索。
### 交互契约
`search_chunks(query, scope?, regexp?) -> [SearchHit]`。
<!-- @id:[FSD]-ait-search:search -->
## search
### 功能描述
search_chunks：按 scope 过滤、match_chunk(关键词/正则) + extract_snippet(命中上下文)。详见 [TDD]-search。
