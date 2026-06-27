<!-- @id:[TDD]-subskill_ait_discuss -->
## subskill_ait_discuss TDD

```yaml
target_file: skill/ait/sub-skills/ait-discuss/SKILL.md
```

### 技术栈

Markdown（Claude Code Skill 指令文档）。

### 文件职责

旧模型 PRD 讨论 sub-skill（触发 /ait prdv1 <title>）：Clarify→Design→Generate，经 CLI prdv1 save-draft/confirm。

### 单元测试要求

skill 文档无单测；由 sub-skill 触发与 CLI 契约间接验证。