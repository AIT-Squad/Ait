<!-- @id:impl-prd-chunk-atomic-impl-merge-confirmation-cli-skill -->
## impl baseline-aware confirmation and explicit overrides

<!-- @ref:prd/global#prd-prd-chunk-atomic-impl-merge rel:implements -->

### Change points

#### 1. `skill/ait/sub-skills/ait-impl-discuss/SKILL.md`

Revise the impl discussion workflow so it is baseline-aware:

1. Load the current PRD context with `context <prd-chunk-id> --scenario prd-to-impl`.
2. If the current PRD chunk is a version-side modify, inspect its `overrides` value from `chunks-index-{version}.yaml`.
3. Read the old PRD chunk through `context <overrides>` where possible.
4. Use specgraph to list baseline impl chunks implementing the old PRD chunk.
5. Discuss whether each old impl should be inherited, modified, or replaced by new impl chunks.
6. Before calling `impl inherit`, show the baseline impl list and require explicit user confirmation.
7. Before creating a modifying impl, show `new_id`, `overrides`, and `reason`, then require explicit user confirmation.
8. Do not introduce a change-plan artifact; confirmed decisions are executed through existing commands.

#### 2. `ait impl create --action modify --overrides <impl-id>`

Extend the impl create CLI with deterministic modify metadata:

Command form: `ait impl create <prd-chunk-id> --content-file <file> --action modify --overrides <baseline-impl-id>`.

Implementation details:

- Add `--action` with choices `add` and `modify`; default is `add`.
- Add `--overrides <impl-id>`.
- `--action add` must reject `--overrides`.
- `--action modify` must require `--overrides`.
- `overrides` must exist in baseline `chunks-index.yaml`.
- `ImplManager.create()` passes `action` and `overrides` into `VersionManager.add_chunk()`.
- For modify records, compute and store `base_hash` for the overridden baseline impl chunk so existing merge conflict detection applies.

#### 3. Tests

Add or update tests for:

- default `impl create` still writes `action: add`;
- `impl create --action modify --overrides impl-old` writes `action: modify` and `overrides: impl-old`;
- `--action modify` without `--overrides` fails with `OVERRIDES_REQUIRED`;
- `--action add --overrides impl-old` fails with `OVERRIDES_NOT_ALLOWED`;
- unknown overrides fail with `OVERRIDES_NOT_IN_BASELINE`;
- ait-impl-discuss skill text requires user confirmation before modify/inherit.

### Acceptance

- Existing impl create behavior is backward compatible when `--action` is omitted.
- Confirmed impl modify decisions can be represented directly in the version index.
- Existing `ait impl inherit <prd-chunk-id>` behavior is unchanged.
- No `action: inherit` is added to the schema.

<!-- @id:impl-prd-recursive-modify-discovery-confirmation-skill -->
## ait-discuss baseline-aware confirmation flow

<!-- @ref:prd/global#prd-prd-recursive-modify-discovery rel:implements -->

### Change points

#### 1. `skill/ait/sub-skills/ait-discuss/SKILL.md`

Update the current Phase 0 wording from "AI produces candidates and skill persists them" to a stricter discussion gate:

1. `prd create` still starts by creating the requirement/version and reading `baseline-summary --scope prd --format yaml`.
2. The baseline summary is treated as discussion context, not as an automatic write source.
3. After Clarify/Design produces the final PRD chunk split, the skill labels chunks as add or modify candidates.
4. Any modify candidate must be rendered to the user with `new_id`, `action`, `overrides`, `confidence`, and `reason`.
5. The skill must wait for explicit user confirmation before calling `prd resolve-candidates`.
6. If the user rejects a modify candidate, the skill records it as add.
7. No new change-plan file, schema, or command is introduced.

#### 2. Prompting and safeguards

- The skill must state that AI suggestions are not persisted decisions.
- `delete_candidates` remains empty unless the user explicitly asks to delete a PRD chunk.
- If baseline summary exceeds the 5 KB budget, keep the existing keyword filtering rule before giving context to the AI.
- Low-confidence modify candidates may still use `context <overrides>` for full-text inspection, but the final decision is still user-confirmed.

#### 3. Regression coverage

Add a focused test or verification script assertion that the ait-discuss skill text contains:

- a requirement to wait for user confirmation before `prd resolve-candidates`;
- the statement that no change plan concept is introduced;
- the baseline summary input step.

### Acceptance

- `skill/ait/sub-skills/ait-discuss/SKILL.md` no longer implies that AI-generated candidates may be persisted before user confirmation.
- PRD candidates still use the existing `.candidates.yaml` flow after confirmation.
- Existing `prd resolve-candidates` tests continue to pass unchanged.
