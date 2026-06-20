<!-- @id:impl-v2-prd-fsd-tdd-parallel-model-compat-layer -->
## PRD/FSD/TDD compatibility layer

<!-- @ref:prd/v2-prd-fsd-tdd#prd-v2-prd-fsd-tdd-parallel-model rel:implements -->

### Change points

#### 1. Chunk parser id compatibility

Extend the markdown parser so it can parse both legacy ids and future PRD/FSD/TDD ids.

- Keep existing support for `prd-*`, `impl-*`, `task-*`, and `global-*`.
- Add support for bracketed document prefixes such as `[PRD]-...`, `[FSD]-...`, and `[TDD]-...`.
- Add support for underscores inside semantic names.
- Add support for internal chunk ids that use `:` between the parent root chunk id and the local split chunk name.
- Apply the same id pattern to `@ref` targets.
- Keep code-fence masking behavior unchanged.

#### 2. Index metadata compatibility

Allow chunks-index records to carry optional new-model metadata without breaking historical records.

- Add optional metadata fields only when needed.
- Preserve existing required fields and default behavior.
- Do not require old index files to be migrated.
- Allow TDD target file metadata to be indexed later while keeping markdown as source of truth.

#### 3. SpecGraph type compatibility

Update specgraph construction so document type is no longer limited to legacy `prd`, `impl`, and `global` assumptions.

- Preserve existing legacy URI behavior for existing chunks.
- Add type support for `fsd` and `tdd`.
- Prefer explicit file location or metadata when determining new-model type.
- Do not infer semantic relationships from file name hierarchy.

### Boundaries

- Do not remove legacy PRD/impl/task parsing.
- Do not rewrite historical `.meta` files.
- Do not change merge behavior in this chunk beyond metadata compatibility needed by later chunks.

<!-- @id:impl-v2-fsd-tdd-structure-rules-validator -->
## PRD/FSD/TDD structure validator

<!-- @ref:prd/v2-prd-fsd-tdd#prd-v2-fsd-tdd-structure-rules rel:implements -->

### Change points

#### 1. New validation module

Add a validator focused on PRD/FSD/TDD structure and specgraph legality.

- Validate allowed relation types: `decomposes`, `details`, and `depends_on`.
- Validate PRD root to root FSD `decomposes`.
- Validate FSD to child FSD `decomposes`.
- Validate leaf FSD to TDD `details`.
- Validate that one FSD node does not mix child FSD and TDD children.

#### 2. Dependency legality

Implement dependency checks through explicit specgraph edges.

- `depends_on` must connect sibling internal split chunks in the same parent FSD file.
- `depends_on` must not point directly at downstream root chunks.
- Cross-level dependency must be reported as invalid.
- The validator should explain that dependency must be lifted to the parent split level.

#### 3. Command integration

Expose validation through a command path that can be used during v2.0 development and future dogfood.

- Return machine-readable JSON violations.
- Include chunk id, file, relation, and reason when possible.
- Keep this validation separate from legacy PRD/impl format validation.

### Boundaries

- Do not auto-rewrite invalid graph relationships.
- Do not introduce additional relation types in v2.0.
- Do not decide FSD split depth automatically.

<!-- @id:impl-v2-prd-fsd-tdd-template-contracts-files -->
## PRD/FSD/TDD template contract files

<!-- @ref:prd/v2-prd-fsd-tdd#prd-v2-prd-fsd-tdd-template-contracts rel:implements -->

### Change points

#### 1. Template files

Update or create the target template files used by the new PRD/FSD/TDD model.

- `TEMPLATE-PRD-AIT-DRAFT.md`
- `TEMPLATE-FSD-AIT-DRAFT.md`
- `TEMPLATE-TDD-AIT-DRAFT.md`

The templates are v2.0 deliverables and must reflect the current agreed document model.

#### 2. PRD template structure

The PRD template must describe requirements without implementation design.

- Root chunk id uses `[PRD]-{semantic_name}`.
- Internal requirement chunk id uses `[PRD]-{semantic_name}-{requirement_name}`.
- Root sections include background/problem, goals/measurement, scope, users/roles, assumptions/constraints, and overall acceptance criteria.
- Requirement sections include user story, requirement description, business rules, user-visible flow, exception scenarios, acceptance criteria, and open questions.

#### 3. FSD template structure

The FSD template must describe functional decomposition and interaction contracts.

- Root chunk id uses `[FSD]-{semantic_name}`.
- Internal split chunk id uses `[FSD]-{semantic_name}:{split_name}`.
- The template must not use literal `:split`.
- Root sections include functional scope, feature overview, common business rules, common definitions, interaction contract overview, data model contract, and non-functional requirements.
- Split sections include functional description, boundary, business flow, business rules, provided interaction contracts, input/output fields, failure codes or exceptions, call constraints, and data contracts.

#### 4. TDD template structure

The TDD template must describe one code file implementation.

