<!-- @id:[TDD]-merge_engine -->
## merge_engine TDD

```yaml
target_file: skill/ait/ait/merge_engine.py
```

### 技术栈

Python 3.10+；纯标准库（`dataclasses`、`typing.Iterable`）。依赖本仓库 `chunk_parser.Chunk/ParsedFile`、`schemas.Action`（`Literal["add","modify","delete"]`）。

### 实现约束

- **纯函数，零 I/O**：只操作内存中的 `ParsedFile` + `VersionChunkOp` 列表，不读写磁盘、不碰 git。读基线文件、冲突检测、写回由调用方 `version_manager.merge` 负责。
- 两个 dataclass 均 `@dataclass(frozen=True)`。

### 关键数据结构

```python
@dataclass(frozen=True)
class VersionChunkOp:
    chunk_id: str
    action: Action                 # "add" | "modify" | "delete"
    overrides: str | None = None   # modify/delete 的目标 baseline chunk id
    insert_after: str | None = None# add 的锚点（None=尾插）
    new_chunk: Chunk | None = None # add/modify 携带的新内容；delete 为 None
    base_hash: str | None = None   # 失效检测用（本模块不消费）

@dataclass(frozen=True)
class MergedFile:
    file: str
    file_header: str
    chunks: list[Chunk]            # 合并后有序 chunk 列表
    new_content: str               # 序列化后的完整文件文本
```

### 代码结构（公开/私有符号）

- `_serialize(file_header, chunks) -> str` / `serialize(...)`（公开别名，测试用）。
- `merge_file(base: ParsedFile, ops: list[VersionChunkOp]) -> MergedFile`：对已存在的基线文件应用 add/modify/delete。
- `merge_new_file(file: str, ops) -> MergedFile`：从纯 add ops 建全新文件。

### 核心逻辑：序列化

`_serialize`：`file_header.rstrip()` 非空则作首段；每个 chunk 取 `chunk.content.strip()`；各段以 `"\n\n"` join，末尾补一个 `"\n"`。

### 算法与流程：merge_file（两趟）

1. **前置守卫**：`base.chunks` 为空但 ops 含 modify/delete → `raise ValueError`（应改用 `merge_new_file`）。
2. **第一趟 分类**（关键：按 baseline **真实存在性** reconcile action，绝不丢 chunk）：
   - 计 `base_ids = {c.id for c in base.chunks}`。
   - `modify`：`target = op.overrides or op.chunk_id`；`target in base_ids` → 入 `modify_map[target]`；否则**视为新增**，入 `add_tail`（这是 v2.4 修复：modify 目标不在 baseline 不再被静默跳过）。
   - `delete`：`op.overrides` 非空 → 入 `delete_set`。
   - `add`：`insert_after is None` → `add_tail`；`insert_after in base_ids` → `add_after_map[insert_after]` 追加；否则 → `orphan_adds`。
3. **孤儿调整**：`add_after_map` 中锚点落在 `delete_set` 的，移出到 `orphan_adds`。
4. **第二趟 重建** `result`（遍历 `base.chunks`，维护 `last_kept_chunk`）：
   - chunk 在 `delete_set`：跳过；若有 orphan 的 `insert_after==该 id` 且有 `last_kept_chunk`，把这些 orphan 的 `new_chunk` 插在此处。
   - chunk 在 `modify_map`：用其 `new_chunk` 替换（`new_chunk is None` → `raise ValueError`）；否则原样保留。更新 `last_kept_chunk`。
   - 处理 `add_after_map[chunk.id]`：其 `new_chunk` 紧随其后插入。
   - 处理 `insert_after not in base_ids` 的未附着 orphan：附在当前 survivor 后，并从 orphan 列表移除。
5. **尾插**：`add_tail` 各 `new_chunk` 追加（含被 reconcile 成 add 的 modify，按 op 顺序保持原序）。
6. **剩余 orphan**：插到列表最前（header 之后）。
7. `new_content = _serialize(base.file_header, result)`，返回 `MergedFile(base.file, base.file_header, result, new_content)`。

### 算法与流程：merge_new_file

ops 含非 add → `raise ValueError("merge_new_file only accepts action=add ops")`；否则收集各 `op.new_chunk`（跳过 None），`file_header=""`，`_serialize("", chunks)`。

### 错误处理（ValueError 触发点）

- 空基线 + modify/delete ops；
- modify 命中但 `new_chunk is None`；
- `merge_new_file` 收到非 add op。

### 边界条件

- modify 目标不在 baseline → 当 add（不丢、保序）。
- delete 的 `overrides=None` → 忽略（不删任何东西）。
- add 锚点指向被删 chunk → 转 orphan，落到最近 survivor 后或表首。
- 同文件「已存在根 modify + 新 split modify」→ 根替换、split 尾插（v2.4 回归场景）。

### 单元测试要求

`tests/test_merge_engine.py`：modify 全替换、add 尾插、add insert_after、delete、delete 带 orphan、`merge_new_file` 只收 add、空基线守卫、**modify 目标不在 baseline 当 add 不丢（回归）**。framework=pytest；独立运行 `pytest tests/test_merge_engine.py`；通过标准=全绿。
