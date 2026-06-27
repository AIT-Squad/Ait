<!-- @id:[FSD]-ait-skill -->
## skill FSD

### 功能范围

AIT 的 skill 层：主 SKILL.md 清单 + 6 个 sub-skills。均为生成目标（target_file 指向各 SKILL.md），新模型为主。

<!-- @id:[FSD]-ait-skill:skill_manifest -->
## skill_manifest

### 功能描述

AIT skill 主清单（Claude 的 AIT 使用指令）。新模型为主叙事：开篇 Pipeline 以 prd(新模型)/fsd/tdd/codegen 为主线，旧 prdv1/impl/task 标 legacy；全局契约（CLI 入口、JSON 输出、project-docs 唯一权威、术语 chunk）；命令速查表新模型在前；版本原子性心智模型；sub-skills 路由索引；common pitfalls；scope boundaries。

<!-- @id:[FSD]-ait-skill:subskill_ait_discuss -->
## subskill_ait_discuss

### 功能描述

旧模型 PRD 讨论 sub-skill（触发 /ait prdv1 <title>）：Clarify→Design→Generate，经 CLI prdv1 save-draft/confirm。

<!-- @id:[FSD]-ait-skill:subskill_ait_impl_discuss -->
## subskill_ait_impl_discuss

### 功能描述

impl 规划 sub-skill：读上下文、生成 impl chunk（含 @extract）、注册到版本工作区。

<!-- @id:[FSD]-ait-skill:subskill_ait_init_guide -->
## subskill_ait_init_guide

### 功能描述

init 差异补全引导 sub-skill：逐项确认 global 文件是否补齐。

<!-- @id:[FSD]-ait-skill:subskill_ait_resume -->
## subskill_ait_resume

### 功能描述

错误恢复 sub-skill：按 CLI JSON code 给恢复步骤（含 version reset 指引）。

<!-- @id:[FSD]-ait-skill:subskill_ait_state -->
## subskill_ait_state

### 功能描述

状态面板 sub-skill：调用 state 渲染面板，兼进度查询、未完成项叙述。

<!-- @id:[FSD]-ait-skill:subskill_ait_task_execute -->
## subskill_ait_task_execute

### 功能描述

task 执行 sub-skill：据聚焦 context bundle 驱动 AI 编码，完成调用 task complete/fail 收口。
