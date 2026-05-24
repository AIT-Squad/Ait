# AIT 项目文档体系

本目录是 **AIT 工具自身的开发与管理依据**，按 AIT 工具设计的目录结构组织。

> 这是 dogfooding：AIT 工具用自己的方式管理自己的 PRD/impl 文档。所有后续设计变更先改这里的 PRD/impl，代码再跟进。

## 目录结构

> **AIT 工具自 v1.1 起强制将本目录视为唯一合法工作根**——目录名 `project-docs` 硬编、不可配置、不向上递归。在仓库根目录（本 README 的父目录）运行 `ait` 命令；在其他位置或 `project-docs/` 内部运行会被拒绝（`NOT_AT_PROJECT_ROOT` / `CWD_INSIDE_PROJECT_DOCS`）。

```
project-docs/
├── docs/                    # 基线文档（Source of Truth）
│   ├── prd/                 #   产品需求层
│   └── impl/                #   实现规范层
├── versions/                # 版本工作空间（增量变更入口）
├── templates/               # 文档模板（复用 project-demo/）
└── .meta/                   # 元数据
    ├── config.yaml          #   项目配置
    ├── blocks-index.yaml    #   全局 Block 索引（由 ait reindex / ait version merge 维护）
    ├── links-index.yaml     #   双向引用索引（同上）
    ├── versions/            #   版本元数据
    ├── changes/             #   变更记录
    ├── snapshots/           #   合并快照
    └── requirements/        #   需求草稿
```

## 文档层次

| 层 | 定位 |
|----|------|
| PRD | 描述 AIT 工具"做什么"和"为什么" |
| impl | 描述 AIT 工具"怎么做"（对应 Python 模块） |

当前 PRD: `overview` / `block-system` / `index-system`；impl: `block-parser` / `merge-engine` / `version-manager`。后续通过 `ait prd create` / `ait impl create` 增量补充。

## @id 命名规范

```
{type}-{domain}-{name}

type ∈ {prd, impl}
domain：所属子域，如 block / index / version / workflow / context / cmd / skill / validation
name：语义化短名，全小写，短横线连接
```

示例：

- `prd-block-format` — Block 标注格式（产品需求）
- `impl-block-parser-algorithm` — Block 解析算法（实现）

## 快速导航

- **想了解 AIT 系统是什么** → 读 [docs/prd/overview.md](docs/prd/overview.md)
- **想看 Block 怎么解析** → 读 [docs/prd/block-system.md](docs/prd/block-system.md) + [docs/impl/block-parser.md](docs/impl/block-parser.md)
- **想了解版本工作流** → 读 [docs/prd/index-system.md](docs/prd/index-system.md) + [docs/impl/version-manager.md](docs/impl/version-manager.md)

详细的全局 Block 列表见 [.meta/blocks-index.yaml](.meta/blocks-index.yaml)；引用关系见 [.meta/links-index.yaml](.meta/links-index.yaml)（两者由 `ait reindex` 维护）。
