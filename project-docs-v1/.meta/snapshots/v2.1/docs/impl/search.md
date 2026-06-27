<!-- @id:impl-workflow-search-cli -->

# Search CLI 实现

## 目标

新增 `bin/ait search <query>`，在已 committed 的 PRD/impl chunk 中执行关键词检索，并返回结构化 JSON。

## 模块

新增 `ait/search.py`。

核心函数：

- `search_chunks(query, scope="all", regexp=False)`：按范围检索 chunk。
- `read_chunk_content(entry)`：根据 index entry 读取 chunk 内容。
- `match_chunk(content, query, regexp)`：执行大小写不敏感关键词或正则匹配。
- `extract_snippet(content, query)`：返回匹配行前后上下文。

## CLI

```text
bin/ait search <query> [--scope prd|impl|all] [--regexp]
```

`--semantic` 暂不实现，避免引入 embedding 依赖。

## 搜索范围

- 默认读取 baseline `.meta/chunks-index.yaml` 中 `state: committed` 的 chunk。
- 如果指定版本，可后续扩展读取 `.meta/chunks-index-<v>.yaml`。
- v1.3 不搜索 working/staged chunk。

## 输出字段

- `chunk_id`
- `file`
- `heading`
- `version`
- `snippet`

## 验收

- `bin/ait search "关键词"` 能返回匹配 chunk。
- `--scope prd` 只返回 PRD。
- `--scope impl` 只返回 impl。

<!-- @ref:prd/todo4-search#prd-search-cli rel:implements -->

<!-- @id:impl-workflow-focus-deps-impact -->

# 聚焦读取、依赖查询与影响面分析实现

## 目标

增强上下文读取能力，并基于 SpecGraph 提供依赖与影响面分析命令。

## context 增强

为现有 `bin/ait context <chunk-id>` 增加：

| 参数 | 行为 |
|---|---|
| `--focus` | 只返回 L1 目标 chunk，不展开 L2 |
| `--deps` | 返回 L1 加 SpecGraph 依赖 chunk |

## deps CLI

新增 `ait/deps.py` 与命令：

```text
bin/ait deps <chunk-id> [--direction in|out|both]
```

- `out`：当前 chunk 依赖哪些 chunk。
- `in`：哪些 chunk 依赖当前 chunk。
- `both`：同时返回。

## impact CLI

新增 `ait/impact.py` 与命令：

```text
bin/ait impact <chunk-id>
```

实现方式为从目标 spec 开始，沿 `depends_on` 与 `implements` 的反向边做 BFS，返回传递影响集合。

## 验收

- `bin/ait context <chunk-id> --focus` 只返回 L1。
- `bin/ait context <chunk-id> --deps` 返回 SpecGraph 依赖。
- `bin/ait deps <chunk-id>` 返回 in/out/both 结构。
- `bin/ait impact <chunk-id>` 返回受影响 chunk 列表。

<!-- @ref:prd/todo4-search#prd-search-cli rel:implements -->
