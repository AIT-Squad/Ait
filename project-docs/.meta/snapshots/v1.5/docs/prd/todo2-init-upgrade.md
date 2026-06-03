<!-- @id:prd-init-upgrade -->

# 需求2：init 流程智能识别旧项目

## 需求来源

`todo.md` 需求2：

> 读取参考项目下的 ait init 实现方式，期望本项目中可以在 init 过程中，可以判断当前是新项目还是旧的项目，旧项目的话，判断是否有 project-docs 管理，如果有则跳过。如果没有，则引导客户把项目版本管理放到该
> 约束要求：按照当前项目的规范来重新组织 skills；按照当前项目 init 的方式不改动

## 背景

当前项目 `ait` 的 `bin/ait init` 功能（对应 `root.py` 中的 init 逻辑）是一个**固定流程**，不区分"新项目"和"已有 project-docs 的旧项目"。

参考项目 `version-design` 的 `ait init` 实现方式中，可能包含：
- 项目类型判断逻辑（新 / 旧）
- 已有 `project-docs/` 的检测
- 引导用户接入版本管理的交互流程

## 重要约束

> **按照当前项目 init 的方式不改动**

这意味着：**不修改 `bin/ait` 的 init 子命令入口，不修改 `root.py` 的 init 函数签名**。

本需求的实现方式是：**在现有 init 流程中调用一个新子 skill（`ait-init-check`），由子 skill 完成智能判断和引导，主流程不变**。

## 设计方案

### 架构：主流程 + 子 skill 增强

```
用户执行: bin/ait init
        │
        ▼
现有 init 流程（root.py）
        │
        ├── 原有逻辑：检查 project-docs/ 是否存在
        │
        └── 【新增】调用 ait-init-check 子 skill
                    │
                    ├── 判断项目类型（新 / 旧）
                    ├── 旧项目：检查是否有 project-docs 管理
                    │   └── 有 → 跳过，输出提示信息
                    └── 旧项目：无 project-docs
                        └── 引导用户：是否接入版本管理？→ 调用 bin/ait version create
```

### 子 Skill：`ait-init-check`

**文件位置**：`skill/ait/sub-skills/ait-init-check/SKILL.md`（新增，不在 v1.2 原规划中）

**触发语**：
```
INVOKE THIS SKILL when the user runs `bin/ait init` and the system needs to determine whether this is a new project or an existing project that already has project-docs management.
```

**职责**：
1. 判断项目类型：新项目（无 git 历史 / 空目录）/ 旧项目（有 git 历史 / 已有代码）
2. 旧项目：检查当前目录或父目录是否存在 `project-docs/`
3. 已有 `project-docs/` → 输出提示："项目已有版本管理，跳过 init"
4. 无 `project-docs/` → 引导用户选择：
   - 选项 A：接入版本管理（`bin/ait version create v0.1`）
   - 选项 B：跳过，保持当前状态

**CLI 依赖**（必须通过 `bin/ait` 调用，不直接写文件）：

| CLI 命令 | 用途 | 副作用 |
|---|---|---|
| `bin/ait version list` | 检查是否已有版本 | 无 |
| `bin/ait version create <vX.Y>` | 引导用户创建第一个版本 | 创建 `versions/<vX.Y>/` + `.meta/versions/<vX.Y>.yaml` |
| `ls project-docs/` | 检查 project-docs 是否存在 | 无 |

**Artifacts**：

| 操作 | 路径 | 方式 |
|---|---|---|
| 读 | `project-docs/`（存在性检查） | shell `ls` |
| 读 | `.meta/versions/*.yaml` | `bin/ait version list` |
| 写 | **无直接写入** | 所有写入通过 `bin/ait version create` |

### 对现有 init 流程的改动（最小侵入）

**改动范围**：仅 `root.py` 的 `init` 函数，**不改动 CLI 入口和参数解析**。

**改动内容**：

```python
# root.py - init() 函数内，在现有逻辑之后追加：

def init():
    """初始化项目版本管理（增强版：智能识别新/旧项目）"""
    # === 原有逻辑（不变）===
    if os.path.exists("project-docs/"):
        print("project-docs/ already exists. Use /ait to manage versions.")
        return

    # === 新增：调用 ait-init-check 子 skill（由 AI 驱动）===
    # AI 在读到这段逻辑时，会 INVOKE ait-init-check skill
    # 以下是给 AI 的提示（以注释形式存在于代码中，AI 可见）
    # AI_HINT: project is new or old? check git log / existing files.
    # AI_HINT: if old project without project-docs, guide user to `bin/ait version create`.
    #
    # 实际行为：AI 读到 init 被调用 → 触发 ait-init-check skill → skill 完成判断和引导

    # === 原有逻辑继续（不变）===
    os.makedirs("project-docs/versions/", exist_ok=True)
    # ...
```

**关键**：`root.py` 代码中的注释 `AI_HINT` 是给 AI 的触发信号，不是运行时逻辑。AI 在执行 `/ait init` 时读到这些注释，自动 INVOKE `ait-init-check` skill。

## 与 v1.2 PRD 的关系

v1.2 `prd-skills-non-goals` 明确写道：

> 不修改 init 流程（`skill/ait/bin/ait` 与 `root.py` 不动）

本需求 **不违反该 non-goal**，因为：
1. `bin/ait` CLI 入口和参数解析不动
2. `root.py` 的 `init()` 函数签名不动
3. 实际增强逻辑由子 skill（AI 驱动）完成，`root.py` 只是增加了 AI 可读的注释提示

## 验收标准

1. **新项目**（空目录 / 无 git）：`bin/ait init` → 正常创建 `project-docs/`（行为不变）
2. **旧项目 + 已有 `project-docs/`**：`bin/ait init` → 输出提示，跳过创建
3. **旧项目 + 无 `project-docs/`**：`bin/ait init` → AI INVOKE `ait-init-check` → 引导用户选择是否接入
4. `skill/ait/sub-skills/ait-init-check/SKILL.md` 存在，且 frontmatter description 以 `INVOKE THIS SKILL when` 起头
5. `grep -r "直接写\|echo >" skill/ait/sub-skills/ait-init-check/` 命中数为 0（无直接文件写入）
6. `bin/ait init --help` 输出不变（CLI 接口不变）

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| 自动检测参考项目 `version-design` 的 init 实现并迁移代码 | 本需求仅定义行为，不迁移参考项目代码 |
| 交互式 CLI 对话（如 `read -p "是否接入？[y/n]"`） | 由 AI 对话完成引导，不引入 CLI 交互 |
| 修改 `pyproject.toml` 或 `setup.py` | 无必要 |
