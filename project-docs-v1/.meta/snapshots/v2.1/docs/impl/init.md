<!-- @id:impl-init-flow -->
## 初始化流程与 docs/ 骨架生成

实现 `/ait init`：通过讨论生成项目全局基线（全局 prd 概览、impl 概览、global 静态/动态骨架），写入 `docs/`，不占版本号。

### 命令入口

```python
@main.command("init")
def init_cmd() -> None:
    # 前置守卫：仅当项目尚无任何版本时才能 init（已被 ait 纳管则拒绝）
    if has_any_version(root):
        return fail("项目已被 ait 纳管（已存在版本），不可重新 init", code="ALREADY_MANAGED")
    result = run_init(root)
    ok(result)
```

### 流程

1. **讨论收集**（由 skill 层驱动对话）：技术栈、项目 overview、核心领域划分
2. **生成 docs/ 骨架**：
   - `docs/global/overview.md`（`global-overview`，static）
   - `docs/global/tech-stack.md`（`global-tech-stack`，static）
   - `docs/global/ddl.md` / `schema.md` / `api.md`（dynamic 空骨架，待 version confirm 提取填充）
   - `docs/prd/README.md` + `docs/impl/README.md`（说明文件，不入索引）
3. **建立基线索引**：`reindex` 重建 chunks-index + 全局 specgraph.yaml（baseline），global chunk 标 `category`
4. **标记已初始化**：`.meta/config.yaml` 写 `initialized: true`

### 判定
- `has_any_version()`：检查 `versions/` 下是否存在任何版本目录，或 `.meta/versions/` 是否有版本定义
- init 不创建 `versions/` 下任何目录，首个功能版本由后续 `prd create` 触发（从 v1.0 起）

### 不变量
- init 产出全部落 `docs/` 基线，不进版本工作区
- 动态 global 此阶段仅建空骨架（category: dynamic，内容空）

<!-- @ref:prd/ait-redesign#prd-init rel:implements -->
