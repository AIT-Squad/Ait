<!-- @id:[FSD]-ait-cli -->
## cli FSD
### 功能范围
ait 命令分发器：click 命令树路由、统一 JSON 输出契约、项目根解析；只分发不含业务逻辑（业务在各 manager）。
### 交互契约
`main` click group → 各命令组(init/prd/prdv1/impl/task/version/fsd/tdd/codegen/specgraph/context/state/lint/search/deps/impact/reindex…)；ok/fail JSON。

<!-- @id:[FSD]-ait-cli:cli -->
## cli
### 功能描述
click 命令树 + ok()/fail() 统一 `{ok,data}`/`{ok,error,code}` 契约 + _root() 项目根解析 + _read_content；新模型 `prd`、旧模型 `prdv1`。详见 [TDD]-cli。
