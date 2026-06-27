<!-- @id:[TDD]-chunk_parser -->
## chunk_parser TDD

```yaml
target_file: skill/ait/ait/chunk_parser.py
```

### 技术栈
Python 3.10+；`re`、`dataclasses`、`pathlib`；依赖 `io_utils.strip_md_ext/to_posix_rel`。纯解析，除 `parse_file` 读文件外无 I/O。

### 正则常量（精确）
- `LEGACY_CHUNK_ID = r"[a-z0-9][a-z0-9-]*"`
- `NEW_MODEL_CHUNK_ID = r"\[(?:PRD|FSD|TDD)\]-[a-z0-9_]+(?:-[a-z0-9_]+)*(?::[a-z0-9_]+)?"`
- `CHUNK_ID_PATTERN = (?:LEGACY|NEW_MODEL)`
- `ID_PATTERN = ^<!--\s*@id:(CHUNK_ID)\s*-->\s*$`
- `REF_PATTERN = <!--\s*@ref:([^#\s]+)#(CHUNK_ID)\s+rel:([a-z][a-z0-9_-]*)\s*-->`
- `EXTRACT_OPEN_PATTERN = ^<!--\s*@extract:([\w\-]+)/([\w\-]+)#([a-z0-9-]+)\s*-->\s*$`；`EXTRACT_END_PATTERN = ^<!--\s*@extract-end\s*-->\s*$`
- `NO_IMPL_PATTERN = ^<!--\s*@prd-no-impl\s*-->\s*$`；`SUMMARY_PATTERN = ^<!--\s*@summary:\s*(.+?)\s*-->\s*$`
- `HEADING_PATTERN = ^(#{1,6})\s+(.+?)\s*$`；`CODE_FENCE_PATTERN = ^\s*(```+|~~~+)`

### 数据结构（@dataclass(frozen=True)）
- `Chunk{id, heading, level:int, content, line_start, line_end, file, no_impl=False, summary=None}`
- `Ref{source_chunk_id, target_file, target_chunk_id, rel}`
- `ExtractBlock{source_chunk_id, target_type, target_category, target_chunk, content, line_start, line_end}`
- `ParsedFile{file, file_header, chunks=[], refs=[]}`
- `ExtractError(ValueError)`

### 核心算法
- `_normalize`：CRLF/CR→LF。
- `_mask_code_fences(lines)->list[bool]`：进出 ```/~~~ 围栏标记 True（开/闭行本身也标 True）；防 @id/@ref 误匹配。
- `_find_heading(lines, start, masked)`：跳过 masked，返回首个 `(#…)` 的 (text, level)。
- `parse_text(text, file)`：normalize→split→mask；收集非 masked 的 @id 位置；无 @id 则整文件为 header；file_header=首个 @id 前 join.rstrip；对每个 @id 段：end=下个 @id 前一行，回退裁掉尾部空行；扫 summary/no_impl；剥离 summary/no-impl marker 行（及其后紧随空行）得 content；heading 取该 @id 后首个标题；构造 Chunk。最后 `_extract_refs`。
- `_extract_refs(lines, masked, chunks)`：按 chunk.line_start/end 建 line→owner 映射；非 masked 行 finditer REF_PATTERN；owner=None（file header 内）忽略；否则收 Ref。
- `parse_file(path, base_dir)`：rel=to_posix_rel；file=strip_md_ext；read_text→parse_text。
- `parse_extract_blocks(text, *, chunks=None)`：mask；建 owner;扫 EXTRACT_OPEN/END；嵌套 opener 或无 opener 的 end 或未闭合 → `ExtractError`；body=开闭之间 join.strip("\n")，归属 owner[open_at]。

### 边界条件
marker 永不在 code fence 内生效；@ref 在 file header 内忽略；chunk body 保留至少 @id 注释行。

### 单元测试要求
`tests/test_chunk_parser.py`：@id 边界、code-fence 屏蔽、bracket 前缀 ID、内部 split `:`、@ref 归属、summary/no-impl 剥离、@extract 嵌套/未闭合报错。pytest。
