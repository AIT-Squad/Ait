# 版本文档模板

> 复制此模板到 `versions/vX.Y/` 目录下使用。

---

## 目录结构

```
versions/vX.Y/
├── prd/                    # PRD 层增量
│   ├── new-feature.md      # ADD：新增的文档，文件名任意
│   └── existing-doc.md     # MODIFY/DELETE：文件名对应 docs/prd/ 下的文件
└── impl/                   # 实现层增量
    ├── new-service.md       # ADD
    └── existing-doc.md      # MODIFY/DELETE
```

## Diff 标记语法

### ADD — 新增章节

```markdown
+++ADD:prd/new-feature#new-feat-xxx
<!-- @id:new-feat-xxx -->
### 标题
新增内容...
+++
```

- 目标路径为文档内不存在的块，合并时创建
- `@id` 使用正式 ID
- 文件名不需要与 docs/ 对应

### MODIFY — 修改章节

```markdown
+++MODIFY:impl/component-inventory#comp-mbti-chart
<!-- @id:comp-mbti-chart -->
### MBTI 图表组件
修改后的完整内容...
+++
```

- 目标路径为 docs/ 中已存在的块，合并时替换
- 文件名必须对应 docs/ 下的文件

### DELETE — 删除章节

```markdown
+++DELETE:impl/component-inventory#comp-legacy-chart
删除原因说明...
+++
```

- 目标路径为 docs/ 中已存在的块，合并时移除
- 文件名必须对应 docs/ 下的文件

## 规则

1. 一个 diff 块只针对一个 `@id` 章节块
2. diff 块之间用空行分隔
3. MODIFY 类型在 `.meta/changes/` 中需记录 `base_hash` 用于冲突检测
4. 同一版本中，同一 `@id` 不要出现多个 diff 块
