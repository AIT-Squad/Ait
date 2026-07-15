<!-- @id:[TDD]-impl_manager -->
## impl_manager TDD

```yaml
target_file: skill/ait/ait/impl_manager.py
```

### 技术栈
Python 3.10+；依赖 chunk_parser、version_manager、index_manager、specgraph、format_validator、validator。

### 数据结构
@dataclass ImplCreateResult/ImplInheritResult；_default_impl_file(impl_chunk_id)。

### 代码结构（ImplManager，旧模型 ait impl）
- create(prd_chunk_id, impl_content, *, impl_file, req_id, prd_file, action, overrides)：assert impl 可写；解析 impl chunk；_validate_create_action(add/modify+overrides、base_hash)；_inject_refs(无 @ref 则注入 @ref:prd_file#prd_chunk rel:implements)；追加写版本 impl 文件；re-parse；逐新 chunk add_chunk；sync_specgraph。
- show / commit(pre-merge：成环/重复 @id/@extract、_assert_summary_ready、_assert_format_ready、_assert_impl_coverage_after) / lock(推进 impl_locked) / inherit(从 baseline 复制 impl 进版本)。
- 辅助：_lookup_prd_file/_pick_impl_file/_prd_chunk_ready/_baseline_chunk_hash。

### 错误码 LOCKED/PRD_NOT_FOUND/PRD_NOT_COMMITTED/PREMERGE_FAILED/DERIVED_NAME_VIOLATION/IMPL_NO_CHUNKS。

### 单元测试要求
tests/test_impl_*.py：create+ref 注入、add/modify、commit pre-merge、inherit、覆盖校验、派生命名。pytest。
