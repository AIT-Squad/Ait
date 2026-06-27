<!-- @id:prd-search-cli -->

# 需求4：检索/聚焦读取命令行迁移

## 需求来源

`todo.md` 需求4：

> 参考项目中，检索/聚焦读取相关的命令行，挪到当前项目
> 结束要求：按照当前项目的实现规范

## 背景

参考项目 `version-design` 中有 **检索（search）** 和 **聚焦读取（focus）** 相关的命令行功能，当前项目（`ait`）尚未实现。

### 推测的功能范围（基于版本管理系统的常见需求）

| 功能 | 说明 | 参考项目可能的命令 |
|---|---|---|
| 检索 | 在全项目范围内搜索 chunk 内容（按关键词 / 语义） | `ait search <keyword>` / `ait search --semantic <query>` |
| 聚焦读取 | 只加载指定 chunk + 其关联 chunk（最小化上下文） | `ait focus <chunk-id>` / `ait context <chunk-id> --focus` |
| 依赖查询 | 查询 chunk 的依赖关系图谱 | `ait deps <chunk-id>` |
| 影响面分析 | 查询修改某个 chunk 会影响哪些其他 chunk | `ait impact <chunk-id>` |

## 与已有功能的关系

当前项目已有相关功能，需要**对齐而非重复**：

| 当前项目已有 | 参考项目可能有 | 处理方式 |
|---|---|---|
| `bin/ait context <chunk-id>`（L1+L2 上下文组装） | `ait focus` | 增强 `context` 命令，增加 `--focus` 模式（只返回 L1，不展开 L2） |
| `bin/ait reindex`（全量重新索引） | `ait scan` | 已对齐（v1.2 已完成） |
| 无 | `ait search` | **新增** |
| 无 | `ait deps` / `ait impact` | **新增**（基于 v1.3 的 SpecGraph） |

## 设计方案

### 新增命令 1：`bin/ait search <query>`

**功能**：在项目所有已 committed 的 PRD/impl chunk 中搜索关键词或语义匹配。

**实现**：

```python
# ait/search.py

import yaml
import os
import re
from typing import List, Dict, Tuple

def search_chunks(query: str, scope: str = "all", semantic: bool = False) -> List[Dict]:
    """
    Args:
        query: 搜索关键词
        scope: prd | impl | all
        semantic: 是否使用语义搜索（需要 embedding，v1.4+）
    """
    results = []
    index = load_chunks_index()

    for chunk in index["chunks"]:
        if scope == "prd" and not chunk["file"].startswith("prd/"):
            continue
        if scope == "impl" and not chunk["file"].startswith("impl/"):
            continue
        if chunk["state"] != "committed":
            continue  # 只搜索已 committed 的 chunk

        content = read_chunk_content(chunk)
        if match_chunk(content, query, semantic):
            results.append({
                "chunk_id": chunk["id"],
                "file": chunk["file"],
                "heading": chunk["heading"],
                "version": chunk["version"],
                "snippet": extract_snippet(content, query)
            })

    return results

def match_chunk(content: str, query: str, semantic: bool) -> bool:
    if semantic:
        # v1.4+：调用 embedding API
        return False
    else:
        # 关键词匹配（大小写不敏感）
        return query.lower() in content.lower()

def extract_snippet(content: str, query: str, context_lines: int = 2) -> str:
    """提取匹配行前后各 context_lines 行作为预览"""
    lines = content.split("\n")
    matches = []
    for i, line in enumerate(lines):
        if query.lower() in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            matches.append("\n".join(lines[start:end]))
    return "\n---\n".join(matches[:3])  # 最多 3 个匹配片段
```

**CLI 接口**：

```
bin/ait search "chunk 重命名" [--scope prd|impl|all] [--semantic]
```

**输出格式**：

```yaml
results:
  - chunk_id: prd-skills-rename-block-to-chunk
    file: versions/v1.2/prd/skills
    heading: Block 到 Chunk 的术语统一重构
    version: v1.2
    snippet: "当前项目的 block 在全项目重命名为 chunk..."
```

---

### 新增命令 2：`bin/ait focus <chunk-id>`（增强已有的 `context` 命令）

**功能**：只加载指定 chunk 本身（L1），不展开关联的 L2 chunk，用于"聚焦阅读"场景。

**与现有 `context` 的关系**：

| 命令 | 行为 |
|---|---|
| `bin/ait context <chunk-id>` | L1（目标 chunk）+ L2（@ref 关联 chunk）|
| `bin/ait context <chunk-id> --focus` | 仅 L1（目标 chunk 本身）|
| `bin/ait context <chunk-id> --deps` | L1 + 依赖图谱（基于 SpecGraph）|