- Root chunk id uses `[TDD]-{semantic_name}`.
- Root chunk includes `target_file: path/to/target_file.ext`.
- Optional implementation detail chunk id uses `[TDD]-{semantic_name}-{detail_name}`.
- Root sections include technology stack, implementation constraints, file responsibility, code structure, core logic, key data structures, algorithms and flow, error handling, boundary conditions, and unit test requirements.
- Unit test requirements include test file path, framework, normal path, boundary conditions, error path, mocks/fixtures, independent run command, passing standards, and failing conditions.

#### 5. Template exclusion checks

Templates must not include AIT-managed relationship or lifecycle fields.

- No document state fields.
- No change log fields.
- No version metadata fields.
- No hierarchy type fields.
- No manual downstream-link fields.
- No manual linked-FSD/TDD fields.
- No specgraph hint fields.
- No task layer.

### Boundaries

- Do not make v2.0's own PRD/impl use these new templates.
- Do not encode concrete downstream specgraph edges in the templates.
- Do not infer graph relationships from template file names or chunk ids.

<!-- @id:impl-v2-fsd-tdd-commands-cli-managers -->
## FSD, TDD, and codegen command groups

<!-- @ref:prd/v2-prd-fsd-tdd#prd-v2-fsd-tdd-commands rel:implements -->

### Change points

#### 1. FSD manager and CLI group

Add an FSD management path parallel to the existing PRD and impl managers.

- Create or update version-side FSD markdown under `versions/<version>/fsd`.
- Register FSD chunks in the version chunks-index.
- Support root chunks and internal split chunks.
- Create specgraph edges explicitly when downstream FSD or TDD relationships are generated.

#### 2. TDD manager and CLI group

Add a TDD management path for file-level technical implementation documents.

- Create or update version-side TDD markdown under `versions/<version>/tdd`.
- Register TDD chunks in the version chunks-index.
- Require a TDD root chunk.
- Require `target_file` in TDD markdown.
- Keep each TDD mapped to one target code file.

#### 3. Codegen CLI group

Add `ait codegen` as the new-model code generation preparation entry point.

- Accept a TDD root chunk id.
- Resolve the target TDD document from version or baseline indexes.
- Return a focused context bundle for the AI coding layer.
- Do not remove or rename `ait task`.

### Boundaries

- Do not remove current `ait prd`, `ait impl`, or `ait task` commands.
- Do not migrate legacy impl documents to TDD.
- Do not execute source-code edits directly from these command groups in v2.0.

<!-- @id:impl-v2-codegen-tdd-context-assembler -->
## TDD codegen context assembler

<!-- @ref:prd/v2-prd-fsd-tdd#prd-v2-codegen-tdd-context rel:implements -->

### Change points

#### 1. TDD entry resolution

Add a context assembly path that starts from a TDD root chunk.

- Locate the TDD root chunk in the active version first, then baseline.
- Read the target TDD file and include its internal implementation chunks.
- Extract `target_file` from the TDD markdown body.
- Return an error when the target file declaration is missing.

#### 2. Upstream collection

Collect requirement and functional context through specgraph traversal.

- Find the parent internal split chunk that points to the TDD root chunk.
- Include that split chunk and the parent FSD root chunk as local contract context.
- Recursively walk upstream FSD and PRD relationships.
- Include root chunks as whole-file common context when file-level context is needed.

#### 3. Dependency collection

Follow dependency context through sibling split chunks.

- From the parent split chunk, follow outgoing `depends_on` edges.
- Resolve each sibling split chunk to its downstream root chunk through `decomposes` or `details`.
- Include dependency contracts without relying on file or chunk naming.
- Deduplicate context slices by chunk id and source.

### Boundaries

- Do not use task YAML as source of truth for new codegen context.
- Do not allow one TDD to target multiple code files.
- Do not infer dependencies from naming conventions.

<!-- @id:impl-v2-version-merge-compatibility-lifecycle -->
## Version lifecycle and merge compatibility

<!-- @ref:prd/v2-prd-fsd-tdd#prd-v2-version-merge-compatibility rel:implements -->

### Change points

#### 1. Version workspace support

Extend version workspace handling so FSD and TDD directories are first-class new-model document locations.

- Create `fsd` and `tdd` directories for new versions when needed.
- Keep existing `prd`, `impl`, and `tasks` behavior.
- Ensure reindex and lint file discovery can see new-model markdown when using new-model validation paths.

#### 2. Merge routing compatibility

Prevent legacy PRD single-file routing from affecting FSD and TDD documents.

- Keep legacy PRD behavior for existing old-model PRD chunks unless explicitly changed later.
- Merge FSD chunks to `docs/fsd`.
- Merge TDD chunks to `docs/tdd`.
- Preserve file containers for new-model PRD/FSD/TDD documents.

#### 3. Confirm compatibility

Allow v2.0 to keep old confirm semantics while preparing for taskless future flows.

- Existing confirm still requires old task completion for legacy workflow.
- New-model confirm rules can be introduced behind explicit code paths.
- Specgraph promotion must preserve `decomposes`, `details`, and `depends_on` edges.

### Boundaries

- Do not delete task metadata.
- Do not rewrite historical merged versions.
- Do not force all projects into new confirm rules in v2.0.
