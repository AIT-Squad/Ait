---
name: ait
description: INVOKE THIS SKILL when the user types /ait followed by a subcommand (init, prd, impl, task, version, reindex, context, search, specgraph, deps, impact, state). AIT provides chunk-level version control for AI-collaborated PRD/impl documentation plus a prd→impl→task→code AI-coding pipeline, and routes concrete workflows to focused sub-skills.
---

# AIT — AI-Assisted Document Versioning

AIT (`/ait <subcommand>`) 是面向 AI 协作 PRD/impl 文档的 chunk 级版本控制系统，并提供 `prd → impl → task → code` 的 AI 编码流水线。主 skill 只负责路由、全局契约和命令速查；具体讨论、进度面板和恢复建议由 `sub-skills/` 下的 micro-skill 承担。

## Global Contract

- **入口命令**：项目根下统一使用 `project-docs/.ait/ait-cli <subcmd>`（由 `init` 自动生成的项目本地 wrapper）；唯一例外是 `init` 自身——首次运行用 `~/.claude/skills/ait/bin/ait init`，或安装路径变更后用 `~/.claude/skills/ait/bin/ait init --refresh-wrapper` 刷新本地 wrapper 与 `.meta/config.yaml`。不要假设系统存在全局 `ait`。
- **运行目录**：必须从包含 `project-docs/` 的项目根目录运行；不要从 `project-docs/` 内部运行。
- **写入规则**：不要直接写 `project-docs/versions/*`、`project-docs/docs/*` 或 `.meta/*`，所有持久化必须通过 `project-docs/.ait/ait-cli` 完成。
- **输出契约**：所有 CLI 命令 stdout 都是单个 JSON 对象：`{"ok": true, "data": {...}}` 或 `{"ok": false, "error": "...", "code": "..."}`。
- **术语约束**：使用 `chunk` 表示 `<!-- @id:xxx -->` 标注的文档单元；不要恢复 `block` 术语。

## 版本原子性（核心心智模型）

- **commit 即锁定**：`prd commit` 锁定 PRD，`impl commit` 锁定 impl。锁定后本版本不可改。
- **无局部撤销**：要反悔只能 `version reset <vX.Y> --confirm` 整版重置（物理删除，不留快照）。merged 版本不可 reset。
- 一个版本是「全有或全无」的原子单元。

## Pipeline

```text
/ait init                       → 引导生成全局基线 docs/global/*（仅在项目无任何版本时允许）
/ait prd create "<title>"       → 讨论并写 PRD（四段结构）→ confirm 写工作区 → commit 锁定
/ait impl create <prd-chunk>    → 设计实现（1 PRD chunk → N impl，可带 @extract）→ commit（pre-merge 校验）锁定
/ait task create <prd-chunk>    → 从 specgraph 派生 task YAML（impl_refs/global_refs/deps）
/ait task execute <id>          → 输出聚焦 context bundle 供 AI 编码
/ait task complete <id>         → 自动收口：标 done + 绑定 code_refs（无 task confirm）
/ait version confirm <vX.Y>     → 预检(全done+git干净)→合入基线→提取动态global→git commit(msg=title)
```

## Project Layout

```text
<cwd>/
└── project-docs/
    ├── docs/
    │   ├── prd/
    │   ├── impl/
    │   └── global/                    # init 生成：overview/tech-stack(static) + ddl/schema/api(dynamic)
    ├── versions/{vX.Y}/
    │   ├── prd/  ├── impl/  ├── tasks/T-*.yaml  └── state.md
    └── .meta/
        ├── chunks-index.yaml          # baseline chunk 台账（状态视角）
        ├── chunks-index-{vX.Y}.yaml   # version chunk 台账
        ├── specgraph.yaml             # baseline 关系图（关系视角，替代 links-index）
        ├── specgraph-{vX.Y}.yaml      # 每版本关系图（分文件）
        ├── requirements/req-NNN.yaml
        ├── versions/{vX.Y}.yaml       # 版本 meta（phase/锁定/title）
        └── changes/chg-NNN.yaml
```

> `links-index.yaml` 已废弃，所有关系查询走 specgraph。chunks-index 管「块自身状态」，specgraph 管「块之间关系」。

若当前目录没有 `project-docs/`，或位于 `project-docs/` 内部，应复述 CLI 错误码并提示切换到项目根目录；不要自动 scaffold。

## Command Quick Reference

| User trigger | CLI | Routed skill |
|---|---|---|
| `/ait init` | `~/.claude/skills/ait/bin/ait init`（引导命令；wrapper 尚未生成） | `ait-init-guide` |
| `/ait prd <title>` | `project-docs/.ait/ait-cli prd create/save-draft/confirm` | `ait-discuss` |
| `/ait prd commit ...` | `project-docs/.ait/ait-cli prd commit ... -m ...`（锁定 PRD） | main |
| `/ait prd show ...` | `project-docs/.ait/ait-cli prd show ...` | main |
| `/ait impl <prd-chunk-id>` | `project-docs/.ait/ait-cli context ...` + `project-docs/.ait/ait-cli impl create` | `ait-impl-discuss` |
| `/ait impl commit ...` | `project-docs/.ait/ait-cli impl commit ... -m ...`（pre-merge 校验+锁定） | main |
| `/ait impl show ...` | `project-docs/.ait/ait-cli impl show ...` | main |
| `/ait task create [chunk]` | `project-docs/.ait/ait-cli task create [chunk]` | main |
| `/ait task execute [id]` | `project-docs/.ait/ait-cli task execute [id]` → 驱动 AI 编码 → `task complete/fail` | main |
| `/ait task list\|show` | `project-docs/.ait/ait-cli task list\|show ...` | `ait-state` |
| `/ait version confirm <v>` | `project-docs/.ait/ait-cli version confirm <v>` | main |
| `/ait version reset <v>` | `project-docs/.ait/ait-cli version reset <v> --confirm` | `ait-resume` |
| `/ait version status <v>` | `project-docs/.ait/ait-cli version status <v>` | `ait-state` |
| `/ait state [--version v]` | `project-docs/.ait/ait-cli state ...` | `ait-state` |
| `/ait search <query>` | `project-docs/.ait/ait-cli search <query>` | main |
| `/ait context <chunk-id>` | `project-docs/.ait/ait-cli context <chunk-id>` | main |
| `/ait specgraph\|deps\|impact ...` | `project-docs/.ait/ait-cli specgraph\|deps\|impact ...` | main |
| CLI error recovery | inspect `code` and `error` | `ait-resume` |

