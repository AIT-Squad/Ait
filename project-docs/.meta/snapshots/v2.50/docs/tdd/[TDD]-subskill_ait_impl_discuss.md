<!-- @id:[TDD]-subskill_ait_impl_discuss -->
## subskill_ait_impl_discuss TDD

```yaml
target_file: skill/ait/sub-skills/ait-impl-discuss/SKILL.md
```

### 技术栈

Markdown（Claude Code Skill 指令文档）。

### 文件职责

impl 规划 sub-skill：读上下文、生成 impl chunk（含 @extract）、注册到版本工作区。

### 单元测试要求

skill 文档无单测；由 sub-skill 触发与 CLI 契约间接验证。
