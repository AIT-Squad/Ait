<!-- @id:prd-skill-state -->

# 目标3：ait-state Skill（版本进度面板）

## 需求来源

用户明确要求：

> 有一个版本的完成进度和信息汇总，放到版本下，命名为 state.md
> state.md 由 skill 在 merge 之后驱动生成，做完 impl 之后 merged，然后确认后再生成 state.md
> state.md 在版本生成时候就产生，然后给用户显示当前的状态，包括 prd 规划进度，impl 规划进度，task 拆分后开发的进度

## 核心设计

### state.md 的生命周期

```
version create v1.3
      │
      ▼
【生成】state.md 初始版本（仅含版本元信息 + PRD 规划进度 0%）
      │
      ▼
... PRD chunks 逐条 prd save-draft → prd commit ...
      │
      ▼
【刷新】ait-state skill 被调用 → 更新 PRD 规划进度
      │
      ▼
... impl chunks 逐条 impl create → impl commit ...
      │
      ▼
【刷新】ait-state skill 被调用 → 更新 impl 规划进度
      │
      ▼
... （未来 v1.4+）task 拆分 → 开发进度 ...
      │
      ▼
【刷新】ait-state skill 被调用 → 更新开发进度
      │
      ▼
version merge v1.3
      │
      ▼
【最终刷新】ait-state skill 被调用 → 生成最终 state.md（含完整进度汇总）
```

### state.md 的三阶段内容

| 阶段 | 内容 | 数据来源 |
|---|---|---|
| Phase 1：PRD 规划中 | 版本元信息 + PRD chunk 三态分布（working/staged/committed）+ PRD 完成百分比 | `.meta/versions/<v>.yaml` + `.meta/chunks-index-<v>.yaml` |
| Phase 2：Impl 规划中 | 上述 + impl chunk 三态分布 + PRD→impl 映射关系 + 未覆盖的 PRD chunk 清单 | 同上 + SpecGraph |
| Phase 3：Merge 后（最终） | 上述 + 版本变更摘要（from baseline → to merged）+ 需求映射表（PRD chunk ↔ 用户需求）+ 健康度评分 | 同上 + merge commit 记录 |

## state.md 格式规范

### 初始版本（Phase 1）

```markdown
# 版本状态：v1.3

> 最后更新：2026-05-26T07:53:00Z | 更新者：ait-state skill | 触发事件：version create

## 元信息

| 字段 | 值 |
|---|---|
| 版本号 | v1.3 |
| 基于版本 | v1.2 |
| 创建时间 | 2026-05-26T07:53:00Z |
| 状态 | planning-prd |
| PRD 完成度 | 0 / 8 chunk（0%） |
| Impl 完成度 | —（PRD 未完成） |

## PRD Chunk 三态分布

| 状态 | 数量 | 占比 |
|---|---|---|
| ✅ committed | 0 | 0% |
| 📝 staged | 0 | 0% |
| ✏️ working | 8 | 100% |
| **合计** | **8** | **100%** |

## 当前 working 中的 PRD Chunk

| Chunk ID | 标题 | 创建时间 | 状态 |
|---|---|---|---|
| `prd-release-v13-overview` | v1.3 版本概述 | 2026-05-26 | working |
| `prd-backlog-v12-legacy` | v1.2 遗留实现清单 | 2026-05-26 | working |
| ... | ... | ... | ... |

## 需求映射（v1.3 覆盖的需求）

| 需求来源 | 需求描述 | 覆盖的 PRD chunk |
|---|---|---|
| v1.2 遗留 | `prd-skills-layout` 未实现 impl | `prd-backlog-v12-legacy` |
| `todo.md#1` | 参考项目 skill 功能迁移 | `prd-skill-migration` |
| `todo.md#2` | init 流程智能识别旧项目 | `prd-init-upgrade` |
| `todo.md#3` | links-index.yaml 重构为 SpecGraph | `prd-specgraph-index` |
| `todo.md#4` | 检索/聚焦读取命令行迁移 | `prd-search-cli` |
| 目标3 | state.md 版本进度面板 | `prd-skill-state` |
| v1.2 遗留 | `prd-skills-router` 等 5 个 chunk 的 impl | `prd-backlog-v12-legacy` |

## 健康度

- 🟡 PRD 规划进行中（0% 完成）
- 无阻塞项
```

### 中期版本（Phase 2，impl 规划中）

在 Phase 1 基础上增加：

```markdown
## Impl Chunk 三态分布

| 状态 | 数量 | 占比 |
|---|---|---|
| ✅ committed | 2 | 20% |
| 📝 staged | 1 | 10% |
| ✏️ working | 7 | 70% |
| **合计** | **10** | **100%** |

## PRD → Impl 覆盖情况

| PRD Chunk | 是否有 Impl | Impl Chunk | 覆盖状态 |
|---|---|---|---|
| `prd-release-v13-overview` | ✅ | `impl-v13-overview` | ✅ 已覆盖 |
| `prd-backlog-v12-legacy` | ✅ | `impl-v13-backlog` | ✅ 已覆盖 |
| ... | ... | ... | ... |
| `prd-skill-state` | ❌ | — | ⚠️ 未覆盖 |

