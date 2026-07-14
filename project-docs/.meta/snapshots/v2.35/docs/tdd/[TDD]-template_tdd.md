<!-- @id:[TDD]-template_tdd -->
## template_tdd TDD

```yaml
target_file: skill/ait/templates/TEMPLATE-TDD-AIT-DRAFT.md
```

### 技术栈

Markdown（随 ait skill 分发的格式资产）。

### 文件职责

新模型 TDD 文档模板（v2.35 定稿:TDD=文件级实现蓝图,白盒,唯一含函数签名/实现逻辑/单测的层）。结构:target_file yaml 块+技术栈与实现约束+文件职责(本文件负责/**本文件不负责〔反向要求〕**)+代码结构(签名/输入输出契约/副作用)+核心实现逻辑+错误处理与边界+单元测试要求。规约:①职责描述详实自包含,禁"参见";②"本文件不负责"即 TDD 的反向要求位,必填且具体(不改哪些文件/不做什么职责);③术语就地展开(使用处展开完整含义,不裸用);④一文件一映射(target_file 唯一,文件级粒度)。

### 单元测试要求

无单测；格式规则的强制由 new_model_validator / chunk_parser 代码侧承担，本文件是人读规范/模板。
