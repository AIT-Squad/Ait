<!-- @id:[TDD]-cli -->
## cli TDD

```yaml
target_file: skill/ait/ait/cli.py
```

### 技术栈
Python 3.10+；click、json；导入分发到全部 manager。

### 实现约束
只分发不含业务逻辑：每命令解析参数→调 manager→ok/fail 输出 JSON；stdout 必须单个 JSON(Windows reconfigure utf-8)。

### 代码结构
- 输出契约：ok(data)→{ok:true,data}；fail(message,code,exit_code,details)→{ok:false,error,code}+sys.exit；_json_safe(datetime/dataclass/pydantic 序列化)。
- _read_content/_scoped_filename/_root(ctx)/_emit_wrapper_hints。
- main click group：resolve_project_root 存 ctx。
- 命令组：init；prdv1(旧模型 create/save-draft/confirm/commit/show/resolve-candidates)；prd(新模型 create/link)；impl；task；**version(create/confirm/merge/revert + legacy status/commit)**；fsd(create/link)；tdd(create)；codegen(prepare)；specgraph(含 validate-new-model)；context/state/lint/search/deps/impact/reindex/baseline-summary/migrate-block-to-chunk。
- **version 命令语义（新模型主线四件套）**：`create <v>`（显式开版本，已存在报错，堵幽灵版本）；`confirm <v>`（**纯门禁**——调 `mgr.gate`，报告 passed + 六不变式违例明细，可重复跑、零落盘、不合入）；`merge <v>`（**原子合入**——调 `mgr.confirm`，内部先过同一门禁再 backup→merge→specgraph 提升→git commit，失败字节级回退；旧 `--conflict-policy` 保留）；`revert <v>`（调 `mgr.reset`，`--confirm` 二次确认物理清空未合入版本）。legacy `commit`（三态锁定）与 `status` 保留。

### 错误处理
捕 ValidationError/VersionManagerError/各 Error→fail(code)；根错误在 main 抛。

### 单元测试要求
tests/test_e2e_cli.py、test_new_model_commands.py：命令路由、JSON 契约、prd/prdv1 重命名、各域 happy/error；**version create/confirm(gate)/merge/revert 路由与 JSON 契约、confirm 报违例不落盘、merge 门禁前置**。pytest。
