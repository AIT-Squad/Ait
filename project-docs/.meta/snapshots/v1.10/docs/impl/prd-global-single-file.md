<!-- @id:impl-prd-global-migrate-script -->
## Baseline PRD 单文件化 — 一次性迁移脚本

<!-- @ref:prd-prd-global-single-file rel:implements -->

### 改动点

#### 1. 新建 `scripts/migrate_prd_to_global.py`（仓库根目录 `scripts/` 下）

脚本作为 v1.6 的一次性 task 执行，跑完即弃，不进 ait CLI 永久 surface。

入参：无（默认读 `project-docs/`，可通过 `--root` 覆盖）。

执行步骤（严格顺序，任一失败立即终止并不修改磁盘）：
1. 加载 baseline `chunks-index.yaml`，过滤出所有 `id` 以 `prd-` 开头的 chunk，按 `file` 分组、再按 chunk 在原文件中的物理顺序聚合，得到 `(file, [chunk_id, ...])` 列表。**保持 chunks-index 中的当前顺序作为最终顺序**（chunks-index 是唯一权威 ordering）。
2. 用 `chunk_parser.parse_file(path, root)` 解析每个原始 PRD 文件，按 1 中顺序取出 chunk 对象（带 raw content / @ref / @extract）。
3. 拼接所有 chunk 的原始 raw 内容到一个新文件 `docs/prd/global.md`，文件头部写 `# Baseline PRD（merged baseline, edit by chunk only）` 单行 H1，**chunk 之间用单空行分隔**，chunk 内容 **逐字保留**（包含 `<!-- @id -->` / `<!-- @ref -->` / `<!-- @extract -->`，不重写、不规范化、不去 BOM）。
4. 用 `chunk_parser.parse_file('docs/prd/global.md', root)` 重新解析，断言：解析出的 chunk 数 = 原 14 个 PRD 文件 chunk 总和（52）；chunk id 集合相等；每个 chunk 的 `chunk_hash(content)` 与原文件中同 id chunk 的 hash 完全相等（这是迁移自反性 / 零内容损失契约）。
5. 物理删除 `docs/prd/` 下除 `global.md` 外的所有 `.md` 文件（先打印将删除文件清单，--apply 才真正删；默认 dry-run）。
6. 调用 `ait reindex`（用 `subprocess.run([sys.executable, '-m', 'ait.cli', 'reindex'], cwd=root, check=True)`），重建 baseline `chunks-index.yaml` 和 `specgraph.yaml`。
7. 跑迁移后自检：
   - `chunks-index.yaml` 中所有 PRD chunk 的 `file` 字段 == `prd/global`。
   - PRD chunk 总数 == 迁移前快照值（从步骤 1 暂存）。
   - specgraph 中 PRD chunk 的 `@ref` 出/入边集合 == 迁移前快照（用 `(src, rel, dst)` 三元组集合相等判定）。
8. 输出 JSON 报告到 stdout：`{ok, prd_chunk_count, deleted_files, specgraph_diff_edges}`。失败任何一步退出码非零，并保留 `--apply` 之前的状态。

参数：`--root`（默认 `project-docs/`）、`--apply`（默认 dry-run，必须显式给才真正落盘）。

