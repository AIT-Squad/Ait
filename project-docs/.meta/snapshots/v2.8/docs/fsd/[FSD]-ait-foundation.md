<!-- @id:[FSD]-ait-foundation -->
## foundation FSD

### 功能范围

通用基础设施域：项目根解析、原子写与路径守卫、YAML↔pydantic 存取、chunk 内容哈希。被几乎所有上层域依赖；纯工具、无业务��态。

### 交互契约（对上层域提供）

- 项目根解析：`resolve_project_root() -> ProjectRoot`，硬约束 `<CWD>/project-docs/`。
- 原子写：`atomic_write_text/atomic_write_bytes`（tmp+rename）；路径守卫 `ensure_within`。
- YAML 存取：`load_model/save_model/load_yaml/dump_model`（pydantic 模型 ↔ YAML）。
- 哈希：`chunk_hash(content) -> 8 hex`（规范化后 SHA-256 前 8 位）。

<!-- @id:[FSD]-ait-foundation:root -->
## root
### 功能描述
解析并校验 AIT 唯一合法工作根 `<CWD>/project-docs/`。提供 `resolve_project_root()` 与 `ProjectRoot(cwd/root/docs/meta)`。三类错误：CWD 在 project-docs 内(E3 CWD_INSIDE_PROJECT_DOCS)、CWD 下无 project-docs(E1 NOT_AT_PROJECT_ROOT)、project-docs 缺 docs/.meta(E2 PROJECT_DOCS_MALFORMED)。**刻意不接受任何覆盖**（无 --root/-C/AIT_ROOT、不向上递归、目录名硬编）。

<!-- @id:[FSD]-ait-foundation:io_utils -->
## io_utils
### 功能描述
原子文件写与路径守卫。提供 `atomic_write_text/atomic_write_bytes`（tmp+fsync+os.replace）、`ensure_within(root,target)`（防越界）、`to_posix_rel`、`strip_md_ext`；`PathOutsideProjectError`。

<!-- @id:[FSD]-ait-foundation:yaml_io -->
## yaml_io
### 功能描述
pydantic 模型与 YAML 文件互转。`load_yaml/load_model/dump_model/save_model`；稳定块状风格（allow_unicode、sort_keys=False、不流式、width=120）；datetime→isoformat。

<!-- @id:[FSD]-ait-foundation:hash_utils -->
## hash_utils
### 功能描述
chunk 内容指纹。`normalize`（CRLF→LF + strip）+ `chunk_hash`（SHA-256 前 8 hex）；`file_hash` 同算法。
