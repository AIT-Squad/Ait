<!-- @id:[FSD]-ait-foundation -->
## foundation 内部分解

### 功能描述
foundation 域的实现分解。该域是通用基础设施底座:项目根解析(定位并校验 AIT 唯一合法工作根)、原子文件写与路径越界守卫、pydantic 模型与 YAML 文件互转、chunk 内容指纹哈希。纯工具、无业务状态,被几乎所有上层域依赖(它自身不依赖任何业务域)。实现拆为四个文件:root(项目根解析)、io_utils(原子写与路径守卫)、yaml_io(YAML↔模型存取)、hash_utils(内容哈希)。

### 反向要求
- 不承载任何业务逻辑与状态(不知道 chunk/version/关系图为何物,只提供机械工具)。
- 不解析 chunk 语法(归 doc_model 域)、不管理索引或关系(归 indexing/specgraph 域)。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 foundation 域块,本文件是内部实现分解)。

### 分解视图
- root 叶(details → [TDD]-root):项目根解析与校验
- io_utils 叶(details → [TDD]-io_utils):原子写与路径守卫
- yaml_io 叶(details → [TDD]-yaml_io):YAML 与 pydantic 模型互转
- hash_utils 叶(details → [TDD]-hash_utils):chunk 内容指纹

<!-- @id:[FSD]-ait-foundation:root -->
## root
### 功能描述
解析并校验 AIT 唯一合法工作根 `<CWD>/project-docs/`。提供 `resolve_project_root() -> ProjectRoot`,返回冻结数据类 `ProjectRoot(cwd, root, docs, meta)`(一次 CLI 调用期内不可变)。校验三类错误各带独立错误码:CWD 本身位于 project-docs/ 内部报 CWD_INSIDE_PROJECT_DOCS、CWD 下不存在 project-docs/ 子目录报 NOT_AT_PROJECT_ROOT、project-docs/ 存在但缺 docs/ 或 .meta/ 子目录报 PROJECT_DOCS_MALFORMED。刻意不接受任何形式的覆盖:不读 --root/-C/AIT_ROOT 命令行或环境变量、不向上递归查找 marker 文件、目录名 project-docs 硬编不可配。

### 反向要求
- 不向上递归、不猜测、不接受配置覆盖工作根(唯一规则就是 `<CWD>/project-docs/`)。
- 不创建缺失的目录(只校验并报错,初始化归 init 域)。

<!-- @id:[FSD]-ait-foundation:io_utils -->
## io_utils
### 功能描述
原子文件写与路径越界守卫。提供:`atomic_write_text(path, content, *, encoding="utf-8")` 与 `atomic_write_bytes(path, data)`——先写 `.tmp` 兄弟文件再 fsync 后 os.replace(POSIX 与 Windows 均保证覆盖式原子改名),异常时清理临时文件并重抛,保证不留半写文件;`ensure_within(project_root, target) -> Path`——解析 target 绝对路径并断言落在 project_root 内,越界抛 PathOutsideProjectError;`to_posix_rel(root, path)` 返回 POSIX 分隔的相对路径;`strip_md_ext(rel_path)` 去除结尾 .md 后缀(供索引 file 字段用)。

### 反向要求
- 不做非原子的直接 open+write(所有写必须走 tmp+replace 保证原子性)。
- 不校验内容格式(只保证写入的原子性与路径安全,内容语义归调用方)。

<!-- @id:[FSD]-ait-foundation:yaml_io -->
## yaml_io
### 功能描述
pydantic 模型与 YAML 文件互转。提供:`load_yaml(path) -> dict`(文件不存在或空返回 {});`load_model(path, model)` 加载 YAML 并按 pydantic 模型校验;`dump_model(model) -> str` 把模型转 YAML 字符串,风格稳定(allow_unicode、sort_keys=False、default_flow_style=False 块状不流式、width=120),datetime/date 转 isoformat;`save_model(path, model)` 经 io_utils 的 atomic_write_text 原子落盘。

### 反向要求
- 不自行写文件(落盘委托 io_utils 的原子写)。
- 不定义业务模型(只做转换,模型 schema 归 doc_model 域)。

<!-- @id:[FSD]-ait-foundation:hash_utils -->
## hash_utils
### 功能描述
chunk 内容指纹。提供:`normalize(text) -> str`(CRLF/CR→LF 归一 + 首尾去空白);`chunk_hash(content) -> str`(对规范化内容做 SHA-256 取前 8 位十六进制);`file_hash(path_content)` 同算法,供 .doc-sync/ 跟踪代码文件用。哈希稳定性由 normalize 保证(跨平台换行差异不影响指纹)。

### 反向要求
- 不读文件(输入是已读入的字符串,IO 归 io_utils)。
- 不保证密码学抗碰撞用途(仅作内容变更检测的短指纹,非安全场景)。

<!-- @id:[FSD]-ait-foundation:TEST -->
## TEST 集成验收
foundation 域所有部件(root + io_utils + yaml_io + hash_utils)合并到一起、作为整体的集成验收:
1. WHEN 从含 project-docs/docs 与 .meta 的目录调 resolve_project_root() THEN 返回 ProjectRoot,其 root/docs/meta 指向正确子目录;从 project-docs/ 内部调则报 CWD_INSIDE_PROJECT_DOCS,缺子目录报 PROJECT_DOCS_MALFORMED,无 project-docs 报 NOT_AT_PROJECT_ROOT。
2. WHEN atomic_write_text 写入目标 THEN 内容以 LF 换行落盘且无 .tmp 残留;写入过程抛异常时目标文件保持原样(无半写)。
3. WHEN ensure_within 收到越界 target(如 ../外部路径)THEN 抛 PathOutsideProjectError;合法子路径返回解析后的绝对路径。
4. WHEN save_model 写模型再 load_model 读回 THEN 得到等价模型(round-trip),YAML 为块状风格、键序保留、datetime 为 isoformat 字符串。
5. WHEN 对同一内容的 CRLF 与 LF 两种换行分别 chunk_hash THEN 得到相同的 8 位十六进制指纹(normalize 消除换行差异)。
