"""Pydantic schemas for AIT's YAML data model.

Five schemas (covering project-docs/.meta/*.yaml):
    - ProjectConfig       — .meta/config.yaml
    - BaselineIndex       — .meta/chunks-index.yaml
    - LinksIndex          — .meta/links-index.yaml
    - VersionIndex        — .meta/chunks-index-{vX.Y}.yaml
    - VersionMeta         — .meta/versions/{vX.Y}.yaml
    - RequirementMeta     — .meta/requirements/req-{N}.yaml
    - ChangeRecord        — .meta/changes/chg-{N}.yaml

Field conventions follow project-docs/docs/prd/index-system.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Action = Literal["add", "modify", "delete"]
State = Literal["working", "staged", "committed"]
VersionPhase = Literal[
    # legacy lifecycle
    "empty", "prd_locked", "impl_locked", "coding",
    # new-model layer flow (v2.22+)
    "prd-creating", "prd-confirm", "fsd-creating", "fsd-confirm",
    "tdd-creating", "tdd-confirm",
    # terminal
    "merged",
]
TaskStatus = Literal["created", "executing", "done", "failed"]
ReqStatus = Literal[
    "draft", "prd_draft", "prd_confirmed", "impl_progress", "impl_done", "merged"
]
ChangeType = Literal["ADD", "MODIFY", "DELETE"]


class StrictModel(BaseModel):
    """Base model: forbid unknown keys, dump nulls explicitly."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ─────────────────────────────────────────────────────────────
# config.yaml
# ─────────────────────────────────────────────────────────────


class ProjectConfig(StrictModel):
    id_prefix_separator: str = "-"
    version_format: str = "{major}.{minor}"
    auto_snapshot_on_merge: bool = True
    custom_relations: list[str] = Field(default_factory=list)
    id_prefixes: dict[str, str] = Field(default_factory=dict)
    mvp_scope_tags: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# baseline chunks-index.yaml
# ─────────────────────────────────────────────────────────────

class BaselineChunkEntry(StrictModel):
    id: str
    file: str
    heading: str
    level: int
    summary: str | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("summary")
    @classmethod
    def _validate_summary_length(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 120:
            raise ValueError("summary must be <= 120 characters")
        return value

class BaselineIndex(StrictModel):
    version: int = 1
    scope: Literal["global"] = "global"
    updated: datetime | None = None
    chunks: list[BaselineChunkEntry] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# links-index.yaml
# ─────────────────────────────────────────────────────────────


class LinkEntry(StrictModel):
    from_: str = Field(alias="from")
    to: str
    rel: str

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LinksIndex(StrictModel):
    version: int = 1
    updated: datetime | None = None
    links: list[LinkEntry] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# version chunks-index-{vX.Y}.yaml
# ─────────────────────────────────────────────────────────────

class VersionChunkEntry(StrictModel):
    id: str
    file: str | None  # null when action=delete
    heading: str | None  # null when action=delete
    level: int | None  # null when action=delete
    action: Action
    state: State
    commit_id: str | None = None
    overrides: str | None = None
    amends: str | None = None
    insert_after: str | None = None
    base_hash: str | None = None
    source_req: str | None = None
    summary: str | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("summary")
    @classmethod
    def _validate_summary_length(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 120:
            raise ValueError("summary must be <= 120 characters")
        return value

class CommitEntry(StrictModel):
    id: str
    timestamp: datetime
    message: str
    chunks: list[str]
    req_id: str | None = None

class VersionIndexStats(StrictModel):
    total_chunks: int = 0
    by_action: dict[str, int] = Field(default_factory=dict)
    by_state: dict[str, int] = Field(default_factory=dict)
    tasks_summary: dict[str, int] = Field(default_factory=dict)

class VersionIndex(StrictModel):
    version: int = 1
    scope: Literal["version"] = "version"
    version_name: str
    based_on_hash: str | None = None
    status: Literal["developing", "committed", "merged"] = "developing"
    chunks: list[VersionChunkEntry] = Field(default_factory=list)
    commits: list[CommitEntry] = Field(default_factory=list)
    stats: VersionIndexStats = Field(default_factory=VersionIndexStats)


# ─────────────────────────────────────────────────────────────
# .meta/versions/{vX.Y}.yaml
# ─────────────────────────────────────────────────────────────


class VersionDependencies(StrictModel):
    based_on: str | None = None
    conflicts_with: list[str] = Field(default_factory=list)
    merge_after: list[str] = Field(default_factory=list)


class VersionMeta(StrictModel):
    version: str
    created_at: datetime
    merged_at: datetime | None = None
    owner: str = "system"
    changes: list[str] = Field(default_factory=list)
    dependencies: VersionDependencies = Field(default_factory=VersionDependencies)
    snapshot: str | None = None
    # ── Redesign: version atomicity & lock state (new fields, default-valued
    # so existing v1.1-v1.3 metadata without them still loads cleanly) ──
    phase: VersionPhase = "empty"
    title: str | None = None        # summarized in prd discuss; used as git commit msg
    prd_locked: bool = False
    impl_locked: bool = False
    # v2.55 cross-repo binding fields (docs/code isolation)
    docs_commit: str | None = None   # docs-repo commit sha produced by version merge
    code_base:   str | None = None   # host HEAD at merge time (read-only snapshot)
    code_result: str | None = None   # host HEAD after acceptance (filled by skill layer)


# ─────────────────────────────────────────────────────────────
# .meta/requirements/req-{N}.yaml
# ─────────────────────────────────────────────────────────────


class PrdChunkSummary(StrictModel):
    id: str
    heading: str
    level: int
    impl_status: Literal["pending", "in_progress", "done"] = "pending"

class ImplChunkDraft(StrictModel):
    id: str
    file: str
    heading: str
    layer: Literal["api", "data", "workflow", "other"] = "other"
    content: str

class ImplDraftBundle(StrictModel):
    prd_id: str
    impl_chunks: list[ImplChunkDraft] = Field(default_factory=list)

class RequirementMeta(StrictModel):
    id: str
    title: str
    status: ReqStatus = "draft"
    created_at: datetime
    updated_at: datetime
    author: str = ""
    assigned_version: str | None = None
    confirmed_at: datetime | None = None
    prd_draft: str = ""
    prd_chunks: list[PrdChunkSummary] = Field(default_factory=list)
    impl_drafts: list[ImplDraftBundle] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# .meta/changes/chg-{N}.yaml
# ─────────────────────────────────────────────────────────────


class ChangeRecord(StrictModel):
    id: str
    version: str
    type: ChangeType
    target: str  # "file#chunk_id"
    author: str = "system"
    date: datetime
    message: str
    base_hash: str | None = None
    base_content: str | None = None
    new_content: str | None = None


# ─────────────────────────────────────────────────────────────
# versions/{vX.Y}/tasks/T-{src}-NN.yaml  (redesign: AI coding tasks)
# ─────────────────────────────────────────────────────────────


class CodeRef(StrictModel):
    commit: str | None = None       # git commit hash
    paths: list[str] = Field(default_factory=list)
    bound_at: datetime | None = None


class TaskYaml(StrictModel):
    id: str                          # T-{src-chunk}-NN
    title: str
    source_chunk: str                # originating PRD chunk id
    impl_refs: list[str] = Field(default_factory=list)
    global_refs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    order_hint: int = 1
    steps: list[str] = Field(default_factory=list)
    status: TaskStatus = "created"
    code_refs: list[CodeRef] = Field(default_factory=list)
