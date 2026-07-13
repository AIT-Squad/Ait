<!-- @id:[TDD]-template_fsd -->
## template_fsd TDD

```yaml
target_file: skill/ait/templates/TEMPLATE-FSD-AIT-DRAFT.md
```

### 技术栈

Markdown（随 ait skill 分发的格式资产）。

### 文件职责

新模型 FSD 文档模板：功能总览/交互契约等章节；可递归拆子 FSD。**v2.31：模板正文零关系声明——不含 depends_on 块**（依赖在 fsd create 讨论时以临时 yaml 块申报、建 specgraph 边后从正文剥离，模板只含注释说明此约定，不把关系当文档内容）。

### 单元测试要求

无单测；格式规则的强制由 new_model_validator / chunk_parser 代码侧承担，本文件是人读规范/模板。