**实现**（增强 `context.py`）：

```python
# ait/context.py - get_context() 函数新增 --focus 和 --deps 模式

def get_context(chunk_id: str, scenario: str = "default", focus: bool = False, deps: bool = False):
    # 读取目标 chunk（L1）
    target = read_chunk_file(chunk_id)

    if focus:
        # 仅返回 L1
        return {"L1": target, "L2": []}

    # 原有逻辑：读取 @ref 关联 chunk（L2）
    l2_chunks = extract_refs(target)

    if deps:
        # 基于 SpecGraph 读取依赖
        graph = SpecGraph.load(".meta/specgraph.yaml")
        uri = f"spec:{chunk_id.split('-')[0]}:{get_version(chunk_id)}:{chunk_id}"
        deps_specs = graph.get_dependencies(uri)
        l2_chunks += [spec.chunk_id for spec in deps_specs]

    return {"L1": target, "L2": l2_chunks}
```

---

### 新增命令 3：`bin/ait deps <chunk-id>`（基于 SpecGraph）

**功能**：查询指定 chunk 的依赖关系（depends_on）和被依赖关系。

**实现**：

```python
# ait/deps.py

def show_deps(chunk_id: str, direction: str = "both"):
    """
    Args:
        chunk_id: 目标 chunk
        direction: "in" (被依赖) / "out" (依赖别人) / "both"
    """
    graph = SpecGraph.load(".meta/specgraph.yaml")
    uri = spec_uri_for_chunk(chunk_id)

    result = {"chunk_id": chunk_id, "in": [], "out": []}

    for edge in graph.edges:
        if direction in ("both", "out") and edge.src == uri and edge.rel == "depends_on":
            dst_spec = graph.get_spec_by_uri(edge.dst)
            result["out"].append({"chunk_id": dst_spec.chunk_id, "title": dst_spec.title})
        if direction in ("both", "in") and edge.dst == uri and edge.rel == "depends_on":
            src_spec = graph.get_spec_by_uri(edge.src)
            result["in"].append({"chunk_id": src_spec.chunk_id, "title": src_spec.title})

    return result
```

**CLI 接口**：

```
bin/ait deps <chunk-id> [--direction in|out|both]
```

---

### 新增命令 4：`bin/ait impact <chunk-id>`

**功能**：修改某个 chunk 会影响哪些其他 chunk（反向依赖分析）。

**实现**：基于 SpecGraph 的**传递闭包**计算。

```python
# ait/impact.py

def compute_impact(chunk_id: str) -> List[Dict]:
    """计算修改 chunk_id 的影响面（所有反向依赖，传递）"""
    graph = SpecGraph.load(".meta/specgraph.yaml")
    uri = spec_uri_for_chunk(chunk_id)

    # BFS 反向遍历
    visited = set()
    queue = [uri]
    impact = []

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        for edge in graph.edges:
            if edge.dst == current and edge.rel in ("depends_on", "implements"):
                spec = graph.get_spec_by_uri(edge.src)
                impact.append({
                    "chunk_id": spec.chunk_id,
                    "title": spec.title,
                    "rel": edge.rel
                })
                queue.append(edge.src)

    return impact
```

**CLI 接口**：

```
bin/ait impact <chunk-id>
```

**输出示例**：

```yaml
impact_analysis:
  target: prd-skills-router
  affected_chunks:
    - chunk_id: impl-skills-router
      title: 主 SKILL.md Router 改造（实现）
      rel: implements
    - chunk_id: prd-skills-mapping
      title: 4 个 Skill 的迁移映射表
      rel: depends_on
```

## 验收标准

1. `bin/ait search "关键词"` 能返回匹配的 chunk 列表（含 snippet）
2. `bin/ait search "关键词" --scope prd` 只返回 PRD chunk
3. `bin/ait context <chunk-id> --focus` 只返回 L1（目标 chunk 本身）
4. `bin/ait context <chunk-id> --deps` 返回 L1 + SpecGraph 依赖
5. `bin/ait deps <chunk-id>` 返回依赖关系（in/out/both）
6. `bin/ait impact <chunk-id>` 返回影响面分析
7. 以上所有命令只读取 `state: committed` 的 chunk（不搜索 working/staged）
8. `ait/search.py`、`ait/deps.py`、`ait/impact.py` 文件存在，有对应的 CLI 注册

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| 语义搜索（embedding + vector store） | v1.4+，需要引入向量数据库 |
| 全文索引持久化（如 whoosh / elasticsearch） | v1.4+ |
| `ait search` 的 Web UI | 不在 CLI 工具范围内 |
