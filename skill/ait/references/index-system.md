# 索引体系

> **状态注记（v2.30）**：chunks-index 与 specgraph 语义为现行；**links-index 段落属已废弃机制**。组合视图（baseline∪版本, chunk_id 世界）见代码 specgraph.combined_view。完整重写随 legacy 退役进行。

<!-- @id:prd-index-baseline -->
## 基线索引

`docs/` 目录的全局 Chunk 索引存储在 `.meta/chunks-index.yaml`。

```yaml
version: 1
scope: global
updated: 2026-05-23T16:00:00+08:00
chunks:
  - id: prd-chunk-format
    file: prd/chunk-system
    heading: "Chunk 标注格式"
    level: 2
```

字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| id | 是 | Chunk @id |
| file | 是 | 相对 `docs/`，无扩展名 |
| heading | 是 | 块标题文本（含 `#` 后内容） |
| level | 是 | 标题级别（2=##, 3=###, 1=# 作为文件标题不入索引） |

基线索引的特征：

1. ID 全局唯一
2. 扁平列表（无嵌套）
3. 只在 `/ait version merge` 时更新
4. 文件被手工编辑后，可用 `/ait reindex` 扫描 `docs/` 重建

<!-- @id:prd-index-version -->
## 版本增量索引

每个版本 `versions/{vX.Y}/` 拥有独立的增量索引 `.meta/chunks-index-{vX.Y}.yaml`。

与基线索引的差异：

| 维度 | 基线 | 版本 |
|------|------|------|
| 范围 | `docs/` | `versions/{vX.Y}/` |
| ID 唯一性 | 全局唯一 | 同 ID 可多条（修订场景） |
| 字段 | id/file/heading/level | + action / state / commit_id / overrides / amends / insert_after / base_hash / source_req |
| 更新频率 | merge 时 | stage/commit/edit 任何操作 |

完整 schema 见 [impl/version-manager.md](../impl/version-manager.md)。

<!-- @id:prd-index-record-fields -->
## 索引记录字段

基线索引仅 4 字段（见上）；版本索引扩展字段：

| 字段 | 适用 action | 说明 |
|------|-----------|------|
| `action` | all | `add` / `modify` / `delete` |
| `state` | all | `working` / `staged` / `committed` |
| `commit_id` | committed | 所属 commit |
| `overrides` | modify, delete | 覆盖的基线块 @id（冗余但明确） |
| `amends` | 修订 committed | 修订的 commit/chunk 标识 |
| `insert_after` | add | 插入位置的基线块 @id；null=末尾 |
| `base_hash` | modify, delete | 操作时基线块的哈希（冲突检测） |
| `source_req` | all | 来源需求 ID（追溯用） |

字段适用矩阵详见 [impl/version-manager.md](../impl/version-manager.md)。

<!-- @id:prd-index-isolation -->
## 分层隔离

基线索引与版本索引完全隔离：

1. 基线索引覆盖 `docs/`，版本索引覆盖 `versions/{vX.Y}/`，互不干扰
2. 版本只能从基线 fork（继承基线的 ID 命名空间）
3. 版本之间互不可见（V1.1 不能引用 V1.2 的 chunk）
4. 合并是单向操作：版本 → 基线，不存在"基线 → 版本"

<!-- @id:prd-index-links -->
## 引用索引

所有 `@ref` 关系汇总到 `.meta/links-index.yaml`：

```yaml
version: 1
updated: 2026-05-23T16:00:00+08:00
links:
  - from: impl/chunk-parser#impl-chunk-parser-api
    to: prd/chunk-system#prd-chunk-parse-rule
    rel: implements
```

links-index 是只读派生数据，由 chunk_parser 扫描所有 `@ref` 后生成。

用途：

1. AI 上下文组装的 L2 关联层（参见 [ai-context.md](ai-context.md)）
2. 影响面分析：修改 PRD 块时找出受影响的 impl 块
3. 一致性校验：检测悬空引用（target 不存在）

<!-- @id:prd-index-atomicity -->
## 原子性

索引写入采用 temp→rename 原子操作（POSIX 保证）：

1. 先写 `.meta/chunks-index.yaml.tmp`
2. fsync 后 rename 为 `chunks-index.yaml`
3. rename 失败时清理 tmp 文件

避免写入中断导致索引半残。Windows 平台用 `os.replace` 保证原子性。
