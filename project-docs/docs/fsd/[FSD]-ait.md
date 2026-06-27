<!-- @id:[FSD]-ait -->
## ait 功能分解根

### 功能范围

AIT 的功能按 CLI 命令域分解为子 FSD。命令域：init/prd/impl/task/version/new-model/specgraph/context/state/lint/search/indexing；外加分发器 cli 与两个基础设施域 doc-model、foundation。每个域 decomposes 一个子 FSD，子 FSD details 到 TDD，每个 TDD 唯一映射一个 .py 文件。
