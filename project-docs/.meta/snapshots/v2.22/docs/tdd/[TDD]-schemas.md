<!-- @id:[TDD]-schemas -->
## schemas TDD

```yaml
target_file: skill/ait/ait/schemas.py
```

### 技术栈
Python 3.10+；`pydantic`（BaseModel/ConfigDict/Field/field_validator）、`datetime`、`typing.Literal`。

### 类型别名（Literal）
`Action=add|modify|delete`；`State=working|staged|committed`；`VersionPhase=empty|prd_locked|impl_locked|coding|merged`；`TaskStatus=created|executing|done|failed`；`ReqStatus=draft|prd_draft|prd_confirmed|impl_progress|impl_done|merged`；`ChangeType=ADD|MODIFY|DELETE`。

### 基类
`StrictModel(BaseModel)`：`model_config=ConfigDict(extra="forbid", populate_by_name=True)`（禁未知键、允许别名填充）。所有模型继承它。

### 模型（字段+默认）
- `ProjectConfig`：id_prefix_separator="-"、version_format="{major}.{minor}"、auto_snapshot_on_merge=True、custom_relations=[]、id_prefixes={}、mvp_scope_tags=[]。
- `BaselineChunkEntry`：id/file/heading/level/summary?/metadata{}；`summary` field_validator ≤120 字符。
- `BaselineIndex`：version=1、scope="global"、updated?、chunks=[]。
- `LinkEntry`：from_(alias="from")/to/rel（extra=forbid,populate_by_name）；`LinksIndex`：version/updated?/links[]（已废弃但保留 schema）。
- `VersionChunkEntry`：id、file?/heading?/level?(delete 时 null)、action、state、commit_id?、overrides?、amends?、insert_after?、base_hash?、source_req?、summary?(≤120 校验)、metadata{}。
- `CommitEntry`：id/timestamp/message/chunks[]/req_id?。
- `VersionIndexStats`：total_chunks/by_action{}/by_state{}/tasks_summary{}。
- `VersionIndex`：version=1、scope="version"、version_name、based_on_hash?、status=developing|committed|merged、chunks[]、commits[]、stats。
- `VersionDependencies`：based_on?/conflicts_with[]/merge_after[]。
- `VersionMeta`：version、created_at、merged_at?、owner="system"、changes[]、dependencies、snapshot?、**phase=empty、title?、prd_locked=False、impl_locked=False**（原子性/锁定字段，default 使旧 meta 仍可加载）。**`VersionPhase` Literal 值域 = legacy `empty/prd_locked/impl_locked/coding` ＋ 新模型层级流转 `prd-creating/prd-confirm`（v2.22 起，后续层按需扩展）＋ 终态 `merged`——两族命名风格（下划线 vs 短横）不相交。**
- `PrdChunkSummary`/`ImplChunkDraft`/`ImplDraftBundle`/`RequirementMeta`（req-N.yaml：id/title/status/时间/author/assigned_version?/prd_draft/prd_chunks[]/impl_drafts[]）。
- `ChangeRecord`：id/version/type/target("file#chunk")/author/date/message/base_hash?/base_content?/new_content?。
- `CodeRef`：commit?/paths[]/bound_at?；`TaskYaml`：id/title/source_chunk/impl_refs[]/global_refs[]/depends_on[]/order_hint=1/steps[]/status=created/code_refs[]��

### 关键约定
StrictModel extra=forbid → 未知键直接报错（schema 演进需显式加字段，default 保后向兼容）；summary ≤120 在 baseline/version chunk 两处校验。

### 单元测试要求
`tests/`（schema 相关）：round-trip、extra 键被拒、summary>120 报错、delete entry 允许 null 字段、旧 version meta（无 phase）仍加载；新模型 phase 值（prd-creating/prd-confirm）round-trip。pytest。
