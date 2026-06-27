<!-- @id:prd-task-relocation -->
## task YAML 目录从 .meta 迁到版本工作区

### 概述
当前 task YAML 落在 `.meta/tasks/{vX.Y}/T-*.yaml`，把"用户/AI 编辑读取的资产"放进了"系统索引账本"目录，与 `versions/{vX.Y}/` 已承载 `prd/`、`impl/`、`state.md` 的版本工作区心智不一致。本期把 task YAML 物理位置迁到 `versions/{vX.Y}/tasks/`，让一个版本的所有用户态资产同处一个目录。

### 业务规则
- task YAML 物理路径变更：`project-docs/versions/{vX.Y}/tasks/T-{源chunk}-NN.yaml`
- 所有 task 子命令读写新路径：`task create` / `task execute` / `task complete` / `task fail` / `task list` / `task show`
- `version reset <vX.Y> --confirm` 在物理删除版本时一并清除 `versions/{vX.Y}/tasks/`
- `version confirm <vX.Y>` 的前置守卫"task 必须全 done"按新路径扫描
- `.meta/` 不再保留 task YAML 单文件；如需要状态快照，由 `chunks-index-{vX.Y}.yaml` 增加 `tasks_summary` 字段在 reindex 时同步生成（counts: created/executing/done/failed）
- task-yaml schema chunk（`global/schema.md`）的路径示例同步更新
- 历史 `.meta/tasks/` 不做迁移：项目本身未真实使用过该路径，零数据；CLI 在启动时若发现旧路径存在，输出一次性告警并建议手动删除

### 验收标准
- [ ] `task create` 后，新文件出现在 `versions/{vX.Y}/tasks/T-*.yaml`，旧路径无新增
- [ ] `task list <vX.Y>` 能枚举新路径下所有 task 且数量正确
- [ ] `task execute` / `complete` / `fail` 全链路读写新路径，状态机闭环
- [ ] `version reset` 后 `versions/{vX.Y}/tasks/` 整目录被删除
- [ ] `version confirm` 在 task 未 done 时仍能正确拦截（错误码 `TASK_NOT_DONE` 不变）
- [ ] `chunks-index-{vX.Y}.yaml` 在 reindex 后含 `tasks_summary` 字段，计数与磁盘文件一致
- [ ] 主 SKILL.md 与 `global/schema.md` 中所有 task 路径引用同步更新

### 边界与非目标
- 不提供 `.meta/tasks/` → `versions/<v>/tasks/` 的自动迁移脚本（零数据）
- 不改 task YAML 的字段结构，仅改物理位置
- 不改 task 命名规则 `T-{源chunk}-NN.yaml`

<!-- @id:prd-init-incremental -->
## init 改为幂等的基线补全器

### 概述
当前 `bin/ait init` 在已有版本的项目上会以 `ALREADY_MANAGED` 错误码硬性拒绝，不区分"完整初始化"和"global 信息缺项"两种场景，导致用户在 global 不全时无法用 init 补齐，只能手工编辑文件。本期把 init 重定位为"幂等的差异补全器"：新项目走全量讨论，已纳管项目按缺项补全，已就绪项目报告状态退出。

### 业务规则
- 删除 `ALREADY_MANAGED` 这条 fail 出口；改为分支判别后走对应路径
- 三种场景：
  - **全新项目**：`project-docs/` 不存在或为空 → 走原全量讨论流程，生成 docs/global/ 全部骨架
  - **已纳管但 global 不全**：存在 `project-docs/` 但 `docs/global/` 下 `overview.md` / `tech-stack.md` / `ddl.md` / `schema.md` / `api.md` 任一缺失或仅含空骨架（无 `<!-- @id -->` 标记）→ 进入差异补全模式
  - **已就绪**：上述全部齐全 → 输出 `{"ok": true, "data": {"status": "ready", ...}}` 并退出
- 差异补全模式：
  - 由 `ait-init-guide` 子 skill（重定位自 `ait-init-check`）逐项讨论缺失文件
  - 每项补全前显式询问用户确认，拒绝则跳过该项
  - 仅写 `docs/global/`，不动 `versions/`、`docs/prd/`、`docs/impl/`、`.meta/specgraph.yaml` 中已有 chunk
  - 补全完成后调用 `reindex` 把新 chunk 注入 baseline `chunks-index.yaml` + `specgraph.yaml`
- 新增 `bin/ait init --check` 仅诊断不写入：返回 global 各项 present/missing 状态，方便 sub-skill 与用户预览
- "缺失"判定标准：文件不存在、文件大小为 0、或文件内容不含任何 `<!-- @id:global-* -->` 标记（仅占位骨架视为缺失）

