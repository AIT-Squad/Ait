<!-- @id:[TDD]-io_utils -->
## io_utils TDD

```yaml
target_file: skill/ait/ait/io_utils.py
```

### 技术栈
Python 3.10+；`os`、`pathlib`。

### 代码结构与契约
- `PathOutsideProjectError(ValueError)`
- `ensure_within(project_root, target) -> Path`：`root=project_root.resolve()`；`target` 绝对则 `target.resolve()` 否则 `(root/target).resolve()`；`resolved.relative_to(root)` 失败抛 `PathOutsideProjectError`；返回 resolved。
- `atomic_write_text(path, content, *, encoding="utf-8")`：`path.parent.mkdir(parents=True, exist_ok=True)`；写 `path` 同名 +`.tmp`（`open(..., newline="\n")`，`write`+`flush`+`os.fsync`）；`os.replace(tmp, path)`；异常时 unlink tmp 后 re-raise。
- `atomic_write_bytes(path, data)`：同上，`"wb"` 模式。
- `to_posix_rel(root, path) -> str`：`path.resolve().relative_to(root.resolve()).as_posix()`。
- `strip_md_ext(rel_path) -> str`：尾部 `.md` 去除。

### 核心算法：原子写
tmp 同目录写满 + `fsync` + `os.replace`（POSIX 与 Windows 均保证覆盖式原子 rename）；失败清理 tmp，保证不留半文件。

### 单元测试要求
`tests/`（io 相关）：原子写覆盖、ensure_within 越界拒绝、posix 相对路径。pytest。
