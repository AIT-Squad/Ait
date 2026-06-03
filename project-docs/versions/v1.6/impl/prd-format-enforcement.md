<!-- @id:impl-prd-format-enforcement-gate -->
## PRD/impl 格式硬约束 + ait lint 命令 + 派生命名校验

<!-- @ref:prd/v1-6-roadmap#prd-prd-format-enforcement rel:implements -->

### 改动点

#### 1. 新建 `ait/format_validator.py`

集中所有格式校验逻辑，提供纯函数接口（不依赖 ImplManager / PrdManager），方便单测和 lint 命令复用。

公开函数（接口轮廓）：
- `validate_prd_chunk(chunk: Chunk) -> list[FormatViolation]` — 检查中文四段：必须**仅**含且按顺序出现 `### 概述` / `### 业务规则` / `### 验收标准` / `### 边界与非目标`；检测英文名（`Goal` / `Non-Goals` / `Approach` / `Acceptance`）→ 给出 `mappable=True` 的 fix hint
- `validate_impl_chunk(chunk: Chunk, *, full_text: str) -> list[FormatViolation]` — 含 ` ``` ` 围栏代码块时必须被 `<!-- @extract:dynamic/{type}#{chunk} -->` ... `<!-- @extract-end -->` 包裹（用 `parse_extract_blocks` 拿到所有 extract 区间，遍历代码块 line range 判断是否在某 extract 区间内）
- `validate_chunk_id(chunk_id: str) -> list[FormatViolation]` — 必须匹配 `^(prd|impl|task|global)-[a-z0-9-]+$`
- `validate_derived_name(chunk: Chunk, baseline_ids: set[str], version_ids: set[str]) -> list[FormatViolation]` — impl chunk id 必须形如 `impl-{prd-id 去 prd- 前缀}-{name}`，并且其 @ref `rel:implements` 指向的 PRD chunk 必须在 baseline ∪ version 中存在
- `validate_task_id(task_id: str) -> list[FormatViolation]` — 必须匹配 `^T-[a-z0-9-]+-\d{2}$`

`FormatViolation` dataclass：`{chunk_id, file, line, code, message, fixable: bool, fix_hint: str | None}`。

错误码常量集中放在本文件顶部：
- `PRD_FORMAT_VIOLATION` / `IMPL_FORMAT_VIOLATION` / `CHUNK_ID_FORMAT_VIOLATION` / `DERIVED_NAME_VIOLATION`

#### 2. `ait/prd_manager.py` + `ait/impl_manager.py` — commit 闸门接 validator

`PrdManager.commit()`（第 304 行）stage 之前，对本次 commit 涉及的每个 chunk 跑 `validate_prd_chunk` + `validate_chunk_id`，把所有 violation 聚合后若非空则抛 `ValidationError`，错误码取首条 violation.code，details 中带完整列表。

`ImplManager.commit()`（第 171 行）类似：调 `validate_impl_chunk` + `validate_chunk_id` + `validate_derived_name`（后者需要传 baseline_ids 和 version_ids 集合）。

不动 stage / commit 后续链路。

#### 3. `ait/cli.py` — 新增 `ait lint` 命令

放在与 `state` / `reindex` 平级位置，新增 `@cli.command("lint")`，参数：
- `--scope` ∈ `{baseline, version, vX.Y}`（默认 `baseline`；`version` 等价于扫所有未 merged 版本工作区；具体版本号仅扫该版本）
- `--fix` flag（默认 False）

实现：
- scope 解析：`baseline` → 扫 `docs/prd/global.md` + `docs/impl/*.md`；`version` → 扫所有未 merged 版本工作区；`v1.6` 之类的具体版本号 → 仅扫该版本工作区
- 对每个 chunk 跑 `format_validator` 全套，聚合 `FormatViolation` 列表
- 输出契约：`{ok: bool, violations: [...]}`；违规非零 → ok=false、退出码非零；空列表 → ok=true 退出 0
- `--fix` 仅处理 `fixable=True` 的违规：
  - (a) 英文四段标题映射 `Goal→概述`、`Non-Goals→边界与非目标`、`Approach→业务规则`、`Acceptance→验收标准`（按行 in-place 替换）
  - (b) 缺段填空骨架：按 PRD 四段顺序检查缺哪段，缺则在该 chunk 末尾按正确顺序追加 `### <段名>\n\n_TODO_\n`
  - 不可机械修复的违规仅报告
