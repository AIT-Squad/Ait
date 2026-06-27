<!-- @id:prd-specgraph-index -->

# 需求3：links-index.yaml 重构为 SpecGraph

## 需求来源

`todo.md` 需求3：

> prd 和 impl 之间的管理 links-index.yaml 格式修改为参考项目的方式，block 改为 chunk，使用参考项目中更加完善系统的 specgraph

## 背景

### 当前实现（v1.2）

当前项目使用 `.meta/links-index.yaml` 来管理 PRD chunk 与 impl chunk 之间的关联关系，格式简单：

```yaml
links:
  - prd_chunk: prd-xxx-overview
    impl_chunk: impl-xxx-overview
    relation: implements
```

**问题**：
1. 只有 `implements` 一种关系，无法表达 `depends_on` / `blocks` / `superseded_by` 等复杂关系
2. 没有 spec 来源的 URI 标准化（`spec:prd:<version>:<chunk-id>`）
3. 不支持跨版本 dependency graph 查询
4. 没有 weight / metadata 扩展能力

### 参考项目实现（version-design）

参考项目使用 **SpecGraph** 格式，核心概念：

| 概念 | 说明 |
|---|---|
| Spec URI | `spec:<type>:<version>:<chunk-id>`（标准化标识符） |
| Edge | `src` → `dst`，带 `rel` 类型 + `weight` + `metadata` |
| Graph | 有向图，支持拓扑排序、依赖分析、影响面分析 |
| Store | `.meta/specgraph.yaml`（替代 `links-index.yaml`） |

**参考项目 SpecGraph 格式示例**（预期格式，需从参考项目确认）：

```yaml
version: 1
specs:
  - uri: spec:prd:v1.2:prd-skills-overview
    title: 概述与目标
    type: prd
    version: v1.2
    chunk_id: prd-skills-overview
  - uri: spec:impl:v1.2:impl-skills-overview
    title: 概述与目标（实现）
    type: impl
    version: v1.2
    chunk_id: impl-skills-overview
edges:
  - src: spec:impl:v1.2:impl-skills-overview
    dst: spec:prd:v1.2:prd-skills-overview
    rel: implements
    weight: 1.0
    metadata:
      committed_at: '2026-05-25T05:45:35Z'
  - src: spec:prd:v1.3:prd-release-v13-overview
    dst: spec:prd:v1.2:prd-skills-overview
    rel: superseded_by
    weight: 1.0
    metadata: {}
```

## 设计方案

### Step 1：定义 SpecGraph 数据模型

**新增文件**：`ait/specgraph.py`

```python
# ait/specgraph.py

from dataclasses import dataclass, field
from typing import Optional, Dict, List
import yaml

@dataclass
class Spec:
    uri: str           # spec:<type>:<version>:<chunk-id>
    title: str
    type: str          # prd | impl
    version: str       # v1.2, v1.3, ...
    chunk_id: str
    metadata: Dict = field(default_factory=dict)

@dataclass
class Edge:
    src: str           # Spec.uri
    dst: str           # Spec.uri
    rel: str          # implements | depends_on | blocks | superseded_by | related
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)

@dataclass
class SpecGraph:
    version: int = 1
    specs: List[Spec] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)

    def add_spec(self, spec: Spec):
        if not any(s.uri == spec.uri for s in self.specs):
            self.specs.append(spec)

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def get_impl_for_prd(self, prd_uri: str) -> Optional[Spec]:
        """查找实现指定 PRD spec 的 impl spec"""
        for e in self.edges:
            if e.dst == prd_uri and e.rel == "implements":
                return self.get_spec_by_uri(e.src)
        return None

    def get_prd_for_impl(self, impl_uri: str) -> Optional[Spec]:
        """查找 impl spec 实现的 PRD spec"""
        for e in self.edges:
            if e.src == impl_uri and e.rel == "implements":
                return self.get_spec_by_uri(e.dst)
        return None

    def get_dependencies(self, uri: str) -> List[Spec]:
        """获取指定 spec 的依赖（depends_on 关系）"""
        result = []
        for e in self.edges:
            if e.src == uri and e.rel == "depends_on":
                spec = self.get_spec_by_uri(e.dst)
                if spec:
                    result.append(spec)
        return result

    def topological_sort(self) -> List[Spec]:
        """拓扑排序（用于确定实现顺序）"""
        # Kahn's algorithm
        ...

    def to_dict(self) -> dict:
        ...

    @classmethod
    def from_dict(cls, d: dict) -> "SpecGraph":
        ...

    def save(self, path: str):
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True)

    @classmethod
    def load(cls, path: str) -> "SpecGraph":
        with open(path) as f:
            d = yaml.safe_load(f)
        return cls.from_dict(d)

    # --- 辅助 ---
    def get_spec_by_uri(self, uri: str) -> Optional[Spec]:
        for s in self.specs:
            if s.uri == uri:
                return s
        return None
```

