<!-- @id:[FSD]-ait-cli -->
## cli 内部分解

### 功能描述
cli 域的实现分解。该域是 ait 的命令行分发器:用 click 定义命令树,把用户命令路由到各领域 manager,并统一输出契约。核心原则是"只分发不含业务逻辑"——每个命令解析参数、调对应 manager、把结果包成统一 JSON 输出,业务规则全在各领域(version/new_model/foundation 等)。实现为单一文件:cli(click 命令树 + 输出契约 + 项目根解析)。

### 反向要求
- 不含任何业务逻辑(版本合并、图校验、文档解析等全部委托对应领域 manager,本域只做参数解析与结果包装)。
- 不直接读写 project-docs 文件(经 manager 与 foundation 的原子写)。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 cli 域块,本文件是内部实现分解)。

### 分解视图
- cli 叶(details → [TDD]-cli):click 命令树、JSON 输出契约、项目根解析

<!-- @id:[FSD]-ait-cli:cli -->
## cli
### 功能描述
click 命令树与统一输出契约的实现。命令面:新模型主线 version(create/confirm/merge/revert/commit/status)、prd(create/confirm/revert)、fsd(create/decompose/confirm/revert)、tdd(create/confirm/revert)、codegen(prepare)、specgraph/deps/impact、acceptance(set/run);legacy(prdv1/impl/task);init/reindex 等。统一输出契约:成功走 ok(data)→`{"ok":true,"data":{...}}`,失败走 fail(message,code)→`{"ok":false,"error":...,"code":...}`;stdout 必须是单个 JSON 对象。JsonGroup 把 click 的用法错误(未知命令/缺参/非法选项)也转成 `{"ok":false,"code":"USAGE_ERROR"}` 而非裸文本 exit 2。_root() 经 foundation 的 resolve_project_root 解析项目根并存入 click ctx;_read_content 从 --content/--content-file 读入内容。领域错误码(如 VERSION_NOT_FOUND、INVARIANT_VIOLATION、TDD_TARGET_FILE_REQUIRED)透传 issues[0].code,不吞成笼统码。

### 反向要求
- 不实现业务规则(只调 manager 并转发其返回与错误码)。
- 不自定义输出格式(只用 ok/fail 两个统一出口,不 print 裸文本)。
- 不做参数以外的状态管理(无缓存、无全局可变状态,一次调用一次解析)。

<!-- @id:[FSD]-ait-cli:TEST -->
## TEST 集成验收
cli 域(命令树 + 输出契约 + 根解析)作为整体的集成验收:
1. WHEN 任一命令成功 THEN stdout 是单个 JSON 对象且含 `"ok":true` 与 data;失败则含 `"ok":false`、error 与领域 code。
2. WHEN 调用未知命令 / 缺必填参数 / 传非法选项值 THEN 输出 `{"ok":false,"code":"USAGE_ERROR"}`(JsonGroup 拦截,不再是裸 click 文本 exit 2)。
3. WHEN 在不含 project-docs 的目录运行业务命令 THEN _root() 报根解析错误码(NOT_AT_PROJECT_ROOT 等)且为 JSON。
4. WHEN manager 抛领域错误(如 tdd create 缺 target_file)THEN CLI 透传其真实错误码(TDD_TARGET_FILE_REQUIRED)而非笼统 VALIDATION_FAILED。
5. WHEN --help THEN 正常输出帮助(不被 JsonGroup 改写)。