## task execute 的职责边界（重要）

`task execute` **不写代码**。它把任务标记为 `executing`，并输出一个 token 聚焦的 context bundle（只含该 task 的 `impl_refs ∪ global_refs`，不读全树）。Skill 层据此驱动 AI 编码，完成后调用：

- `project-docs/.ait/ait-cli task complete <id> --commit <hash> --path <file>` → 标 done + 绑定 code_refs
- `project-docs/.ait/ait-cli task fail <id>` → 标 failed（可重跑 execute）

没有 `task confirm`——execute 成功即收口，人工审核统一到 `version confirm`。

## Sub-skills 索引

| Sub-skill | Trigger | Purpose |
|---|---|---|
| `ait-discuss` | `/ait prd <title>` 创建/讨论 PRD | Clarify → Design → Generate，CLI 保存草稿与确认 PRD。 |
| `ait-impl-discuss` | `/ait impl <prd-chunk-id>` 规划/生成 impl | 读上下文、生成 impl chunk（含 @extract）、CLI 注册到版本工作区。 |
| `ait-state` | 查看/刷新 `state.md`、询问版本进度、chunk 三态、impl 覆盖、task 状态 | 调用 `state [--save]` 渲染面板，并兼任进度查询、未完成项叙述。 |
| `ait-resume` | CLI 返回错误或要求恢复中断流程 | 根据 JSON `code` 给恢复步骤（含 version reset 指引）。 |
| `ait-init-guide` | `/ait init` 进入差异补全模式时使用 | init 进入差异补全模式时，逐项确认 global 文件是否补齐；不再做新/旧项目判别（CLI 自识别）。 |

## Required Knowledge

参考文档位于 skill 内 `references/`：

- `chunk-system.md`：`@id` / `@ref` / `@extract` 规范。
- `index-system.md`：baseline/version index 与 specgraph 语义。
- `chunk-parser.md`：chunk 与 @extract 解析边界。
- `version-manager.md`：三态提交、锁定、confirm、reset。
- `merge-engine.md`：merge 与动态 global 提取。
- `overview.md`：设计边界。

## Common Pitfalls

| Code / symptom | Likely cause | Recovery |
|---|---|---|
| `LOCKED` | 试图改已 commit 的 PRD/impl | 锁定后不可改；要改用 `version reset <v> --confirm` 整版重来。 |
| `ID_FORMAT` | chunk ID 含大写/下划线/非法字符 | 改为 `{type}-{domain}-{name}` 小写短横线。 |
| `PRD_NOT_COMMITTED` | impl 引用的 PRD chunk 仍 working/staged | 先 `project-docs/.ait/ait-cli prd commit <prd-file> -m "..."`。 |
| `PREMERGE_FAILED` | impl commit 时检出依赖成环或版本内重复（同 @id / 同 @extract 目标） | 修正 impl 设计后重新 commit。 |
| `PRD_NOT_LOCKED` | task create 时 PRD 未锁定 | 先 `prd commit` 锁定 PRD。 |
| `NO_IMPL` | task create 的 PRD chunk 无 impl 覆盖 | 先为该 PRD chunk 设计 impl。 |
| `BLOCKED` | task execute 的依赖 task 未 done | 先执行其 `depends_on` 的上游 task。 |
| `TASK_NOT_DONE` | version confirm 时有 task 非 done | 先跑完/修复所有 task。 |
| `GIT_DIRTY` | version confirm 时 git 工作区不干净 | 先提交/暂存改动，或加 `--allow-dirty-git`。 |
| `MERGE_ROLLBACK` | confirm 的 merge/commit 阶段失败 | docs/ 已自动回退；查 error 详情修复后重试。 |
| `NOT_AT_PROJECT_ROOT` / `CWD_INSIDE_PROJECT_DOCS` | 运行目录不对 | 切到包含 `project-docs/` 的父目录。 |
| `ENOENT_BIN_AIT`（虚拟码，shell 错误：`no such file or directory: bin/ait` 或 `command not found: ait`） | 在用户项目根用了相对路径 `bin/ait` 调用 CLI；shell 找不到入口，CLI 不会执行 | 改用 `project-docs/.ait/ait-cli <subcmd>`；若该薄壳不存在，先跑 `~/.claude/skills/ait/bin/ait init --refresh-wrapper` 生成。注：此 code **非** CLI 真实返回，仅为文档兜底标识，不在 `ait/schemas.py` 注册，也不进入 `ait-resume` 处理链路。 |

## Scope Boundaries

- AI 编码由 Skill 层驱动；CLI 只负责派生 task、输出聚焦上下文、记录 code_refs，不直接生成业务代码。
- 不提供多用户协作锁。
- 不提供系统级全局 `ait` 命令。
- 不支持 `/ait:foo` colon 命名空间；skill 触发使用 `/ait foo`。
- 不绕过 CLI 直接修改 AIT 管理文档或 `.meta`。
- 动态 global（ddl/schema/api）内容只来自 impl 的 @extract，不接受人工直接编辑。