### 验收标准
- [ ] 全新空目录 `bin/ait init` 行为不变（向后兼容）
- [ ] 已纳管但 `docs/global/tech-stack.md` 缺失时，`bin/ait init` 不再返回 `ALREADY_MANAGED`，进入补全流程
- [ ] 已就绪项目 `bin/ait init` 返回 `ok: true` + `status: ready`，不修改任何文件
- [ ] `bin/ait init --check` 输出 5 项 global 文件的 present/missing 字典
- [ ] 补全过程中用户拒绝某项，该项跳过且其他项继续
- [ ] 补全完成后 baseline `chunks-index.yaml` 与 `specgraph.yaml` 含新增 global chunk
- [ ] 不修改 `versions/`、`docs/prd/`、`docs/impl/` 任何已有内容
- [ ] 主 SKILL.md 的 Common Pitfalls 表移除 `ALREADY_MANAGED` 行

### 边界与非目标
- init 仍不创建版本号、不创建 `versions/{vX.Y}/` 目录
- 动态 global（ddl/schema/api）补全只生成空骨架（带 `<!-- @id -->`），真实内容仍由后续 version confirm 从 impl @extract 提取
- 不引入交互式 shell 输入（read -p）；逐项确认由 AI 对话完成
- 不支持选择性"重置某项 global 文件"（要重置仍需手动删文件后重跑 init）

<!-- @id:prd-skill-cli-resolution -->
## bin/ait 路径解析与 SKILL 文档约定修订

### 概述
SKILL.md 与 sub-skills 中所有 CLI 调用使用相对路径 `bin/ait ...`，AI 在用户项目根（cwd 不在 skill 安装目录）执行时直接抛 `zsh:1: no such file or directory: bin/ait`。本期通过"文档约定 + 入口脚本自定位 + 错误码兜底"三层解决：让 AI 不论从哪个 cwd 触发都能正确调用 CLI。

