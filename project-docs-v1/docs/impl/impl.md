<!-- @id:impl-impl-stage-cli -->
## impl 阶段命令实现

实现 `impl create` / `impl confirm`，支持 1:N 派生与无 id 逐批交互。

### 命令

```python
@impl_group.command("create")
@click.argument("prd_chunk_id", required=False)  # 无 id → 逐批交互
@click.option("--content-file")
def impl_create(prd_chunk_id, content_file):
    if prd_chunk_id is None:
        # 逐批模式：遍历本版本所有 committed PRD chunk 中尚无 impl 的，依次设计
        return _interactive_impl_loop(root)
    # 单 chunk：校验 PRD 已 committed → 写 impl 到 versions/{v}/impl/ → 自动注入 @ref
    ...

@impl_group.command("confirm")
@click.argument("chunk_id", required=False)
def impl_confirm(chunk_id):
    # 1. pre-merge 校验：把版本 specgraph dry-run 合并进全局图，检测冲突
    issues = pre_merge_check(root, version)   # 见下「pre-merge 校验」
    if issues:
        return fail(f"impl 设计存在问题，无法 confirm: {issues}", code="PREMERGE_FAILED")
    # 2. 写工作区，置 impl_locked=True；无 id 则确认全部待确认 impl
    ...
```

### pre-merge 校验（impl confirm 的质量门）
confirm 时把本版本 specgraph 试合并进全局图，做 dry-run，检测两类问题，有问题拒绝 confirm：

```python
def pre_merge_check(root, version) -> list[str]:
    vgraph = load_specgraph(root, version)      # specgraph-{version}.yaml
    ggraph = load_specgraph(root, "baseline")   # 全局 specgraph.yaml
    merged = ggraph.dry_run_merge(vgraph)       # 不落盘
    issues = []
    # ① 依赖成环：合并后的图做拓扑排序，有环则失败
    if cycle := merged.detect_cycle():
        issues.append(f"依赖成环: {cycle}")
    # ② 版本内重复：同 @id 多定义 / 多个 impl 抢同一 @extract 目标
    issues += detect_intra_version_dup(version)
    return issues
```

- 严格串行单版本，故无需检测基线分叉冲突（不会发生）
- 跨版本同名 @extract 目标是合法演进（替换），不算冲突

### 1:N 派生
- 一个 PRD chunk 可被多次 `impl create` 调用，或单次提交含多个 `@id` 的文件
- 派生命名 `impl-{源chunk去前缀}-{名}`，由 impl-formats-naming 校验
- 每个 impl 自动注入 `@ref:{prd-file}#{prd-chunk} rel:implements`

### 逐批交互
- `_interactive_impl_loop`：查 specgraph（version 维度）找出"有 PRD committed 但无 impl 覆盖"的 chunk，逐个提示设计
- 覆盖判定：specgraph 中是否有 `rel:implements` 边指向该 PRD chunk（不再依赖 links-index）

### 锁定
- confirm 置 `impl_locked=True`，之后本版本 impl 不可改

<!-- @ref:prd/ait-redesign#prd-impl-stage rel:implements -->

<!-- @id:impl-impl-stage-extract -->
## @extract 提取标记解析器

解析 impl chunk 内的 `@extract` 注释块，识别可提取到动态 global 的片段。

### 标记格式

```
<!-- @extract:dynamic/{type}#{chunk} -->
...任意内容（代码块或纯文本）...
<!-- @extract-end -->
```

### 解析数据结构

<!-- @extract:dynamic/schema#extract-block -->
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
<!-- @extract-end -->

### 解析算法
1. 扫描 impl chunk 正文，配对 `@extract:` 与 `@extract-end`
2. 解析 target：`dynamic/{type}#{chunk}` → target_type + target_chunk
3. 抽取中间内容（保留代码块围栏，便于动态 global 直接渲染）
4. 未配对的 `@extract`（缺 end）→ 校验错误 `EXTRACT_UNCLOSED`

### 规则
- 一个 impl chunk 可含多个 @extract 块
- @extract 块嵌套不允许（与 @id 一致）
- 提取动作发生在 version confirm（见 impl-version-merge-extract），此处只负责解析

### 版本内重复检测（detect_intra_version_dup）
供 impl confirm 的 pre-merge 校验调用，检测同一开发中版本内的自相矛盾：

```python
def detect_intra_version_dup(version) -> list[str]:
    issues = []
    # 形态A：同 @id 在本版本多处定义
    ids = collect_chunk_ids(version)
    issues += [f"重复 @id: {i}" for i in find_duplicates(ids)]
    # 形态B：多个 impl 抢同一 @extract 目标（同 target_chunk）
    targets = [b.target_chunk for b in all_extract_blocks(version)]
    issues += [f"@extract 目标冲突: {t}" for t in find_duplicates(targets)]
    return issues
```

- 形态A：同 @id 重复 → `DUP_CHUNK_ID`
- 形态B：同版本内两个 impl 提取到同一 target_chunk → `EXTRACT_TARGET_CONFLICT`
- 注意：跨版本同 target_chunk 是合法演进（version confirm 时替换），不在此拦截

<!-- @ref:prd/ait-redesign#prd-impl-stage rel:implements -->
