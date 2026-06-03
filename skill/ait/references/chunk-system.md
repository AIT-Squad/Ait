# Chunk 体系

<!-- @id:prd-chunk-format -->
## Chunk 标注格式

每个 Chunk 以 HTML 注释形式标注：

```markdown
<!-- @id:prd-book-entry -->
## 图书录入
...块内容...
```

标注规则：

1. 标注是独立一行，前后用空行分隔
2. `@id:` 后紧跟 Chunk ID，无空格
3. 标注行**属于 Chunk 内容的一部分**（不被排除），合并时保留
4. 一个标注只标识一个 Chunk，不允许嵌套

<!-- @id:prd-chunk-parse-rule -->
## 解析规则

Chunk 的边界由 `@id` 标注界定，不依赖标题层级：

| 规则 | 说明 |
|------|------|
| 起始 | `<!-- @id:xxx -->` 标注行 |
| 结束 | 下一个 `<!-- @id:yyy -->` 标注前一行，或文件末尾 |
| 内容 | 起始行至结束行的全部内容（含标注、标题、正文、代码块） |
| 文件头 | 第一个 `@id` 之前的内容归入"文件头"，合并时保留 |

详细解析算法见 [impl/chunk-parser.md](../impl/chunk-parser.md)。

<!-- @id:prd-chunk-id-naming -->
## ID 命名规范

格式：`{type}-{domain}-{name}`

| 段 | 取值 | 示例 |
|----|------|------|
| type | `prd` / `impl` | `prd` |
| domain | 子域名（小写短横线） | `chunk` / `version` / `workflow` |
| name | 语义化短名（小写短横线） | `format` / `lifecycle` |

完整示例：`prd-chunk-format`、`impl-version-manager-commit`。

约束：

1. ID 全局唯一（基线索引中不允许重复）
2. 同一版本索引中可有同 ID 多条记录（修订场景）
3. ID 一经 committed 不可重命名（已有 `@ref` 会失效）
4. ID 中只允许小写字母、数字、短横线

<!-- @id:prd-chunk-relations -->
## Chunk 关联（@ref）

跨 Chunk 引用通过专用注释建立：

```markdown
<!-- @ref:prd/book-management#prd-book-entry rel:implements -->
```

字段说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| target | `{file}#{chunk-id}` | `prd/book-management#prd-book-entry` |
| rel | 关系类型 | `implements` |
| file | 相对于 `docs/` 的路径，无扩展名 | `prd/book-management` |

`@ref` 标注可放在两处：

1. 块内部任意位置（作为块内容的一部分）
2. 块的末尾（紧邻下一块前）

合并/解析时，`@ref` 与所在 Chunk 关联，写入 `links-index.yaml`。

<!-- @id:prd-chunk-relation-types -->
## 关系类型

内置 3 种：

| 关系 | 方向 | 语义 |
|------|------|------|
| `implements` | impl → prd | impl 块实现某个 PRD 块（最常见） |
| `modifies` | impl → impl | impl 块修改/取代已有 impl 块 |
| `see-also` | 任意 → 任意 | 补充参考（无强依赖） |

项目可在 `.meta/config.yaml` 的 `custom_relations` 中扩展。本项目扩展了：

| 关系 | 用途 |
|------|------|
| `refines` | impl 子块细化父块（如 algorithm refines api） |
| `depends-on` | impl 模块间依赖（如 version-manager depends-on index-manager） |

<!-- @id:prd-chunk-validation -->
## 块校验规则

所有 Chunk 必须满足（违反触发 E1 阻断，详见 [validation](validation.md)）：

1. ID 符合命名规范
2. ID 在基线索引中唯一
3. Chunk 内容非空（至少含标题）
4. `@ref` 的 target 必须可解析（E2 警告，不阻断）
5. `@ref` 的 rel 必须是内置或 `custom_relations` 中已声明的类型
