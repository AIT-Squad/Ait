---
name: ait-discuss
description: INVOKE THIS SKILL when the user asks to write or discuss a product requirement document with `/ait prd <title>` (PRD authoring stage).
---

# ait-discuss

## Purpose

Drive PRD Clarify -> Design -> Generate discussion and persist the confirmed result through `project-docs/.ait/ait-cli prd` commands.

## CLI Dependencies

- `project-docs/.ait/ait-cli prd create <title>`
- `project-docs/.ait/ait-cli baseline-summary --scope prd --format yaml`
- `project-docs/.ait/ait-cli context <overrides>`
- `project-docs/.ait/ait-cli prd resolve-candidates --from-file <file>`
- `project-docs/.ait/ait-cli prd save-draft <req_id> --content-file <file>`
- `project-docs/.ait/ait-cli prd confirm <req_id> --file prd/<slug>`
- `project-docs/.ait/ait-cli prd show <prd-file> [chunk-id]`

## Artifacts

- **Reads**: user requirement, baseline PRD summaries, optional old PRD chunk context, requirement metadata, PRD draft state.
- **Writes**: only through `project-docs/.ait/ait-cli prd save-draft`, `prd resolve-candidates`, and `prd confirm`.
- **Side-effect**: version workspace gets `prd/*.md`; version index registers working chunks.

## Workflow

1. Confirm the current directory is the project root containing `project-docs/`.
2. Call `project-docs/.ait/ait-cli prd create <title>` and record `req_id` and `version`.
3. Read baseline PRD context with `project-docs/.ait/ait-cli baseline-summary --scope prd --format yaml`.
4. Treat the baseline summary as discussion context only. AI suggestions are not persisted decisions.
5. If the baseline summary exceeds 5 KB, filter by keywords from the user request across `id`, `heading`, and `summary` until the input fits the budget.
6. Clarify: ask focused questions to settle boundaries, users, acceptance criteria, and non-goals.
7. Design: propose 3-6 PRD chunks and label each as `add` or a possible `modify`.
8. For every possible `modify`, render a confirmation table with `new_id`, `action`, `overrides`, `confidence`, and `reason`.
9. For low-confidence modify candidates, call `project-docs/.ait/ait-cli context <overrides>` for full-text inspection, then re-render the confirmation table.
10. Wait for explicit user confirmation before calling `project-docs/.ait/ait-cli prd resolve-candidates --from-file <file>`.
11. If the user rejects a modify candidate, record it as `add`. If the user adjusts `overrides`, use the adjusted baseline chunk id.
12. Keep `delete_candidates` empty unless the user explicitly asks to delete a PRD chunk.
13. Do not introduce a change plan concept, file, schema, or command. Confirmed decisions still use the existing `.candidates.yaml` flow.
14. For each confirmed modify, inspect the old chunk content with `context <overrides>` before generating the final draft.
15. Generate the final Markdown draft. A modify chunk is a full replacement chunk, not a patch: it must restate all old information that remains valid plus the new information. Do not write placeholders like "old content unchanged" or only the changed paragraphs.
16. If a chunk uses an existing baseline id, CLI may register it as `action: modify, overrides: <same-id>`; if a new id modifies an old chunk, the confirmed candidates YAML must provide `overrides`.
17. Call `project-docs/.ait/ait-cli prd save-draft <req_id> --content-file <file>`.
18. Call `project-docs/.ait/ait-cli prd confirm <req_id> --file prd/<slug>`.
19. Report `req_id`, `version`, file path, chunk ids, and any confirmed modify mappings.

## Output Contract

Summarize only key CLI JSON fields: `req_id`, `version`, `file`, `chunk_ids`, and confirmed `action/overrides` decisions. If `ok=false`, repeat `error` and `code`; do not invent successful state.

## Common Pitfalls

- `ID_FORMAT`: ask the user to confirm or rewrite the chunk id.
- `CHUNK_ID_COLLISION`: do not use a baseline id as a candidate `new_id`; either keep the same id in the draft or choose a new id with confirmed `overrides`.
- `OVERRIDES_NOT_IN_BASELINE`: ask the user to choose a valid baseline PRD chunk.
- `CONFIRM_FAILED`: check that the draft is non-empty and the file path has no `.md` suffix.
- Information loss on modify: merge does not backfill old content. Regenerate the modify chunk as a complete replacement before saving the draft.
- `NOT_AT_PROJECT_ROOT`: return to the project root.
- `CWD_INSIDE_PROJECT_DOCS`: leave `project-docs/` and run from its parent.
