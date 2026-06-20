<!-- @id:impl-cli-file-option-names-normalization -->
## CLI file option normalization

<!-- @ref:prd/cli-file-options#prd-cli-file-option-names rel:implements -->

### Change points

#### 1. CLI boundary helper

Add a small CLI helper that accepts an optional file-name option and returns a canonical scoped file key.

- `None` remains `None`, preserving existing manager defaults.
- A valid value is mapped to `<scope>/<name>`, where scope is `prd` or `impl`.
- Invalid values call the existing JSON `fail()` path with code `INVALID_FILE_NAME`.
- Invalid values include empty strings, `.`, `..`, path separators, drive separators, and `.md` suffixes.

#### 2. PRD confirm

Apply the helper in `prd confirm` before calling `PrdManager.write_to_version()`.

- `--file path-check` becomes `prd/path-check`.
- `--file prd/path-check` is rejected instead of writing or indexing a caller-supplied path.
- The command output still reports the canonical `file` returned by the manager.

#### 3. Impl create

Apply the helper in `impl create` before calling `ImplManager.create()`.

- `--impl-file version` becomes `impl/version`.
- `--impl-file impl/version` is rejected.
- `--prd-file path-check` becomes `prd/path-check`.
- `--prd-file prd/path-check` is rejected.

#### 4. Tests and instructions

Update CLI regression tests and command guidance.

- Test bare-name PRD and Impl file options write into scoped directories and do not create root-level version markdown.
- Test path-like PRD/Impl options fail with `INVALID_FILE_NAME`.
- Update AIT sub-skill instructions and user-facing examples so future AI-driven calls use bare names for create/confirm file options.

### Boundaries

- Keep manager-level persisted file keys unchanged.
- Keep `prd show`, `prd commit`, and `impl commit` operating on canonical file keys.
- Do not migrate existing merged version workspaces as part of this implementation.
