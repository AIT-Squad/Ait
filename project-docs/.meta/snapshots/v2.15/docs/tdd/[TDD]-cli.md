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
- 命令组：init；prdv1(旧模型 create/save-draft/confirm/commit/show/resolve-candidates)；prd(新模型 create/link)；impl；task；version(status/commit/confirm/merge/reset)；fsd(create/link)；tdd(create)；codegen(prepare)；specgraph(含 validate-new-model)；context/state/lint/search/deps/impact/reindex/baseline-summary/migrate-block-to-chunk。

### 错误处理
捕 ValidationError/VersionManagerError/各 Error→fail(code)；根错误在 main 抛。

### 单元测试要求
tests/test_e2e_cli.py、test_new_model_commands.py：命令路由、JSON 契约、prd/prdv1 重命名、各域 happy/error。pytest。
