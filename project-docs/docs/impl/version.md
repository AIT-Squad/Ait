<!-- @id:impl-version-merge-engine -->
## 版本合并引擎（两阶段 + 失败回退）

实现 `version confirm`：守卫 → merge → git commit，保证原子性。

### 流程

```python
def version_confirm(root: Path, version: str) -> dict:
    # ── 阶段1：预检守卫 ──
    state = load_version_state(root, version)
    tasks = load_tasks(root, version)
    if any(t.status != "done" for t in tasks):
        return fail("存在未完成 task，无法 confirm", code="TASK_NOT_DONE")
    if not git_clean(root):
        return fail("git 工作区不干净", code="GIT_DIRTY")

    # ── 阶段2：merge（写 docs/，可回退）──
    backup = snapshot_docs(root)            # 内存/临时备份 docs/
    try:
        merge_chunks_to_baseline(root, version)        # 同名 chunk 替换
        extract_dynamic_global(root, version)          # impl @extract → 动态 global
        merge_specgraph_to_baseline(root, version)     # 版本图节点/边并入全局 specgraph.yaml
        # ── 阶段3：git commit ──
        git_add_commit(root, message=state.title)
    except Exception as e:
        restore_docs(root, backup)          # 回退：恢复 docs/ 到 merge 前
        return fail(f"merge/commit 失败已回退: {e}", code="MERGE_ROLLBACK")

    state.phase = "merged"; save(state)
    return {"ok": True, "version": version, "commit_msg": state.title}
```

### 合并规则（按 chunk 维度）
- 同名 chunk：用本版本内容替换基线对应 chunk（不覆盖无关全局信息）
- 新增 chunk：追加到基线
- 其他 chunk：保持不动

### specgraph 合并（merge_specgraph_to_baseline）
- 将 `specgraph-{version}.yaml` 的节点与边并入全局 `specgraph.yaml`（baseline）
- 节点 URI 的 version 段由 `{version}` 改写为 `baseline`
- 同名 chunk 的节点/边按替换处理（与 chunk 合并一致）
- 合并成功后，`specgraph-{version}.yaml` 可随版本归档（merged 版本工作区保留供追溯）

### 原子性
- commit 失败 → 回退 docs/ 到 merge 前，要么全成要么全不动
- 守卫不通过 → 不动任何文件
- pre-merge 校验已在 impl confirm 阶段完成（环/版本内重复），此处不再重复

<!-- @ref:prd/ait-redesign#prd-version-merge rel:implements -->

<!-- @id:impl-version-merge-extract -->
## impl → 动态 global 提取

version confirm 时，从本版本 impl 的 @extract 块提取片段，按 chunk 合并进动态 global。

### 算法

```python
def extract_dynamic_global(root: Path, version: str) -> list[str]:
    written = []
    for impl_chunk in version_impl_chunks(root, version):
        for blk in parse_extract_blocks(impl_chunk):    # 见 impl-impl-stage-extract
            # blk.target_type = dynamic/ddl|schema|api, blk.target_chunk = 目标 chunk id
            target_file = root / "docs" / "global" / f"{blk.target_type.split('/')[1]}.md"
            upsert_chunk(target_file, blk.target_chunk, blk.content, category="dynamic")
            written.append(blk.target_chunk)
    return written
```

### 规则
- 提取目标按 @extract 的 `dynamic/{type}` 路由到 `docs/global/{type}.md`
- 写入方式：同名 chunk 替换（与 merge 一致）
- 动态 global chunk 标 `category: dynamic`，不接受人工直接编辑
- 提取是 merge 阶段的一部分，纳入两阶段回退保护

### 不变量
- 动态 global 内容 100% 来自 impl 的 @extract，无其他来源（防漂移）

<!-- @ref:prd/ait-redesign#prd-version-merge rel:implements -->
