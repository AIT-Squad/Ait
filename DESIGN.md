# AIT 设计文档

> 本文说明 AIT **为什么这样设计**。操作方法见 [USER_GUIDE.md](USER_GUIDE.md)；
> 文档格式的权威规范见
> [skill/ait/references/new-model-format.md](skill/ait/references/new-model-format.md)；
> Skill 的命令契约见 [skill/ait/SKILL.md](skill/ait/SKILL.md)。

## 目录

1. [定位与核心矛盾](#1-定位与核心矛盾)
2. [设计原则](#2-设计原则)
3. [解决的五个问题](#3-解决的五个问题)
4. [核心架构](#4-核心架构)
5. [治理支柱](#5-治理支柱)
6. [关键技术决策](#6-关键技术决策)
7. [模块地图](#7-模块地图)
8. [演进史](#8-演进史)
9. [设计边界（非目标）](#9-设计边界非目标)

---

## 1. 定位与核心矛盾

**AIT = 为"AI 驱动编码"服务的规格版本控制系统。**

Git 以**文件**为版本控制单元，以**行**为 diff 单元。这对代码够用，对驱动 AI 编码的设计文档
不够用：

- AI 需要的是**语义完整的片段**，不是文件片段
- 文档之间的**派生关系**（这段实现哪个需求）是 AI 最需要的信息，却完全不在 Git 的视野里
- 一次需求变更会波及 PRD、功能设计、技术设计、代码四层，Git 只能看到"几个文件改了"

AIT 的答案：以 `<!-- @id:xxx -->` 标注的 **chunk** 为版本控制与关联的最小单元，
把 chunk 之间的关系提取成一张显式的 **SpecGraph**，并用不变式强制这张图的完整性。

### 主线模型

```
[PRD]-app ──derives──▶ [FSD]-app          问题域 → 方案域
                          │
              [FSD]-app:core ──decomposes──▶ [FSD]-core   递归功能树
                          │
                          └──details──▶ [TDD]-parser       叶子 → 实现蓝图
                                             │
                                        target_file: src/parser.py
```

- **PRD**：why / what。用户视角，零技术内容
- **FSD**：功能分解的结构 + 对外能力契约（黑盒接口）
- **TDD**：单文件实现蓝图（白盒）。每个 TDD 唯一映射一个 `target_file`
- **codegen**：沿 SpecGraph 上溯组装聚焦上下文，驱动 AI 编码

旧模型 `prdv1 → impl → task` 为 legacy：仍可运行，不再演进。

---

## 2. 设计原则

### 2.1 关系是一等公民，且只有显式边

文档正文**不承载任何 chunk 间关系**。四种关系只作为 SpecGraph 边存在，且每种关系**只有一个
出生地**——随内容创建原子出生：

| 关系 | 出生地 |
|---|---|
| `derives` | `fsd create --parent <PRD根>` |
| `decomposes` | `fsd decompose <parent> <child>` |
| `details` | `tdd create --parent <split>` |
| `depends_on` | `fsd create` 内容里的 `depends_on:` yaml 块（建边后剥离） |

**为什么没有 `link` 命令**：任何独立建边的入口都能绕过"端点必须真实存在"的检查，产生幽灵边。
把建边绑定到内容创建，幽灵边在入口就不可能出现。v2.50 因此退役了 `specgraph add-edge`。

**为什么关系不从命名推断**：命名约定是脆弱的隐式契约，重命名即断链，且无法表达"这条边是谁在
什么时候有意建立的"。

### 2.2 门禁双层，拒绝即零落盘

- **写时门禁**拦"永远不该合法存在"的增量：幽灵端点、TDD 第二个父、PRD 第二个 FSD、
  制品路径撞车。这些不需要全局视野就能判定
- **全局门禁**（confirm/merge）在 `baseline ∪ version` 组合视图上查孤儿、断链、环——
  这些必须有全局视野

两层都遵守**拒绝＝零落盘**：失败不留半成品，原地修正即可重试。这是"可重试"的前提。

### 2.3 门禁与落盘分离

`confirm` 只校验、只产计划，可重复跑；`merge` 只执行已确认的计划。

**为什么分开**：把"判断能不能合"和"执行合并"耦在一起，就无法在合之前反复检查，也无法保证
"检查通过的那个状态"就是"实际合并的那个状态"。计划带输入指纹，输入变了 merge 报
`CONFIRMATION_STALE`，强制重新 confirm。

**边界澄清（v2.72–v2.73）**：confirm 的"零写入"指**不写文档内容、不动 baseline**。它仍会
持久化合并计划到版本 meta，并在宿主仓有未提交制品时主动提交宿主仓、绑定 `code_result`
（与 merged 版本的双仓回滚互为对称——提交侧与回滚侧都是 AIT 自建，不要求用户手工 git）。

### 2.4 每道门禁都配返工路径

`prd/fsd/tdd` 三层各有 `confirm` / `revert` 对，版本级有 `version revert`。

**为什么**：单向门禁会造成终态陷阱——用户冻结了某层后发现要改，如果没有解锁路径，
唯一出路就是废掉整个版本。这会让人倾向于"不敢 confirm"，门禁反而形同虚设。

### 2.5 版本原子性

一个版本是一次完整的"规格变更 + 实现"事务：

- 一次只有一个开放版本（`ACTIVE_VERSION_EXISTS`）
- `merge` 是唯一落盘点，失败字节级回退
- 不提供局部撤销；不满意就整版 `revert`

**为什么不做局部撤销**：局部撤销需要维护 chunk 级的反向依赖与失效传播（改了 PRD，
下游 FSD/TDD 是否还有效？），这套机制的复杂度远超它带来的便利。v1.4 明确取消了局部回滚、
单 chunk 放弃、checksum 失效检测、增量版本继承等子系统，换成"版本是原子的"这一条简单规则。

### 2.6 严格自顶向下

phase 状态机强制 `prd → fsd → tdd` 顺序，`add` 与 `modify` 门禁完全相同。

**为什么 modify 也要从头走**：如果允许直接改 TDD，就会出现"代码改了但需求文档没动"的漂移——
这恰恰是 AIT 要消灭的问题。迭代的正确形态是"从 PRD 开始，沿既有关系逐层向下改"。

### 2.7 fail closed

依赖配置的门禁在"读不到配置"时必须失败，不能当成"没配置"而放行。
`config_store` 因此在配置层损坏时抛 `CONFIG_UNREADABLE`，而不是降级成 `{}`。

---

## 3. 解决的五个问题

### 3.1 行级 diff 捕获不到意图

Git diff 告诉你"第 42 行改了"，但没告诉你"推荐算法的业务规则从按评分改成了按借阅频率"。

AIT 以 chunk 为变更单位，`.meta/changes/chg-NNN.yaml` 记录每个 chunk 的操作类型与完整内容。
变更历史读起来是"哪个语义单元怎么变了"。

### 3.2 跨文件关系对 AI 不可见

一份 PRD 对应哪些功能设计？某个技术设计实现了哪条需求？改了这个接口会影响谁？
在纯 markdown 世界里，这些信息散落在人的脑子里。

AIT 把关系提取成 SpecGraph 显式边，`deps` / `impact` / `specgraph query` 可查询，
`graph-html` 可视化成文件级规格树。

### 3.3 AI 需要的是结构化上下文，不是原始文件

把整个 `docs/` 塞给 AI：token 爆炸、信噪比低。只给目标文件：AI 不知道上游约束和依赖契约。

`codegen prepare` 沿 SpecGraph 组装**聚焦 bundle**：TDD 正文 + 上溯到 PRD 的全链 +
`depends_on` 兄弟的能力契约 + `target_file` 当前内容。刚好够写这个文件，不多不少。

这也解释了能力契约为什么放在**父级 split**（decompose 边的上方）：`depends_on` 边落在父级域
split，契约随之放父级，codegen 顺依赖边一跳就能取到对端的公共接口。

### 3.4 AI 协作产生的文档变更难以版本化

AI 一轮对话可能改动五个文档的十几个片段。逐文件 review 成本高，且难以判断"这批改动是不是一致的"。

AIT 用版本工作区（`versions/vX.Y/`）隔离在制品，三态锁定（working → staged → committed）
控制冻结节奏，六不变式在合入前保证这批改动的结构一致性。

### 3.5 文档版本与代码版本脱节

文档仓和代码仓各自演进，几个月后没人知道哪版文档对应哪版代码。

AIT 让 `project-docs/` 成为**独立 git 仓库**（被宿主仓 ignore），并在 `version merge` 时记录
跨仓绑定：

| 字段 | 含义 |
|---|---|
| `docs_commit` | 本次 merge 在 docs 仓产生的提交 |
| `code_base` | merge 时宿主仓 HEAD（只读快照） |
| `code_result` | 验收完成后的宿主仓 HEAD |
| `revert_anchor` | 持久 tag `refs/tags/ait/<v>`，指向绑定提交 |

`version revert` 据此把 docs 仓与宿主仓**同步回滚**到某个已合入版本的状态。

**为什么用 tag 而不是 SHA**：绑定信息本身写在版本 meta 里，而 meta 又会被提交——
直接存 SHA 会陷入自引用（记录的 SHA 是记录之前的提交，不含记录本身）。tag 指向"记录绑定"
那个提交，避免了这个陷阱。

---

## 4. 核心架构

### 4.1 项目布局

```
<project-root>/                     # 所有命令从这里运行
├── .gitignore                      # init 追加 project-docs/
├── src/ ...                        # 你的代码（宿主仓）
└── project-docs/                   # 名字硬编；独立 git 仓库
    ├── .git/
    ├── .gitignore                  # versions/*/state.md, .meta/snapshots/, .ait/
    ├── docs/                       # baseline：merge 的落盘目标
    │   ├── prd/[PRD]-<name>.md
    │   ├── fsd/[FSD]-<name>.md
    │   └── tdd/[TDD]-<name>.md
    ├── versions/vX.Y/              # 版本工作区（在制品）
    │   ├── prd/ fsd/ tdd/
    │   └── state.md                # 状态面板（不入 git）
    ├── .ait/ait-cli                # 项目本地 wrapper（生成，不入 git）
    └── .meta/
        ├── chunks-index.yaml           # chunk 状态（baseline）
        ├── chunks-index-vX.Y.yaml      # chunk 状态（每版本一份）
        ├── specgraph.yaml              # chunk 关系（baseline）
        ├── specgraph-vX.Y.yaml         # chunk 关系（每版本一份）
        ├── versions/vX.Y.yaml          # phase、计划、git 绑定
        ├── changes/chg-NNN.yaml        # chunk 级变更记录
        ├── config.yaml                 # 共享配置（入 git）
        └── config.local.yaml           # 机器本地配置（不入 git）
```

**为什么工作根硬编为 `<CWD>/project-docs/`**：v1.1 的决策。可配置的根路径带来
"同一命令在不同环境指向不同目录"的不确定性，而 AIT 的所有操作都是破坏性写入。
硬编 + 快速失败（三个明确错误码）比灵活更重要。因此没有 `--project`、没有 `AIT_ROOT`、
不向上递归找 marker 文件。

### 4.2 两套索引，各管一摊

| 索引 | 管什么 | 关键字段 |
|---|---|---|
| `chunks-index*.yaml` | **块自身状态** | `id`、`file`、`heading`、`summary`、`state`、`action`、`hash` |
| `specgraph*.yaml` | **块之间关系** | `specs`（节点）、`edges`（src/dst/rel/metadata） |

都按 baseline + per-version 分文件。查询时 `combined_view` 把 `baseline ∪ version`
折叠到 chunk_id 身份空间——这样在制品 chunk 与基线 chunk 在同一视图里可比较、可遍历。

`links-index.yaml` 已废弃（v1.3 起关系统一走 SpecGraph）。

**为什么分文件而不是一个大索引**：版本工作区必须能独立清空（`version revert`）。
如果所有版本的记录混在一个文件里，清空某版本就要做行级手术；分文件则是删一个文件。

### 4.3 chunk 生命周期

```
create/modify ──▶ working ──version commit──▶ staged ──▶ committed ──version merge──▶ baseline
                     ▲                                        │
                     └────────── 层级 revert（uncommit）───────┘
```

`working` 可反复覆写（同 id 就地替换）；`committed` 在本版本内冻结（改则 `CHUNK_LOCKED`）；
merged 版本拒绝 uncommit。

### 4.4 命令分层

```
init                    项目接入：骨架 + docs 仓 + 根 chunk + derives 边 + wrapper
  │
version create          开版本（一次只一个）
  │
prd    create/confirm/revert       ┐
fsd    create/decompose/confirm/revert  ├ 三层规格：讨论 → 写入 → 冻结
tdd    create/confirm/revert       ┘
  │
codegen prepare         组装聚焦上下文（不写代码）
acceptance set/run      配置并执行制品验收
  │
version commit          working → committed
version confirm         纯门禁 + 生成合并计划
version merge           唯一原子落盘
version revert          任意阶段退出
  │
state/search/deps/impact/context/specgraph/lint/reindex    只读查询与诊断
```

### 4.5 讨论背景与上下文令牌

**关联关系的目的论**：完整性（六不变式）→ 可靠检索（关系＝现状的检索路径）→
修改连续性（现状 + 修改方向 → 新 chunk）。

每层 `create` 省略内容即返回该层**讨论背景**（`mode=discussion-context`，零写入、
受同层 phase 门禁）：

| 调用 | 形态 | 背景内容 |
|---|---|---|
| `prd create <id>` | 现状 | baseline ∪ 版本的全部 PRD chunk 全文 + 目标既有内容 |
| `fsd create <id>` | 发现式 | 锚点＝本版本改动的 `[PRD]-` chunk 全文 + 每锚一跳关联 |
| `fsd decompose <p> <c>`（c 未建） | 锚定式 | 父块全文 + 全部邻接（含 rel/方向）+ 上溯链到 PRD |
| `tdd create <id> --parent <s>` | 锚定式 | 同上（锚＝叶 split） |

有正文的写入必须携带同一意图的 `context_token`。令牌绑定层级、目标、父锚点、最终 file、
操作、action、overrides 与**实际背景内容**的摘要；背景或意图变化后旧令牌失效。

**为什么要令牌**：讨论背景是零成本的（不写盘），如果不强制，AI 很容易跳过讨论直接写入，
产生与现状脱节的 chunk。令牌把"讨论过"变成可验证的前置条件。它**只证明上下文连续性**，
不代表身份认证、授权或所有权。`--skip-context` 是明确的退出通道，留最小审计痕迹。

### 4.6 Skill 分层

```
skill/ait/
├── SKILL.md              router：全局契约 + 命令速查 + pitfalls + sub-skill 索引
├── bin/ait, ait.cmd      自举 wrapper（首次运行自建 .venv）
├── ait/                  Python 实现（CLI + 领域模块）
├── references/           7 篇参考文档（随 skill 分发）
├── templates/            PRD/FSD/TDD 模板骨架 + YAML 模板
├── sub-skills/           6 个 sub-skill
└── scripts/              验证脚本（术语泄漏、回归、wrapper 自定位、触发词）
```

**为什么拆 sub-skill**：v1.2 的决策。单体 SKILL.md 随功能增长膨胀到难以维护，且每次调用都要
加载全部内容。按"用户所处阶段"拆分后，主 skill 只做路由，具体流程按需加载。
子 skill 不引入新 CLI、不直接读写 `docs/` 与 `.meta/`。

---

## 5. 治理支柱

### 5.1 六不变式

| # | 不变式 | 违例码 | 保证了什么 |
|---|---|---|---|
| 1 | 每个 PRD 根恰关联 1 个 FSD | `PRD_FSD_LINK_NOT_UNIQUE` | 问题域到方案域的映射唯一 |
| 2 | 每个 TDD 向上恰 1 个 FSD、向下恰 1 个制品 | `TDD_MULTI_PARENT` / `TDD_TARGET_FILE_REQUIRED` | 实现蓝图归属明确 |
| 3 | 每个制品路径只由 1 个 TDD 持有 | `DUPLICATE_TARGET_FILE` | 两个 AI 任务不会抢同一文件 |
| 4 | 所有关联经真实存在的 chunk | `MISSING_ENDPOINT` | 无幽灵边 |
| 5 | 除规格树根外无孤儿 chunk | `ORPHAN_CHUNK` | 没有写了却没人用的规格 |
| 6 | 任一制品沿 TDD→FSD→…→PRD 可追溯 | `TRACE_BROKEN` / `SPEC_CYCLE` | 每行代码都有需求出处 |

不变式 ① 只约束 PRD **根** chunk；PRD 的需求 split 不受此限（v2.47 修正——PRD chunk 化后
每个需求 split 显然不该各自对应一个 FSD）。

`:TEST` 是验收节点（既非分解节点也非 details 叶子），结构上隶属 root，
不触发孤儿/追溯校验。

**环检测的边界**：`SPEC_CYCLE` 只覆盖树关系（derives/decomposes/details）与 id 结构通道
（root→split）。**`depends_on` 环不设门禁**——横向域依赖天然允许双向（本项目基线就有
version↔task↔indexing 环，来自真实 import），且没有删边命令，硬门禁会成终态陷阱；
它们仍可通过 `detect_cycle` 诊断。

### 5.2 FSD 三类分化与所有权分层

每个 FSD 文件递归同构 = root + N 个功能 split + 恰 1 个 `:TEST`：

- **root**：功能域职责边界 + 分解视图（列子块结构，不列签名）
- **功能 split**：功能描述 + 能力契约（**provide-only**）
- **`:TEST`**：本文件所有块合并的集成验收。功能 split 上不写验收标准

**能力契约只写"对外提供什么"**——提供方式、接口签名、错误语义。绝不写"需要什么"
（那是 `depends_on`，只在 SpecGraph）、绝不写内部实现（那是 TDD）。

由此得到多人协作的**所有权分层**：

```
接口层（父 FSD 文件）    拆分者 owns：域契约 + 依赖关系
        │
   decomposes 边 ＝ 所有权交接线
        │
实现层（子 FSD + TDD）   开发者 owns：内部结构与实现
```

对外接口变更是架构决策，走父层可见受控；实现细节完全自治。

### 5.3 depends_on 的 owned-scope 对账

同父约束意味着所有合法依赖边都是"本文件内的兄弟边"——**文件＝依赖边的所有权边界**。

`fsd create` 后按申报对账，但采用 **preserve 语义**（v2.32）：**没有 `depends_on` 块的 split
保留其现有边**。改依赖＝带块 modify（该 split 权威覆盖），清空＝显式 `depends_on: []`，
不动＝不带块。

**为什么是 preserve 而不是 wipe**：v2.31 把 depends_on 块从正文剥离后，如果对账采用
"没申报就清空"，那么任何一次不带块的正文重排都会静默删掉全部依赖边——这是个致命的脚枪。

### 5.4 三条通用书写规约

1. **详实自包含**：每块完整讲清自己，禁"参见/详见 X"式引用甩锅。功能描述（做什么）、
   能力契约（对外接口）、TDD（怎么实现）角度不同，各自完整
2. **反向要求必填**：每块明确"不实现什么/不负责什么（及归属）"
3. **术语就地展开**：总结性用语在使用处展开完整含义，不裸用名词、不设集中术语表

**为什么强制这三条**：codegen 组装的 bundle 是 chunk 的拼接。如果 chunk 之间靠"参见"互相
指向，bundle 就会出现信息空洞；如果只写"做什么"不写"不做什么"，AI 会自行发挥、越界实现。

### 5.5 制品验收

`acceptance set "<cmd>"` 配置后，`confirm` 与 `merge` 在落盘前自动执行该命令（cwd = 项目根），
exit ≠ 0 → `ACCEPTANCE_FAILED`，拒于落盘前。未配置则跳过（真空通过）。

**为什么存在机器本地配置层**：这个值**会被执行**，且路径因机器而异。让它随共享历史传播
既不可移植也是安全隐患（拉取他人配置即执行他人命令）。

### 5.6 受治理制品范围（v2.83–v2.85）

六不变式保证"规格图结构合法"，但不保证"某类制品都被规格覆盖"。`config.yaml` 的
`artifact_scopes` 把一类制品（如测试文件）纳入治理：

| 校验 | 含义 | 默认 |
|---|---|---|
| `TEST_SPLIT_UNCOVERED` | 范围内 `:TEST` split 没有任何 details 子（验收空转） | 可配 |
| `UNCOVERED_ARTIFACT` | 范围内存在没有 TDD 属主的制品文件 | 可配 |
| `TARGET_FILE_SCOPE_ESCAPE` | TDD 的 target_file 逃逸出治理范围 | 可配 |

每条按范围配 `warn`（报告不阻断）或 `block`（confirm 拒绝）；`exempt_test_splits` /
`exempt_paths`（v2.85）提供显式豁免。**未配置 `artifact_scopes` 时全部真空通过**——
存量项目行为不变。

### 5.7 合并语义

`version merge` 按每个 chunk 的**真实存在性**逐块处理：

- **modify = 整块全替换**：版本侧提供完整最终内容（要保留的自带）
- **add = 仅新增** baseline 不存在的 chunk；命中已存在报 `DUPLICATE_BASELINE_CHUNK`
- modify 目标不在 baseline → 自动当 add 追加。**merge 绝不静默丢 chunk**

**为什么 modify 是全替换而不是增量 patch**：增量 patch 需要三方合并与冲突解决，而 chunk 是
语义单元——"这个 chunk 的最终形态"本身就是 AI 讨论的产物，全替换语义更简单也更可预测。

---

## 6. 关键技术决策

### 6.1 为什么用 `<!-- @id:xxx -->` 而不是 YAML frontmatter

- frontmatter 只能标注**整个文件**，无法标注文件内的多个片段
- HTML 注释在所有 markdown 渲染器里都不可见，文档保持人类可读
- 注释形式对 AI 极友好：生成/解析都不需要额外语法层

### 6.2 为什么 chunk 边界不依赖标题层级

如果按标题层级切分，`## 父功能` 下的 `### 子功能 A`、`### 子功能 B` 会被迫成为独立 chunk 或
被迫合并——由排版决定语义边界。

AIT 的规则：**chunk 边界 = 从一个 `@id` 注释到下一个 `@id` 注释**。作者显式决定语义边界，
标题层级纯排版。解析时代码围栏（```）内的内容被屏蔽，不会把示例里的注释误认成 chunk 标记。

### 6.3 为什么讨论与写入分成两次调用

一次调用里既讨论又写入，意味着 AI 必须在同一轮里完成"理解现状 → 与用户收敛 → 产出内容"。
拆成两次后：第一次调用返回背景（零写入，可反复取），AI 与用户在这个背景上充分讨论，
收敛后第二次调用写入。令牌保证第二次写入确实基于第一次的背景。

### 6.4 为什么索引写入用 temp → rename

索引是所有查询的入口。写入中途崩溃留下截断的 YAML 会让整个项目不可用。
`atomic_write_text` 先写临时文件再 rename——POSIX 保证 rename 原子性，
读者要么看到旧版本要么看到新版本，绝不会看到半个文件。

### 6.5 为什么 stdout 只输出一个 JSON

CLI 的唯一消费者是 AI Agent。多行输出、混合日志、进度条都会让解析变脆。
契约是：stdout 恒为单个 JSON 对象，提示与警告一律走 stderr。
连 `click` 的参数错误也被包装成 `{"ok": false, "code": "USAGE_ERROR"}`（v2.27）。

### 6.6 为什么 `project-docs/` 是独立 git 仓库

方案 A（文档与代码同仓）：AIT 的每次 confirm/merge 都会往你的代码历史里插提交，
且版本生命周期中 docs 目录长期"脏"，与代码提交流程互相干扰。

方案 B（独立仓，v2.55 采用）：AIT 提交完全隔离；confirm 因此可以取消 docs 侧的 `GIT_DIRTY`
预检（docs 仓在版本生命周期中本就应该是脏的），改为检查**宿主仓**干净（`HOST_DIRTY`）——
确保代码侧的状态是可绑定的。

### 6.7 为什么 merge 不再默认打快照

`auto_snapshot_on_merge` 在 v2.71 改为默认 `false`。原因：快照树写了却**没有任何读者**——
回滚依赖 `docs_commit` 与持久 tag，不依赖这些拷贝。默认打开只是在 docs 仓里堆积无用文件。
显式设为 `true` 的项目不受影响。

---

## 7. 模块地图

`skill/ait/ait/` 下约 13.7k 行 Python。依赖方向自底向上，无环。

| 层 | 模块 | 职责 |
|---|---|---|
| 基础 | `root.py` | 工作根解析（硬编 `project-docs/`，三个错误码） |
| | `io_utils.py` | `atomic_write_text` 等原子写 |
| | `yaml_io.py` | YAML 安全读写（只用 `safe_load`） |
| | `hash_utils.py` | 内容哈希 |
| | `config_store.py` | 分层配置（共享/机器本地，fail closed） |
| 文档模型 | `chunk_parser.py` | chunk 解析（`@id`/`@ref`/`@extract`，代码围栏屏蔽） |
| | `schemas.py` | 全部 pydantic 模型（`extra="forbid"`） |
| | `format_validator.py` / `validator.py` | 格式校验 |
| 索引 | `index_manager.py` | chunks-index 构建/加载/保存 |
| | `specgraph.py` | SpecGraph 模型、`combined_view`、`sync_specgraph` |
| | `migrations.py` | 一次性数据迁移 |
| 新模型 | `new_model_manager.py` | 三层 create/confirm/revert、讨论背景、令牌、codegen |
| | `new_model_validator.py` | 六不变式、图合法性与治理范围校验 |
| 版本 | `version_manager.py` | 三态、phase 机、gate、计划、merge、revert、验收 |
| | `merge_engine.py` | 逐 chunk 按存在性合并 |
| 查询 | `deps.py` / `impact.py` / `search.py` / `context_assembler.py` / `state.py` / `graph_md.py` | 关系查询、影响分析、检索、上下文、面板、图可视化 |
| 交付 | `codegen_brief.py` | codegen bundle 的渲染（交付文本形态） |
| 接入 | `init_manager.py` | 骨架、docs 仓、根 chunk、wrapper、治理迁移 |
| 入口 | `cli.py` | click 命令面、JSON 输出契约 |
| 发布 | `publisher.py` | `ait push` 双仓发布（先宿主后 docs） |
| legacy | `prd_manager.py` / `impl_manager.py` / `task_manager.py` | 旧模型三态流水线（冻结） |

测试：`tests/` 下 434 个用例通过（1 skipped；另有 2 个 `dual_repo_publish` 用例依赖
git 默认分支环境——bare 仓 HEAD 指向 master 而推送分支为 main 时失败，非代码 bug）。

---

## 8. 演进史

主要里程碑（完整记录见 [CHANGELOG.md](CHANGELOG.md)）：

| 阶段 | 版本 | 主题 |
|---|---|---|
| MVP | v1.0–v1.1 | chunk 级版本控制；工作根锁定为 `<CWD>/project-docs/` |
| 体系化 | v1.2–v1.6 | block→chunk 术语统一；SpecGraph 取代 links-index；sub-skill 拆分；`prd→impl→task` 三态流水线 |
| 新模型立骨 | v2.0–v2.21 | PRD/FSD/TDD 三层落地；`prd` 归新模型（旧改名 `prdv1`）；六不变式强制；version 四件套 |
| 命令面成型 | v2.22–v2.30 | 三层 create/confirm/revert 对齐；制品验收门禁；合并与 JSON 契约加固 |
| 格式收敛 | v2.31–v2.45 | 正文零关系声明；FSD 三类分化与能力契约；三条书写规约；全域文档迁移 |
| 治理收口 | v2.46–v2.54 | 不变式修正；退役 `add-edge`；P7 严格自顶向下；`derives` 独立成关系；讨论背景；空目录起步 |
| 跨仓与可视化 | v2.55–v2.63 | docs/代码 git 隔离；跨仓绑定与同步回滚；SpecGraph HTML 规格树 |
| 一致性加固 | v2.64–v2.71 | docs 仓治理；关系出生边界收口；上下文令牌；同文件覆盖保留；codegen 上下文收紧；配置分层 |
| 交付与治理深化 | v2.72–v2.87 | 回滚锚点韧性（SHA 权威）；confirm 制品绑定；codegen 临时文件交付与子 agent 编排；PRD 写作契约与演进纪律；`push` 双仓发布；artifact_scopes 治理；`--content` 写时拦截 |

AIT 从 v2.0 起**完全由自身开发**：每个版本都走完整的
`version create → prd → fsd → tdd → codegen → confirm → merge` 闭环。
`project-docs/` 是权威设计源（1 个 PRD 文件、17 个 FSD 文件、97 个 TDD 文件）；
`project-docs-v1/` 是归档的 legacy 基线。

---

## 9. 设计边界（非目标）

- **CLI 不生成业务代码**。它派生上下文、记录关系与状态；编码由 Skill 层驱动 AI 完成
- **不提供多用户协作锁**。单写者模型；所有权分层靠 FSD 的 decompose 边界表达，不靠运行时锁
- **不提供系统级全局 `ait`**。一律项目本地 wrapper，避免"哪个 ait"的歧义
- **不支持 `/ait:foo` 冒号命名空间**（Claude Code 保留给插件系统），只支持 `/ait foo`
- **不绕过 CLI 直接改被管文档或 `.meta`**
- **不做 chunk delete**。当前 `add`/`modify` 全覆盖，delete 挂起
- **不做局部撤销/单 chunk 放弃/checksum 失效传播**（v1.4 明确取消，被版本原子性取代）
- **legacy 流水线不再演进**，仅保持可运行
