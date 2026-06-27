<!-- @id:impl-data-specgraph-model -->

# SpecGraph 数据模型实现

## 目标

新增 `ait/specgraph.py`，用标准化 Spec URI 和有向边替代单一的 `links-index.yaml` 关系表达。

## 数据结构

- `Spec`：表示一个 PRD 或 impl chunk，字段包括 `uri`、`title`、`type`、`version`、`chunk_id`、`metadata`。
- `Edge`：表示 spec 间关系，字段包括 `src`、`dst`、`rel`、`weight`、`metadata`。
- `SpecGraph`：包含 `specs` 与 `edges`，提供增删查、序列化、依赖查询和拓扑排序。

## URI 规范

```text
spec:<type>:<version>:<chunk-id>
```

示例：`spec:prd:v1.3:prd-specgraph-index`。

## 兼容策略

- `.meta/links-index.yaml` 继续保留。
- 新增 `.meta/specgraph.yaml` 作为增强索引。
- v1.3 的写入逻辑双写或通过 `specgraph sync` 从旧索引迁移。

## 验收

- `SpecGraph`、`Spec`、`Edge` 可导入。
- `SpecGraph.load/save` 能读写 `.meta/specgraph.yaml`。
- 能根据 PRD URI 查询实现它的 impl URI。

<!-- @ref:prd/todo3-specgraph#prd-specgraph-index rel:implements -->

<!-- @id:impl-workflow-specgraph-cli -->

# SpecGraph CLI 与自动维护实现

## 目标

新增 `bin/ait specgraph` 命令组，并在 PRD/impl 生命周期中自动维护 `.meta/specgraph.yaml`。

## CLI 子命令

| 命令 | 用途 |
|---|---|
| `bin/ait specgraph sync` | 从 `.meta/links-index.yaml` 迁移到 `.meta/specgraph.yaml` |
| `bin/ait specgraph add-edge <src> <dst> --rel <rel>` | 手动添加关系边 |
| `bin/ait specgraph query <uri> --deps` | 查询依赖 |
| `bin/ait specgraph query <uri> --implements` | 查询实现关系 |
| `bin/ait specgraph export --format dot` | 导出 Graphviz DOT |

## 自动维护点

- `prd commit`：注册 `spec:prd:<version>:<chunk-id>`。
- `impl create`：解析 `@ref ... rel:implements` 并写入 `implements` edge。
- `impl commit`：可通过 SpecGraph 校验 PRD 是否 ready，同时保留现有 index 校验。

## 验收

- `bin/ait specgraph --help` 显示上述子命令。
- `specgraph sync` 能迁移现有 links。
- `specgraph export --format dot` 输出合法 DOT。

<!-- @ref:prd/todo3-specgraph#prd-specgraph-index rel:implements -->
