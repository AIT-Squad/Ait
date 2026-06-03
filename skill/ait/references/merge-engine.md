# Merge Engine 实现

<!-- @id:impl-merge-engine-overview -->
## 概述

`src/ait/merge_engine.py` 实现块级合并算法：把版本工作区的增量块缝合回基线文件。

<!-- @ref:prd/index-system#prd-index-baseline rel:implements -->
<!-- @ref:prd/chunk-system#prd-chunk-parse-rule rel:implements -->

被 `version_manager.merge` 调用。本模块本身**不做 I/O**，只做内存中的块列表合并，便于单元测试。

<!-- @id:impl-merge-engine-api -->
## 公开 API

```python
from ait.chunk_parser import Chunk, ParsedFile

@dataclass(frozen=True)
class VersionBlockOp:
    """版本索引中一条对基线的操作"""
    chunk_id: str
    action: str               # add / modify / delete
    overrides: str | None     # action in (modify, delete) 时指向基线块 id
    insert_after: str | None  # action=add 时的插入锚点；null=末尾
    new_block: Chunk | None   # action in (add, modify) 时提供新内容；delete=None
    base_hash: str | None     # action in (modify, delete) 时的基线块 hash 快照

@dataclass(frozen=True)
class MergedFile:
    file: str
    file_header: str
    chunks: list[Chunk]       # 合并后块列表
    new_content: str          # 序列化后的完整 markdown

def merge_file(
    base: ParsedFile,
    ops: list[VersionBlockOp],
) -> MergedFile: ...

def merge_new_file(
    file: str,
    ops: list[VersionBlockOp],
) -> MergedFile:
    """基线中不存在的新文件：所有 ops 必须 action=add。"""

def serialize(file_header: str, chunks: list[Chunk]) -> str:
    """序列化为 markdown 文本，块之间用一个空行分隔。"""
```

<!-- @id:impl-merge-engine-algorithm -->
## 合并算法

<!-- @ref:prd/index-system#prd-index-version rel:implements -->

```
merge_file(base, ops):
  1. 把 ops 按 action 分桶：
       modify_map: { overrides → VersionBlockOp }
       delete_set: { overrides }
       add_after_map: { insert_after → [VersionBlockOp]（保持原顺序）}
       add_tail: [VersionBlockOp]  # insert_after=null

  2. result = []
     for chunk in base.chunks:
       if chunk.id in delete_set:
         continue
       elif chunk.id in modify_map:
         result.append(modify_map[chunk.id].new_block)
       else:
         result.append(chunk)

       # 在当前块之后插入所有以 chunk.id 为 insert_after 的 add
       for op in add_after_map.get(chunk.id, []):
         result.append(op.new_block)

  3. 追加 add_tail
     for op in add_tail:
       result.append(op.new_block)

  4. 处理孤儿插入：
     如果有 insert_after 指向被 delete 的块：
     "追加到该块的前一个未被删除的块之后"
     → 用反向扫描找到第一个未删除的祖先块，把孤儿 op 接在其后；
     若找不到（已是首块）→ 接在 file_header 之后（result 头部）

  5. 返回 MergedFile(file=base.file, file_header=base.file_header, chunks=result,
                     new_content=serialize(base.file_header, result))
```

<!-- @id:impl-merge-engine-conflict-detection -->
## 冲突检测（不在本模块）

`merge_engine` **不做** base_hash 比对，原因：
- 保持本模块纯函数特性，便于测试
- 冲突检测需要读基线文件，应在 `version_manager.merge` 的前置步骤完成
- 本模块假定调用者已经处理过冲突（要么用版本 op，要么把 op 改为 noop）

<!-- @id:impl-merge-engine-edge-cases -->
## 边界场景

| 场景 | 处理 |
|------|------|
| ops 为空 | 返回 base 的原样 MergedFile |
| modify 的 overrides 在基线找不到 | merge_engine 静默忽略（应由前置 validator 报错） |
| add 的 insert_after 在基线找不到且非 null | 按"孤儿插入"规则处理（接在 header 之后） |
| 同一 insert_after 多个 add | 按 ops 出现顺序插入 |
| add 的 chunk_id 与基线已有冲突 | merge_engine 不检查（validator 应在 stage/commit 时报 E1） |
| 全新文件（base.chunks=[]）传入 modify/delete | 报 ValueError（应调用 merge_new_file） |

<!-- @id:impl-merge-engine-serialize -->
## 序列化规则

```python
def serialize(file_header, chunks):
  parts = []
  if file_header.strip():
    parts.append(file_header.rstrip())
  for chunk in chunks:
    parts.append(chunk.content.strip())
  return "\n\n".join(parts) + "\n"
```

- 块之间用恰好一个空行分隔
- 文件末尾保证一个换行符
- 不重排块内部的空行（依赖 chunk.content 的原貌）

<!-- @id:impl-merge-engine-tests -->
## 测试要点

- 纯 add 到末尾、add 到指定位置、连续多个 add 顺序正确
- 单 modify 替换、连续 modify 不互相影响
- 单 delete、连续 delete、delete 后跟 add（删除后还能 insert_after 指向其他块）
- 删除-插入孤儿：delete 块 A 同时 add 一个 insert_after=A 的块
- 全新文件（merge_new_file）
- 序列化空文件头时不留多余空行
- 用 project-demo/docs/prd/book-management.md 做 base，构造一组 ops，断言合并结果可被 chunk_parser 再次解析出预期数量的块（自反性）
