<!-- @id:impl-prd-stage-cli -->
## PRD 阶段命令实现

实现 `prd create` / `prd discuss` / `prd confirm` 三个入口。create 带标题直建，discuss 启动讨论，confirm 写工作区并锁定。

### 命令

```python
@prd_group.command("create")
@click.argument("title")
def prd_create(title: str):
    # 无活跃版本则自动创建（从 v1.0 起），记录 req + title
    ...

@prd_group.command("discuss")
def prd_discuss():
    # 启动讨论模式（skill 层驱动多轮对话）；收敛后调 _summarize_title 写 state.md
    ...

@prd_group.command("confirm")
@click.argument("req_id", required=False)
def prd_confirm(req_id):
    # 写入版本工作区 versions/{v}/prd/，置 prd_locked=True，刷新 state.md
    ...
```

### 锁定语义
- confirm 成功后调用 `assert_prd_writable` 的反向操作：置 `VersionState.prd_locked = True`
- 锁定后再调 `prd create/discuss/confirm` 修改本版本 PRD → 返回 `LOCKED` 错误

### 与现有实现的术语对齐
- 现有 `prd confirm` 仅写工作区（state=working），需扩展为同时置 `prd_locked`
- 锁定的"冻结"语义由 impl-core-model-state 的 `prd_locked` 标志承载

<!-- @ref:prd/ait-redesign#prd-prd-stage rel:implements -->

<!-- @id:impl-prd-stage-title -->
## title 抽取与 state.md 写入

实现 discuss 收敛后总结 title，并写入 state.md 独立字段（后续作为 git commit message）。

### 数据流

```python
def set_version_title(root: Path, version: str, title: str) -> None:
    state = load_version_state(root, version)
    state.title = title
    save_version_state(root, state)   # 持久化到版本元数据
    refresh_state_md(root, version)   # 重新渲染 state.md，title 单独成行
```

### state.md 渲染扩展

state.md 顶部 Summary 区新增 title 字段：

```markdown
# AIT State — v1.0

## Summary
- Title: `宠物建档功能`        ← 新增，来自 prd discuss 总结
- Version: `v1.0`
- ...
```

### 规则
- title 仅在 prd 阶段写入；一旦 PRD 锁定，title 随之冻结
- version confirm 时取该 title 作为 git commit message

<!-- @ref:prd/ait-redesign#prd-prd-stage rel:implements -->
