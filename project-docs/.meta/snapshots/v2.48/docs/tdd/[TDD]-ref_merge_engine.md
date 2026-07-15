<!-- @id:[TDD]-ref_merge_engine -->
## ref_merge_engine TDD

```yaml
target_file: skill/ait/references/merge-engine.md
```

### 技术栈

Markdown（随 ait skill 分发的参考资产）。

### 文件职责

合并引擎参考：按 baseline 真实存在性逐 chunk 处理（modify=整块全替换、add=仅新增、目标不存在当 add、绝不丢 chunk）；顶部状态注记说明入口已从 version confirm 改为 version merge（confirm 现为纯门禁）。

### 单元测试要求

无单测；本文件是人读参考，规则强制在代码侧门禁。
