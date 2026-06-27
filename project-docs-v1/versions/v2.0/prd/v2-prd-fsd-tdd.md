<!-- @id:prd-v2-prd-fsd-tdd-parallel-model -->
## v2.0 introduces parallel PRD/FSD/TDD model

<!-- @summary: v2.0 adds PRD/FSD/TDD as a parallel document model while keeping the old workflow available -->

### 概述

AIT currently uses a PRD/impl/task workflow. v2.0 must keep that workflow available so v2.0 itself can be developed through current AIT dogfood, while adding a new PRD/FSD/TDD model for later versions.

The target model separates intent, decomposition, and code generation instructions:

- PRD describes requirements: why and what.
- FSD describes functional decomposition and interaction contracts.
- TDD describes the concrete technical implementation of one target code file.

### 业务规则

- v2.0 development itself must use the current AIT PRD/impl/task flow.
- v2.0 must introduce PRD/FSD/TDD as parallel capability, not replace the old workflow immediately.
- Existing `ait prd`, `ait impl`, and `ait task` commands remain available.
- New capability is exposed through `ait fsd`, `ait tdd`, and `ait codegen`.
- v2.0 must not migrate historical v1.x documents into the new PRD/FSD/TDD format.
- Versions after v2.0 can start using the new PRD/FSD/TDD document format and new AIT capability as the normal dogfood flow.

### 验收标准

- Existing v1.x PRD/impl/task commands and tests continue to work.
- v2.0 documents explicitly describe the PRD/FSD/TDD model, template contracts, command surface, codegen context behavior, and merge compatibility.
- AIT can parse and index PRD/FSD/TDD-style chunk ids while still accepting legacy chunk ids.
- AIT can represent PRD/FSD/TDD semantic relationships as specgraph edges.

### 边界与非目标

- v2.0's own PRD and impl do not need to use the new PRD/FSD/TDD format.
- v2.0 does not remove `ait impl` or `ait task`.
- v2.0 does not rewrite historical baseline or merged version documents.

<!-- @id:prd-v2-fsd-tdd-structure-rules -->
## PRD/FSD/TDD structure and graph rules

<!-- @summary: The new model must enforce chunk-level PRD/FSD/TDD hierarchy, naming, and dependency rules -->

### 概述

The target document model is a chunk graph:

```text
Version
  -> one PRD
      -> root FSD
          -> recursive child FSD
              -> leaf FSD
                  -> one or more TDD
                      -> each TDD maps to one code file
```

Files are physical containers. Chunks are the semantic unit. Relationships are chunk-to-chunk specgraph edges.

### 业务规则

- Each version in the new model has exactly one PRD.
- Every PRD/FSD/TDD file must have a root chunk.
- The root chunk represents the whole file and carries common file-level context.
- The root chunk does not replace internal semantic chunks.
- A file may contain internal chunks for requirement items, split items, or implementation detail blocks.
- PRD root chunk maps to the root FSD root chunk with `decomposes`.
- Parent PRD/FSD files describe downstream FSD/TDD parts through internal split chunks.
- Parent-child edges are emitted from the parent internal split chunk, except for the PRD root to root FSD case.
- `decomposes` is used for PRD/FSD to FSD relationships.
- `details` is used for FSD to TDD relationships.
- `depends_on` is used only between sibling internal split chunks inside the same parent FSD file.
- FSD files may recursively decompose into child FSD files.
- A leaf FSD may detail one or more TDD files.
- One FSD node must not mix child FSD and TDD children.
- If a lower-level FSD needs a dependency owned by a parent sibling, the dependency must be lifted to the parent split level.
- Infrastructure capabilities such as database, Redis, and message queue are modeled as normal FSD parts.

Naming rules:

- File name equals root chunk id plus `.md`.
- File name and root chunk id use `[PRD]`, `[FSD]`, or `[TDD]` prefixes.
- `_` joins words inside one semantic name.
- `-` joins hierarchy levels.
- Internal split chunk id uses `<parent_root_chunk_id>:<internal_split_chunk_name>`.
- Internal split chunk id must not use literal `:split` as a fixed suffix.
- AIT must not infer semantic relationships from chunk id or file name strings.
- Normal AIT usage must create specgraph relationships explicitly when documents are generated.

### 验收标准