## 未覆盖的 PRD Chunk（需要 impl 规划）

- `prd-skill-state`（ait-state skill 本身是否需要 impl？→ 需要，对应 `impl-v13-state-skill`）
```

### 最终版本（Phase 3，merge 后）

在 Phase 2 基础上增加：

```markdown
## 版本变更摘要

### 相较于 v1.2 baseline

**PRD 变更**：
- 新增 7 个 PRD chunk（`prd-v13-*`）
- 继承 v1.2 的 8 个 PRD chunk（通过 `based-on: v1.2`）

**Impl 变更**：
- 新增 10 个 impl chunk（`impl-v13-*`）
- v1.2 的 2 个 impl chunk 继续有效（已 committed）

### Merge 信息

| 字段 | 值 |
|---|---|
| Merge 时间 | 2026-06-01T10:00:00Z |
| Merge 触发者 | /ait version merge v1.3 |
| 冲突解决方式 | 无冲突（baseline 无后续提交） |

## 健康度评分

| 维度 | 评分 | 说明 |
|---|---|---|
| PRD 覆盖率 | 100% | 8 / 8 committed |
| Impl 覆盖率 | 100% | 10 / 10 committed |
| 需求覆盖率 | 100% | 6 / 6 需求有对应 PRD + impl |
| **综合评分** | **100%** | ✅ 版本健康 |

## 已知问题（Non-Goals 追踪）

- `ait-progress` / `ait-resume` 子 skill 本期仅占位，未完整实现（留 v1.4）
- `phases/` + `task/` 体系未引入（留 v1.4+）
- 语义搜索（embedding）未实现（留 v1.4+）
```

## ait-state Skill 设计

### 文件位置

`skill/ait/sub-skills/ait-state/SKILL.md`（新增子 skill）

### 触发语

```
INVOKE THIS SKILL when the user types `/ait state` or after any `version merge` operation to display the current version's progress panel (PRD distribution, impl coverage, health score).
```

### 行为流程

```
用户调用 /ait state
        │
        ▼
【Step 1】读取版本元信息
        └── cat .meta/versions/<current>.yaml
        │
        ▼
【Step 2】读取 chunks-index
        └── load .meta/chunks-index-<current>.yaml
        │
        ▼
【Step 3】读取 SpecGraph（如有）
        └── load .meta/specgraph.yaml
        │
        ▼
【Step 4】计算三态分布 + 覆盖率 + 健康度
        │
        ▼
【Step 5】渲染 state.md 内容（输出到终端 + 可选写入文件）
        │
        ▼
【Step 6】询问用户：是否写入 versions/<v>/state.md？
        └── y → bin/ait state save（写入文件）
        └── n → 仅终端显示
```

### CLI 接口

| 命令 | 用途 |
|---|---|
| `bin/ait state` | 显示当前版本状态（终端输出） |
| `bin/ait state --save` | 显示并写入 `versions/<v>/state.md` |
| `bin/ait state --version v1.2` | 查看指定版本状态 |
| `bin/ait state --format json` | JSON 格式输出（供 AI 解析） |

### 自动触发时机

| 触发事件 | 是否自动调用 ait-state |
|---|---|
| `bin/ait prd commit` | ✅ 自动调用（刷新 PRD 分布） |
| `bin/ait impl commit` | ✅ 自动调用（刷新 PRD + impl 分布） |
| `bin/ait version merge` | ✅ 自动调用（生成最终 state.md） |
| 用户手动 `/ait state` | ✅ 手动触发 |

## 与 v1.2 PRD 的关系

v1.2 `prd-skills-contract` 中定义了子 skill 的写入禁令：

> 子 skill 禁止直接写文件，必须通过 `bin/ait` CLI

**ait-state 遵守该契约**：
- `ait-state` 默认只**终端输出**，不写文件
- 写入 `state.md` 必须通过 `bin/ait state --save`（主 CLI 入口）
- 符合 v1.2 定义的子 skill 行为边界

## 验收标准

### state.md 内容验收

1. 版本创建后 `versions/v1.3/state.md` 存在（初始版本）
2. `state.md` 包含三态分布表（working/staged/committed）
3. `state.md` 包含需求映射表（PRD chunk ↔ 用户需求）
4. Impl commit 后，`state.md` 自动刷新，显示 impl 覆盖率
5. `version merge` 后，`state.md` 显示最终变更摘要 + 健康度评分

### ait-state skill 验收

1. `skill/ait/sub-skills/ait-state/SKILL.md` 存在
2. frontmatter description 以 `INVOKE THIS SKILL when` 起头
3. `bin/ait state --help` 显示 4 个子命令
4. `bin/ait state` 终端输出与 `state.md` 内容一致
5. `bin/ait state --save` 成功写入 `versions/<v>/state.md`
6. `bin/ait prd commit` 后自动刷新 `state.md`（验证自动触发）

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| state.md 的 Web UI 展示 | 不在 CLI 工具范围内 |
| 历史版本 state.md 的 diff 对比 | v1.4+ |
| state.md 的 AI 自然语言问答（"这个版本还差多少完成？"） | v1.4+（需要 AI 端支持） |
