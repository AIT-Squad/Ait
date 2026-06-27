<!-- @id:[TDD]-migrations -->
## migrations TDD

```yaml
target_file: skill/ait/ait/migrations.py
```

### 技术栈
Python 3.10+；`pathlib`、`yaml`；原子写。

### 代码结构
- `MigrationError(RuntimeError)`；`@dataclass MigrationReport`(迁移结果计数/重命名清单)。
- `_rename_keys(node, counter)`：递归把历史 block 相关 key 改名（计数）。
- `_atomic_write(path,text)`；`_rewrite_yaml_file(path,dry_run)->(changed,count)`。
- `_rename_index_files(meta_dir,dry_run)->list[(old,new)]`（如 blocks-index→chunks-index）。
- `migrate_block_to_chunk(meta_dir, dry_run=False)->MigrationReport`：遍历 .meta YAML，_rename_keys + _rename_index_files；非 dry_run 时原子写 + `_validate_or_raise`。
- `_validate_or_raise(meta_dir)`：迁移后 schema 校验。

### 关键约定
一次性历史迁移；dry_run 预览不写；失败 MigrationError。

### 单元测试要求
`tests/`（migration 相关）：dry_run 不改盘、block→chunk key/文件改名、迁移后校验通过。pytest。