不得改动：
- 任何 chunk 的 raw 内容（包括尾随空行）。
- impl 文件、impl chunks-index、versions/* 历史快照。
- 已 merged 的 v1.1~v1.5 工作区。
- baseline `chunks-index-{vX.Y}.yaml` 历史文件（仅当前 baseline `chunks-index.yaml` 重建）。

### 单元测试
- `tests/test_migrate_prd_to_global.py`：在 `tmp_path` 构造 mini project-docs（3 个 PRD 文件、共 5 个 chunk + 跨文件 @ref），跑脚本（apply=True），断言 `docs/prd/global.md` 存在、其它 `.md` 不存在、parse_file 重解析出 5 chunk、id 集合相等、每 chunk hash 相等。
- `tests/test_migrate_prd_to_global.py::test_dry_run_does_not_touch_disk`：默认 dry-run 模式断言磁盘零变更（mtime 全等）。
- `tests/test_migrate_prd_to_global.py::test_specgraph_isomorphic`：迁移前 / 后 specgraph 中 PRD 节点的所有 (src, rel, dst) 三元组集合完全相等。

<!-- @ref:prd/v1-6-roadmap#prd-prd-global-single-file rel:implements -->

<!-- @id:impl-prd-global-merge-target-rewrite -->
## Baseline PRD 单文件化 — version confirm 路由收敛

<!-- @ref:prd-prd-global-single-file rel:implements -->

### 改动点

#### 1. `ait/version_manager.py`

`_perform_merge_internal`（约第 497~506 行）的 `by_file` 分组逻辑：在循环里追加一段"PRD chunk 路由强制收敛"判定，紧跟在 `file_key = r.file` 推断之后、`by_file.setdefault(...)` 之前：当 `file_key` 以 `prd/` 开头且不是 `prd/global` 时，将其改写为 `prd/global`。

判定标准：file_key 当前以 `prd/` 开头（说明是 PRD 类目）但不是 `prd/global` 本身——一律改写为 `prd/global`。delete 记录走 overrides → baseline file 的回查路径，命中同样的判定（这条逻辑前面已经把 file_key 解出来了）。

不得改动：
- `_merge_one_file` 函数本身（它接到的 file_key 已经被改写为 `prd/global`，按现有逻辑去 `docs/prd/global.md` 读 baseline、写回，无需感知"全局合并"语义）。
- impl 类目（`impl/*`）的路由 —— PRD 改动**不影响 impl 多文件**。
- chunks-index 的 `file` 字段写入逻辑：confirm 完成后由 `rebuild_baseline()` 自动用 `parse_file(global.md)` 重扫，所有 PRD chunk 的 `file` 字段会自然变成 `prd/global`，无需人为干预。

#### 2. `ait/version_manager.py` — version 工作区侧不约束

版本工作区 `versions/{vX.Y}/prd/*.md` 仍允许多文件（人写更舒服），`prd commit` 阶段不做合并、不做路由改写，记录的 `file` 字段仍是版本侧文件名（如 `prd/v1-6-roadmap`）。这条记录只在 `version confirm` 阶段被改写为 `prd/global`。**不**改 `prd commit` 任何逻辑。

#### 3. CLI `prd commit` —— 不变

确认无改动：`prd commit` 既不读 baseline 也不写 baseline，路由改写与它无关。

### 单元测试
- `tests/test_version_confirm.py::test_prd_chunks_force_routed_to_global`：构造 mini project-docs，baseline `docs/prd/global.md` 已存在含 1 个 chunk；版本工作区 `versions/v0.1/prd/foo.md` 加 1 个新 chunk（add）+ 修改 baseline 的 chunk（modify）。confirm 后断言：(a) `docs/prd/global.md` 含 2 个 chunk； (b) `docs/prd/foo.md` 不存在； (c) chunks-index 中所有 PRD chunk 的 `file` == `prd/global`。
- `tests/test_version_confirm.py::test_impl_chunks_unaffected`：同样场景但版本侧加的是 `impl/bar.md` 的 impl chunk，断言 baseline 里 `docs/impl/bar.md` 被正常创建——证明 impl 路由不被牵连。
- `tests/test_version_confirm.py::test_delete_prd_chunk_routes_to_global`：版本侧 delete 一个 baseline 中存在的 PRD chunk，断言它从 `docs/prd/global.md` 中被移除，且 `docs/prd/global.md` 仍是单文件存在。

<!-- @ref:prd/v1-6-roadmap#prd-prd-global-single-file rel:implements -->

<!-- @id:impl-prd-global-parser-compat-check -->
## Baseline PRD 单文件化 — 解析与依赖系统兼容性验证

<!-- @ref:prd-prd-global-single-file rel:implements -->

### 改动点

本 chunk 不改产品代码，只新增**回归测试**与**自检脚本**，确保单文件 baseline 下整套 chunk 索引 / specgraph / context / deps / impact 仍正常工作。

#### 1. 新建 `tests/test_global_prd_baseline.py`

构造一个 fixture：mini project-docs，baseline 仅含 `docs/prd/global.md`（手工写入 3 个 PRD chunk + 跨 chunk @ref），跑 `IndexManager.rebuild_baseline()` 后断言：
- `chunks-index.yaml` 中 3 个 chunk 的 `file` 字段全为 `prd/global`、`id` 字段与文件内 @id 一一对应、顺序与文件内物理顺序一致。
- `specgraph.yaml` 中三元组集合 == 手工写入的 @ref 关系集合。
- `ait context <chunk_id>` 对每个 chunk 都能命中 L1/L2，不返回空。
- `ait deps <chunk_id>` / `ait impact <chunk_id>` 输出与多文件等价构造下完全一致（用同一组 @ref 在多文件版下作为 oracle 对比）。

#### 2. 新建 `tests/test_chunk_parser_global.py::test_large_single_file_parses_full`

直接读真实 baseline（`project-docs/docs/prd/global.md`，迁移完成后才会存在；测试用 `pytest.importorskip` + 文件存在判定守卫，避免在迁移前的 CI 上误失败），断言：
- `parse_file` 解析出的 chunk 数 ≥ 52（v1.6 基线 52，未来增不退）。
- 所有 chunk 的 @id 唯一。
- 所有 @ref 的 dst 要么在本文件内、要么在 `docs/impl/*.md` 中能找到（用 chunks-index 验证）。

#### 3. 新建一次性自检脚本 `scripts/verify_prd_global_invariants.py`

不进 CLI，作为迁移完成后的人工触发自检（`python scripts/verify_prd_global_invariants.py`），打印：
- `docs/prd/` 是否仅有 `global.md` 一个文件。
- baseline chunks-index 中 PRD chunk 总数、file 字段唯一值集合（应只有 `{"prd/global"}`）。
- specgraph PRD 节点 / 边数。
- `ait state` / `ait specgraph` / `ait deps prd-prd-global-single-file` / `ait impact prd-prd-global-single-file` 的 ok 状态（用 subprocess 跑、断 returncode）。

#### 4. 不得改动

- `chunk_parser.py` 任何代码（PRD 单文件解析仅是数据规模变化，不是语义变化，原解析器已具备能力）。
- `IndexManager.rebuild_baseline()` 任何代码（同理）。
- `specgraph.py` 任何代码。
- `context_builder.py` / `deps.py` / `impact.py` 任何代码。

如以上任一测试失败，说明此前隐藏的"单文件下假设多文件 file 字段差异化"耦合，需要回到 impl#1 / impl#2 修补，**不在本 chunk 中改产品代码**。

### 单元测试
- 上述 #1、#2 即测试本身；本 chunk 没有"产品代码 + 配套测试"的二元结构，整体就是一组回归保护网。
- 验收：跑 `pytest tests/test_global_prd_baseline.py tests/test_chunk_parser_global.py -q` 全绿，且 `python scripts/verify_prd_global_invariants.py` 退出码 0。

<!-- @ref:prd/v1-6-roadmap#prd-prd-global-single-file rel:implements -->
