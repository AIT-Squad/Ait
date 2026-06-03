<!-- @ref:prd/skills#prd-skills-rename-block-to-chunk rel:implements -->
<!-- @id:impl-data-chunk-rename -->
## Chunk 数据模型重命名（Schema + 索引文件 + 一次性迁移）

落实 PRD `prd-skills-rename-block-to-chunk` 中"代码符号 / 索引与元数据文件 / 用户态文档迁移"三项要求中**与数据模型相关**的部分。具体包括：`ait/schemas.py` 的 Pydantic 模型重命名、`ait/index_manager.py` 的索引文件名常量重命名，以及一次性迁移 CLI `bin/ait migrate-block-to-chunk` 的算法与契约。代码符号面（除 schema 外的 11 个 .py 文件、SKILL.md、references/）由配套 chunk `impl-workflow-chunk-rename` 承担，本 chunk 是它的前置依赖。

### 0. 非目标（Out-of-Scope）

- **不修改注释语法**：`<!-- @id:xxx -->` / `<!-- @ref:file#id rel:type -->` 完全保持不变。`block_parser.py` 中的 `ID_PATTERN = re.compile(r"^<!--\s*@id:([a-z0-9-]+)\s*-->\s*$")` 与 `REF_PATTERN` 在符号重命名后语法不变，仍然只识别 `@id` / `@ref` 关键字（不引入 `@chunk:`）。
- **不保留向后兼容层**：旧字段（`blocks` / `prd_blocks` / 等）与旧文件名（`blocks-index.yaml`）一律 hard-rename，由本 chunk 的迁移脚本一次性重写存量数据后即不再支持回读。
- **不动 `chg-*.yaml` 内的 `base_content` / `new_content`**：这两个字段保存的是用户 markdown 原文，自然语言"block"已在 PRD 验收标准中允许保留，迁移脚本不进入这两个字段做文本替换。

### 1. Schema 字段映射表

`ait/schemas.py` 内全部 Pydantic 模型与字段的重命名对照（`extra="forbid"` 严格模式下，每条都是破坏性变更）。

#### 模型类名（6 项）

| 当前 | 重构后 | 出现位置（schemas.py） |
|---|---|---|
| `BaselineBlockEntry` | `BaselineChunkEntry` | baseline 索引条目 |
| `VersionBlockEntry`  | `VersionChunkEntry`  | version 索引条目 |
| `PrdBlockSummary`    | `PrdChunkSummary`    | requirement 内 PRD 摘要 |
| `ImplBlockDraft`     | `ImplChunkDraft`     | requirement 内 impl 草稿 |
| `ImplDraftBundle.impl_blocks` 关联类型同步 | 同步为 `ImplChunkDraft` | 引用更新 |
| 文件头 docstring 中的 "block" 文案 | "chunk"               | 模块顶部注释 |

#### Pydantic 字段名（9 项）

| 模型 | 旧字段 | 新字段 |
|---|---|---|
| `BaselineIndex`        | `blocks: list[BaselineBlockEntry]`           | `chunks: list[BaselineChunkEntry]` |
| `VersionIndex`         | `blocks: list[VersionBlockEntry]`            | `chunks: list[VersionChunkEntry]` |
| `CommitEntry`          | `blocks: list[str]`                          | `chunks: list[str]` |
| `VersionIndexStats`    | `total_blocks: int`                          | `total_chunks: int` |
| `RequirementMeta`      | `prd_blocks: list[PrdBlockSummary]`          | `prd_chunks: list[PrdChunkSummary]` |
| `ImplDraftBundle`      | `impl_blocks: list[ImplBlockDraft]`          | `impl_chunks: list[ImplChunkDraft]` |
| `MergeRecord`*         | `merged_blocks: list[str]`（version_manager.py 内 dataclass） | `merged_chunks: list[str]` |
| `ChangeRecord.target`  | 不变（值是 `"file#id"`，无 block 字眼）       | 不变 |
| `Action` Literal       | 不变（`add`/`modify`/`delete`，无 block 字眼） | 不变 |

\* `MergeRecord` 实际定义在 `version_manager.py`，但字段属于数据模型层，迁移脚本需识别其在 yaml 中的序列化形式。

#### Pydantic 别名声明（无）

> 所有重命名均为 hard-rename，**不使用** `Field(alias="blocks")` 之类的兼容别名。`extra="forbid"` 严格模式确保旧字段在反序列化时立即报错（而非静默忽略），强制迁移脚本必须先跑。

### 2. 索引文件命名常量

`ait/index_manager.py` 的两处文件名常量：

| 位置 | 旧值 | 新值 |
|---|---|---|
| `IndexManager.BASELINE_FILE` | `"blocks-index.yaml"` | `"chunks-index.yaml"` |
| `IndexManager._version_file()` | `f"blocks-index-{version}.yaml"` | `f"chunks-index-{version}.yaml"` |
| `links-index.yaml` | 不变 | 不变（命名中无 block） |

类内方法名同步：`_load_baseline_blocks()` → `_load_baseline_chunks()`、`_persist_blocks_index()` → `_persist_chunks_index()` 等（详见 chunk #2 的代码符号清单，本 chunk 仅声明常量层面的契约）。

