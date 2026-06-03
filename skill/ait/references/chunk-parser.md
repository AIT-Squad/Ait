# Chunk Parser 实现

<!-- @id:impl-chunk-parser-overview -->
## 概述

`src/ait/chunk_parser.py` 实现 Markdown → Chunk 列表的解析。是所有上层模块（索引、版本管理、合并、上下文组装）的基础。

<!-- @ref:prd/chunk-system#prd-chunk-format rel:implements -->
<!-- @ref:prd/chunk-system#prd-chunk-parse-rule rel:implements -->

<!-- @id:impl-chunk-parser-api -->
## 公开 API

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Chunk:
    id: str               # @id, e.g. "prd-book-entry"
    heading: str          # 标题文本，去掉 # 前缀
    level: int            # 2 / 3 / 4 ...（# 不入块，作为文件头）
    content: str          # 完整块内容：含 @id 注释行 + 标题 + 正文
    line_start: int       # 1-indexed
    line_end: int         # 1-indexed，含
    file: str             # 相对路径（无扩展名），用于索引

@dataclass(frozen=True)
class ParsedFile:
    file: str             # 相对路径（无扩展名）
    file_header: str      # 第一个 @id 之前的内容（含 # 标题）
    chunks: list[Chunk]
    refs: list["Ref"]     # 文件中所有 @ref 关联（含所属 chunk_id）

@dataclass(frozen=True)
class Ref:
    source_chunk_id: str  # @ref 所在的块 id
    target_file: str      # @ref:{file}#{id} 中的 file
    target_chunk_id: str  # @ref:{file}#{id} 中的 id
    rel: str              # rel:xxx

def parse_file(path: Path, base_dir: Path) -> ParsedFile: ...
def parse_text(text: str, file: str) -> ParsedFile: ...
```

`base_dir` 用于计算 `file` 字段（相对路径，无扩展名，正斜杠分隔）。

<!-- @id:impl-chunk-parser-algorithm -->
## 算法

<!-- @ref:prd/chunk-system#prd-chunk-parse-rule rel:implements -->

```
parse_text(text, file):
  1. 按行切分，保留行号
  2. 扫描所有 <!-- @id:xxx --> 标注行
     正则：^<!--\s*@id:([a-z0-9-]+)\s*-->\s*$
  3. 第一个 @id 之前的内容 → file_header
  4. 对每个 @id（i），下一个 @id（i+1）的前一行作为该块结束
     最后一个 @id 块结束于文件末尾
  5. 块标题：从 @id 标注的下一行开始，找第一个以 # 开头的行
     标题级别 = # 的数量
     标题文本 = 去掉 # 和首尾空白
  6. 块内容：从 @id 标注行到结束行的完整文本（保留首尾空格但去掉文件末尾的多余空行）
  7. 扫描 <!-- @ref:{file}#{id} rel:{rel} --> 标注
     正则：^<!--\s*@ref:([\w\-/.]+)#([a-z0-9-]+)\s+rel:([a-z\-]+)\s*-->\s*$
     每个 @ref 归属到包含它的块
```

<!-- @id:impl-chunk-parser-edge-cases -->
## 边界场景

| 场景 | 处理 |
|------|------|
| 代码块内出现 `<!-- @id:xxx -->` | **忽略**（解析前先剔除 \`\`\` 围栏内的内容） |
| 同一文件出现重复 @id | parse 阶段不报错（返回所有），由 validator 报 E1 |
| @id 标注后没有 # 标题 | heading=""，level=0，记录为 E3（不阻断） |
| 文件没有任何 @id | chunks=[]，整个文件作为 file_header |
| @id 在行尾有内容 | 严格按正则匹配，行尾必须仅是注释 |
| Windows CRLF | 解析前统一 normalize 为 LF |

<!-- @id:impl-chunk-parser-tests -->
## 测试要点

- fixtures 用 [project-demo/docs/prd/book-management.md](../../../project-demo/docs/prd/book-management.md) 应能解析出 14 个块
- fixtures 用 [project-demo/docs/impl/api-contracts.md](../../../project-demo/docs/impl/api-contracts.md) 应能解析出 9 个块 + 5 个 implements 关联
- 代码围栏测试：构造一个含 ` ```markdown ... <!-- @id:fake --> ... ``` ` 的文件，确认 fake 不被识别
- 嵌套块测试：## 块下含 ### 子块，应解析出独立的父块和子块（不嵌套）