- 修复后立即重跑校验，若仍有违规，输出仍包含；保证 `--fix` 后再无 fixable 残留

#### 4. `ait/task_manager.py` — task 创建 / 加载时校验 task id

定位 task_manager 中创建 task YAML 的入口（task create 调用栈中写盘前），在 `atomic_write_text` / `yaml.safe_dump` 之前调 `validate_task_id(task.id)`，违规直接抛 `ValidationError(code="DERIVED_NAME_VIOLATION")` 并不写 YAML。

#### 5. v1.5 `prd-formats` 软告警的去除

源码 grep 验证：`impl-formats-parser` / `FORMAT_VIOLATION` / `format_violation` 在 ait 源码中均 0 hit，确认 v1.5 该 chunk 主要在文档/skill 文档中体现，**未实装到 CLI**。本 impl 直接以首次实装姿态落地，无需清理任何"已有告警代码"。

#### 6. 不得改动

- chunk_parser 任何代码（格式校验是上层语义检查，不改解析层）
- merge_engine（格式问题在 commit 闸门已拦下，不会进入 merge）
- baseline 历史 chunk 内容（PRD 已声明不回溯阻断；仅 `lint --scope baseline` 主动扫描时报告）

### 单元测试

- `tests/test_format_validator_prd.py::test_chinese_four_sections_pass` — 合规 PRD chunk 无违规。
- `tests/test_format_validator_prd.py::test_english_sections_violation` — 含 `### Goal` 等英文段名 → 报 `PRD_FORMAT_VIOLATION`、fixable=True、fix_hint 标出映射。
- `tests/test_format_validator_prd.py::test_missing_section_violation` — 缺 `### 验收标准` → 违规列出缺段名，fixable=True。
- `tests/test_format_validator_prd.py::test_section_order_wrong` — 四段齐全但顺序乱（验收标准在业务规则之前）→ 违规、fixable=False。
- `tests/test_format_validator_impl.py::test_naked_codeblock_violation` — impl chunk 含 ``` 但无 @extract 包裹 → `IMPL_FORMAT_VIOLATION`。
- `tests/test_format_validator_impl.py::test_extract_wrapped_codeblock_passes` — 同代码块被 @extract 包裹 → 通过。
- `tests/test_format_validator_id.py::test_chunk_id_uppercase_violation` — `Prd-Foo` → `CHUNK_ID_FORMAT_VIOLATION`。
- `tests/test_format_validator_id.py::test_derived_impl_name_violation` — `impl-foo-x` 但 baseline/version 都无 `prd-foo` → `DERIVED_NAME_VIOLATION`。
- `tests/test_format_validator_id.py::test_derived_task_id` — `T-foo-3`（缺补 0）→ 违规；`T-foo-03` → 通过。
- `tests/test_prd_commit_format_gate.py::test_english_sections_blocks_commit` — 含英文段的 chunk → `prd commit` 报错阻断、退出码非零、stdout 是合法 `{ok:false}` JSON、details.violations 列表非空。
- `tests/test_impl_commit_format_gate.py::test_naked_codeblock_blocks_commit` — 含裸代码块的 impl chunk → `impl commit` 阻断。
- `tests/test_lint_cli.py::test_lint_baseline_clean` — 干净 baseline → ok=true 退出 0。
- `tests/test_lint_cli.py::test_lint_version_v16_clean_after_dogfood` — 在本 impl 落地后跑 `ait lint --scope v1.6` → 0 违规（dogfood 自洽，PRD 验收最后一条）。
- `tests/test_lint_cli.py::test_lint_fix_english_to_chinese` — fixture 含 `### Goal` 的 chunk，`--fix` 后再扫无违规、文件内容已变中文段名。
- `tests/test_lint_cli.py::test_lint_fix_only_fixable` — fixture 含"段顺序错"（不可修）+"英文段名"（可修），`--fix` 只修后者、前者仍报告。
- `tests/test_task_create_format.py::test_task_id_format_blocks` — 构造非法 task id → task create 报 `DERIVED_NAME_VIOLATION` 不写盘。
