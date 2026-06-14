# AIT MVP — 5 分钟端到端 Walkthrough

跑一遍 AIT 的 7 个核心命令，从空目录到完整的"PRD → impl → 合并到基线"闭环。

## 准备

```bash
# 1. 安装
cd /path/to/ait
uv venv
uv pip install -e ".[dev]"

# 2. 在 /tmp 下创建一个新项目目录
#    AIT 自 v1.1 起强制要求工作目录下有 project-docs/ 子目录，名字硬编。
mkdir -p /tmp/ait-demo/project-docs/{docs/{prd,impl},versions,.meta/{versions,changes,requirements}}

# 3. cd 到项目根（project-docs/ 的父目录），后续所有 ait 命令都从这里运行。
#    不要 cd 进 project-docs/——会被拒绝（CWD_INSIDE_PROJECT_DOCS）。
cd /tmp/ait-demo
```

> 也可以让 AIT 自己来 dogfood：`cd d:/Research/AIT-project`（注意是仓库根，不是 `project-docs/` 本身），这是项目自身的文档目录。

## Step 1 — `/ait prd <title>` 创建需求 + AI 讨论

```bash
uv run ait prd create "图书推荐"
```

输出：

```json
{"ok": true, "data": {"req_id": "req-001", "version": "v1.0", "title": "图书推荐"}}
```

→ 已经自动创建 `project-docs/versions/v1.0/`、`project-docs/.meta/requirements/req-001.yaml`、`project-docs/.meta/versions/v1.0.yaml`。

接下来是 **AI 三阶段讨论**（在 Skill 形态里由 Claude 主导对话）。本 walkthrough 跳过对话过程，直接给出讨论收敛后的 PRD：

```bash
cat > /tmp/recommend-prd.md <<'EOF'
<!-- @id:prd-recommend-overview -->
## 概述

基于借阅历史推荐图书。MVP 仅按借阅频率，不考虑评分。

<!-- @id:prd-recommend-rules -->
## 业务规则

1. 不推荐用户已借阅过的图书
2. 推荐列表上限 20 本，分页返回
3. 借阅频率统计窗口为最近 90 天
EOF

uv run ait prd save-draft req-001 --content-file /tmp/recommend-prd.md
```

输出：

```json
{"ok": true, "data": {"req_id": "req-001", "status": "prd_draft",
                       "chunk_count": 2,
                       "chunk_ids": ["prd-recommend-overview", "prd-recommend-rules"]}}
```

PRD 草稿存进了 `project-docs/.meta/requirements/req-001.yaml`，状态推进到 `prd_draft`。

## Step 2 — `confirm` 写入版本工作区

```bash
uv run ait prd confirm req-001 --file recommend
```

```json
{"ok": true, "data": {"req_id": "req-001", "version": "v1.0",
                       "file": "prd/recommend",
                       "chunk_ids": ["prd-recommend-overview", "prd-recommend-rules"]}}
```

现在：

- `project-docs/versions/v1.0/prd/recommend.md` 已经写入完整 PRD markdown
- `project-docs/.meta/chunks-index-v1.0.yaml` 注册了 2 个 chunk，`state=working`，`action=add`
- requirement 状态推进到 `prd_confirmed`

## Step 3 — `/ait prd commit` 提交 PRD

```bash
uv run ait prd commit prd/recommend -m "首版推荐 PRD" --req-id req-001
```

```json
{"ok": true, "data": {"version": "v1.0", "prd_file": "prd/recommend",
                       "staged": ["prd-recommend-overview", "prd-recommend-rules"],
                       "commit_id": "c1",
                       "changes": ["chg-001", "chg-002"]}}
```

`project-docs/.meta/changes/chg-001.yaml` 和 `chg-002.yaml` 已生成，记录了每个块的 ADD 操作和完整内容。

## Step 4 — `/ait impl <chunk-id>` 生成 impl

先看一下 AI 上下文（这是 `/ait impl` 真正驱动 AI 之前的一步）：

```bash
uv run ait context prd-recommend-overview --scenario prd-to-impl
```

返回 L1 (PRD chunk) + L2 (已有 impl 模式，本例为空)。AI 据此生成 impl。这里直接给出 impl markdown：

