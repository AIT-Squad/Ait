<!-- @id:[TDD]-template_fsd -->
## template_fsd TDD

```yaml
target_file: skill/ait/templates/TEMPLATE-FSD-AIT-DRAFT.md
```

### 技术栈

Markdown（随 ait skill 分发的格式资产）。

### 文件职责

新模型 FSD 文档模板：功能总览/功能依赖/交互契约/数据契约等章节；可递归拆子 FSD。

### 单元测试要求

无单测；格式规则的强制由 new_model_validator / chunk_parser 代码侧承担，本文件是人读规范/模板。