### 3. @id / @ref 注释语法不变

[block_parser.py](/Users/jenningwang/Documents/project/ait/skill/ait/ait/block_parser.py)（即将更名为 `chunk_parser.py`）中的两条 regex 在重命名后**字符串内容保持不变**：

```python
# Before & After（regex 字符串完全相同）：
ID_PATTERN = re.compile(r"^<!--\s*@id:([a-z0-9-]+)\s*-->\s*$")
REF_PATTERN = re.compile(
    r"<!--\s*@ref:([\w\-/.]+)#([a-z0-9-]+)\s+rel:([a-z\-]+)\s*-->"
)
```

效果：`project-docs/docs/**.md` 与 `project-docs/versions/**/*.md` 中**已落盘的 `<!-- @id:... -->` / `<!-- @ref:... -->` 注释零改动**。这也是 PRD 验收标准里"用户态文档迁移：注释保持不变"的实现保障。

### 4. 一次性迁移脚本 `bin/ait migrate-block-to-chunk`

迁移脚本以**新增 CLI 子命令**形式实现（不放在临时 scripts/）。理由：易测试、可重入（幂等）、便于其他基于 ait 框架的项目在升级到本版本时复用。

#### 4.1 模块位置

- **新增模块**：`skill/ait/ait/migrations.py`
- **CLI 注册**：`skill/ait/ait/cli.py` 增加 `@cli.command("migrate-block-to-chunk")` 入口
- **依赖**：复用 `yaml_io.py` 的读写、`root.py` 的项目根解析；不引入新第三方包

#### 4.2 公开 API

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class MigrationReport:
    """Report returned by migrate_block_to_chunk(). Idempotent: re-runs return all-empty."""
    yaml_files_rewritten: list[Path] = field(default_factory=list)
    files_renamed: list[tuple[Path, Path]] = field(default_factory=list)  # (old, new)
    fields_renamed_count: int = 0
    skipped_reason: str | None = None  # set when already migrated

def migrate_block_to_chunk(meta_dir: Path, dry_run: bool = False) -> MigrationReport:
    """One-time migration from `block` to `chunk` data model.

    Atomic: writes through tempfile + os.replace. All-or-nothing per yaml.
    Idempotent: detects already-migrated state via marker file `.meta/.migrated-chunk-v1`
                and returns early with report.skipped_reason set.
    """
```

#### 4.3 算法

```text
Step 0: Idempotency guard
   if (meta_dir / ".migrated-chunk-v1").exists():
       return MigrationReport(skipped_reason="already migrated")

Step 1: Walk meta_dir for yaml files
   targets = list(meta_dir.rglob("*.yaml"))

Step 2: For each yaml, deep-rewrite field names per FIELD_MAP
   FIELD_MAP = {
       "blocks": "chunks",
       "prd_blocks": "prd_chunks",
       "impl_blocks": "impl_chunks",
       "merged_blocks": "merged_chunks",
       "total_blocks": "total_chunks",
   }
   - Use yaml.safe_load + recursive dict walker (depth-first, in-place)
   - Skip walking into ChangeRecord.{base_content,new_content} string values
   - Write through tempfile in same dir, fsync, os.replace (atomic)

Step 3: Rename baseline + version index files
   if (meta_dir / "blocks-index.yaml").exists():
       (meta_dir / "blocks-index.yaml").rename(meta_dir / "chunks-index.yaml")
   for old in meta_dir.glob("blocks-index-*.yaml"):
       new_name = old.name.replace("blocks-index-", "chunks-index-", 1)
       old.rename(meta_dir / new_name)