### Step 2：在 `bin/ait` 中新增 SpecGraph 子命令

**新增 CLI**：

| 命令 | 用途 |
|---|---|
| `bin/ait specgraph add-edge <src> <dst> --rel implements` | 手动添加 edge |
| `bin/ait specgraph query <uri> --deps` | 查询依赖 |
| `bin/ait specgraph query <uri> --implements` | 查询实现关系 |
| `bin/ait specgraph export --format dot` | 导出 Graphviz DOT（可视化） |
| `bin/ait specgraph sync` | 从现有 `links-index.yaml` 迁移数据 |

### Step 3：在 `bin/ait prd commit` 和 `bin/ait impl commit` 时自动维护 SpecGraph

**自动化规则**：

1. **PRD commit** 时：自动在 SpecGraph 中注册 `spec:prd:<version>:<chunk-id>`
2. **Impl create** 时：若 YAML frontmatter 含 `@ref ... rel:implements`，自动添加 `implements` edge
3. **Impl commit** 时：验证对应的 PRD chunk 已 committed（通过 SpecGraph 查询）

### Step 4：迁移现有 `links-index.yaml`

**迁移脚本**（由 `bin/ait specgraph sync` 执行）：

```python
def migrate_links_index():
    """从 .meta/links-index.yaml 迁移到 .meta/specgraph.yaml"""
    old = load_yaml(".meta/links-index.yaml")
    graph = SpecGraph()

    for link in old.get("links", []):
        prd_uri = f"spec:prd:v1.2:{link['prd_chunk']}"
        impl_uri = f"spec:impl:v1.2:{link['impl_chunk']}"

        # 注册 specs
        graph.add_spec(Spec(
            uri=prd_uri,
            title=link['prd_chunk'],
            type="prd",
            version="v1.2",
            chunk_id=link['prd_chunk']
        ))
        graph.add_spec(Spec(
            uri=impl_uri,
            title=link['impl_chunk'],
            type="impl",
            version="v1.2",
            chunk_id=link['impl_chunk']
        ))

        # 注册 edge
        graph.add_edge(Edge(
            src=impl_uri,
            dst=prd_uri,
            rel=link.get("relation", "implements")
        ))

    graph.save(".meta/specgraph.yaml")
```

## 与 v1.2 的关系

- v1.2 的 `links-index.yaml` **继续保留**（向后兼容），但新增操作同时写入 `specgraph.yaml`
- `bin/ait specgraph sync` 提供一次性迁移
- v1.4+ 可以考虑完全废弃 `links-index.yaml`

## 验收标准

1. `ait/specgraph.py` 存在，`SpecGraph` / `Spec` / `Edge` 可导入
2. `bin/ait specgraph --help` 显示 5 个子命令
3. `bin/ait specgraph sync` 能成功从 `.meta/links-index.yaml` 迁移数据到 `.meta/specgraph.yaml`
4. `bin/ait prd commit` 后，`.meta/specgraph.yaml` 中自动注册对应 `spec:prd:` 条目
5. `bin/ait impl create` 时，若内容含 `@ref ... rel:implements`，自动添加 edge
6. `bin/ait specgraph query spec:prd:v1.2:prd-skills-overview --implements` 返回正确的 impl spec URI
7. `bin/ait specgraph export --format dot` 输出合法的 Graphviz DOT 格式

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| 在 AI 对话中自动渲染依赖图（Mermaid） | v1.4+，需要 AI 端支持 |
| 跨版本 dependency conflict 检测 | v1.4+ |
| SpecGraph 的 Web UI 可视化 | 不在 CLI 工具范围内 |
