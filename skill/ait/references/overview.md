# AIT 设计总览（overview）

> 随 ait skill 分发的设计参考。现行形态＝**新模型主线**；v1 impl 流为 legacy。命令与格式的权威速查见 `SKILL.md` 与 `references/new-model-format.md`。

## 1. 核心矛盾

传统 Git 以"文件"为版本控制单元，而 AI 协作产生的设计文档需要更细颗粒度的**块级（chunk）管理**：需求讨论、PRD、功能分解、技术设计、代码生成需要全程**可追溯、可回滚、可上下文复用**。AIT 用 `<!-- @id -->` 标注的 chunk 作为版本控制与关联的最小单元。

## 2. 双模型定位

| 模型 | 管线 | 状态 |
|------|------|------|
| **新模型（主线）** | `prd → fsd → tdd → codegen → 制品 → 验收 → merge` | 现行，六不变式治理 |
| legacy（v1） | `prdv1 → impl → task → code` | 遗留可用，不再演进 |

新模型的三层规格树：PRD（why/what）递归分解为 FSD 功能树（how 的结构），叶 FSD 细化为 TDD（一文件一映射），`codegen prepare` 沿关系上溯组装聚焦上下文驱动 AI 编码。

## 3. 治理支柱（新模型）

- **六不变式**（写时门禁＋confirm 全局门禁双层强制）：PRD↔1FSD、TDD↔1FSD/1制品、制品↔1TDD、关联经真实 chunk、无孤儿、制品可追溯到 PRD。
- **关系只随内容创建原子出生**：depends_on 随 fsd create 的 split 内 yaml 声明、decomposes 随 fsd decompose、details 随 tdd create --parent；无任何 link/depend 命令，幽灵边从入口消灭。
- **四层命令面**：version/prd/fsd/tdd 各配 create + confirm/revert 冻结-返工对——每道门禁配返工路径，无终态陷阱。
- **版本原子性**：confirm＝纯门禁（可重复、零落盘）；merge＝唯一落盘点（失败字节级回退）；revert＝任意阶段整版退出。
- **制品验收**：配置 `acceptance_command` 后，confirm/merge 前自动跑测试，红则拒于落盘前。

## 4. 角色视角

| 角色 | 用法 |
|------|------|
| 独立开发者 | 与 AI 讨论出 PRD → 逐层分解到 TDD → codegen 驱动编码，规格与代码始终同源 |
| Tech Lead | 经 specgraph/deps/impact 追踪设计决策的实现映射与改动波及面 |
| AI（Claude 等） | 按 SKILL.md 契约调 CLI；stdout 恒为单个 JSON |

## 5. 设计边界（非目标）

- AI 编码由 Skill 层驱动；CLI 只派生上下文、记录关系与状态，不生成业务代码。
- 不提供多用户协作锁；不提供系统级全局 `ait`（一律项目本地 wrapper）。
- 不绕过 CLI 直接改 AIT 管理文档或 `.meta`。
- chunk delete 与 legacy 退役为后续能力（当前 modify/add 全覆盖，delete 挂起）。
