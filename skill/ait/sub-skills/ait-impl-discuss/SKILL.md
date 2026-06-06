---
name: ait-impl-discuss
description: INVOKE THIS SKILL when the user asks to design implementation modules for an existing committed PRD chunk via `/ait impl <prd-chunk-id>` (implementation design stage).
---

# ait-impl-discuss

## Purpose

Assemble focused context for a committed PRD chunk, discuss baseline implementation impact with the user, and persist confirmed impl chunks through `project-docs/.ait/ait-cli impl` commands.

## CLI Dependencies

- `project-docs/.ait/ait-cli context <prd-chunk-id> --scenario prd-to-impl`
- `project-docs/.ait/ait-cli context <prd-chunk-id> --focus`
- `project-docs/.ait/ait-cli context <prd-chunk-id> --deps`
- `project-docs/.ait/ait-cli specgraph query <prd-chunk-id> --implements`
- `project-docs/.ait/ait-cli impl inherit <prd-chunk-id>`
- `project-docs/.ait/ait-cli impl create <prd-chunk-id> --content-file <file> --impl-file impl/<name>`
- `project-docs/.ait/ait-cli impl create <prd-chunk-id> --content-file <file> --action modify --overrides <baseline-impl-id>`
- `project-docs/.ait/ait-cli impl show <impl-chunk-id>`
- `project-docs/.ait/ait-cli impl commit <impl-chunk-id> -m <message>`

## Artifacts

- **Reads**: current PRD context, version chunk metadata, old PRD context when the PRD chunk is modify, baseline impl chunks from specgraph, existing impl examples.
- **Writes**: only through `project-docs/.ait/ait-cli impl inherit`, `impl create`, and `impl commit`.
- **Side-effect**: version workspace gets impl chunks with `rel:implements` references.

## Workflow

1. Call `project-docs/.ait/ait-cli context <prd-chunk-id> --scenario prd-to-impl`.
2. Inspect the active version index. If the PRD chunk is `action: modify`, record its `overrides` old PRD chunk id.
3. When `overrides` exists, call `project-docs/.ait/ait-cli context <overrides>` where possible to inspect the old PRD chunk.
4. Use specgraph to list baseline impl chunks implementing the old PRD chunk. If the PRD chunk is new, use current PRD context only.
5. Discuss whether each old impl should be inherited, modified, replaced by new impl, or left out because the PRD no longer needs it.
6. Before calling `impl inherit`, show the baseline impl chunk list to the user and wait for explicit confirmation.
7. Before creating an impl modify, show `new_id`, `overrides`, and `reason`, then wait for explicit user confirmation.
8. Do not introduce a change plan concept, file, schema, or command. Confirmed decisions are executed directly with existing commands.
9. For inherited impl, call `project-docs/.ait/ait-cli impl inherit <prd-chunk-id>` only after confirmation.
10. For new impl, call `project-docs/.ait/ait-cli impl create <prd-chunk-id> --content-file <file>`.
11. For modified impl, call `project-docs/.ait/ait-cli impl create <prd-chunk-id> --content-file <file> --action modify --overrides <baseline-impl-id>`.
12. Report generated files, chunk ids, and confirmed modify/inherit mappings.
13. If the user asks to submit, call `project-docs/.ait/ait-cli impl commit <impl-chunk-id> -m <message>`.

## Output Contract

On success, summarize `version`, `file`, `chunk_ids`, and confirmed `action/overrides` or inherited ids. On failure, repeat `error` and `code`, then give the next recovery step.

## Common Pitfalls

- `PRD_NOT_FOUND`: the target PRD chunk is not in baseline or the current version.
- `PRD_NOT_COMMITTED`: commit PRD before committing impl.
- `OVERRIDES_REQUIRED`: `--action modify` needs `--overrides <baseline-impl-id>`.
- `OVERRIDES_NOT_ALLOWED`: remove `--overrides` for add operations.
- `OVERRIDES_NOT_IN_BASELINE`: choose an existing baseline impl chunk id.
- `IMPL_NO_CHUNKS`: generated content needs `<!-- @id:impl-... -->`.
- `CHUNK_NOT_IN_VERSION`: do not bypass `impl create` by writing files directly.
