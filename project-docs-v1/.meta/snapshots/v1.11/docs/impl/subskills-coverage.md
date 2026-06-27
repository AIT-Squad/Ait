<!-- @id:impl-subskill-task-execute-add -->
## 新增 ait-task-execute 子 skill

<!-- @ref:prd-subskills-coverage rel:implements -->

### 产出物
新建 `skill/ait/sub-skills/ait-task-execute/SKILL.md`，frontmatter + 五段结构：

```markdown
---
name: ait-task-execute
description: INVOKE THIS SKILL when the user runs /ait task execute or asks to start coding a specific task; orchestrates context bundle → AI coding → task complete/fail.
---

# ait-task-execute — drive AI coding for a single task

## Trigger
- `/ait task execute T-xxx-01`
- "帮我跑一下 T-xxx-01" / "开始编码 task T-xxx" 等中文等价请求

## CLI Dependencies
- `project-docs/.ait/ait-cli task execute <id>` — 标 executing + 输出 context bundle
- `project-docs/.ait/ait-cli task complete <id> --commit <hash> --path <files>` — 收口
- `project-docs/.ait/ait-cli task fail <id>` — 失败回退
- `project-docs/.ait/ait-cli task show <id>` — 查 steps / impl_refs / global_refs

## Artifacts
- Reads: task YAML(`versions/<v>/tasks/T-*.yaml`)、context bundle(impl_refs + global_refs 拼装)
- Writes: 业务代码（由 AI 编辑工具落盘）；`task complete` 触发的 code_refs 字段更新（CLI 写）
- 严禁直接编辑 `.meta/`、`versions/`、`docs/global|prd|impl/`

## Workflow
1. 解析触发参数得到 `task_id`，调 `task execute <id>` 拿 bundle JSON。
2. 复述 `task_id` 与 `impl_refs` / `global_refs` 路径列表给用户。
3. 按 task YAML 的 `steps` 顺序，使用 AI 编辑工具改业务代码。
4. 让用户/AI 跑 `git add` + `git commit`（commit message 可建议格式 `feat(<task_id>): <heading>`）。
5. 拿到 commit hash 后调 `task complete <id> --commit <hash> --path <files...>`。
6. 出错则调 `task fail <id>` 并把控制权移交 `ait-resume`。

## Output Contract
每步必须复述：
- `task_id`
- 当前 step 序号 / 总数
- commit hash（步骤 5 之后）
- code_refs 路径列表（步骤 5 之后）

## Common Pitfalls
| Code | Symptom | Recovery |
|---|---|---|
| `BLOCKED` | 依赖 task 未 done | 先跑 `depends_on` 的上游 task |
| `TASK_NOT_FOUND` | id 不存在或路径迁移未生效 | `task list <v>` 核对；必要时 `reindex` |
| commit 缺失 | `git log` 空或 user 漏 commit | 引导补 commit 后重试 task complete |
```

### 验收
- `ls skill/ait/sub-skills/ait-task-execute/SKILL.md` 文件存在。
- 五段（Trigger / CLI Dependencies / Artifacts / Workflow / Output Contract / Common Pitfalls）齐全。
- description 触发关键词与其他 6 个 sub-skill 不重叠（关键词："task execute" / "start coding"）。

### 边界
- 不在 sub-skill 中嵌入具体业务代码模板（只编排流程）。
- 不引入对 `ait-resume` 的硬性 import；失败时由 AI 根据 `code` 自主切换。

<!-- @ref:prd/v1-5-roadmap#prd-subskills-coverage rel:implements -->

<!-- @id:impl-subskill-state-merge -->
## ait-progress 合入 ait-state

<!-- @ref:prd-subskills-coverage rel:implements -->

### 改动

#### 1. 删除 `skill/ait/sub-skills/ait-progress/`
整目录 `rm -rf`。删除前确认无外部 git 依赖（已 grep `ait-progress` 在主 SKILL.md 仅 2 处引用）。

#### 2. 重写 `skill/ait/sub-skills/ait-state/SKILL.md`
- frontmatter description 扩展（保留原 state.md 渲染职责 + 新增 progress 职责）：
  ```
  description: INVOKE THIS SKILL when the user asks to view AIT version state, refresh state.md, check version progress, chunk three-state distribution, impl coverage, or task counts.
  ```
- Workflow 增加：
  - **A. State 渲染**：`state --version <v>`（默认）/ `state --save`（落盘 state.md）
  - **B. 进度查询**：调 `state --version <v> --format json` 后从 `counts` / `working` / `staged` / `committed` / `impl_coverage` / `tasks_summary` 五段输出 ASCII 摘要
  - **C. 任务清单**：`task list <v>`（替代原 ait-progress 的 task list 触发场景）
- Common Pitfalls 增加：
  - 用户问"v1.5 进度"或"哪些 chunk 还没 impl" → 用 `--format json` + `impl_coverage` 字段筛 missing。
  - 用户问"task 跑到哪了" → 用 `tasks_summary` 字段（来自 `impl-task-summary-index`）。

#### 3. 主 `SKILL.md` 速查表 / Sub-skills 索引同步
- Quick Reference 表：
  - `/ait task list|show` 行的 Routed skill 列：`ait-progress` → `ait-state`
  - `/ait version status <v>` 行的 Routed skill 列：`ait-progress` → `ait-state`
