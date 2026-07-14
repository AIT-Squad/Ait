# 新模型 PRD/FSD/TDD 格式规范（权威源）

> 本文件是 AIT 新模型文档格式的**单一权威说明**，随 ait skill 分发，用户在任意项目使用时以此为准。
> **强制执行**在代码侧：`chunk_parser.py`（语法）、`new_model_validator.py`（图/六不变式/唯一性）、`new_model_manager.py`（写时门禁）、`version_manager.py`（confirm 全局门禁与验收）。本文件是人读规范；章节骨架见 `skill/ait/templates/TEMPLATE-{PRD,FSD,TDD}-AIT-DRAFT.md`。

## 1. 模型概览

```
[PRD]-<name> ──decomposes──▶ [FSD]-<name>（根 FSD）
[FSD]-x ──(内部 split)──▶ [FSD]-x:<split> ──decomposes──▶ [FSD]-y（子 FSD 根）
                                            └─details──▶ [TDD]-z（叶子，绑 target_file）
[FSD]-x:<a> ──depends_on──▶ [FSD]-x:<b>（同父兄弟 split）
```

PRD 递归分解为 FSD 功能树；叶子 FSD 的内部 split `details` 到 TDD；每个 TDD 唯一映射一个 `target_file`（生成目标）。

## 2. 六不变式（规格治理契约，门禁强制）

| # | 不变式 | 违例错误码 |
|---|--------|-----------|
| 1 | 每份 PRD 恰与 1 个 FSD 关联 | `PRD_FSD_LINK_NOT_UNIQUE` |
| 2 | 每个 TDD 向上恰 1 个 FSD（details 入边），向下恰 1 个制品 | `TDD_MULTI_PARENT` / `TDD_TARGET_FILE_REQUIRED` |
| 3 | 每个制品路径只由 1 个 TDD 持有 | `DUPLICATE_TARGET_FILE`（归一化判重） |
| 4 | 所有关联经真实存在的 chunk（无幽灵边） | `MISSING_ENDPOINT` |
| 5 | 除规格树根外无孤儿 chunk | `ORPHAN_CHUNK` |
| 6 | 任一制品沿 TDD→FSD→…→PRD 可追溯 | `TRACE_BROKEN`（树关系环另报 `SPEC_CYCLE`） |

写时门禁拦"永远不该合法存在"的增量（幽灵端点/TDD 第二父/PRD 第二 FSD/制品撞车，拒绝＝零落盘可重试）；全局完整性（孤儿/断链/环）在 `version confirm`/`merge` 前对 baseline∪版本组合视图全量校验。

## 3. chunk ID 格式

- **根 chunk**：`[PRD]-<name>` / `[FSD]-<name>` / `[TDD]-<name>`，且**文件名 = 根 chunk id**（如 `fsd/[FSD]-ait.md`）。
- **内部 split**：`<父根id>:<split名>`，如 `[FSD]-ait:version`。split 名用 `_` 连接多词。**`:TEST` 是唯一的保留大写标记**——每个 FSD 文件的验收节点 chunk（见 §5b）；其余 split 名一律小写。
- **前缀**：必须是 `[PRD]` / `[FSD]` / `[TDD]`（方括号）。名内用 `_`，层级用 `-`；字符集 `[a-z0-9_]`。
- 解析见 `chunk_parser.py`：`@id` 注释、代码围栏屏蔽、bracket 前缀、`:` split。

## 4. 关系（仅三种；只随内容创建原子出生，无 link/depend 命令）

| 关系 | 合法连接 | 出生地 |
|------|----------|--------|
| `decomposes` | PRD 根 → 根 FSD 根；FSD 内部 split → 子 FSD 根 | `fsd decompose <parent> <child> [--content]`（拆分即建边，父侧门禁前置） |
| `details` | 叶 FSD 内部 split → TDD 根 | `tdd create <[TDD]-id> --parent <fsd_split>`（创建即建边） |
| `depends_on` | 同一父 FSD 下的两个**兄弟 internal split** | **fsd create 时以临时 yaml 块申报**，建边后从正文剥离（见 §5） |

**结构规则**：一个 FSD 节点**不得混用** FSD 子（decomposes）与 TDD 子（details）——要么是分解节点、要么是叶子（`FSD_MIXED_CHILDREN`）。

> **文档正文零关系声明（核心）**：PRD/FSD/TDD 的 markdown 正文**不承载任何 chunk↔chunk 关系**。三种关系（decomposes/details/depends_on）只作为 SpecGraph 显式边存在，一律经 `ait deps`/`specgraph` 查询。命令产生边（decompose/tdd --parent）或临时申报（depends_on）——申报块用完即从正文剥离。`target_file` 是制品指向（chunk→文件属性），非 chunk 间关系，故保留在 TDD 正文。

