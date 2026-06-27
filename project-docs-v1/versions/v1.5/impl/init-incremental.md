<!-- @id:impl-init-state-detect -->
## init 三态识别与 --check 子命令

<!-- @ref:prd-init-incremental rel:implements -->

### 设计

#### 1. 三态判别函数
新增 `ait/init_manager.py` 中：
```python
GLOBAL_FILES = ["overview", "tech-stack", "ddl", "schema", "api"]

def _scan_global_state(self) -> dict:
    """返回 {filename: status} 与整体 status。"""
    g = self.root / "docs" / "global"
    per_file = {}
    for name in GLOBAL_FILES:
        path = g / f"{name}.md"
        per_file[name] = self._classify_global_file(path)
    if all(s == "present" for s in per_file.values()):
        overall = "ready"
    elif (self.root / "project-docs").exists() or g.exists():
        overall = "incomplete"
    else:
        overall = "fresh"
    return {"overall": overall, "files": per_file}

def _classify_global_file(self, path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "missing"
    text = path.read_text(encoding="utf-8")
    if not re.search(r"<!--\s*@id:global-[\w-]+\s*-->", text):
        return "skeleton"   # 占位骨架视为缺失
    return "present"
```
注：`skeleton` 与 `missing` 在调用方等价（都触发补全），但分别上报，便于 sub-skill 显示差异。

#### 2. 删除 `ALREADY_MANAGED` 硬拒
- `InitManager.run()` 移除现有 `if self.has_any_version(): raise InitManagerError(... "ALREADY_MANAGED")` 整段。
- `has_any_version()` 函数保留，仅用于决定是否走"全新讨论模板"或"差异补全"。
- 主 SKILL.md 的 Common Pitfalls 表 `ALREADY_MANAGED` 行删除（与 `prd-skill-cli-resolution` 的文档改写动作合并到一个 grep 验收即可）。

#### 3. `run()` 分支改造
```python
def run(self, *, check_only: bool = False) -> InitResult:
    state = self._scan_global_state()
    if check_only:
        return InitResult(status=state["overall"], files=state["files"])
    if state["overall"] == "ready":
        return InitResult(status="ready", files=state["files"])
    if state["overall"] == "fresh":
        return self._run_full_bootstrap()        # 原 run() 主体提取为此函数
    return self._run_incremental(state["files"]) # 仅写缺失的 global 文件
```
- `InitResult` dataclass 增加：`status: Literal["fresh","incomplete","ready"] = "fresh"`，`files: dict[str, str] = field(default_factory=dict)`。

#### 4. `_run_incremental` 实现
```python
def _run_incremental(self, files_state: dict) -> InitResult:
    created = []
    g = self.root / "docs" / "global"
    g.mkdir(parents=True, exist_ok=True)
    for name in GLOBAL_FILES:
        if files_state[name] == "present":
            continue
        if name in _STATIC_GLOBALS:
            chunk_id, heading, body = name_to_static(name)
            content = f"<!-- @id:global-{name} -->\n## {heading}\n\n{body}\n"
        else:
            heading = _DYNAMIC_GLOBALS[name]
            content = (
                f"<!-- @id:global-{name} -->\n## {heading}\n\n"
                f"<!-- 动态 global：内容由 version confirm 从 impl @extract 提取 -->\n"
            )
        atomic_write_text(g / f"{name}.md", content)
        created.append(self._rel(g / f"{name}.md"))
    self.indexes.rebuild_baseline()
    from .specgraph import sync_specgraph
    sync_specgraph(self.root)
    self._mark_initialized()
    return InitResult(created_files=created, status="incomplete", files=files_state)
```
- "用户拒绝某项跳过"由 sub-skill 层（`ait-init-guide`）决定要不要在写入前删除占位文件 / 跳过对应 chunk；CLI 收到的就是用户已决策的最终列表（通过未来扩展 `init --only static-overview,api` 的 flag 实现，本期暂不开口子，统一全量补全所有缺失项）。

#### 5. CLI 入口扩展
- `ait/cli.py` 的 `init` 命令增加 `--check` flag：
  ```python
  @click.option("--check", is_flag=True, help="Diagnose only, no writes.")
  def init(check):
      mgr = InitManager(find_project_root())
      result = mgr.run(check_only=check)
      click.echo(json.dumps({"ok": True, "data": asdict(result)}, ensure_ascii=False))
  ```
- 与 `prd-skill-cli-resolution` 的 `init --refresh-wrapper` 共存（两个 flag 互斥时优先 `--check`）。

### 测试
- `tests/test_init_manager.py`：
  - case fresh：空目录跑 init → 5 个文件全部生成。
  - case incomplete：手工删除 `tech-stack.md` 跑 init → 仅 `tech-stack.md` 重建，其他不变（mtime 不动）。
  - case ready：完整目录跑 init → `status=ready` 且无文件被写。
  - case `--check`：返回 `files` 字典 5 项，无文件写入。

