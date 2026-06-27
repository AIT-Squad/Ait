<!-- @id:impl-task-yaml-path -->
## TaskManager 物理路径迁移到版本工作区

<!-- @ref:prd-task-relocation rel:implements -->

### 改动点

#### 1. `ait/task_manager.py`
- 第 5 行模块 docstring：`.meta/tasks/{version}/T-{src-chunk}-NN.yaml` → `versions/{version}/tasks/T-{src-chunk}-NN.yaml`。
- 第 67-68 行 `tasks_dir`：返回 `self.root / "versions" / version / "tasks"`，去掉 `.meta`。
- 检查 `task_path` / `list_tasks` / `mkdir(parents=True, exist_ok=True)` 链路是否还引用 `self.meta_dir`，如有去除。
- 不改 `task_id` 命名规则、不改 YAML schema、不改任何字段。

#### 2. `ait/state.py`
- 第 120 行 docstring：把 `.meta/tasks/{version}/` 改为 `versions/{version}/tasks/`。
- 第 123 行 `tasks_dir = project_root / ".meta" / "tasks" / version` → `tasks_dir = project_root / "versions" / version / "tasks"`。
- 同时把"扫不存在目录"的早返回逻辑保留（兼容尚未创建任何 task 的版本）。

#### 3. `ait/version_manager.py`
- 第 378 行 reset 删目录：`shutil.rmtree(self.meta_dir / "tasks" / version, ...)` → 删除整段语句（`versions/{version}/` 整目录已在同一函数前面物理 rmtree，不必再二次清理）。
- 验证 `_purge_version` 函数主体已经覆盖 `versions/<v>/` 整目录递归删，**确保 task 目录顺带被清理**。
- confirm 守卫无需改动（`tm.list_tasks(version)` 自动跟随 task_manager 新路径）。

#### 4. `ait/schemas.py`
- 第 211 行注释路径同步：`.meta/tasks/{vX.Y}/T-{src}-NN.yaml` → `versions/{vX.Y}/tasks/T-{src}-NN.yaml`。

### 单元测试
- `tests/test_task_manager.py`：断言 `tasks_dir(v).resolve()` 末段为 `versions/{v}/tasks`，旧路径 `.meta/tasks/{v}/` 不再被创建。
- `tests/test_version_reset.py`：在 reset 前注入 fake task，reset 后断言 `versions/{v}/tasks/` 目录不存在。
- `tests/test_state.py`：断言 state 计数读新路径下的 yaml。

### 边界
- 不引入 `.meta/tasks/` → 新路径的迁移脚本（PRD 已明确零数据）。
- 不改 `tasks_summary` 字段（独立 chunk `impl-task-summary-index` 处理）。
- 不改 task 命令行参数与子命令名。

<!-- @ref:prd/v1-5-roadmap#prd-task-relocation rel:implements -->

<!-- @id:impl-task-summary-index -->
## chunks-index-{vX.Y}.yaml 注入 tasks_summary 字段

<!-- @ref:prd-task-relocation rel:implements -->
<!-- @ref:impl-task-yaml-path rel:depends-on -->

### 改动点

#### 1. `ait/schemas.py` — VersionIndex 扩展
- `VersionIndexStats` 新增字段：
  ```python
  tasks_summary: dict[str, int] = Field(default_factory=dict)
  ```
- `dict` 取值：`{"created": int, "executing": int, "done": int, "failed": int}`，全 0 时仍写入空字典而非省略字段（保持 schema 稳定）。

#### 2. `ait/index_manager.py` — rebuild_version 注入
- `rebuild_version(version)` 在构建 `VersionIndex` 末尾、`stats` 计算后注入：
  ```python
  from .task_manager import TaskManager
  tm = TaskManager(self.root)
  summary = {"created": 0, "executing": 0, "done": 0, "failed": 0}
  for t in tm.list_tasks(version):
      summary[t.status] = summary.get(t.status, 0) + 1
  vi.stats.tasks_summary = summary
  ```
- 隔离失败：`tasks_dir` 不存在时 `list_tasks` 返回空，`summary` 全 0，正常写入。

#### 3. `ait/cli.py` — reindex 子命令
- `reindex` 已调 `rebuild_baseline()`；新增对所有现存版本的 `rebuild_version(v)` 调用：
  ```python
  for v in sorted(p.stem for p in (root / ".meta" / "versions").glob("*.yaml")):
      mgr.rebuild_version(v)
  ```
- 输出 JSON 增加 `data.versions_reindexed: ["v1.1", "v1.2", ...]`。

#### 4. impl/prd commit 钩子
- `prd_manager.commit` / `impl_manager.commit` 末尾已经调 `rebuild_version(v)`，本次只需确认 `tasks_summary` 同步生成（修改 schema 后自动生效）。

### 验收命令
```bash
project-docs/.ait/ait-cli reindex
yq '.stats.tasks_summary' project-docs/.meta/chunks-index-v1.5.yaml
# 期望输出：{created: 0, executing: 0, done: 0, failed: 0} 且字段 5 个版本一致
```

### 边界
- 不在 baseline `chunks-index.yaml` 注入 tasks_summary（baseline 不绑版本，task 是版本资产）。
- 不引入新 CLI 子命令（`reindex` 直接覆盖）。
- `tasks_summary` 字段仅由 reindex / commit 钩子写入，CLI 不暴露独立写入路径。

<!-- @ref:prd/v1-5-roadmap#prd-task-relocation rel:implements -->

<!-- @id:impl-task-legacy-warn -->
## 旧 .meta/tasks 路径检测告警

<!-- @ref:prd-task-relocation rel:implements -->
<!-- @ref:impl-task-yaml-path rel:depends-on -->

### 改动点

#### 1. `ait/cli.py` — 命令入口检测
- 在 `main()` 装饰器或 `cli` group `invoke_without_command=True` 钩子里，加入一次性预检：
  ```python
  legacy = root / ".meta" / "tasks"
  if legacy.exists() and any(legacy.rglob("*.yaml")):
      click.echo(
          f"⚠️  legacy task path detected: {legacy} — "
          f"task YAML 已迁至 versions/<v>/tasks/，请手动删除旧目录",
          err=True,
      )
  ```
- 仅 stderr 输出，不抛异常、不阻塞 stdout JSON 契约。
- 用进程级缓存（模块全局 bool）避免一次 CLI 进程内重复打印。

#### 2. 文档同步
- 主 `SKILL.md` 的 `Project Layout` 段：
  - `.meta/tasks/{vX.Y}/T-*.yaml` → 整行删除
  - `versions/{vX.Y}/` 段下追加：`└── tasks/T-*.yaml         # AI 编码任务 YAML`
- `references/index-system.md`：如有 task 路径示意同步更新。
- `docs/global/schema.md` 中的 task-yaml 示例路径同步。

### 测试
- `tests/test_legacy_warn.py`：mock `.meta/tasks/v1.0/T-x.yaml` 存在，运行任意 CLI 子命令，断言 stderr 含 `legacy task path detected`，stdout JSON 仍干净。

### 边界
- 不自动迁移、不自动删除（PRD 明确零数据，要求手动删）。
- 不为告警新增 error code。
- 检测仅在 CLI 入口跑一次；TaskManager 内部调用不重复检测。

<!-- @ref:prd/v1-5-roadmap#prd-task-relocation rel:implements -->
