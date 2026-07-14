<!-- @id:[TDD]-template_fsd -->
## template_fsd TDD

```yaml
target_file: skill/ait/templates/TEMPLATE-FSD-AIT-DRAFT.md
```

### 技术栈

Markdown（随 ait skill 分发的格式资产）。

### 文件职责

新模型 FSD 文档模板（v2.35 定稿:FSD=结构与职责,黑盒接口层）。递归同构:root(功能描述+分解视图)+功能 split(功能描述+**反向要求**+能力契约)+恰 1 个 `:TEST` 验收 split。规约:
- **功能描述详实自包含**:完整讲清该块做什么(行为/职责/关键约束),禁"参见/详见 X"——功能描述(做什么,自然语言)、能力契约(对外接口签名)、TDD(怎么实现)三者角度不同,各自完整。
- **反向要求 section(每块必有)**:明确不实现什么、不涉及什么、不负责什么——划清边界防越界。
- **能力契约 provide-only**:提供方式+接口(方法/端点、参数名与类型、返回结构、错误语义);只写"我对外提供什么",绝不写"需要什么"(依赖只在 SpecGraph)、不写内部实现(那是 TDD)。
- **`:TEST`**:本文件所有块合并的集成验收(WHEN/THEN);功能 split 上无验收。
- **术语就地展开**:总结性用语在使用处展开完整含义(如提"六不变式门禁"须列明六条),不裸用、不设集中术语表、不指向别处。
- **正文零关系声明**:depends_on 临时申报建边后剥离;decomposes/details 随命令出生。

### 单元测试要求

无单测；格式规则的强制由 new_model_validator / chunk_parser 代码侧承担，本文件是人读规范/模板。
