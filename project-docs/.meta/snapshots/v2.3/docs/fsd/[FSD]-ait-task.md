<!-- @id:[FSD]-ait-task -->
## task FSD

### 功能范围

ait task：从 specgraph 派生、聚焦上下文、状态机、code_refs 回写。

<!-- @id:[FSD]-ait-task:task_manager -->
## task_manager

### 功能描述

TaskManager：create（从 specgraph 派生 impl_refs∪global_refs）、execute（输出聚焦 bundle）、complete/fail（状态机 created→executing→done/failed + 回写 code_refs）、list/show。