### 边界
- 不在 CLI 层引入交互式 `read -p`（PRD 明确"逐项确认由 AI 对话完成"）。
- 不引入"重置某项"flag（PRD 非目标）。
- 占位骨架仍写 `<!-- @id:global-* -->`，符合"动态 global 仅生成空骨架"约束。

<!-- @ref:prd/v1-5-roadmap#prd-init-incremental rel:implements -->

<!-- @id:impl-init-guide-skill -->
## ait-init-guide 子 skill 升级（差异补全交互）

<!-- @ref:prd-init-incremental rel:implements -->
<!-- @ref:impl-init-state-detect rel:depends-on -->
<!-- @ref:prd-subskills-coverage rel:complements -->

### 设计

> 这是 PRD `prd-init-incremental` 的 sub-skill 端配套。`prd-subskills-coverage` 中的"重命名 ait-init-check → ait-init-guide" 仅做目录搬迁；本 chunk 负责 SKILL.md 内容重写以承载补全工作流。两个 chunk 通过 `complements` 关系耦合，由 task 层先后调度。

#### 1. SKILL.md 工作流（重写 `sub-skills/ait-init-guide/SKILL.md`）
四段结构：
- **Trigger**：`INVOKE THIS SKILL when bin/ait init returns status=incomplete and the user needs to fill missing docs/global/* files interactively`
- **CLI Dependencies**：
  - `project-docs/.ait/ait-cli init --check` — 诊断
  - `project-docs/.ait/ait-cli init` — 执行补全（CLI 自动识别 incomplete 进入差异写入）
  - `project-docs/.ait/ait-cli reindex` — 兜底刷新（init 已自动调用，此处仅恢复路径用）
- **Workflow**：
  1. 调 `init --check`，解析 `data.files` 字典。
  2. 对每个 status ≠ `present` 的项，向用户朗读"我准备补 `<filename>`，要我现在补么？"。
  3. 用户同意：把该 filename 加入待补列表；用户拒绝：跳过并记入 `skipped`。
  4. 全部用户决策完毕后，调 `init`（CLI 全量补全所有缺失，但 sub-skill 提前已让用户在 docs/global/<name>.md 写入"留空保护标记"——见步骤 5）。
  5. **拒绝项保护机制**：用户拒绝某项时，sub-skill 在 `docs/global/<name>.md` 预先写入：
     ```
     <!-- @id:global-<name> -->
     ## <heading>
     
     <!-- ait-init-guide: user-skipped, will not be touched by init -->
     ```
     CLI 端 `_classify_global_file` 见到 `<!-- @id -->` 即视为 `present`，跳过覆盖。
  6. 输出 ASCII 表格汇报最终结果（含 `created` / `skipped`）。
- **Common Pitfalls**：
  - `--check` 输出 `status: ready` → 无需补全，引导用户跑 `prd create`。
  - `init` 之后若 `chunks-index.yaml` 缺新增 chunk → 兜底跑 `reindex`。

#### 2. Artifacts 段
- Reads：`docs/global/*.md`、`.meta/chunks-index.yaml`
- Writes：`docs/global/*.md`（仅缺失项 + 用户拒绝项的占位写入由 sub-skill 直接做，因为这是配置类小文件，符合 Global Contract 的例外条款；其它写入仍走 CLI）
- ⚠️ 修订：上述"sub-skill 直接写占位"违反 Global Contract，改为：**新增 CLI 子命令 `bin/ait init --skip <name1,name2>` 把跳过列表传给 CLI**，由 CLI 写占位。
  - `ait/cli.py` `init` 命令增加 `--skip TEXT`（逗号分隔），传到 `InitManager.run(skip=[...])`。
  - `_run_incremental` 中遇到 `name in skip` 时，写入"用户跳过占位"内容（带 @id 但加注释 `user-skipped`）。

#### 3. 旧 ait-init-check 删除（在 `prd-subskills-coverage` 的 impl 中执行 `rm -rf`，本 chunk 仅写新文件）

### 验收
- `cat skill/ait/sub-skills/ait-init-guide/SKILL.md` 含 Workflow 6 步与 `--check`、`--skip` 命令引用。
- 端到端：tmp 目录 init 后删 `tech-stack.md` 与 `api.md` → AI 跑 ait-init-guide → 用户拒绝 `api` → 最终 `tech-stack.md` 完整骨架、`api.md` 含 `user-skipped` 注释。

### 边界
- 不引入用户 GUI / 交互输入框；交互由 AI 对话完成。
- 不实现"已 skipped 的文件被用户后续手动补内容后自动重纳管"——只要文件含 `<!-- @id -->` CLI 视为 present，已自然覆盖该场景。

<!-- @ref:prd/v1-5-roadmap#prd-init-incremental rel:implements -->
