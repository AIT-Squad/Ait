<!-- @id:[TDD]-ref_new_model_format -->
## ref_new_model_format TDD

```yaml
target_file: skill/ait/references/new-model-format.md
```

### 技术栈

Markdown（随 ait skill 分发的格式资产）。

### 文件职责

新模型格式权威规范（单一来源）：ID([PRD]/[FSD]/[TDD] 前缀、内部 split <父>:<名>)、三关系(decomposes PRD/FSD→FSD、details 叶FSD→TDD、depends_on 同父兄弟)及合法性、target_file 唯一且可指任意生成目标、章节结构、validate-new-model 校验项与错误码。

### 单元测试要求

无单测；格式规则的强制由 new_model_validator / chunk_parser 代码侧承担，本文件是人读规范/模板。
