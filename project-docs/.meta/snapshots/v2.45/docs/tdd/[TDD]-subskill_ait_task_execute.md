<!-- @id:[TDD]-subskill_ait_task_execute -->
## subskill_ait_task_execute TDD

```yaml
target_file: skill/ait/sub-skills/ait-task-execute/SKILL.md
```

### 技术栈

Markdown（Claude Code Skill 指令文档）。

### 文件职责

task 执行 sub-skill：据聚焦 context bundle 驱动 AI 编码，完成调用 task complete/fail 收口。

### 单元测试要求

skill 文档无单测；由 sub-skill 触发与 CLI 契约间接验证。