```bash
cat > /tmp/recommend-impl.md <<'EOF'
<!-- @id:impl-api-recommend -->
## 推荐接口

GET /api/v1/books/recommend

| 字段 | 类型 | 说明 |
|------|------|------|
| reader_id | string | 必填 |
| limit | int | 默认 20 |

响应：图书列表 + 推荐分数。
EOF

uv run ait impl create prd-recommend-overview \
  --content-file /tmp/recommend-impl.md --req-id req-001
```

```json
{"ok": true, "data": {"version": "v1.0",
                       "file": "impl/api-contracts",
                       "chunk_ids": ["impl-api-recommend"]}}
```

`project-docs/versions/v1.0/impl/api-contracts.md` 已经写入，并自动追加了：

```markdown
<!-- @ref:prd/recommend#prd-recommend-overview rel:implements -->
```

## Step 5 — `/ait impl commit`

```bash
uv run ait impl commit impl-api-recommend -m "推荐 API" --req-id req-001
```

```json
{"ok": true, "data": {"version": "v1.0",
                       "impl_block_id": "impl-api-recommend",
                       "staged": ["impl-api-recommend"],
                       "commit_id": "c2",
                       "changes": ["chg-003"]}}
```

注意：如果忘了先 commit PRD，这里会报 `E1 PRD_NOT_COMMITTED`，提示先 commit 关联 PRD。

## Step 6 — `/ait version merge`

```bash
uv run ait version merge v1.0
```

```json
{"ok": true, "data": {"merged_chunks": ["prd-recommend-overview",
                                          "prd-recommend-rules",
                                          "impl-api-recommend"],
                       "conflicts": [], "skipped": [], "status": "completed"}}
```

执行完后：

```
/tmp/ait-demo/project-docs/docs/prd/recommend.md          # ← 新建，含两个 PRD 块
/tmp/ait-demo/project-docs/docs/impl/api-contracts.md     # ← 新建，含 impl 块 + @ref
/tmp/ait-demo/project-docs/.meta/chunks-index.yaml        # ← 重建，包含 3 个 chunk
/tmp/ait-demo/project-docs/.meta/links-index.yaml         # ← 包含 implements 关联
/tmp/ait-demo/project-docs/.meta/snapshots/v1.0/docs/     # ← 合并快照
```

## 完整目录结构

跑完上面 6 步后：

```
/tmp/ait-demo/                  # ← 你 cd 到这里运行 ait
└── project-docs/               # ← AIT 唯一识别的工作根（名字硬编）
    ├── docs/
    │   ├── prd/
    │   │   └── recommend.md
    │   └── impl/
    │       └── api-contracts.md
    ├── versions/
    │   └── v1.0/
    │       ├── prd/recommend.md
    │       └── impl/api-contracts.md
    └── .meta/
        ├── chunks-index.yaml
        ├── chunks-index-v1.0.yaml
        ├── links-index.yaml
        ├── changes/{chg-001,chg-002,chg-003}.yaml
        ├── requirements/req-001.yaml
        ├── snapshots/v1.0/docs/
        └── versions/v1.0.yaml
```

## 冲突场景演示

假设有人在你 fork 后修改了基线，再跑 merge 会触发冲突：

```bash
# 人工编辑 project-docs/docs/prd/recommend.md 制造分歧（更新 prd-recommend-overview 内容）
# 然后再创建新版本 v1.1，对同一个 chunk 做 modify

uv run ait version merge v1.1 --conflict-policy abort
```

输出：

```json
{"ok": true, "data": {"merged_chunks": [],
                       "conflicts": [{"chunk_id": "prd-recommend-overview",
                                       "reason": "hash_mismatch", ...}],
                       "status": "aborted"}}
```

可选策略：

- `--conflict-policy abort` — 默认，安全策略
- `--conflict-policy use-version` — 强制用版本覆盖基线
- `--conflict-policy use-baseline` — 放弃版本中的冲突块，合并其余部分

## 下一步

- 跑 `uv run pytest` 看完整测试套件（66 个用例）
- 把 `skill/ait/` 复制到 `~/.claude/skills/ait/` 启用 Claude Code Skill 形态
- 在 Claude Code 里直接输入 `/ait prd 新功能` 触发 Skill 工作流
- 阅读 [project-docs/docs/prd/chunk-system.md](../project-docs/docs/prd/chunk-system.md) 了解 Chunk 格式规范