- Sub-skills 索引表：
  - 删除 `ait-progress` 整行
  - `ait-state` 行 Purpose 列改写为：`渲染/落盘 state.md，并兼任版本进度、chunk 三态分布、impl 覆盖、task 统计的查询入口。`

### 验收
```bash
[ ! -d skill/ait/sub-skills/ait-progress ]                   # 必须为真
grep -r "ait-progress" skill/ait/                            # 命中 0
grep -c "ait-state" skill/ait/SKILL.md                       # ≥ 3（速查表 2 + 索引 1）
```

### 边界
- 不改 `bin/ait state` CLI 行为（已在 v1.4 实现）。
- 不为 `version status` 实现单独子命令（直接用 `state --version`）。
- 旧 ait-progress 的 README/templates/scripts 子文件随目录一并删除。

<!-- @ref:prd/v1-5-roadmap#prd-subskills-coverage rel:implements -->

<!-- @id:impl-subskill-init-guide-rename -->
## ait-init-check → ait-init-guide 目录搬迁

<!-- @ref:prd-subskills-coverage rel:implements -->

### 改动

#### 1. 物理搬迁
```bash
git mv skill/ait/sub-skills/ait-init-check skill/ait/sub-skills/ait-init-guide
```
保留旧 SKILL.md 内容 → 由 `impl-init-guide-skill`（属于 `prd-init-incremental`）后续重写为差异补全工作流。本 chunk 仅做目录搬迁与触发语调整，**不重写工作流正文**。

#### 2. SKILL.md frontmatter description 调整
仅改 description 一行：
- 旧：`INVOKE THIS SKILL when running bin/ait init or asking how to onboard an existing project ...`
- 新：`INVOKE THIS SKILL when bin/ait init returns status=incomplete and the user needs to fill missing docs/global/* files interactively`

正文保留原内容（避免与 `impl-init-guide-skill` 冲突；待后者执行时再覆盖）。

#### 3. 主 SKILL.md 速查表更新
Quick Reference 表 `/ait init` 行的 Routed skill 列：`ait-init-check` → `ait-init-guide`。
Sub-skills 索引表 `ait-init-check` 行 → `ait-init-guide`，Purpose 列改写为：`init 进入差异补全模式时，逐项确认 global 文件是否补齐；不再做新/旧项目判别（CLI 自识别）。`

### 验收
```bash
[ -d skill/ait/sub-skills/ait-init-guide ]                   # true
[ ! -d skill/ait/sub-skills/ait-init-check ]                 # true
grep -r "ait-init-check" skill/ait/                          # 命中 0
```

### 边界
- 工作流正文重写见 `impl-init-guide-skill`（不在本 chunk 范围）。
- 不删除 `ait-init-guide/templates/` 等子目录（保留以备后续工作流复用）。

<!-- @ref:prd/v1-5-roadmap#prd-subskills-coverage rel:implements -->

<!-- @id:impl-subskill-trigger-audit -->
## sub-skill 触发关键词去重 + 四段完整性审计

<!-- @ref:prd-subskills-coverage rel:implements -->
<!-- @ref:impl-subskill-task-execute-add rel:depends-on -->
<!-- @ref:impl-subskill-state-merge rel:depends-on -->
<!-- @ref:impl-subskill-init-guide-rename rel:depends-on -->

### 设计

#### 1. 触发关键词矩阵（人工 review + 自动 lint）
最终 6 个 sub-skill 的 description 关键词分配：

| Sub-skill | 主关键词 | 触发短语示例 |
|---|---|---|
| ait-discuss | `prd create` / 写需求 | `/ait prd "标题"` |
| ait-impl-discuss | `impl create` / 设计实现 | `/ait impl <prd-id>` |
| ait-task-execute | `task execute` / 开始编码 | `/ait task execute T-x` |
| ait-state | `state` / 进度 / 完成度 / chunk 分布 | `/ait state` / "v1.5 进度怎样" |
| ait-resume | error code / 恢复中断 | CLI 报错时 |
| ait-init-guide | `init` 补全 / 缺失 global | `init` 返回 incomplete |

#### 2. 自动 lint 脚本
新增 `skill/ait/scripts/verify-subskill-triggers.sh`：
- 解析 6 个 SKILL.md 的 frontmatter `description`
- 提取每个 description 的关键短语（用空格 + 标点切分后取 ≥3 字小写词）
- 计算两两交集；交集词在白名单（`ait`/`skill`/`/ait`/`when`/`user`）外即报错
- exit 1 时 stderr 输出冲突词与归属 sub-skill

#### 3. 四段完整性审计
同脚本扩展：检查每个 SKILL.md 必须包含以下 4 段标题（H2）：
- `## CLI Dependencies` 或等价 `## Dependencies`
- `## Artifacts`
- `## Workflow` 或等价 `## Output Contract` + `## Workflow`
- `## Common Pitfalls`

任一缺失即 exit 1。

#### 4. 集成入口
- 加入 `scripts/verify-all.sh` 调用链。
- CI / 本地 verify 触发该脚本。

### 验收
- `bash skill/ait/scripts/verify-subskill-triggers.sh` 退出码 0。
- 故意把 ait-state 的 description 加入 `prd create` 关键词 → 脚本退出码 1 且报告冲突。

### 边界
- 不引入 yaml/json schema 校验（保持 shell 轻量）。
- 不强制 description 字符长度上限（Anthropic skill 系统未限制）。
- 不审计正文内容质量（只看结构完整性）。

<!-- @ref:prd/v1-5-roadmap#prd-subskills-coverage rel:implements -->
