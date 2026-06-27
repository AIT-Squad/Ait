<!-- @id:impl-task-stage-build -->
## task 拆分（task create）

实现 `task create`：从锁定的 PRD+impl 拆分出 AI coding 任务 YAML。一个 PRD chunk 可拆多个 task。

### 命令

```python
@task_group.command("create")
@click.argument("chunk_id", required=False)  # 无 id → 逐批交互
def task_create(chunk_id):
    if chunk_id is None:
        return _interactive_task_loop(root)  # 遍历无 task 的 committed chunk
    # 1. 从 specgraph（version 维度）收集 PRD chunk 的 impl_refs + global_refs
    # 2. 依据 impl 的步骤性内容切分为 1~N 个 task
    # 3. 生成 .meta/tasks/{v}/T-{源chunk}-NN.yaml
    ...
```

### 拆分规则
- task 命名 `T-{源chunk去前缀}-NN`（NN 两位序号，同 chunk 内递增）
- `impl_refs`：查 **specgraph（version 维度）** 中 `rel:implements` 指向该 PRD chunk 的所有 impl chunk（数据源是 specgraph，不是 links-index）
- `global_refs`：impl 中 @ref 指向的 global chunk + 项目级默认（tech-stack）
- `depends_on`：依据 specgraph 中 impl 间 `depends-on` 边推导上游 task
- `order_hint`：同 chunk 内 task 的执行序

### 前置
- 本版本 PRD 与 impl 均须 committed/locked，否则拒绝拆分

<!-- @ref:prd/ait-redesign#prd-task-stage rel:implements -->

<!-- @id:impl-task-stage-schema -->
## task YAML Schema

定义 task YAML 的字段规范，供 create 生成、execute 消费。

<!-- @extract:dynamic/schema#task-yaml -->
```yaml
# .meta/tasks/{version}/T-{源chunk}-NN.yaml
id: T-pet-archive-01          # 派生式：T-{源chunk}-NN
title: 实现宠物档案创建接口
source_chunk: prd-pet-archive # 血缘：源 PRD chunk
impl_refs:                    # 该读的 impl chunk
  - impl-pet-archive-ddl
  - impl-pet-archive-api
global_refs:                  # 该遵守的全局约束
  - global-tech-stack
depends_on: []                # 上游 task id（拓扑）
order_hint: 1                 # 同 chunk 内执行序
steps:                        # AI coding 步骤
  - 读 impl-pet-archive-ddl 建表
  - 按 impl-pet-archive-api 实现 POST /pets
  - 写单测覆盖必填校验
status: created               # created | executing | done | failed
code_refs: []                 # done 时回写：[{commit, paths, bound_at}]
```
<!-- @extract-end -->

### 字段约束
- `id` 全局唯一；`source_chunk` 必填且须为 committed PRD chunk
- `status` 初始 `created`；由 execute 流转
- `code_refs` 仅 done 时非空
- 砍掉 v1.4 的 `inherited_from` / `status_inherited` / `provenance`

<!-- @ref:prd/ait-redesign#prd-task-stage rel:implements -->

<!-- @id:impl-task-stage-execute -->
## task 执行与自动收口（task execute）

实现 `task execute`：AI coding 执行，成功自动标 done 并回写 code_refs，无单独 confirm。

### 命令

```python
@task_group.command("execute")
@click.argument("task_or_chunk", required=False)  # 无参 → 逐批交互
def task_execute(task_or_chunk):
    # 解析为一组 task（taskId 单个 / chunkId 该 chunk 全部 / 无参全部 pending）
    for t in resolve_tasks(task_or_chunk):
        if not deps_satisfied(t):           # depends_on 未全 done → 跳过/blocked
            continue
        t.status = "executing"; save(t)
        ctx = assemble_context(t)           # 只取 impl_refs ∪ global_refs，token 聚焦
        result = ai_coding(ctx, t.steps)    # skill 层驱动 AI 写代码
        if result.ok:
            t.status = "done"
            t.code_refs = [{"commit": result.commit, "paths": result.paths}]
        else:
            t.status = "failed"
        save(t); refresh_state_md(root, version)
```

### 状态机
```
created → executing → done（成功，回写 code_refs）
                  └─→ failed（失败，可重跑 execute）
```

### 规则
- execute 成功即收口，无 task confirm
- 依赖未满足（depends_on 有非 done）→ 不执行
- 上下文严格限定 task 的 refs，不读全局文件树（token 聚焦）
- 人工审核统一到 version confirm

### 状态双存（决策11）
- **单一真相源 = task YAML 的 `status`**：`save(t)` 持久化到 `T-{源chunk}-NN.yaml`
- **聚合展示 = state.md**：`refresh_state_md` 每次状态变更后重渲染，汇总本版本所有 task 的 status
- 读取时以 YAML 为准；state.md 仅供人查看进度，不作为权威数据源

<!-- @ref:prd/ait-redesign#prd-task-stage rel:implements -->
