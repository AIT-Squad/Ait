<!-- @id:[TDD]-hash_utils -->
## hash_utils TDD

```yaml
target_file: skill/ait/ait/hash_utils.py
```

### 技术栈
Python 3.10+；`hashlib`。

### 代码结构与契约
- `normalize(text) -> str`：`replace("\r\n","\n").replace("\r","\n").strip()`（统一换行 + 去首尾空白）。
- `chunk_hash(content) -> str`：`hashlib.sha256(normalize(content).encode("utf-8")).hexdigest()[:8]`（8 位十六进制前缀）。
- `file_hash(path_content) -> str`：同 `chunk_hash`（用于 .doc-sync/ 跟踪代码文件）。

### 关键约定
哈希前必须 normalize（CRLF/CR→LF + strip），保证跨平台/空白差异不影响指纹；8 hex 前缀用于 chunk 失效检测的 base_hash。

### 单元测试要求
`tests/`（hash 相关）：normalize 幂等、相同规范化内容同哈希、CRLF/LF 等价。pytest。
