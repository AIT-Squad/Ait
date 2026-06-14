<!-- @id:global-schema -->
## 数据结构 Schema

<!-- @id:version-state -->
## version-state

```python
from dataclasses import dataclass, field
from enum import Enum

class VersionPhase(str, Enum):
    EMPTY = "empty"            # 空白起点
    PRD_LOCKED = "prd_locked"  # prd confirm 后
    IMPL_LOCKED = "impl_locked"# impl confirm 后
    CODING = "coding"          # task 执行中
    MERGED = "merged"          # version confirm 后

@dataclass
class VersionState:
    version: str
    phase: VersionPhase = VersionPhase.EMPTY
    title: str | None = None        # 来自 prd discuss 总结，写 state.md
    prd_locked: bool = False
    impl_locked: bool = False
```

<!-- @id:specgraph-store -->
## specgraph-store

```python
# 全局基线图：.meta/specgraph.yaml          （version 段 = baseline）
# 开发中版本图：.meta/specgraph-{version}.yaml （version 段 = vX.Y）

def specgraph_path(root: Path, version: str) -> Path:
    if version == "baseline":
        return root / ".meta" / "specgraph.yaml"
    return root / ".meta" / f"specgraph-{version}.yaml"
```

<!-- @id:schema-prd-sections -->
## schema-prd-sections

```python
@dataclass(frozen=True)
class PrdSections:
    overview: str        # 概述
    rules: list[str]     # 业务规则（拆 task 的依据）
    acceptance: list[str]# 验收标准（task 完成判定）
    boundary: str        # 边界与非目标
```

<!-- @id:global-index -->
## global-index

```yaml
# .meta/specgraph.yaml 片段（baseline）
specs:
  - uri: spec:global:baseline:global-tech-stack
    type: global
    chunk_id: global-tech-stack
    metadata:
      category: static          # static | dynamic
      path: docs/global/tech-stack.md
  - uri: spec:global:baseline:global-ddl-pet
    type: global
    chunk_id: global-ddl-pet
    metadata:
      category: dynamic
      path: docs/global/ddl.md
```

<!-- @id:extract-block -->
## extract-block

```python
@dataclass(frozen=True)
class ExtractBlock:
    source_impl_id: str   # @extract 所在的 impl chunk id
    target_type: str      # dynamic/ddl | dynamic/schema | dynamic/api
    target_chunk: str     # 提取后在动态 global 中的 chunk id
    content: str          # @extract 与 @extract-end 之间的原文（去注释行）
    line_start: int
    line_end: int
```

<!-- @id:task-yaml -->
## task-yaml

```yaml
# .meta/tasks/{version}/T-{源chunk}-NN.yaml
id: T-pet-archive-01          # 派生式：T-{源chunk}-NN
title: 实现宠物档案创建接口
source_chunk: prd-pet-archive # 血缘：源 PRD chunk
impl_refs:                    # 该读的 impl chunk
  - impl-pet-archive-ddl
  - impl-pet-archive-api
global_refs:                  # 该遵守的全局约束
  - global-tech-stack
depends_on: []                # 上游 task id（拓扑）
order_hint: 1                 # 同 chunk 内执行序
steps:                        # AI coding 步骤
  - 读 impl-pet-archive-ddl 建表
  - 按 impl-pet-archive-api 实现 POST /pets
  - 写单测覆盖必填校验
status: created               # created | executing | done | failed
code_refs: []                 # done 时回写：[{commit, paths, bound_at}]
```
