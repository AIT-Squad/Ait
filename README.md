# AIT — Take AI Development from One-Off Generation to Continuous Delivery

> AIT is a Claude Code Skill for projects that evolve over time. It breaks requirements and designs into traceable semantic chunks, preserves the long-term integrity of AI development context, gives AI only trusted specifications relevant to the current task, and applies phase gates, dependency checks, and artifact acceptance to every iteration.

AIT is designed for teams whose projects accumulate business rules and implementation constraints, and where multiple developers or AI agents need to work from the same source of truth.

**AIT is not another code repository, and it does not replace Git, code review, or project management.** It sits before those tools and turns “what to build, how to divide it, and how each file should be implemented” into shared, versioned specifications.

中文：[README.zh-CN.md](README.zh-CN.md)

---

## What Problems Does AIT Solve?

### 1. Keep AI focused on the current feature

As a project grows, sending all documents and code to AI dilutes important constraints. Sending only the target file has the opposite problem: the model can miss upstream requirements and dependency contracts.

AIT divides specifications into semantic chunks with stable IDs and records their relationships in a SpecGraph. For a TDD, AIT assembles only:

- the technical design for the current file;
- upstream FSD and PRD constraints;
- capability contracts of direct dependencies;
- the current contents of the target file.

This removes irrelevant context, improves signal-to-noise ratio, and usually reduces token usage. Actual token consumption still depends on chunk size and dependency depth; AIT does not currently enforce a hard token budget or automatic trimming.

### 2. Turn AI work into assignable team boundaries

AIT progressively breaks a requirement into three specification layers:

```text
PRD: align the team on why it matters and what users observe
  ↓
FSD: divide the work into functional domains, contracts, and dependencies
  ↓
TDD: create single-file implementation tasks (1 TDD → 1 target_file)
  ↓
codegen: prepare isolated context for each file and drive AI coding
```

FSDs can be recursively decomposed, and every TDD must own a unique `target_file`. These constraints let a team assign work first by functional domain and then by file, reducing the chance that multiple developers or agents edit the same file.

AIT currently uses a **single-active-version, single-writer** model. It does not create Git branches, merge pull requests, provide multi-user locks, or record who approved a PRD. Team review, assignment, and branch integration remain in your Git platform and project workflow. The recommended setup is one AIT integrator, with contributors implementing confirmed TDDs in separate code branches or worktrees.

### 3. Add engineering constraints for continuous delivery

AIT does more than store documents. It turns delivery into a checkable state machine:

```text
version create
  → PRD create / confirm
  → FSD create / decompose / confirm
  → TDD create / confirm
  → codegen
  → acceptance
  → version confirm / merge
```

At key points, AIT checks:

- whether work proceeds in PRD → FSD → TDD order;
- whether requirements, functions, and implementations remain traceable;
- whether the graph contains orphans, broken links, invalid tree cycles, or duplicate `target_file` ownership;
- whether a confirmed merge plan has become stale;
- whether the configured tests, build, or other acceptance command passes;
- whether the specification version is bound to the corresponding code commit.

AIT is therefore best suited to projects that need reliable delivery across many iterations—not one-time code generation.

---

## Capabilities and Boundaries

| What you need | What AIT provides | What remains external |
|---|---|---|
| Context integrity and AI focus | Versioned specifications, receipts and gates for stale/conflicting context, plus graph-based selection for the current TDD | Semantic correctness of source specifications, model token limits, and cost controls |
| Team PRD review | Versioned user stories and acceptance criteria, frozen by `prd confirm` | Reviewers, approval records, meetings, or PR workflows |
| Functional decomposition | Recursive FSD decomposition with capability contracts and dependencies | Staffing, scheduling, and task assignment |
| Multi-branch development | Unique `target_file` ownership as an independent TDD boundary | Branch/worktree creation, code merge, and conflict resolution |
| AI coding | Isolated context per TDD, used by the Skill to drive implementation | Final code review and human decisions |
| Production constraints | Phase gates, graph validation, acceptance commands, deterministic merge plans, version binding, and rollback anchors | CI/CD, authorization, release approval, and operations |

---

## Recommended Team Workflow

The following workflow supports shared review, layered decomposition, branch-based implementation, and controlled integration while respecting AIT's current boundaries.

### Phase 1: Agree on the PRD

1. Product, design, and engineering discuss user stories, scope, and acceptance criteria.
2. One integrator records the final decisions through AIT.
3. After external review, run `/ait prd confirm` to freeze the requirement layer.

### Phase 2: Decompose the FSD

1. Derive FSDs from the PRD and recursively divide functional domains with `fsd decompose`.
2. Define the capability and same-level dependencies of each function.
3. Assign functional areas to owners. Contributors may submit design proposals; the integrator writes the accepted result through AIT.
4. Validate dependencies and the graph, then run `/ait fsd confirm`.

### Phase 3: Create file-level TDD tasks