- A validator can detect invalid edge types and invalid graph structures.
- A validator can reject FSD nodes that mix FSD children and TDD children.
- A validator can reject `depends_on` edges that do not connect sibling internal split chunks.
- A validator can reject `depends_on` edges that point directly to downstream root chunks.
- A validator can reject parent-child edges emitted from the wrong source chunk.
- Demo documents can represent infrastructure as ordinary FSD capability and dependency.

### 边界与非目标

- v2.0 does not introduce file-level graph edges.
- v2.0 does not introduce additional trace relation types beyond `decomposes`, `details`, and `depends_on`.
- v2.0 does not decide FSD split depth automatically.

<!-- @id:prd-v2-prd-fsd-tdd-template-contracts -->
## PRD/FSD/TDD template contracts

<!-- @summary: v2.0 must deliver explicit PRD, FSD, and TDD template files matching the new document model -->

### 概述

The new PRD/FSD/TDD model needs concrete markdown templates that humans can audit and AIT can later generate. These templates are part of the v2.0 requirement, not optional supporting notes.

The target template files are:

- `TEMPLATE-PRD-AIT-DRAFT.md`
- `TEMPLATE-FSD-AIT-DRAFT.md`
- `TEMPLATE-TDD-AIT-DRAFT.md`

### 业务规则

PRD template:

- Root chunk id uses `<!-- @id:[PRD]-{semantic_name} -->`.
- Internal requirement chunk id uses `<!-- @id:[PRD]-{semantic_name}-{requirement_name} -->`.
- Root chunk includes background and problem, goals and measurement, scope, users and roles, assumptions and constraints, and overall acceptance criteria.
- Requirement chunks include user story, requirement description, business rules, user-visible flow, exception scenarios, acceptance criteria, and open questions.
- PRD writes why and what, not module decomposition, technical design, or target code files.

FSD template:

- Root chunk id uses `<!-- @id:[FSD]-{semantic_name} -->`.
- Internal split chunk id uses `<!-- @id:[FSD]-{semantic_name}:{split_name} -->`.
- Root chunk includes functional scope, feature overview, common business rules, common definitions, interaction contract overview, data model contract, and non-functional requirements.
- Split chunks include functional description, boundary, business flow, business rules, provided interaction contracts, input/output fields, failure codes or exceptions, call constraints, and data contracts.
- FSD template content defines interaction fields and interaction methods, but dependencies are expressed through specgraph instead of ordinary prose management fields.

TDD template:

- Root chunk id uses `<!-- @id:[TDD]-{semantic_name} -->`.
- TDD root chunk includes a YAML-style `target_file: path/to/target_file.ext` declaration.
- TDD root chunk includes technology stack, implementation constraints, file responsibility, code structure, core logic, key data structures, algorithms and flow, error handling, boundary conditions, and unit test requirements.
- Optional internal implementation detail chunk id uses `<!-- @id:[TDD]-{semantic_name}-{detail_name} -->`.
- Unit test requirements must include test file path, framework, normal path, boundary conditions, error path, mocks/fixtures, independent run command, passing standards, and failing conditions.
- Each TDD maps to exactly one target code file.

Template exclusion rules:

- Templates must not include AIT-managed fields such as document state, change log, version metadata, hierarchy type fields, manual downstream-link fields, manual linked-FSD/TDD fields, or specgraph hint fields.
- Templates must not reintroduce task as a document layer.
- Relationship creation belongs to AIT-generated refs, metadata, and specgraph update actions.

### 验收标准

- The three template files exist and use `[PRD]`, `[FSD]`, and `[TDD]` root chunk ids.
- The FSD template shows internal split chunk id format with `:<split_name>`.
- The FSD template does not use literal `:split`.
- The TDD template includes `target_file` as markdown source of truth.
- The TDD template includes passing standards and failing conditions for unit tests.
- The templates do not contain AIT-managed relationship or state fields.

### 边界与非目标

- v2.0 templates are target-format templates for later versions, not the required format of v2.0's own PRD/impl files.
- v2.0 does not require templates to contain concrete downstream specgraph edges.
- v2.0 does not require PRD internal requirement chunks to map one-to-one to implementation chunks.

<!-- @id:prd-v2-fsd-tdd-commands -->
## Parallel FSD, TDD, and codegen commands

<!-- @summary: v2.0 adds ait fsd, ait tdd, and ait codegen while preserving existing commands -->

### 概述

Users need first-class commands to create and manage FSD and TDD documents without overloading the old impl/task concepts. The new commands should coexist with the existing workflow so v1.x projects remain usable while v2.x projects can start adopting the new model.

