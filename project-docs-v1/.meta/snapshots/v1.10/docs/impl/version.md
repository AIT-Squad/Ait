<!-- @id:impl-version-merge-duplicate-add-guard -->
## version merge duplicate-add guard and inherited impl no-op semantics

<!-- @ref:prd/merge-inherit-noop#prd-version-merge rel:implements -->

### Change points

#### 1. Duplicate add guard

Add a merge precheck in `VersionManager` that inspects effective committed records before any docs write.

- Build the current baseline chunk id set from `IndexManager.load_baseline()`.
- For every effective record with `action == "add"`, if `record.id` already exists in baseline, raise `ValidationError` with code `DUPLICATE_BASELINE_CHUNK`.
- The error must include the duplicate chunk id and file where possible.
- Run the same guard from `confirm()` before the rollback phase starts, so `version confirm` returns `DUPLICATE_BASELINE_CHUNK` instead of wrapping it as `MERGE_ROLLBACK`.

#### 2. Inherited impl representation

Change `ImplManager.inherit()` so inherited baseline impl chunks are not recorded as `action=add`.

- Keep copying the baseline impl chunk into the version workspace so task/context assembly can read it.
- Register inherited chunks as `action=modify`, `overrides=<same impl id>`, and `base_hash=<baseline chunk hash>`.
- The chunk content is identical to baseline, so merge replaces the existing chunk with equivalent content instead of appending a duplicate.
- This preserves the existing schema and does not add `action=inherit`.

#### 3. Merge behavior

`merge_engine.merge_file()` already replaces `overrides` for `modify`; keep that behavior unchanged.

- `action=modify` plus `overrides` replaces the baseline chunk.
- `action=add` appends only when the id is truly new.
- `action=delete` removes `overrides`.

#### 4. Tests

Add focused regression tests in `tests/test_merge_workflow.py` and `tests/test_impl_inherit.py`.

- `VersionManager.merge()` rejects an `action=add` record whose id already exists in baseline.
- `VersionManager.confirm()` surfaces the same error code before docs mutation.
- `ImplManager.inherit()` records inherited chunks as same-id modify records.
- Inheriting baseline impl chunks and confirming the version leaves only one copy of each inherited chunk in baseline.

### Boundaries

- Do not add `action=inherit` to schemas.
- Do not change `merge_engine.merge_file()` replacement semantics.
- Do not make merge perform semantic or partial-content patching.
