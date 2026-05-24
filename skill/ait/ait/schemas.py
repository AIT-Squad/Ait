"""Pydantic schemas for AIT's YAML data model.

Five schemas (covering project-docs/.meta/*.yaml):
    - ProjectConfig       — .meta/config.yaml
    - BaselineIndex       — .meta/blocks-index.yaml
    - LinksIndex          — .meta/links-index.yaml
    - VersionIndex        — .meta/blocks-index-{vX.Y}.yaml
    - VersionMeta         — .meta/versions/{vX.Y}.yaml
    - RequirementMeta     — .meta/requirements/req-{N}.yaml
    - ChangeRecord        — .meta/changes/chg-{N}.yaml

Field conventions follow project-docs/docs/prd/index-system.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["add", "modify", "delete"]
State = Literal["working", "staged", "committed"]
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
# baseline blocks-index.yaml
# ─────────────────────────────────────────────────────────────


class BaselineBlockEntry(StrictModel):
    id: str
    file: str
    heading: str
    level: int


class BaselineIndex(StrictModel):
    version: int = 1
    scope: Literal["global"] = "global"
    updated: datetime | None = None
    blocks: list[BaselineBlockEntry] = Field(default_factory=list)


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
# version blocks-index-{vX.Y}.yaml
# ─────────────────────────────────────────────────────────────


class VersionBlockEntry(StrictModel):
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


class CommitEntry(StrictModel):
    id: str
    timestamp: datetime
    message: str
    blocks: list[str]
    req_id: str | None = None


class VersionIndexStats(StrictModel):
    total_blocks: int = 0
    by_action: dict[str, int] = Field(default_factory=dict)
    by_state: dict[str, int] = Field(default_factory=dict)


class VersionIndex(StrictModel):
    version: int = 1
    scope: Literal["version"] = "version"
    version_name: str
    based_on_hash: str | None = None
    status: Literal["developing", "committed", "merged"] = "developing"
    blocks: list[VersionBlockEntry] = Field(default_factory=list)
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


# ─────────────────────────────────────────────────────────────
# .meta/requirements/req-{N}.yaml
# ─────────────────────────────────────────────────────────────


class PrdBlockSummary(StrictModel):
    id: str
    heading: str
    level: int
    impl_status: Literal["pending", "in_progress", "done"] = "pending"


class ImplBlockDraft(StrictModel):
    id: str
    file: str
    heading: str
    layer: Literal["api", "data", "workflow", "other"] = "other"
    content: str


class ImplDraftBundle(StrictModel):
    prd_id: str
    impl_blocks: list[ImplBlockDraft] = Field(default_factory=list)


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
    prd_blocks: list[PrdBlockSummary] = Field(default_factory=list)
    impl_drafts: list[ImplDraftBundle] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# .meta/changes/chg-{N}.yaml
# ─────────────────────────────────────────────────────────────


class ChangeRecord(StrictModel):
    id: str
    version: str
    type: ChangeType
    target: str  # "file#block_id"
    author: str = "system"
    date: datetime
    message: str
    base_hash: str | None = None
    base_content: str | None = None
    new_content: str | None = None