## 5. depends_on 申报（临时输入，只入 SpecGraph）

兄弟依赖在 `fsd create` 传入内容的 split chunk 正文里，以 `depends_on:` yaml 块**申报**——这是**用完即走的建边输入指令**，不是持久文档内容：

```markdown
<!-- @id:[FSD]-app:feat -->
## feat 模块
```yaml
depends_on: [store, config]
```
```

- `fsd create` 解析该块 → 建 SpecGraph 边 → **从写入磁盘的 markdown 中剥离**。持久 FSD 正文不含 `depends_on`。
- **简写按同父解析**（`store` → `[FSD]-app:store`）；完整 id 必须同父（跨父报 `DEPENDS_ON_CROSS_LEVEL`）。
- 申报指向文件内不存在的兄弟 → `DEPENDS_ON_UNKNOWN_SIBLING`；指向自己 → `DEPENDS_ON_SELF`。拒绝＝零落盘。
- **owned-scope 对账（v2.32 preserve 语义）**：同父约束使全部合法依赖边都是"本文件兄弟边"——文件＝依赖边的所有权边界。`fsd create`（add/modify）后按申报对账，但**无 `depends_on` 块的 split 保留其现有边（不 wipe）**：改依赖＝带块 modify（该 split 权威覆盖），清空＝显式 `depends_on: []`，不动＝不带块。⇒ 重排 FSD 正文（不带块）不丢依赖边。SpecGraph 是唯一权威存储。

## 5b. FSD 文件结构与能力契约（v2.33 三类分化）

**每个 FSD 文件递归同构** ＝ root ＋ N 个功能 split ＋ 恰 1 个 `:TEST`：

- **root chunk**：功能域职责边界（承接哪部分上游、负责/不负责）＋ **分解视图**（列子块结构，不列签名）。
- **功能 split**：功能描述 ＋ **能力契约（provide-only）**。
- **`:TEST` chunk**（保留大写标记）：本文件所有块合并的**集成验收**。是本文件的验收落点——一个 decompose 出子文件的 split，其验收看子文件的 `:TEST`；叶子 split 的验收由本文件 `:TEST` 覆盖。**功能 split 上不写验收标准**。

**能力契约 = 只写"本块对外提供什么"（黑盒接口，消费方开发依据）**：
- `提供方式`：HTTP 端点 / 模块函数 / CLI 命令 / 事件…
- `接口`：方法/端点 ＋ 参数名与类型 ＋ 返回结构与类型 ＋ 错误语义。
- **绝不写"需要/依赖什么"**（那是 depends_on 关系，只在 SpecGraph）；**不写函数内部实现/算法**（那是 TDD）。

**FSD vs TDD 边界**：FSD 能力契约＝对外接口（黑盒，别的块怎么调）；TDD＝实现蓝图（白盒，这个文件内部怎么建：技术栈/内部函数/算法/单测）。签名在叶子处会重合，但 TDD 额外扛全部实现细节。

**能力契约放"父级 split"（decompose 边的上方）**：depends_on 边落在父级域 split，契约随之放父级 split → codegen 顺 depends_on 一跳取到对端公共接口。多人协作的所有权分层：**接口层（父 FSD 文件＝拆分者 owns 域契约＋依赖）／实现层（子 FSD 文件＋TDD＝开发者 owns）；decompose 边＝所有权交接线**。对外接口变更是架构决策，走父层可见受控；实现完全自治。

**codegen 契约**：为某 TDD 组装上下文 ＝ TDD 正文 ＋ 向上全链（details/decomposes 到 PRD）＋ 沿 SpecGraph depends_on 拉入对端的能力契约（对外接口）作开发依据。依赖不在正文，全靠 specgraph 一层层找。

> **`:TEST` 是验收节点**（既非 decompose 节点、也非 details 叶子）——冒号 split 结构隶属 root，不触发孤儿/追溯校验。将来（P9）从它 `details` 出 `target_file: tests/*.py` 的测试 TDD，把项目测试也纳入制品治理。

## 6. target_file 规则

- **每个 TDD 必须含 `target_file`**（缺失报 `TDD_TARGET_FILE_REQUIRED`）；写在 TDD 根 chunk 的 yaml 代码块。
- **唯一性**：不同 TDD 不得声明同一 `target_file`（重复报 `DUPLICATE_TARGET_FILE`）；比对按**归一化路径**（分隔符/`./`/大小写变体判同一制品）。
- **可指任意生成目标文件**：不限源码，测试/模板/SKILL.md/脚本等皆可。
- markdown 为准（target_file 从 TDD 正文读）。

