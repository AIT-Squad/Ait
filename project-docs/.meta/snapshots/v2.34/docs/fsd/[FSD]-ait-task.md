<!-- @id:[FSD]-ait-task -->
## task FSD
### 功能范围
旧模型 task：从 specgraph 派生 AI 编码单元、聚焦上下文、状态机、code_refs 回写。
### 交互契约
`create(prd_chunk) / execute(begin) / complete / fail / list / resolve`；deps_satisfied 守卫。

<!-- @id:[FSD]-ait-task:task_manager -->
## task_manager
### 功能描述
TaskManager：create(从 PRD chunk 的 impl 覆盖派生 TaskYaml，impl_refs∪global_refs)、begin_execute、complete(标 done+绑 code_refs)、fail、deps_satisfied、assemble_context(聚焦 bundle)、list/resolve/pending。详见 [TDD]-task_manager。
