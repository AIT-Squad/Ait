<!-- @id:[TDD]-skill_manifest -->
## skill_manifest TDD

```yaml
target_file: skill/ait/SKILL.md
```

### 技术栈

Markdown（Claude Code Skill 指令文档）。

### 文件职责

AIT skill 主清单（Claude 的 AIT 使用指令）。新模型为主叙事：开篇 Pipeline 以 prd(新模型)/fsd/tdd/codegen 为主线，旧 prdv1/impl/task 标 legacy；全局契约（CLI 入口、JSON 输出、project-docs 唯一权威、术语 chunk）；命令速查表新模型在前；**版本原子性心智模型（v2.21 命令面）：`version create` 显式开版本 → 逐层构建（写时门禁即时拦非法关联）→ `version confirm` 纯门禁可重复跑（六不变式报告，零落盘）→ `version merge` 唯一原子落盘（门禁前置，失败字节级回退）→ `version revert --confirm` 任意阶段整版退出（未合入版本；无局部撤销）。速查表 version 行 = create|commit|confirm|merge|revert|status；pitfalls 中 LOCKED/整版重置引用 revert（reset 已更名）**；sub-skills 路由索引；common pitfalls；scope boundaries。

### 单元测试要求

skill 文档无单测；由 sub-skill 触发与 CLI 契约间接验证。
