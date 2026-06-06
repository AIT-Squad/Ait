<!-- @id:impl-global-index -->
## 全局信息索引与 context 注入

实现 global 的 static/dynamic 分类索引，以及在 context 组装时注入全局约束。

### 索引扩展

specgraph 中 global chunk 节点的 `metadata` 增加 `category` 字段（不再使用 links-index）：

<!-- @extract:dynamic/schema#global-index -->
```yaml
# .meta/specgraph.yaml 片段（baseline）
specs:
  - uri: spec:global:baseline:global-tech-stack
    type: global
    chunk_id: global-tech-stack
    metadata:
      category: static          # static | dynamic
      path: docs/global/tech-stack.md
  - uri: spec:global:baseline:global-ddl-pet
    type: global
    chunk_id: global-ddl-pet
    metadata:
      category: dynamic
      path: docs/global/ddl.md
```
<!-- @extract-end -->

### category 判定
- `reindex` 扫 `docs/global/` 时，按 chunk id 前缀或文件名归类，写入 specgraph 节点 metadata：
  - `overview` / `tech-stack` → static
  - `ddl` / `schema` / `api` → dynamic
- static 人工维护可编辑；dynamic 标只读（应改 impl 再 version confirm 提取）

### context 注入
- `ait context <chunk>` 输出附加 `<global-context>` 区块，数据源为 specgraph
- task execute 组装上下文时，按 task 的 `global_refs` 加载对应 global chunk
- 同目录存放，不分子目录，靠 specgraph 节点的 category metadata 区分（非物理路径）

<!-- @ref:prd/ait-redesign#prd-global rel:implements -->