### 业务规则
- **文档层约定**：SKILL.md / 所有 sub-skill SKILL.md / references/* 中的 CLI 调用统一改为占位符 `${SKILL_DIR}/bin/ait`，并在 Global Contract 增加一条：*"调用 CLI 时使用 skill 安装目录下的绝对路径（默认 `~/.claude/skills/ait/bin/ait`）；不要在用户项目根使用相对路径 `bin/ait`"*
- **入口脚本自定位**：`bin/ait` shell wrapper 与 `bin/ait.cmd` 在执行前用脚本自身路径（`$(dirname "$0")` 等价）解析 venv 位置，不依赖 cwd；保证用户即便手动从绝对路径调用也能找到 venv 与 ait 包
- **CLI cwd 校验**：`bin/ait` 子命令保持原有"必须从含 `project-docs/` 的目录运行"约束（这指的是用户业务 cwd，与 wrapper 自定位无关）
- **错误码兜底**：当 shell 抛出 `command not found` 类错误时（不在 CLI 控制内），sub-skill 必须能识别症状并给出修正命令；主 SKILL.md 的 Common Pitfalls 增加一条 `ENOENT_BIN_AIT`（虚拟代码，不是 CLI 真实返回）
- **install.py 行为不变**：仍把 skill 拷贝到 `~/.claude/skills/ait/`，仍预热 venv

### 验收标准
- [ ] `grep -rn "bin/ait" skill/ait/SKILL.md skill/ait/sub-skills/` 命中数为 0（除非紧跟在 `${SKILL_DIR}/` 之后）
- [ ] 主 SKILL.md 的 Global Contract 含路径绝对化条款
- [ ] 用户在任意 cwd（如用户项目根）执行 `~/.claude/skills/ait/bin/ait --version` 都能正常输出版本号
- [ ] `bin/ait` wrapper 不再依赖 `cd` 到特定目录才能找到 venv
- [ ] Common Pitfalls 表新增 `ENOENT_BIN_AIT` 行：症状 = `no such file or directory: bin/ait`，恢复 = 改用绝对路径
- [ ] 现有 sub-skill（ait-discuss / ait-impl-discuss / ait-progress / ait-resume / ait-init-check / ait-state）的 CLI Dependencies 段全部更新

### 边界与非目标
- 不引入系统级全局 `ait` 命令（PATH 注入），保持当前"显式路径调用"哲学
- 不修改 `install.py` 拷贝逻辑与 venv 机制
- 不改变 CLI 子命令名与参数
- 不引入环境变量 `AIT_HOME` 之类的可配置 skill 路径（保持默认 `~/.claude/skills/ait/`）

<!-- @id:prd-subskills-coverage -->
## sub-skills 治理：补齐 task 阶段、合并 progress/state、init-check 重定位

### 概述
当前 6 个 sub-skill 覆盖了 PRD/impl/接入诊断/进度/state/恢复 6 个场景，但 **task 阶段裸奔**（拆 task → AI 编码 → 收口由 main 直接处理，缺契约约束）；同时 `ait-progress` 与 `ait-state` 触发条件高度重叠（都读同一份状态数据），存在 AI 同时加载两个 skill 稀释 prompt 的风险。本期治理范围限定 3 件事：新增 task 执行 skill、合并 progress 入 state、重定位 init-check 为 init-guide。

### 业务规则

#### 规则 1：新增 ait-task-execute 子 skill
- 文件位置：`skill/ait/sub-skills/ait-task-execute/SKILL.md`
- 触发语：`INVOKE THIS SKILL when the user runs /ait task execute or asks to start coding a specific task`
- 职责：
  1. 调 `bin/ait task execute <id>` 拿到 token 聚焦的 context bundle（含 `impl_refs ∪ global_refs`）
  2. 驱动 AI 按 task YAML 的 `steps` 字段编码
  3. 编码完成后让用户/AI 执行 git commit 拿到 commit hash
  4. 调 `bin/ait task complete <id> --commit <hash> --path <files>` 收口
  5. 失败路径：调 `bin/ait task fail <id>` 后转交 `ait-resume`
- CLI Dependencies：`task execute` / `task complete` / `task fail` / `task show`
- Artifacts：Reads = task YAML + context bundle；Writes = 业务代码（由 AI 编辑工具落盘） + `task complete` 触发的 code_refs 回写；不直接写 `.meta/` 或 `versions/`
- 输出契约：每步必须复述 task id、commit hash、code_refs 路径

#### 规则 2：合并 ait-progress 进 ait-state
- 删除 `skill/ait/sub-skills/ait-progress/` 整个目录
- `ait-state` 扩展职责：兼任进度看板（原 progress 职责），既能渲染面板（`bin/ait state --version <v>`）又能落盘（`--save`），还能输出"未完成 chunk 列表"和"下一步建议"等进度叙述
- 触发语扩展为：`INVOKE THIS SKILL when the user asks to view AIT version state, refresh state.md, or check version progress / chunk three-state distribution / impl coverage`
- 主 SKILL.md 的速查表把 `/ait task list|show`、`/ait version status` 的 Routed skill 列从 `ait-progress` 改为 `ait-state`
- 主 SKILL.md 的 Sub-skills 索引表移除 `ait-progress` 行

#### 规则 3：ait-init-check 重定位并更名为 ait-init-guide
- 目录改名：`skill/ait/sub-skills/ait-init-check/` → `ait-init-guide/`
- 新职责：当 `bin/ait init` 进入"差异补全模式"（见 `prd-init-incremental`）时，逐项讨论用户要补哪些 global 文件，**不再做"新项目/旧项目"判别**（CLI 自己已能识别三种场景）
- 触发语改为：`INVOKE THIS SKILL when bin/ait init returns status=incomplete and the user needs to fill missing docs/global/* files interactively`
- CLI Dependencies：`bin/ait init --check`（诊断） / `bin/ait init`（执行补全） / `bin/ait reindex`
- 主 SKILL.md 的速查表把 `/ait init` 的 Routed skill 从 `ait-init-check` 改为 `ait-init-guide`

#### 规则 4：触发关键词去重与契约一致性
- 所有保留的 sub-skill（ait-discuss / ait-impl-discuss / ait-init-guide / ait-state / ait-resume / ait-task-execute）的 `description` 触发语两两不重叠
- 每个 sub-skill 的 CLI Dependencies / Artifacts / Output Contract / Common Pitfalls 四段必须完整
- 写入路径仍受主 SKILL.md Global Contract 限制（不直接写 `docs/` / `.meta/` / `versions/`）

### 验收标准
- [ ] `skill/ait/sub-skills/ait-task-execute/SKILL.md` 存在且四段完整（CLI Dependencies / Artifacts / Workflow / Common Pitfalls）
- [ ] `skill/ait/sub-skills/ait-progress/` 目录被删除
- [ ] `skill/ait/sub-skills/ait-init-guide/SKILL.md` 存在；旧 `ait-init-check/` 目录被删除
- [ ] `ait-state/SKILL.md` 的 description 触发语包含 progress / 进度 / 完成度 等关键词
- [ ] 主 SKILL.md 速查表的 Routed skill 列与 Sub-skills 索引表均同步更新（progress 全部替换为 state；init-check 替换为 init-guide）
- [ ] `grep -r "ait-progress\|ait-init-check" skill/ait/` 命中数为 0
- [ ] 6 个 sub-skill 的触发语两两不重叠（人工 review 通过）
- [ ] `/ait task execute` 端到端走通：CLI → ait-task-execute skill → AI 编码 → task complete

### 边界与非目标
- 不为 `prd commit` / `impl commit` / `version confirm` / `version reset` 单独建 sub-skill（单步 CLI 调用，main 路由足够）
- 不引入 `ait-task-create` 子 skill（拆 task 当前由 main 处理，复杂度未到需要独立 skill 的程度）
- 不重写所有现有 sub-skill 的 description（仅 ait-state 与 ait-init-guide 必需修改）
- 不引入 sub-skill 之间的显式调用链（仍由 AI 根据触发条件自主切换）

<!-- @ref:prd/ait-redesign#prd-task-stage rel:supersedes-path -->
<!-- @ref:prd/ait-redesign#prd-init rel:refines -->
<!-- @ref:prd/skills#prd-skills-overview rel:refines -->
