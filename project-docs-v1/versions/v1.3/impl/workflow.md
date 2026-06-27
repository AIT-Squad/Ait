<!-- @id:impl-workflow-skill-migration -->

# 参考项目 Skill 功能迁移实现

## 目标

把参考项目 `tools/ait/templates/skills` 中可复用的 micro-skill 能力迁移到当前项目，但按当前 AIT 的目录、CLI 和写入契约重新组织。

## 输入素材

- 参考项目的主 router 模板。
- 参考项目的 PRD 讨论、impl 讨论、progress、resume 子 skill 模板。
- 当前项目 v1.2 的 `prd-skills-*` 规划。

## 迁移步骤

1. 对参考项目模板做术语替换：`block` 全部改为 `chunk`。
2. 将 `.planning/*` 数据源替换为 `project-docs/.meta/*`。
3. 将所有 `ait <cmd>` 调用替换为 `bin/ait <cmd>`。
4. 删除与 `phases/`、`task/`、`issues.md` 强绑定的流程，只保留 v1.3 允许的占位说明。
5. 将具体流程写入四个子 skill，主 `SKILL.md` 仅保留 router 索引。

## 子 Skill 清单

| 子 skill | 来源能力 | 当前项目职责 |
|---|---|---|
| `ait-discuss` | PRD 讨论 | 驱动 `prd create/save-draft/confirm` |
| `ait-impl-discuss` | impl 讨论 | 驱动 `context` 与 `impl create` |
| `ait-progress` | 进度查看 | 读取 chunks-index 输出三态统计 |
| `ait-resume` | 错误恢复 | 基于 CLI `code` 给出恢复建议 |

## 验收

- 4 个子 skill 均存在，且格式满足 `impl-skills-format-adapt`。
- 主 router 不再包含长篇 PRD/impl 生成流程。
- 全部迁移内容均使用当前项目路径和命令。

<!-- @ref:prd/todo1-skill-migration#prd-skill-migration rel:implements -->

<!-- @id:impl-workflow-init-upgrade -->

# Init 流程智能识别实现

## 目标

在不改变 `bin/ait init` 入口和 `root.py` 函数签名的前提下，让 AI 在 init 场景中识别新项目、旧项目和已有 `project-docs/` 的项目。

## 子 Skill

新增 `skill/ait/sub-skills/ait-init-check/SKILL.md`。

触发语用于描述：当用户运行 `bin/ait init`，且需要判断当前目录是否为新项目或已有项目时调用。

## root.py 最小改动

只在现有 init 逻辑附近添加 AI 可读提示注释：

```python
# AI_HINT: if project-docs exists, explain that version management is already enabled.
# AI_HINT: if this is an existing project without project-docs, invoke ait-init-check to guide adoption.
```

不修改 CLI 参数解析，不新增交互式 `read -p`。

## 判断规则

| 场景 | 判断方式 | 行为 |
|---|---|---|
| 新项目 | 目录为空或无明显源码/git 历史 | 走原有 init 创建流程 |
| 旧项目且已有 `project-docs/` | 存在项目文档目录 | 提示已接入，跳过 |
| 旧项目但无 `project-docs/` | 有源码/git 历史但无文档目录 | 引导用户是否创建初始版本 |

## 验收

- `bin/ait init --help` 输出不变。
- `ait-init-check/SKILL.md` 存在且不直接写文件。
- 旧项目无 `project-docs/` 时，由 AI 给出接入版本管理的下一步命令建议。

<!-- @ref:prd/todo2-init-upgrade#prd-init-upgrade rel:implements -->
