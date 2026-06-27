<!-- @id:impl-core-model-state -->
## 核心模型：版本与锁定状态机数据结构

实现 prd → impl → task 三态及版本原子性的底层数据结构。版本是原子单元，内部各 chunk 有锁定状态，confirm 单向推进。

### 数据结构

版本元数据扩展 `phase` 字段表达单向推进的阶段，锁定通过 chunk 的 `locked` 标志实现。

<!-- @extract:dynamic/schema#version-state -->
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
<!-- @extract-end -->

### 锁定校验

任何写操作前检查锁：PRD 写操作要求 `prd_locked == False`，impl 写操作要求 `impl_locked == False`。锁定后写操作直接拒绝（错误码 `LOCKED`），提示只能 `version reset`。

```python
def assert_prd_writable(state: VersionState) -> None:
    if state.prd_locked:
        raise AitError("PRD locked in this version; use `ait version reset` to restart", code="LOCKED")
```

### 不变量
- phase 单向推进，无逆转换（除 reset 直接归零）
- prd_locked / impl_locked 一旦 True，本版本内不可变 False

<!-- @ref:prd/ait-redesign#prd-core-model rel:implements -->

<!-- @id:impl-core-model-reset -->
## 核心模型：version reset 清空逻辑

实现唯一的逃生口 `/ait version reset`：物理删除版本工作区，回到空白起点。

### 算法

```python
def version_reset(root: Path, version: str, *, confirmed: bool) -> dict:
    # 1. 二次确认守卫
    if not confirmed:
        return {"ok": False, "code": "NEED_CONFIRM",
                "warning": f"将物理删除版本 {version} 的所有工作区内容，不可恢复"}
    # 2. 物理删除版本工作区
    shutil.rmtree(root / "versions" / version, ignore_errors=True)
    # 3. 删除版本索引与定义（含版本 specgraph 分文件，直接删除即彻底清理）
    (root / ".meta" / f"chunks-index-{version}.yaml").unlink(missing_ok=True)
    (root / ".meta" / f"specgraph-{version}.yaml").unlink(missing_ok=True)
    (root / ".meta" / "versions" / f"{version}.yaml").unlink(missing_ok=True)
    # 4. 清理该版本产生的 requirement 草稿与 changes（按 version 字段筛）
    _purge_version_artifacts(root, version)
    # 5. 重建索引基线（剔除已删 chunk）
    rebuild_indexes(root)
    return {"ok": True, "version": version, "reset": True}
```

### 规则
- 必须显式二次确认（`--confirm` 或交互应答），否则只返回告警不执行
- 物理删除，不保留快照（符合"反悔即重置"原则）
- 已 merged 的历史版本不可 reset（只能 reset 当前开发中版本）
- reset 后该版本号可被重新 `prd create` 复用

### 不变量
- reset 不影响 docs/ 基线与其他版本
- reset 是幂等的：对不存在的版本 reset 返回成功（无副作用）
- 版本 specgraph 分文件存储，reset 即 `rm specgraph-{version}.yaml`，无残留（区别于单文件需精确摘除）

<!-- @ref:prd/ait-redesign#prd-core-model rel:implements -->

<!-- @id:impl-core-specgraph-store -->
## SpecGraph 分文件存储与环检测

实现 specgraph 的全局+版本分文件存储，并提供 pre-merge 校验所需的环检测。彻底替代 links-index。

### 分文件布局

<!-- @extract:dynamic/schema#specgraph-store -->
```python
# 全局基线图：.meta/specgraph.yaml          （version 段 = baseline）
# 开发中版本图：.meta/specgraph-{version}.yaml （version 段 = vX.Y）

def specgraph_path(root: Path, version: str) -> Path:
    if version == "baseline":
        return root / ".meta" / "specgraph.yaml"
    return root / ".meta" / f"specgraph-{version}.yaml"
```
<!-- @extract-end -->

### 写入时机
- `prd confirm` / `impl create` / `impl confirm`：写当前版本图 `specgraph-{version}.yaml`
- `version confirm`：版本图并入全局图（见 impl-version-merge-engine）
- `version reset`：直接删除 `specgraph-{version}.yaml`
- `reindex`：重建全局图 `specgraph.yaml`（扫 docs/）

### 环检测（detect_cycle）

```python
def detect_cycle(graph) -> list[str] | None:
    # 对 depends-on 边做 DFS / Kahn 拓扑排序
    # 若存在无法排序的节点 → 返回环路径，否则 None
    indeg = compute_indegree(graph, rel="depends-on")
    queue = [n for n in graph.nodes if indeg[n] == 0]
    visited = 0
    while queue:
        n = queue.pop()
        visited += 1
        for m in graph.successors(n, rel="depends-on"):
            indeg[m] -= 1
            if indeg[m] == 0: queue.append(m)
    if visited < len(graph.nodes):
        return extract_cycle(graph)   # 剩余节点构成环
    return None
```

### 查询接口（替代 links-index 的全部职责）
- `implements_of(prd_chunk, version)`：查指向该 PRD 的 impl（task 拆分用）
- `deps_of(chunk)` / `impact_of(chunk)`：依赖与影响面分析
- `dry_run_merge(version_graph)`：pre-merge 校验用，不落盘

### 不变量
- links-index 彻底废弃，不再生成或读取
- 所有关联查询唯一数据源 = specgraph

<!-- @ref:prd/ait-redesign#prd-core-model rel:implements -->
