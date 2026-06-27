<!-- @id:impl-formats-parser -->
## 格式解析扩展（四段 PRD + chunk 解析）

扩展现有 chunk 解析器，支持 PRD 四段固定结构识别与 @extract 块。

### PRD 四段识别

PRD chunk 内的固定四段（`### 概述` / `### 业务规则` / `### 验收标准` / `### 边界与非目标`）作为子结构解析，供 task 拆分时定位"业务规则"和"验收标准"。

<!-- @extract:dynamic/schema#prd-sections -->
```python
@dataclass(frozen=True)
class PrdSections:
    overview: str        # 概述
    rules: list[str]     # 业务规则（拆 task 的依据）
    acceptance: list[str]# 验收标准（task 完成判定）
    boundary: str        # 边界与非目标
```
<!-- @extract-end -->

### 解析规则
- 四段以 `### ` 三级标题为锚，缺段时对应字段为空 + 校验警告（非阻断）
- 不破坏现有 chunk 边界规则（chunk 仍由 `@id` 界定，四段是 chunk 内部子结构）
- @extract 块解析复用 impl-impl-stage-extract 的逻辑

### 兼容
- 现有非四段格式的 PRD chunk 仍可解析（四段为推荐结构，解析器容错）

<!-- @ref:prd/ait-redesign#prd-formats rel:implements -->

<!-- @id:impl-formats-naming -->
## 派生式命名校验

校验 impl / task 的派生式命名规则，保证血缘可反推。

### 规则

```python
def validate_derived_name(chunk_id: str, source_chunk: str) -> bool:
    # impl: impl-{源chunk去prd前缀}-{名}
    # task: T-{源chunk去prd前缀}-NN
    stem = source_chunk.removeprefix("prd-")
    if chunk_id.startswith("impl-"):
        return chunk_id.startswith(f"impl-{stem}")
    if chunk_id.startswith("T-"):
        return re.match(rf"^T-{stem}-\d{{2}}$", chunk_id) is not None
    return False
```

### 校验点
- `impl create`：校验生成的 impl id 以 `impl-{源stem}` 开头
- `task create`：校验 task id 匹配 `T-{源stem}-NN`
- 违反 → 校验错误 `NAMING_VIOLATION`（阻断）

### 价值
- 名字自带血缘，AI 在 execute 时看 task id 即知源 chunk 与该读的 impl，减少查索引开销（呼应 token 聚焦）
- chunk id 仍遵守全局唯一 + 小写短横线规则

<!-- @ref:prd/ait-redesign#prd-formats rel:implements -->
