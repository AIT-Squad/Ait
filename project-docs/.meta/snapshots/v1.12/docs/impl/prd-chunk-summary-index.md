<!-- @id:impl-prd-chunk-summary-field -->
## chunks-index 增加 summary 字段 + @summary 注释解析

<!-- @ref:prd/v1-6-roadmap#prd-prd-chunk-summary-index rel:implements -->

### 改动点

#### 1. `ait/schemas.py` — 扩展 BaselineChunkEntry

第 56~60 行 `BaselineChunkEntry` 新增可选字段（默认 `None`，向后兼容）：

`class BaselineChunkEntry(StrictModel)` 增加一行 `summary: str | None = None`（≤ 120 字符；旧数据 reindex 后保持 None）。

同步在第 92~106 行 `VersionChunkEntry` 增加 `summary: str | None = None`，让版本工作区 chunk 也能携带 summary（commit 时同步到 baseline）。

约束：summary 长度校验放在 `chunks-index` 加载时（pydantic field validator），> 120 字符直接拒绝加载并抛 `INDEX_SCHEMA_VIOLATION`，避免劣化数据潜伏。

#### 2. `ait/chunk_parser.py` — 解析 `<!-- @summary: ... -->` 注释

参考第 28 行 `EXTRACT_PATTERN` 的写法，新增模式 `SUMMARY_PATTERN = re.compile(r"^<!--\s*@summary:\s*(.+?)\s*-->\s*$")`。

在 `Chunk` 数据类（找当前 `Chunk` 定义位置，在 id/heading/level/content 之后）加 `summary: str | None = None` 字段。

在主解析循环（`parse_text`/`parse_file` 内构造 chunk 的位置）：当一行匹配 `SUMMARY_PATTERN` 且当前位于某个 `@id` 块内时，把 group(1) 赋给该 chunk 的 `summary`。**注释行本身从 chunk content 中剔除**（与 `@ref` 处理一致），保证 chunk_hash 不被注释扰动。

边界：
- 同一 chunk 出现多次 `@summary` → 取最后一次（与 `@ref` 多重声明处理对称）
- summary 文本若超 120 字符 → 解析阶段不报错（解析器宽容），由 schema validator 在写 index 时拒绝
- 解析器不再从其他地方推断 summary（严格"声明优先"，不做猜测）

#### 3. `ait/index_manager.py` — 写入 / 保留 summary

第 81~95 行 `IndexManager.rebuild_baseline()` 内构造 `BaselineChunkEntry` 时：
1. 从 parsed chunk 取 `chunk.summary`（来自 markdown 内 `@summary` 注释）
2. 若为 `None`，回查上一份已存在的 `chunks-index.yaml` 同 id 的 entry，若有 `summary` → 沿用（不丢已生成数据）
3. 否则保持 `None`

同样的回查逻辑加到第 198 行附近 `VersionChunkEntry` 写入路径（`add_chunk` 流程）。

不得改动 reindex 主链路其他逻辑（id/file/heading/level 仍按现规则刷新）。

#### 4. `ait/prd_manager.py` + `ait/impl_manager.py` — commit 时校验 summary

`PrdManager.commit()`（约 304 行）/`ImplManager.commit()`（约 171 行）成功 stage 之前，对本次 commit 涉及的每个 chunk 检查其 `summary` 字段：
- 若 markdown 已声明 `@summary` → 已通过 #2 解析进入 chunk 对象，断言 ≤ 120 字符；超长则 `SUMMARY_TOO_LONG` 阻断 commit
- 若 chunk.summary 为 None → 抛 `SUMMARY_REQUIRED` 错误码并阻断 commit，错误体含未填 summary 的 chunk id 列表 + 每个 chunk 的 heading 提示

**LLM 自动生成 summary 的工作放在 skill 侧（ait-discuss / ait-impl-discuss）**——CLI 只校验、不联网调 LLM，保持 CLI 二进制无外部 API 依赖。skill 在用户进入 commit 前，对缺 summary 的 chunk 调 LLM 生成、写回 markdown 的 `<!-- @summary: ... -->` 注释，再触发 `ait prd commit` / `ait impl commit`。

#### 5. `ait/cli.py` — 新增 `ait baseline-summary` 命令

放在与 `state` / `specgraph` 平级的位置（第 750~760 行附近，紧邻 `reindex`）：

新增 `@cli.command("baseline-summary")` 装饰器、`--scope ∈ {prd, impl, all}`（默认 `all`）、`--format ∈ {yaml, json}`（默认 `yaml`）。

实现：从 `IndexManager.load_baseline()` 拿 chunks，按 scope 过滤（id 前缀 `prd-` / `impl-`），输出 `[{id, heading, summary}, ...]`；缺 summary 的 entry 输出 `summary: null`（不报错，这是查询命令）。

退出码：始终 0（查询命令）；找不到 baseline 时输出空数组、退出 0。

### 单元测试

- `tests/test_chunk_parser_summary.py::test_summary_extracted` — markdown 含 `<!-- @summary: 一句话 -->` 时，parse 出的 chunk.summary 字段正确；该注释行不出现在 chunk.content；chunk_hash 与无注释版相同（验证注释行被剥离）。
- `tests/test_chunk_parser_summary.py::test_no_summary_remains_none` — 未声明时 chunk.summary == None。
- `tests/test_chunk_parser_summary.py::test_multiple_summary_take_last` — 同 chunk 多次 @summary 取最后一次。
- `tests/test_index_manager_summary.py::test_rebuild_preserves_existing_summary` — 旧 index 已有 summary、markdown 中无 @summary 时，rebuild 后 summary 字段保留（不被清空）。
- `tests/test_index_manager_summary.py::test_rebuild_picks_markdown_over_index` — markdown 中的 @summary 优先于 index 中已存值。
- `tests/test_prd_commit_summary.py::test_commit_blocks_when_summary_missing` — 含未填 summary 的 chunk 时 `prd commit` 报 `SUMMARY_REQUIRED` 并阻断，stdout 是合法 `{ok:false}` JSON。
- `tests/test_prd_commit_summary.py::test_commit_blocks_when_summary_too_long` — > 120 字符报 `SUMMARY_TOO_LONG`。
- `tests/test_baseline_summary_cmd.py::test_scope_prd` — 在 fixture 上跑 `ait baseline-summary --scope prd --format json`，输出仅含 PRD chunk、字段集合 == {id, heading, summary}、退出 0。
- `tests/test_baseline_summary_cmd.py::test_token_budget` — 用 30 个 chunk × 平均 80 字符 summary 的 fixture，断言 `--format yaml` 输出 ≤ 5 KB（PRD chunk 9 节验收第 6 条对齐）。
