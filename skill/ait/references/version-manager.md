# Version Manager 实现

<!-- @id:impl-version-manager-overview -->
## 概述

`src/ait/version_manager.py` 实现版本生命周期、三阶段提交、和合并入口。

<!-- @ref:prd/index-system#prd-index-version rel:implements -->
<!-- @ref:prd/overview#prd-overview-scope rel:implements -->

依赖：`index_manager` / `chunk_parser` / `hash_utils` / `validator` / `merge_engine`。

<!-- @id:impl-version-manager-state-model -->
## 三阶段状态模型

```
working ──stage──► staged ──commit──► committed ──merge──► (baseline)
   │                  │                    │
   └─unstage──────────┘                    │
                                           │
   ┌─re-edit──────────────────────────────┘
   ▼
working (amends c{N})
```

| 状态 | 可见性 | 可编辑 | 入 merge | 索引字段 |
|------|--------|--------|---------|---------|
| working | `--all` | 是 | 否 | state=working, commit_id=null |
| staged | `--staged` / `--all` | 是（退回 working） | 否 | state=staged, commit_id=null |
| committed | 默认 | 否（重编辑产生新 working+amends） | 是 | state=committed, commit_id=cN |

<!-- @id:impl-version-manager-api -->
## 公开 API

```python
class VersionManager:
    def __init__(self, project_root: Path): ...

    # ── 版本生命周期 ──
    def create(self, version: str, based_on: str | None = None) -> VersionMeta: ...
    def list_versions(self) -> list[VersionMeta]: ...
    def current(self) -> str | None:
        """返回未合并的最新版本，无则 None。新需求默认进此版本。"""

    # ── 三阶段 ──
    def stage(self, version: str, chunk_ids: list[str] | None = None) -> StageResult:
        """chunk_ids=None 表示 --all；只处理 state=working 的记录。"""
    def unstage(self, version: str, chunk_ids: list[str]) -> UnstageResult: ...
    def commit(self, version: str, message: str, req_id: str | None = None) -> CommitResult:
        """提交所有 staged 块。空 commit → 抛 E1。生成 chg-{id}.yaml。"""
    def status(self, version: str) -> StatusReport: ...

    # ── 合并 ──
    def merge(self, version: str, *, conflict_policy: str = "abort") -> MergeResult:
        """conflict_policy: abort / use-version / use-baseline / interactive(CLI 才用)"""
```

<!-- @id:impl-version-manager-stage-commit -->
## stage / commit 流程

```
stage(v, ids):
  1. 加载版本索引 chunks-index-{v}.yaml
  2. 若 ids=None：选所有 state=working 的记录
     否则：按 ids 过滤；不存在的 id 报 E1
  3. 对每条记录：
     a. validator.validate_block_content（文件中能找到 @id、内容非空）
     b. 计算当前内容 hash
     c. 若 action=modify：base_hash 已在记录中，验证 hash 与基线对应块的 hash
        若 hash 改变 → 警告但允许 stage（merge 时再判定冲突）
     d. state: working → staged
  4. 原子写回版本索引

commit(v, msg, req_id):
  1. 加载版本索引
  2. 选所有 state=staged 的记录
  3. 若为空 → E1 阻断："无暂存变更"
  4. 生成 commit_id = c{N}（N = 现有 commits 数 + 1）
  5. 对每条 staged 记录：
     - state: staged → committed
     - commit_id 设为 c{N}
  6. 生成 chg-{auto}.yaml（按 templates/change-record-template.yaml）
     - 对 modify：base_content 从基线提取，new_content 从版本文件提取
     - 对 add：base_*=null，new_content 从版本文件提取
     - 对 delete：new_content=null
  7. 更新版本元数据 .meta/versions/{v}.yaml 的 commits 列表
  8. 全部原子写入（任何一步失败回滚）
```

<!-- @id:impl-version-manager-merge -->
## merge 流程

<!-- @ref:prd/index-system#prd-index-baseline rel:implements -->

```
merge(v, conflict_policy):
  1. 加载版本索引 + 基线索引
  2. 校验：版本中所有块必须 state=committed
     若有 working/staged → E2 警告："只合并 committed 部分？" 阻断式询问（CLI 层处理）
  3. 冲突检测：
     对每条 action=modify/delete 记录：
       baseline_hash_now = hash(基线中 overrides 指向的块)
       if baseline_hash_now != record.base_hash:
         按 conflict_policy 处理：
           abort         → 终止整个 merge
           use-version   → 强制覆盖（记录到 merge log）
           use-baseline  → 跳过此块
           interactive   → CLI 层弹询问
  4. 调用 merge_engine.merge_file(file, baseline_blocks, version_blocks, version_index)
     对每个受影响文件：
       - 解析基线文件 → 块列表
       - 应用版本索引中的 add/modify/delete
       - 原子写回 docs/{file}.md
  5. 重建基线索引：index_manager.rebuild_baseline()
  6. 生成快照 .meta/snapshots/{v}/ （复制合并后的 docs/）
  7. 版本元数据状态 → merged，记录 merged_at
  8. 返回 MergeResult（成功合并块数、冲突块数、跳过块数）
```

<!-- @id:impl-version-manager-amends -->
## 修订已 committed 块

<!-- @ref:prd/chunk-system#prd-chunk-id-naming rel:implements -->

```
当用户对已 committed 的块再次修改时：
  1. version_manager 不直接修改原 committed 记录
  2. 在版本索引中新增一条记录：
       id 相同
       action=modify
       state=working
       amends=c{N}/{chunk_id}  指向被修订的 commit
       base_hash=hash(已 committed 版本的内容)
  3. 版本文件中替换该块内容（保留 @id）
  4. 查询规则：同 id 多记录时取最新 committed；含 working amends 时按 stage 显示给用户

merge 时只看 committed 记录，取 commit_id 最大的（最新一次 commit）
```

<!-- @id:impl-version-manager-tests -->
## 测试要点

- create → stage --all → commit 流水线，断言版本索引和 chg-yaml 正确生成
- 空 commit 触发 E1
- 同 id 修订：committed → 再 stage → commit 产生第二条 committed 记录
- merge 三场景：纯 add / 含 modify / 含 delete
- merge 冲突：fork 后基线变动，base_hash 不匹配，按各 conflict_policy 行为正确
- 事务性：在 commit 写文件中途模拟 IOError，断言版本索引未被部分更新
