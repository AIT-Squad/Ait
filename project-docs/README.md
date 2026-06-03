# AIT 项目文档体系

本目录是 **AIT 工具自身的开发与管理依据**，按 AIT 工具设计的目录结构组织。

> 这是 dogfooding：AIT 工具用自己的方式管理自己的 PRD/impl 文档。所有后续设计变更先改这里的 PRD/impl，代码再跟进。

## 目录结构

> **AIT 工具自 v1.1 起强制将本目录视为唯一合法工作根**——目录名 `project-docs` 硬编、不可配置、不向上递归。在仓库根目录（本 README 的父目录）运行 `ait` 命令；在其他位置或 `project-docs/` 内部运行会被拒绝（`NOT_AT_PROJECT_ROOT` / `CWD_INSIDE_PROJECT_DOCS`）。

```
project-docs/
├── docs/                          # 基线文档（Source of Truth）
│   ├── prd/                       #   产品需求层
│   ├── impl/                      #   实现规范层
│   └── global/                    #   全局信息层（overview/tech-stack 静态 + ddl/schema/api 动态）
├── versions/                       # 版本工作空间（增量变更入口）
│   └── {vX.Y}/
│       ├── prd/
│       ├── impl/
│       ├── tasks/T-*.yaml         #   v1.5+ task YAML 与版本同位
│       └── state.md
├── templates/                      # 文档模板（复用 project-demo/）
└── .meta/                         # 元数据
    ├── config.yaml                 #   项目配置（initialized / skill_path）
    ├── chunks-index.yaml           #   基线块台账（状态视角，替代旧 blocks-index）
    ├── chunks-index-{vX.Y}.yaml   #   版本块台账
    ├── specgraph.yaml              #   基线关系图（关系视角，替代旧 links-index）
    ├── specgraph-{vX.Y}.yaml      #   每版本关系图（分文件）
    ├── versions/                   #   版本元数据（phase/锁定/title/tasks_summary）
    ├── changes/                    #   变更记录
    ├── snapshots/                  #   合并快照
    └── requirements/               #   需求草稿
```

> **变更说明（v1.5）**：
> - `blocks-index.yaml` 已重命名为 `chunks-index.yaml`（块台账）
> - `links-index.yaml` 已废弃，关系查询统一由 `specgraph.yaml` 管理
> - task YAML 从 `.meta/tasks/` 迁移到 `versions/{vX.Y}/tasks/`（与版本同位）

## 文档层次

| 层 | 定位 |
|----|------|
| PRD | 描述 AIT 工具"做什么"和"为什么" |
| impl | 描述 AIT 工具"怎么做"（对应 Python 模块） |

当前 PRD: `overview` / `chunk-system` / `index-system` / `global`；impl: `chunk-parser` / `merge-engine` / `version-manager` / `task` / `specgraph`。后续通过 `ait prd create` / `ait impl create` 增量补充。

## @id 命名规范

```
{type}-{domain}-{name}

type ∈ {prd, impl}
domain：所属子域，如 chunk / index / version / workflow / context / cmd / skill / validation
name：语义化短名，全小写，短横线连接
```

示例：

- `prd-chunk-format` — Chunk 标注格式（产品需求）
- `impl-chunk-parser-algorithm` — Chunk 解析算法（实现）

## 快速导航

- **想了解 AIT 系统是什么** → 读 [docs/prd/global.md](docs/prd/global.md)（概述 + 完整 PRD）
- **想看 Chunk 怎么解析** → 读 [docs/prd/global.md](docs/prd/global.md) + [docs/impl/chunk-parser.md](docs/impl/chunk-parser.md)
- **想了解版本工作流** → 读 [docs/impl/version-manager.md](docs/impl/version-manager.md) + [docs/impl/workflow.md](docs/impl/workflow.md)
- **想了解 task 流水线** → 读 [docs/impl/task.md](docs/impl/task.md) + [docs/impl/workflow.md](docs/impl/workflow.md)

详细的全局 Chunk 列表见 [.meta/chunks-index.yaml](.meta/chunks-index.yaml)；关系图见 [.meta/specgraph.yaml](.meta/specgraph.yaml)（两者由 `ait reindex` 维护）。

## 常用命令

```bash
# 初始化项目（首次）
ait init

# 重建索引
ait reindex

# 查看版本状态
ait state --version vX.Y

# 全文搜索
ait search "关键词"
```
