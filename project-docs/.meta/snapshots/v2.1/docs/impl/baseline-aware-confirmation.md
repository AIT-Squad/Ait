<!-- @id:impl-prd-chunk-atomic-impl-merge-inherit-noop -->
## impl inherit no longer appends baseline chunks during merge

<!-- @ref:prd/merge-inherit-noop#prd-prd-chunk-atomic-impl-merge rel:implements -->

### Change points

#### 1. `ImplManager.inherit()`

Change inherit registration while keeping the user-facing command stable.

- Continue to find baseline impl chunks through specgraph.
- Continue to copy each inherited baseline impl chunk into the version workspace.
- Register each inherited chunk as `action=modify`, `overrides=<impl-id>`, and `base_hash=<baseline hash>`.
- Preserve idempotency: a second inherit call skips chunks already present in the version index.
- Do not introduce `action=inherit`.

#### 2. Task and coverage behavior

Inherited impl chunks must still count as version-side impl coverage.

- `task create` should continue to see inherited impl refs in the version graph.
- `_with_atomic_impl_deletes()` should not synthesize delete records for inherited impl chunks, because they remain implemented in the version graph.
- The inherited chunk stays available for `task execute` context.

#### 3. Merge behavior

Inherited chunks must not produce duplicate baseline chunks.

- Same-id modify records replace the existing baseline chunk with equivalent content.
- If an inherited or manually edited record is mistakenly marked `action=add` while baseline already has that id, the duplicate-add guard blocks merge.

#### 4. Baseline cleanup

Remove the duplicate inherited impl chunks that v1.9 appended into `project-docs/docs/impl/skill-cli-doc-rewrite.md`, then rebuild baseline indexes.

### Boundaries

- Do not add a new schema action.
- Do not remove inherited chunks from the version workspace, because task context needs them.
- Do not change explicit impl modify behavior.

<!-- @id:impl-prd-recursive-modify-discovery-full-replacement-skill -->
## ait-discuss requires full replacement PRD modify chunks

<!-- @ref:prd/merge-inherit-noop#prd-prd-recursive-modify-discovery rel:implements -->

### Change points

#### 1. Skill workflow text

Update `skill/ait/sub-skills/ait-discuss/SKILL.md` so the PRD modify flow is explicit.

- A modify candidate is not a patch.
- After the user confirms a modify candidate, the skill must inspect the old chunk content, not only the baseline summary.
- The generated version-side PRD chunk must include all old information that remains valid plus the new information.
- The skill must not persist a modify draft that says old content is implicit, inherited, or unchanged without restating the retained content.

#### 2. Existing candidate flow stays

Keep the existing candidate persistence path.

- User-confirmed decisions still use `prd resolve-candidates`.
- Same-id modifications still become `action=modify, overrides=<same-id>`.
- New-id modifications still require explicit `overrides` from confirmed candidates.
- No change-plan artifact is introduced.

#### 3. Verification

Add or update focused tests or documentation assertions so the skill text includes:

- a full replacement requirement for modify chunks;
- an instruction to read old chunk content before generating a modify draft;
- an instruction that merge does not backfill missing old content.

### Boundaries

- Do not add semantic diff or patch support.
- Do not make CLI infer which old content should be retained.
- Do not change `prd resolve-candidates` storage format.
