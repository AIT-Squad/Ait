# 新模型 PRD/FSD/TDD 格式规范（权威源）

> 本文件是 AIT 新模型文档格式的**单一权威说明**，随 ait skill 分发，用户在任意项目使用时以此为准。
> **强制执行**在代码侧：`chunk_parser.py`（语法）、`new_model_validator.py`（图/唯一性）、`new_model_manager.py`（target_file）。本文件是人读规范；章节骨架见 `skill/ait/templates/TEMPLATE-{PRD,FSD,TDD}-AIT-DRAFT.md`。

## 1. 模型概览

```
[PRD]-<name> ──decomposes──▶ [FSD]-<name>（根 FSD）
[FSD]-x ──(内部 split)──▶ [FSD]-x:<split> ──decomposes──▶ [FSD]-y（子 FSD 根）
                                            └─details──▶ [TDD]-z（叶子，绑 target_file）
[FSD]-x:<a> ──depends_on──▶ [FSD]-x:<b>（同父兄弟 split）
```

PRD 递归分解为 FSD 功能树；叶子 FSD 的内部 split `details` 到 TDD；每个 TDD 唯一映射一个 `target_file`（生成目标）。

## 2. chunk ID 格式

- **根 chunk**：`[PRD]-<name>` / `[FSD]-<name>` / `[TDD]-<name>`，且**文件名 = 根 chunk id**（如 `fsd/[FSD]-ait.md`）。
- **内部 split**：`<父根id>:<split名>`，如 `[FSD]-ait:version`、`[TDD]-x:detail`。split 名用 `_` 连接多词。
- **前缀**：必须是 `[PRD]` / `[FSD]` / `[TDD]`（方括号）。名内用 `_`，层级用 `-`。
- 解析见 `chunk_parser.py`：`@id` / `@ref` 注释、代码围栏屏蔽、bracket 前缀、`:` split。

## 3. 关系（仅三种，必须显式建边，不从命名推断）

| 关系 | 合法连接 | 说明 |
|------|----------|------|
| `decomposes` | PRD 根 → 根 FSD 根；FSD 内部 split → 子 FSD 根 | 功能分解；父子边从**父的内部 split**发出（PRD 根→根 FSD 除外） |
| `details` | 叶 FSD 内部 split → TDD 根 | 叶子细化到代码/产物 |
| `depends_on` | 同一父 FSD 下的两个**兄弟 internal split** | 依赖只在同级 split 间；跨级须上提到父 split 层 |

**结构规则**：一个 FSD 节点**不得混用** FSD 子（decomposes）与 TDD 子（details）—— 要么是分解节点、要么是叶子。

## 4. target_file 规则

- **每个 TDD 必须含 `target_file`**（缺失报 `TDD_TARGET_FILE_REQUIRED`）；写在 TDD 根 chunk 的 yaml 代码块：```yaml\ntarget_file: <path>\n```。
- **唯一性**：同范围内不同 TDD 不得声明同一 `target_file`（重复报 `DUPLICATE_TARGET_FILE`）—— 这是"多人不撞同一文件"的硬保证。
- **可指任意生成目标文件**：不限源码，测试/模板/SKILL.md/脚本等皆可。
- markdown 为准（target_file 从 TDD 正文读）。

## 5. 章节结构

各类文档的章节骨架见模板（指引性，代码不强制章节）：
- `templates/TEMPLATE-PRD-AIT-DRAFT.md`：背景/目标/范围/用户故事/验收（只写 why/what，不拆模块）。
- `templates/TEMPLATE-FSD-AIT-DRAFT.md`：功能总览/功能依赖/交互契约/数据契约（可递归拆子 FSD）。
- `templates/TEMPLATE-TDD-AIT-DRAFT.md`：target_file/技术栈/文件职责/核心逻辑/单元测试要求（一文件一映射）。

## 6. 校验与错误码

运行 `ait specgraph validate-new-model [--version v]` 触发：

| code | 含义 |
|------|------|
| `INVALID_PRD_DECOMPOSES` / `INVALID_FSD_DECOMPOSES` / `INVALID_DETAILS` / `INVALID_DEPENDS_ON_TYPES` | 关系连接的类型/根-split 不合法 |
| `DEPENDS_ON_ROOT_CHUNK` / `DEPENDS_ON_CROSS_LEVEL` | depends_on 指向根、或跨级（须上提父 split） |
| `FSD_MIXED_CHILDREN` | 一个 FSD 混用 FSD 子与 TDD 子 |
| `DUPLICATE_TARGET_FILE` | 两个 TDD 声明同一 target_file |
| `MISSING_ENDPOINT` | 边端点 chunk 不在 specgraph |

## 7. 版本合并语义（modify / add）

`version confirm` 时 merge 按**每个 chunk 的真实存在性**逐块处理（`merge_engine.py`）：
- **modify = 整块全替换**：version 侧提供该 chunk 的**完整最终内容**（要保留的须自带），整个替换 baseline 对应 chunk。
- **add = 仅新增** baseline 不存在的 chunk。
- modify 的目标若不在 baseline → 自动当作 add 追加；**merge 绝不静默丢 chunk**。
- `add` 命中已存在 chunk 报错（提示改 modify）。

## 8. 生命周期速查

`init --new-model` → `prd/fsd/tdd create`（+`fsd link` 建边）→ `validate-new-model` → `version commit`（working→committed）→ `version confirm`（合入基线）→ `codegen prepare <[TDD]>`（驱动编码）。
