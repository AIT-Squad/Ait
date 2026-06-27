<!-- @id:[TDD]-search -->
## search TDD
```yaml
target_file: skill/ait/ait/search.py
```
### 技术栈
Python 3.10+；依赖 `index_manager`/`chunk_parser`。
### 数据结构
`@dataclass SearchHit{chunk_id,file,line,snippet,...}`。
### 代码结构
- `search_chunks(project_root, query, *, scope=None, regexp=False)->[SearchHit]`：遍历 baseline+version chunk，`_scope_matches` 过滤，`match_chunk(content,query,regexp)` 命中则 `extract_snippet(lines,idx,radius=1)`。
- `_match_entry/match_chunk/extract_snippet/_scope_matches`。
### 单元测试要求
`tests/`(search 相关)：关键词/正则命中、scope 过滤、snippet 上下文。pytest。
