<!-- @id:[TDD]-yaml_io -->
## yaml_io TDD

```yaml
target_file: skill/ait/ait/yaml_io.py
```

### 技术栈
Python 3.10+；`pyyaml`、`pydantic.BaseModel`；依赖 `io_utils.atomic_write_text`。`TypeVar T bound=BaseModel`。

### 代码结构与契约
- `_json_safe(value)`：dict/list 递归；`datetime`/`date` → `.isoformat()`；其余原样（把 pydantic dump 值转 YAML 安全标量）。
- `load_yaml(path) -> dict`：不存在返回 `{}`；`yaml.safe_load`；`data or {}`。
- `load_model(path, model: type[T]) -> T`：`load_yaml` + `model.model_validate`。
- `dump_model(model) -> str`：`model.model_dump(by_alias=True, exclude_none=False)` → `_json_safe` → `yaml.safe_dump(allow_unicode=True, sort_keys=False, default_flow_style=False, width=120)`。
- `save_model(path, model)`：`dump_model` + `atomic_write_text`。

### 关键约定
`by_alias=True`（字段别名）、`sort_keys=False`（保持声明序）、`allow_unicode=True`（中文不转义）；这些直接影响 .meta YAML 的可读性与 diff 稳定。

### 单元测试要求
`tests/`（yaml 相关）：round-trip load/save、datetime 序列化、空文件返回 {}。pytest。