Step 4: Validate (deserialize all rewritten yaml with NEW schemas)
   - Try BaselineIndex.model_validate(yaml.safe_load(chunks-index.yaml))
   - Try VersionIndex.model_validate(...) for each chunks-index-{vX.Y}.yaml
   - Try RequirementMeta.model_validate(...) for each requirements/*.yaml
   - On any failure: report.errors.append(...) and raise MigrationError
     (atomic per-file already done; rollback is "manual git checkout")

Step 5: Write marker
   (meta_dir / ".migrated-chunk-v1").write_text("migrated_at: <iso8601>\n")

Step 6: Return MigrationReport
```

#### 4.4 CLI 入口

```python
# skill/ait/ait/cli.py 新增
@cli.command("migrate-block-to-chunk")
@click.option("--dry-run", is_flag=True, help="Show what would change, don't write.")
@click.pass_obj
def migrate_block_to_chunk_cmd(root: ProjectRoot, dry_run: bool) -> None:
    """One-time migration: rename `block` to `chunk` in all .meta/*.yaml files."""
    report = migrate_block_to_chunk(root.meta, dry_run=dry_run)
    click.echo(json.dumps({
        "ok": True,
        "data": {
            "skipped": report.skipped_reason is not None,
            "skipped_reason": report.skipped_reason,
            "yaml_rewritten": [str(p) for p in report.yaml_files_rewritten],
            "files_renamed": [[str(o), str(n)] for o, n in report.files_renamed],
            "fields_renamed_count": report.fields_renamed_count,
        },
    }, ensure_ascii=False, indent=2))
```

#### 4.5 幂等性与可重入

- **首跑**：扫描 → 重写 → 重命名 → 写 marker
- **再跑**：marker 存在直接返回 `skipped_reason="already migrated"`，零副作用
- **半完成态恢复**：若 Step 2~4 之间崩溃（marker 未写），重跑会重新处理；由于 `os.replace` 原子且 yaml 内容已是新格式，walker 在新 yaml 上跑 FIELD_MAP 会发现"无 `blocks` 字段可改"，自然跳过

#### 4.6 测试矩阵

| 用例 | 输入 | 期望输出 |
|---|---|---|
| 全新项目（仅 baseline） | `.meta/blocks-index.yaml` + `links-index.yaml` | 1 文件改写 + 1 文件重命名，无报错 |
| 含进行中版本 | 上 + `blocks-index-v1.2.yaml` + `versions/v1.2.yaml` | 3 文件改写 + 2 文件重命名 |
| 含已 merged 版本 + 需求 + 变更 | 上 + `requirements/req-*.yaml` + `changes/chg-*.yaml` | 全部 yaml 改写；chg 的 base/new_content 不改 |
| 重复执行 | 已迁移过的项目 | `skipped=true`，无文件操作 |
| dry-run | `--dry-run` 任意状态 | 报告完整，但磁盘零变化 |

### 5. 数据兼容性矩阵

| 数据资产 | 旧形态 | 新形态 | 破坏性 | 迁移方式 |
|---|---|---|---|---|
| `.meta/blocks-index.yaml` 文件名 | `blocks-index.yaml` | `chunks-index.yaml` | 是 | Step 3 重命名 |
| `.meta/blocks-index-{vX.Y}.yaml` 文件名 | `blocks-index-v1.2.yaml` | `chunks-index-v1.2.yaml` | 是 | Step 3 重命名 |
| BaselineIndex.blocks 字段 | `blocks:` | `chunks:` | 是 | Step 2 字段重写 |
| VersionIndex.blocks 字段 | `blocks:` | `chunks:` | 是 | Step 2 字段重写 |
| CommitEntry.blocks 字段 | `commits[].blocks:` | `commits[].chunks:` | 是 | Step 2 字段重写（深层） |
| VersionIndexStats.total_blocks | `stats.total_blocks:` | `stats.total_chunks:` | 是 | Step 2 字段重写（深层） |
| RequirementMeta.prd_blocks | `prd_blocks:` | `prd_chunks:` | 是 | Step 2 字段重写 |
| ImplDraftBundle.impl_blocks | `impl_drafts[].impl_blocks:` | `impl_drafts[].impl_chunks:` | 是 | Step 2 字段重写（深层） |
| `<!-- @id:xxx -->` 注释 | 不变 | 不变 | 否 | 零迁移 |
| `<!-- @ref:f#id rel:t -->` 注释 | 不变 | 不变 | 否 | 零迁移 |
| `chg-*.yaml` 的 base_content / new_content | 不变 | 不变 | 否 | walker 跳过 |
| `links-index.yaml` 字段 | 不变 | 不变 | 否 | 零迁移（无 block 字段） |
| `versions/{vX.Y}.yaml` | 不变 | 不变 | 否 | 零迁移（无 block 字段） |
| `config.yaml` | 不变 | 不变 | 否 | 零迁移 |

### 6. 与 chunk #2 的协作契约

- **执行顺序约束**：本 chunk 的代码改造（schema + 索引常量 + migrations.py）必须先于 chunk #2 的 12 个业务模块改造**或同 PR 完成**。原因：业务模块 `import` schema 中的类与字段，schema 改名时业务模块若未同步会立即编译/运行失败。
- **迁移脚本运行时机**：在 chunk #2 全部代码与文档改造完成后、回归测试**之前**运行一次。回归测试本身依赖新 schema 能成功反序列化已迁移的 yaml。
- **回滚预案**：本 chunk 不提供回滚 CLI；如需回滚以 `git checkout` 为准（迁移脚本运行前应当处于一个 clean commit）。

### 7. 验收要点（本 chunk 自检，整体验收见 chunk #2）

- `python -c "from ait.schemas import BaselineChunkEntry, VersionChunkEntry, PrdChunkSummary, ImplChunkDraft"` 全部成功
- `python -c "from ait.migrations import migrate_block_to_chunk"` 成功
- `bin/ait migrate-block-to-chunk --dry-run` 在已存在 `.meta/blocks-index.yaml` 的项目上输出完整迁移计划且不写盘
- `bin/ait migrate-block-to-chunk` 跑完后：
  - `.meta/chunks-index.yaml` 存在、`.meta/blocks-index.yaml` 不存在
  - `.meta/.migrated-chunk-v1` 存在
  - 对 `chunks-index.yaml` 跑 `BaselineIndex.model_validate(...)` 成功
- 重复执行 `bin/ait migrate-block-to-chunk` 输出 `skipped=true` 且无文件变化

<!-- @ref:prd/skills#prd-skills-rename-block-to-chunk rel:implements -->
