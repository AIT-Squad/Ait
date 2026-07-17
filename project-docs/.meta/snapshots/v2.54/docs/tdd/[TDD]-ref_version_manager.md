<!-- @id:[TDD]-ref_version_manager -->
## ref_version_manager TDD

```yaml
target_file: skill/ait/references/version-manager.md
```

### 技术栈

Markdown（随 ait skill 分发的参考资产）。

### 文件职责

版本管理参考（v2.30 重写对齐）：三态 working→staged→committed 与 commit 锁定;**version 四件套**——create 显式开版本/confirm 纯门禁（六不变式+制品验收,可重复零落盘）/merge 唯一原子落盘（字节级回退,git 三分语义）/revert 整版退出;层级冻结-返工对（prd/fsd/tdd confirm+revert,uncommit 原语）;错误码。

### 单元测试要求

无单测；本文件是人读参考，规则强制在代码侧门禁。
