# Version Manager 参考（版本生命周期与门禁）

> 随 ait skill 分发的参考。实现在 `skill/ait/ait/version_manager.py`；命令面权威速查见 `SKILL.md`。

## 1. 三态与锁定

chunk 在版本工作区经历 `working → staged → committed`：

- **working**：可反复 create/modify（同 id 就地替换）。
- **staged → committed**：`version commit <v>` 一次性把全部 working 锁定（staged 为中间态）。committed 后本版本不可改（改则 `CHUNK_LOCKED`）。
- **uncommit（层级返工原语）**：committed/staged → working，由各层 `revert` 调用；merged 版本拒绝。

## 2. version 四件套

| 命令 | 语义 |
|------|------|
| `version create <v>` | 显式开版本（已存在报错；**P7:有活动未 merged 版本报 ACTIVE_VERSION_EXISTS**）；`prd create` 不再自动开版本（P7:须先 version create） |
| `version confirm <v>` | **纯门禁**：task 完成度＋去重/override 冲突＋**六不变式**（组合视图全量）＋**制品验收**（acceptance_command）。可重复跑、零落盘、不合入；报告 `passed` 与违例明细 |
| `version merge <v>` | **唯一原子落盘点**：内部先过同一门禁 → 备份 → 逐 chunk 合入基线 → specgraph 提升与依赖对账 → git commit。任一步失败**字节级回退**（docs 与 .meta 同步还原，`MERGE_ROLLBACK`），不残留 merged 标记 |
| `version revert <v> --confirm` | 任意阶段整版退出（物理清空，未合入版本可用） |

## 3. 层级冻结-返工对

每层 `confirm` 冻结该层 chunk（锁定＋phase 推进），`revert` 成对返工（uncommit 解锁＋phase 回退）：

```
prd confirm/revert   phase prd-creating ⇄ prd-confirm
fsd confirm/revert   phase fsd-creating ⇄ fsd-confirm
tdd confirm/revert   phase tdd-creating ⇄ tdd-confirm
```

冻结后 modify 报 `CHUNK_LOCKED`；返工后可继续修改——**每道门禁配返工路径，无终态陷阱**。

## 4. git 提交三分语义

merge 的 git 提交（`_git_commit`）：

- 非 git 仓库 / git 不可用 → 容忍，merge 结果带 `git: "unavailable"`（不伪装成功）。
- 仓库内无变更（nothing to commit）→ no-op，返回当前 HEAD。
- 仓库内提交真实失败 → `GIT_COMMIT_FAILED`，进入回滚路径。

## 5. 制品验收

`acceptance set "<cmd>"` 写入 `.meta/config.yaml`；confirm 与 merge 在落盘前自动运行该命令（项目根为 cwd），exit≠0 → `ACCEPTANCE_FAILED` 拒绝。未配置则跳过（vacuous）。`acceptance run` 手动执行回显。

## 6. 常见错误码

`CHUNK_LOCKED` `GIT_DIRTY` `MERGE_ROLLBACK` `GIT_COMMIT_FAILED` `INVARIANT_VIOLATION` `ACCEPTANCE_FAILED` `MODIFY_RENAME_COLLISION` `DUPLICATE_OVERRIDES_TARGET` `DUPLICATE_BASELINE_CHUNK` `VERSION_NOT_FOUND`——恢复指引见 `SKILL.md` Common Pitfalls。