### 业务规则

- `ait fsd` manages FSD documents and FSD decomposition.
- `ait tdd` manages TDD documents and target file implementation instructions.
- `ait codegen` prepares code generation context from a TDD root chunk.
- New commands must write version-side files under `versions/<version>/fsd` and `versions/<version>/tdd` for new-model work.
- New commands must create chunk records in version chunks-index.
- New commands must create or update specgraph edges explicitly as documents are generated.
- New commands must not remove or change the behavior of `ait prd`, `ait impl`, or `ait task`.

### 验收标准

- CLI help exposes `fsd`, `tdd`, and `codegen` command groups.
- FSD command flow can create or update an FSD markdown file with a root chunk and internal split chunks.
- TDD command flow can create or update a TDD markdown file with a root chunk and target file declaration.
- Codegen command flow accepts a TDD root chunk id and returns a focused context bundle.
- Existing end-to-end PRD/impl/task tests continue to pass.

### 边界与非目标

- v2.0 does not remove the existing task YAML implementation.
- v2.0 does not require old impl documents to be rewritten as TDD documents.
- v2.0 does not execute AI code generation directly inside the CLI unless an existing AIT pattern already supports that safely.

<!-- @id:prd-v2-codegen-tdd-context -->
## TDD-based code generation context

<!-- @summary: Code generation starts from a TDD root chunk and gathers upstream and dependency context through specgraph -->

### 概述

The target model removes task as the new code generation unit. A TDD root chunk represents the implementation instruction for one concrete target code file. The code generation context must be assembled by traversing chunk-level relationships from that TDD root.

### 业务规则

- Each TDD maps to exactly one target code file.
- TDD markdown must specify `target_file`; metadata may redundantly index it, but markdown is the source of truth.
- TDD must include unit test requirements with passing and failing conditions.
- TDD context assembly starts from the TDD root chunk.
- Context assembly includes the TDD file's internal implementation chunks.
- Context assembly recursively collects upstream FSD and PRD chunks needed to understand requirements and functional contracts.
- Context assembly follows the parent internal split chunk to find sibling `depends_on` edges.
- Dependency context is collected through sibling split chunks and their downstream root chunks.
- TDD context assembly must not infer dependencies from names.

### 验收标准

- Given a valid TDD root chunk, `ait codegen` returns the target file path.
- Given a valid TDD root chunk, `ait codegen` returns the TDD root and internal implementation chunks.
- Given a valid TDD root chunk, `ait codegen` returns relevant upstream FSD/PRD chunks.
- Given sibling `depends_on` relationships, `ait codegen` includes dependency contracts required by the target TDD.
- Unit tests cover at least one multi-level FSD to TDD context traversal.

### 边界与非目标

- v2.0 does not require the CLI to edit source code directly.
- v2.0 does not make task YAML the source of truth for new-model code generation.
- v2.0 does not allow one TDD to target multiple code files.

<!-- @id:prd-v2-version-merge-compatibility -->
## Version and merge compatibility

<!-- @summary: v2.0 must merge new PRD/FSD/TDD documents at chunk level while preserving old baseline behavior -->

### 概述

AIT must continue to provide versioned document development and baseline merge. The new PRD/FSD/TDD model should participate in the same chunk-level add/modify/delete lifecycle without breaking existing historical data.

### 业务规则

- New PRD/FSD/TDD files in a version are not one-off drafts.
- After confirm and merge, new-model documents must update the global baseline current state.
- Merge must remain chunk-based.
- chunks-index and specgraph must be rebuilt or updated after merge.
- v1.x PRD baseline single-file behavior must not accidentally swallow FSD/TDD files.
- New-model PRD/FSD/TDD baseline files should preserve their intended file containers.
- Backward compatibility must allow old baseline chunks and new-model chunks to coexist.

### 验收标准

- Version merge can promote FSD and TDD chunks into baseline docs without forcing them into `docs/prd/global.md`.
- Version merge can preserve specgraph edges for `decomposes`, `details`, and `depends_on`.
- Legacy confirm behavior still passes existing tests.
- New tests cover merge of at least one FSD file and one TDD file.
- New tests cover mixed legacy baseline data and new-model version data.

### 边界与非目标

- v2.0 does not rewrite historical `.meta` files except through normal version operations.
- v2.0 does not delete old task metadata.
- v2.0 does not require all projects to switch to new-model confirm rules immediately.
