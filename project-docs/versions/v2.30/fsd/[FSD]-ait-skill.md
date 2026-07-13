<!-- @id:[FSD]-ait-skill -->
## skill FSD

### 功能范围

AIT 的 skill 层：主 SKILL.md 清单 + 6 个 sub-skills + 3 个文档模板 + 7 个 references 参考资产。均为生成目标（target_file 指向对应分发文件），新模型为主。

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

<!-- @id:[FSD]-ait-skill:template_prd -->
## template_prd
### 功能描述
新模型 PRD 文档模板（章节结构指引），details [TDD]-template_prd。随 skill 分发。

<!-- @id:[FSD]-ait-skill:template_fsd -->
## template_fsd
### 功能描述
新模型 FSD 文档模板（功能分解/交互契约章节），details [TDD]-template_fsd。随 skill 分发。

<!-- @id:[FSD]-ait-skill:template_tdd -->
## template_tdd
### 功能描述
新模型 TDD 文档模板（target_file/技术栈/职责/单测章节），details [TDD]-template_tdd。随 skill 分发。

<!-- @id:[FSD]-ait-skill:ref_new_model_format -->
## ref_new_model_format
### 功能描述
新模型 PRD/FSD/TDD 格式权威规范（ID 前缀、内部 split、三关系及合法性、target_file 唯一性、章节结构、validate-new-model 校验项），details [TDD]-ref_new_model_format。随 skill 分发，是用户在任意项目使用 AIT 时的格式权威源。

<!-- @id:[FSD]-ait-skill:ref_chunk_system -->
## ref_chunk_system
### 功能描述
chunk 系统参考（@id 语法、chunk 边界、ID 命名规则；@ref/@extract 与 links-index 段属 legacy 机制），details [TDD]-ref_chunk_system。随 skill 分发。

<!-- @id:[FSD]-ait-skill:ref_chunk_parser -->
## ref_chunk_parser
### 功能描述
chunk 解析器参考（@id/@ref 解析边界、代码围栏屏蔽、数据结构），as-built 解析行为说明，details [TDD]-ref_chunk_parser。随 skill 分发。

<!-- @id:[FSD]-ait-skill:ref_index_system -->
## ref_index_system
### 功能描述
索引体系参考（chunks-index baseline/per-version 语义、specgraph 关系存储；links-index 段属已废弃机制），details [TDD]-ref_index_system。随 skill 分发。

<!-- @id:[FSD]-ait-skill:ref_merge_engine -->
## ref_merge_engine
### 功能描述
合并引擎参考（按 baseline 真实存在性逐 chunk 处理 add/modify、整块全替换、绝不丢 chunk），details [TDD]-ref_merge_engine。随 skill 分发。

<!-- @id:[FSD]-ait-skill:ref_overview -->
## ref_overview
### 功能描述
AIT 设计总览参考（核心矛盾、双模型定位——新模型主线 prd→fsd→tdd→codegen 与 legacy、设计边界），details [TDD]-ref_overview。随 skill 分发。

<!-- @id:[FSD]-ait-skill:ref_version_manager -->
## ref_version_manager
### 功能描述
版本管理参考（三态 working→staged→committed、四件套 create/confirm纯门禁/merge唯一落盘/revert、层级冻结-返工、验收门禁），details [TDD]-ref_version_manager。随 skill 分发。