## 7. 章节结构

各类文档的章节骨架见模板（指引性，代码不强制章节）：
- `templates/TEMPLATE-PRD-AIT-DRAFT.md`：背景/目标/范围/用户故事/验收（只写 why/what，不拆模块）。
- `templates/TEMPLATE-FSD-AIT-DRAFT.md`：功能总览/交互契约（split 段含 depends_on 声明块示例，可递归拆子 FSD）。
- `templates/TEMPLATE-TDD-AIT-DRAFT.md`：target_file/技术栈/文件职责/核心逻辑/单元测试要求（一文件一映射）。

## 8. 生命周期（四层命令面）

```
version create <v>            显式开版本（或 prd create 无活动版本时自动开——迭代入口）
prd  create / confirm / revert     PRD 层：创建讨论 → 冻结 / 成对返工（phase 阶段机）
fsd  create / decompose / confirm / revert   FSD 层：写文档(含依赖声明) → 下钻建边 → 冻结/返工
tdd  create --parent / confirm / revert      TDD 层：创建即建 details 边 → 冻结/返工
version commit <v>            全部 working chunk → committed（锁定）
version confirm <v>           纯门禁：六不变式＋制品验收（acceptance_command），可重复跑、零落盘
version merge <v>             唯一原子落盘：门禁前置 → 合入基线 → git commit；失败字节级回退
version revert <v> --confirm  任意阶段整版退出（未合入）
codegen prepare <[TDD]-id>    上下文契约：TDD 正文＋上溯全链（FSD→PRD）＋路径 depends_on 兄弟契约
```

制品验收：`acceptance set "<cmd>"` 配置后，confirm/merge 前自动跑，红（exit≠0）→ `ACCEPTANCE_FAILED` 拒于落盘前；未配置则跳过。

## 9. 版本合并语义（modify / add）

`version merge` 时按**每个 chunk 的真实存在性**逐块处理（`merge_engine.py`）：
- **modify = 整块全替换**：version 侧提供该 chunk 的**完整最终内容**（要保留的须自带），整个替换 baseline 对应 chunk。
- **add = 仅新增** baseline 不存在的 chunk；命中已存在报 `DUPLICATE_BASELINE_CHUNK`。
- modify 的目标若不在 baseline → 自动当作 add 追加；**merge 绝不静默丢 chunk**。
- 前置拦截：modify 改名撞已存在 id → `MODIFY_RENAME_COLLISION`；两记录撞同一 override 目标 → `DUPLICATE_OVERRIDES_TARGET`。

## 10. 错误码速查

| 组 | 错误码 |
|----|--------|
| 格式/解析 | `ROOT_CHUNK_REQUIRED` `INVALID_PROJECT_NAME` `INVALID_FILE_NAME` |
| 关系合法性 | `INVALID_PRD_DECOMPOSES` `INVALID_FSD_DECOMPOSES` `INVALID_DETAILS` `INVALID_DEPENDS_ON_TYPES` `DEPENDS_ON_ROOT_CHUNK` `DEPENDS_ON_CROSS_LEVEL` `FSD_MIXED_CHILDREN` |
| 依赖声明 | `DEPENDS_ON_UNKNOWN_SIBLING` `DEPENDS_ON_SELF` |
| 写时门禁 | `MISSING_ENDPOINT` `TDD_MULTI_PARENT` `PRD_FSD_LINK_NOT_UNIQUE` `DUPLICATE_TARGET_FILE` `TDD_TARGET_FILE_REQUIRED` `VERSION_NOT_FOUND` |
| 全局门禁 | `INVARIANT_VIOLATION`（明细含 `ORPHAN_CHUNK` `TRACE_BROKEN` `SPEC_CYCLE` 等）`ACCEPTANCE_FAILED` |
| 合并 | `MERGE_ROLLBACK` `GIT_COMMIT_FAILED` `MODIFY_RENAME_COLLISION` `DUPLICATE_OVERRIDES_TARGET` `DUPLICATE_BASELINE_CHUNK` `CHUNK_LOCKED` |
| CLI 契约 | `USAGE_ERROR` `NO_VERSION` `GIT_DIRTY` |

`ait specgraph validate-new-model [--version v]` 保留为只读诊断（图合法性＋唯一性）；权威强制在 confirm/merge 门禁。