1. Create one or more TDDs for each leaf FSD.
2. Bind every TDD to a unique `target_file`, including file responsibility, implementation design, and test requirements.
3. Review all TDDs, then run `/ait tdd confirm`.

### Phase 4: Implement in parallel with people and AI

1. Create separate Git branches or worktrees for different TDDs.
2. Each developer or agent runs `/ait codegen prepare <TDD-id>` for its assigned task.
3. Complete code, tests, and review, then merge branches through the external Git workflow.

### Phase 5: Validate and close the version

1. Ensure the host repository contains only the changes intended for this AIT version.
2. Run acceptance and inspect version status.
3. Use `version confirm` for global gates and code-commit binding.
4. Use `version merge` to merge the specification workspace into the baseline.
5. If publishing, preview with `/ait push --dry-run` before `/ait push`.

> Note: after its gates pass, `version confirm` may run `git add -A` and create an artifact commit in the host repository. Commit or remove unrelated local changes first.

---

## Quick Start

### Prerequisites

- Claude Code;
- Python 3.10 or newer;
- Git;
- access to a Python package index during first-time dependency installation.

### 1. Install the Skill

From the AIT repository root:

```bash
python install.py
```

AIT is installed to `~/.claude/skills/ait/` by default. To upgrade:

```bash
python install.py update
```

Restart Claude Code after installation. AIT is a Skill, not a system-wide CLI; daily usage is through `/ait <subcommand>`.

### 2. Initialize a project

Open Claude Code at the root of your code repository:

```text
/ait init --new-model --name my_project
```

AIT creates an independent `project-docs/` specification repository. Run subsequent commands from the project root that contains this directory.

### 3. Complete the first iteration

```text
/ait version create v0.1

/ait prd create "[PRD]-my_project"
# Discuss and write the requirements with AI
/ait prd confirm

/ait fsd create "[FSD]-my_project"
# Decompose further when needed:
/ait fsd decompose "[FSD]-my_project:core" "[FSD]-core"
/ait fsd confirm

/ait tdd create "[TDD]-core" --parent "[FSD]-core:feature"
/ait tdd confirm

/ait codegen prepare "[TDD]-core"

/ait acceptance set "pytest -q"
/ait acceptance run
/ait version commit v0.1
/ait version confirm v0.1 --conflict-policy abort
/ait version merge v0.1
```

For `prd/fsd/tdd create`, the Skill first retrieves related context and discusses the change with you, then writes it using a context receipt. You normally do not edit `project-docs/` yourself. Do not bypass AIT to modify managed documents or `.meta` files.

---

## What Belongs in Each Layer?

| Layer | Core question | Main contents | Review focus |
|---|---|---|---|
| **PRD** | Why are we building this, and what does the user get? | User stories, scope, goals, and user-level acceptance criteria | Does the team agree on the requirement? |
| **FSD** | How is the feature divided, and what does each module provide? | Functional boundaries, capability contracts, dependencies, and integration acceptance | Can work be assigned independently, and are interfaces clear? |
| **TDD** | How should one file be implemented? | `target_file`, code structure, core logic, error boundaries, and unit-test requirements | Can AI implement this file independently? |

AIT marks every chunk with `<!-- @id:... -->` and maintains four relationship types in the SpecGraph:

- `derives`: PRD to FSD;
- `decomposes`: FSD to a child FSD;
- `details`: leaf FSD to TDD;
- `depends_on`: dependencies between sibling functions.

You do not maintain these relationships manually; the corresponding commands create and validate them.

---

## When Should You Use AIT?

**A good fit:**

- the project will live through many versions;
- business rules, interface constraints, and historical decisions keep accumulating;
- multiple developers or AI agents need a shared specification;
- a change in one area often affects several modules;
- the team wants tests and builds to become pre-merge gates.

**Probably not a fit:**

- one-off scripts, quick prototypes, or very small isolated features;
- the team does not intend to maintain PRD, FSD, and TDD specifications;
- you expect automatic Git branch management, PR approval, or CI/CD;
- multiple operators must write to the same AIT version concurrently.

---

## How Is AIT Different from Git or Agent Memory?

- **Git versions code; AIT versions the specifications and relationships that drive AI development.** They complement each other, and AIT records the binding between specification versions and code commits.
- **AGENTS.md and MEMORY.md hold general rules or personal preferences; AIT holds reviewable, testable, traceable project requirements and designs.**
- **Task-execution skills focus on completing this task; AIT focuses on preserving constraints after hundreds of iterations.**

---

## Status and Further Reading

AIT is under active development and has used its own PRD → FSD → TDD → codegen process since v2.0.

| Document | Read it when... |
|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | You are adopting AIT, need the complete command reference, or are troubleshooting |
| [DESIGN.md](DESIGN.md) | You want to understand the architecture, state machine, and design trade-offs |
| [CHANGELOG.md](CHANGELOG.md) | You want the release history and latest capabilities |
| [skill/ait/SKILL.md](skill/ait/SKILL.md) | You need the Skill routing and command contract |

MIT License.
