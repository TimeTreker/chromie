from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AgentSkillAuthority = Literal["agent_method_only"]
AgentSkillExecutionAuthority = Literal["none"]
AgentSkillProjectionName = Literal[
    "goal_association",
    "fast_planner",
    "deep_planner",
    "response_composer",
    "tool_result_interpreter",
]
AgentSkillSelectionDecision = Literal["select_skills", "no_skill"]
AgentSkillSelectionStatus = Literal[
    "selected",
    "no_skill",
    "no_candidates",
    "model_unavailable",
    "model_contract_failed",
]
AgentSkillDisclosureStatus = Literal[
    "loaded",
    "partial",
    "no_skill",
    "unavailable",
]
AgentSkillDisclosureFailureReason = Literal[
    "selection_not_selected",
    "selection_role_mismatch",
    "selection_provenance_mismatch",
    "projection_load_failed",
    "projection_too_large",
    "total_budget_exceeded",
    "projection_count_limit_exceeded",
]
AgentSkillLoadFailureReason = Literal[
    "root_not_found",
    "root_not_directory",
    "unsafe_path",
    "metadata_missing",
    "metadata_invalid",
    "owner_approval_required",
    "content_missing",
    "content_too_large",
    "content_digest_mismatch",
    "duplicate_agent_skill_id",
    "unknown_parent_skill",
    "inheritance_cycle",
]

_AGENT_SKILL_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_SEMANTIC_VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _normalize_identifier(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not _AGENT_SKILL_ID.fullmatch(text):
        raise ValueError(
            f"{field_name} must be a namespaced lower-case identifier"
        )
    return text


def _normalize_identifier_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _normalize_identifier(item, field_name=field_name)
        if text in seen:
            raise ValueError(f"{field_name} contains duplicate identifier {text!r}")
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_relative_markdown_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("projection paths must be normalized package-relative paths")
    if path.suffix.lower() != ".md":
        raise ValueError("projection paths must reference Markdown files")
    return path.as_posix()


class AgentSkillProjectionDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: AgentSkillProjectionName
    path: str

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, value: Any) -> str:
        return _normalize_relative_markdown_path(value)


class AgentSkillMetadata(BaseModel):
    """Strict, passive metadata for one owner-reviewed Agent Skill package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    agent_skill_id: str = Field(min_length=3, max_length=160)
    version: str = Field(min_length=5, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=800)
    authority: AgentSkillAuthority
    execution_authority: AgentSkillExecutionAuthority
    owner_approved: bool
    content_digest: str
    extends: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    required_capabilities: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    optional_capabilities: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    applicable_routes: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    projections: tuple[AgentSkillProjectionDeclaration, ...] = Field(min_length=1, max_length=5)

    @field_validator("agent_skill_id", mode="before")
    @classmethod
    def normalize_agent_skill_id(cls, value: Any) -> str:
        return _normalize_identifier(value, field_name="agent_skill_id")

    @field_validator("version", mode="before")
    @classmethod
    def validate_semantic_version(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not _SEMANTIC_VERSION.fullmatch(text):
            raise ValueError("version must be a valid semantic version")
        return text

    @field_validator("title", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("content_digest", mode="before")
    @classmethod
    def validate_content_digest(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not _SHA256.fullmatch(text):
            raise ValueError("content_digest must use sha256:<64 lowercase hex>")
        return text

    @field_validator("extends", mode="before")
    @classmethod
    def normalize_extends(cls, value: Any) -> tuple[str, ...]:
        return tuple(_normalize_identifier_list(value, field_name="extends"))

    @field_validator("required_capabilities", mode="before")
    @classmethod
    def normalize_required_capabilities(cls, value: Any) -> tuple[str, ...]:
        return tuple(_normalize_identifier_list(value, field_name="required_capabilities"))

    @field_validator("optional_capabilities", mode="before")
    @classmethod
    def normalize_optional_capabilities(cls, value: Any) -> tuple[str, ...]:
        return tuple(_normalize_identifier_list(value, field_name="optional_capabilities"))

    @field_validator("applicable_routes", mode="before")
    @classmethod
    def normalize_applicable_routes(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("applicable_routes must be an array")
        routes: list[str] = []
        for item in value:
            route = "_".join(
                str(item or "").strip().casefold().replace("-", "_").split()
            )
            if route and route not in routes:
                routes.append(route)
        return tuple(routes)

    @field_validator("projections", mode="before")
    @classmethod
    def normalize_projections(cls, value: Any) -> tuple[dict[str, str], ...]:
        if not isinstance(value, dict):
            raise ValueError("projections must be an object")
        normalized: list[dict[str, str]] = []
        seen_paths: set[str] = set()
        for name, raw_path in value.items():
            projection_name = str(name or "").strip()
            path = _normalize_relative_markdown_path(raw_path)
            if path in seen_paths:
                raise ValueError(f"projection path {path!r} is declared more than once")
            seen_paths.add(path)
            normalized.append({"name": projection_name, "path": path})
        return tuple(normalized)

    @model_validator(mode="after")
    def validate_dependencies(self) -> "AgentSkillMetadata":
        if self.agent_skill_id in self.extends:
            raise ValueError("an Agent Skill cannot extend itself")
        overlap = set(self.required_capabilities) & set(self.optional_capabilities)
        if overlap:
            raise ValueError(
                "required_capabilities and optional_capabilities overlap: "
                + ", ".join(sorted(overlap))
            )
        return self


class AgentSkillSummary(BaseModel):
    """Bounded startup index entry; no full Skill or projection text is included."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_skill_id: str
    version: str
    title: str
    description: str
    authority: AgentSkillAuthority = "agent_method_only"
    execution_authority: AgentSkillExecutionAuthority = "none"
    owner_approved: Literal[True] = True
    content_digest: str
    extends: tuple[str, ...] = Field(default_factory=tuple)
    required_capabilities: tuple[str, ...] = Field(default_factory=tuple)
    optional_capabilities: tuple[str, ...] = Field(default_factory=tuple)
    applicable_routes: tuple[str, ...] = Field(default_factory=tuple)
    available_projections: tuple[AgentSkillProjectionName, ...] = Field(default_factory=tuple)


class AgentSkillProjection(BaseModel):
    """One explicitly requested, digest-bound projection loaded as read-only text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_skill_id: str
    version: str
    projection: AgentSkillProjectionName
    content: str = Field(min_length=1)
    content_digest: str
    projection_digest: str
    source: str = Field(min_length=1)


class AgentSkillDocument(BaseModel):
    """The full SKILL.md body, loaded only through an explicit call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_skill_id: str
    version: str
    content: str = Field(min_length=1)
    content_digest: str
    document_digest: str
    source: str = Field(min_length=1)


class AgentSkillSelectionGoalContext(BaseModel):
    """Bounded semantic Goal context shown to the responsible Agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_id: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1000)
    bindings: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    success_criteria: tuple[str, ...] = Field(default_factory=tuple, max_length=32)

    @field_validator("goal_id", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("bindings", "success_criteria", mode="before")
    @classmethod
    def normalize_text_items(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("selection Goal context collections must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)


class AgentSkillSelectionRequest(BaseModel):
    """Request for one Agent to select passive methods for its own responsibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    sid: str = Field(min_length=1, max_length=200)
    turn_id: str = Field(min_length=1, max_length=200)
    agent_role: AgentSkillProjectionName
    text: str = Field(min_length=1, max_length=8000)
    language: str = Field(default="und", min_length=1, max_length=40)
    goals: tuple[AgentSkillSelectionGoalContext, ...] = Field(
        default_factory=tuple,
        max_length=16,
    )
    context_summary: tuple[str, ...] = Field(default_factory=tuple, max_length=24)
    candidate_agent_skill_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=64,
    )

    @field_validator("sid", "turn_id", "text", "language", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("context_summary", mode="before")
    @classmethod
    def normalize_context_summary(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("context_summary must be an array")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())[:1000]
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)

    @field_validator("candidate_agent_skill_ids", mode="before")
    @classmethod
    def normalize_candidate_ids(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            _normalize_identifier_list(
                list(value or []),
                field_name="candidate_agent_skill_ids",
            )
        )

    @model_validator(mode="after")
    def validate_goal_ids(self) -> "AgentSkillSelectionRequest":
        goal_ids = [item.goal_id for item in self.goals]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("Agent Skill selection Goal IDs must be unique")
        return self


class AgentSkillSelectionModelItem(BaseModel):
    """Exact structured item authored by the responsible Agent's model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_skill_id: str
    version: str
    projection: AgentSkillProjectionName
    relevant_goal_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    rationale: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("agent_skill_id", mode="before")
    @classmethod
    def normalize_agent_skill_id(cls, value: Any) -> str:
        return _normalize_identifier(value, field_name="agent_skill_id")

    @field_validator("version", mode="before")
    @classmethod
    def validate_semantic_version(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not _SEMANTIC_VERSION.fullmatch(text):
            raise ValueError("version must be a valid semantic version")
        return text

    @field_validator("relevant_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("relevant_goal_ids must be an array")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class AgentSkillSelectionModelOutput(BaseModel):
    """Closed model contract for explicit no/one/multi-Skill selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: AgentSkillSelectionDecision
    selected_agent_skills: tuple[AgentSkillSelectionModelItem, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reason_summary: str = Field(min_length=1, max_length=800)

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_decision_shape(self) -> "AgentSkillSelectionModelOutput":
        if self.decision == "select_skills" and not self.selected_agent_skills:
            raise ValueError("select_skills requires at least one selected Agent Skill")
        if self.decision == "no_skill" and self.selected_agent_skills:
            raise ValueError("no_skill requires an empty selected_agent_skills array")
        ids = [item.agent_skill_id for item in self.selected_agent_skills]
        if len(ids) != len(set(ids)):
            raise ValueError("selected Agent Skill IDs must be unique")
        return self


class SelectedAgentSkill(BaseModel):
    """Host-validated selection with immutable package provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_skill_id: str
    version: str
    projection: AgentSkillProjectionName
    content_digest: str
    relevant_goal_ids: tuple[str, ...] = Field(default_factory=tuple)
    rationale: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("agent_skill_id", mode="before")
    @classmethod
    def normalize_agent_skill_id(cls, value: Any) -> str:
        return _normalize_identifier(value, field_name="agent_skill_id")

    @field_validator("version", mode="before")
    @classmethod
    def validate_semantic_version(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not _SEMANTIC_VERSION.fullmatch(text):
            raise ValueError("version must be a valid semantic version")
        return text

    @field_validator("content_digest", mode="before")
    @classmethod
    def validate_content_digest(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not _SHA256.fullmatch(text):
            raise ValueError("content_digest must use sha256:<64 lowercase hex>")
        return text

    @field_validator("relevant_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("relevant_goal_ids must be an array")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class PlanAgentSkillProvenance(BaseModel):
    """Content-free record of one Agent Skill projection that informed a Plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selection_id: str = Field(min_length=1, max_length=200)
    disclosure_id: str = Field(min_length=1, max_length=200)
    disclosure_digest: str
    selected_by_agent_role: AgentSkillProjectionName
    agent_skill_id: str
    version: str
    projection: AgentSkillProjectionName
    content_digest: str
    projection_digest: str
    relevant_goal_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    selection_rationale: str = Field(min_length=1, max_length=500)
    selection_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("agent_skill_id", mode="before")
    @classmethod
    def normalize_agent_skill_id(cls, value: Any) -> str:
        return _normalize_identifier(value, field_name="agent_skill_id")

    @field_validator("version", mode="before")
    @classmethod
    def validate_semantic_version(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not _SEMANTIC_VERSION.fullmatch(text):
            raise ValueError("version must be a valid semantic version")
        return text

    @field_validator(
        "disclosure_digest",
        "content_digest",
        "projection_digest",
        mode="before",
    )
    @classmethod
    def validate_digests(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not _SHA256.fullmatch(text):
            raise ValueError("Plan Agent Skill digests must use sha256:<64 lowercase hex>")
        return text

    @field_validator("relevant_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("relevant_goal_ids must be an array")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        if not out:
            raise ValueError("Plan Agent Skill provenance requires relevant Goal IDs")
        return tuple(out)

    @field_validator("selection_rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_planner_projection(self) -> "PlanAgentSkillProvenance":
        if self.selected_by_agent_role not in {"fast_planner", "deep_planner"}:
            raise ValueError("Canonical Plan provenance may be selected only by a planner")
        if self.projection != self.selected_by_agent_role:
            raise ValueError("Plan Agent Skill projection must match the selecting planner role")
        return self


class AgentSkillSelectionResolution(BaseModel):
    """Observable optional method selection; never execution evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    selection_id: str = Field(min_length=1)
    sid: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    agent_role: AgentSkillProjectionName
    decision: AgentSkillSelectionDecision
    status: AgentSkillSelectionStatus
    selected_agent_skills: tuple[SelectedAgentSkill, ...] = Field(default_factory=tuple)
    candidate_summaries: tuple[AgentSkillSummary, ...] = Field(default_factory=tuple)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_summary: str = Field(min_length=1, max_length=1000)
    candidate_total: int = Field(default=0, ge=0)
    candidate_truncated: bool = False
    model: str | None = None
    contract_repair_attempted: bool = False
    contract_repair_succeeded: bool = False
    error_type: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> "AgentSkillSelectionResolution":
        if self.decision == "select_skills" and not self.selected_agent_skills:
            raise ValueError("select_skills resolution requires selected Agent Skills")
        if self.decision == "no_skill" and self.selected_agent_skills:
            raise ValueError("no_skill resolution must not retain selected Agent Skills")
        if self.status == "selected" and self.decision != "select_skills":
            raise ValueError("status=selected requires decision=select_skills")
        if self.status != "selected" and self.decision != "no_skill":
            raise ValueError("non-selected statuses require decision=no_skill")
        candidate_by_id = {item.agent_skill_id: item for item in self.candidate_summaries}
        if len(candidate_by_id) != len(self.candidate_summaries):
            raise ValueError("candidate Agent Skill summaries must have unique IDs")
        selected_ids = [item.agent_skill_id for item in self.selected_agent_skills]
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("selected Agent Skill IDs must be unique")
        for item in self.selected_agent_skills:
            try:
                candidate = candidate_by_id[item.agent_skill_id]
            except KeyError as exc:
                raise ValueError(
                    f"selected Agent Skill {item.agent_skill_id!r} was not disclosed"
                ) from exc
            if item.version != candidate.version:
                raise ValueError("selected Agent Skill version does not match candidate")
            if item.content_digest != candidate.content_digest:
                raise ValueError("selected Agent Skill digest does not match candidate")
            if item.projection not in candidate.available_projections:
                raise ValueError("selected projection is not declared by the candidate")
            if item.projection != self.agent_role:
                raise ValueError("selected projection must match the responsible Agent role")
        return self


class AgentSkillDisclosureRequest(BaseModel):
    """Request to load only projections already selected by one responsible Agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    selection: AgentSkillSelectionResolution


class DisclosedAgentSkillProjection(BaseModel):
    """One bounded projection with exact selection and package provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selection_id: str = Field(min_length=1, max_length=200)
    selected_by_agent_role: AgentSkillProjectionName
    agent_skill_id: str
    version: str
    projection: AgentSkillProjectionName
    content: str = Field(min_length=1)
    content_digest: str
    projection_digest: str
    relevant_goal_ids: tuple[str, ...] = Field(default_factory=tuple)
    selection_rationale: str = Field(min_length=1, max_length=500)
    selection_confidence: float = Field(ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    char_count: int = Field(ge=1)

    @field_validator("agent_skill_id", mode="before")
    @classmethod
    def normalize_agent_skill_id(cls, value: Any) -> str:
        return _normalize_identifier(value, field_name="agent_skill_id")

    @field_validator("version", mode="before")
    @classmethod
    def validate_semantic_version(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not _SEMANTIC_VERSION.fullmatch(text):
            raise ValueError("version must be a valid semantic version")
        return text

    @field_validator("content_digest", "projection_digest", mode="before")
    @classmethod
    def validate_digests(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not _SHA256.fullmatch(text):
            raise ValueError("projection provenance digests must use sha256:<64 lowercase hex>")
        return text

    @field_validator("relevant_goal_ids", mode="before")
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("relevant_goal_ids must be an array")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)

    @model_validator(mode="after")
    def validate_projection_identity(self) -> "DisclosedAgentSkillProjection":
        if self.projection != self.selected_by_agent_role:
            raise ValueError("disclosed projection must match the selecting Agent role")
        if self.char_count != len(self.content):
            raise ValueError("char_count must equal the disclosed projection content length")
        return self


class AgentSkillDisclosureFailure(BaseModel):
    """Observable optional projection omission; never execution evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_skill_id: str | None = None
    version: str | None = None
    projection: AgentSkillProjectionName | None = None
    reason: AgentSkillDisclosureFailureReason
    message: str = Field(min_length=1, max_length=1000)


class AgentSkillDisclosureResolution(BaseModel):
    """Bounded model context loaded from one validated Skill selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    disclosure_id: str = Field(min_length=1, max_length=200)
    selection_id: str = Field(min_length=1, max_length=200)
    sid: str = Field(min_length=1, max_length=200)
    turn_id: str = Field(min_length=1, max_length=200)
    agent_role: AgentSkillProjectionName
    status: AgentSkillDisclosureStatus
    projections: tuple[DisclosedAgentSkillProjection, ...] = Field(default_factory=tuple)
    failures: tuple[AgentSkillDisclosureFailure, ...] = Field(default_factory=tuple)
    total_chars: int = Field(default=0, ge=0)
    max_projection_chars: int = Field(ge=1)
    max_total_chars: int = Field(ge=1)
    projection_count_limit: int = Field(ge=1)
    disclosure_digest: str

    @staticmethod
    def compute_disclosure_digest(
        *,
        selection_id: str,
        agent_role: AgentSkillProjectionName,
        status: AgentSkillDisclosureStatus,
        projections: tuple[DisclosedAgentSkillProjection, ...],
        failures: tuple[AgentSkillDisclosureFailure, ...],
        max_projection_chars: int,
        max_total_chars: int,
        projection_count_limit: int,
    ) -> str:
        payload = {
            "selection_id": selection_id,
            "agent_role": agent_role,
            "status": status,
            "projections": [
                {
                    "agent_skill_id": item.agent_skill_id,
                    "version": item.version,
                    "projection": item.projection,
                    "content_digest": item.content_digest,
                    "projection_digest": item.projection_digest,
                    "relevant_goal_ids": list(item.relevant_goal_ids),
                    "char_count": item.char_count,
                }
                for item in projections
            ],
            "failures": [item.model_dump(mode="json") for item in failures],
            "max_projection_chars": max_projection_chars,
            "max_total_chars": max_total_chars,
            "projection_count_limit": projection_count_limit,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @field_validator("disclosure_digest", mode="before")
    @classmethod
    def validate_disclosure_digest(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not _SHA256.fullmatch(text):
            raise ValueError("disclosure_digest must use sha256:<64 lowercase hex>")
        return text

    @model_validator(mode="after")
    def validate_disclosure_shape(self) -> "AgentSkillDisclosureResolution":
        if len(self.projections) > self.projection_count_limit:
            raise ValueError("disclosed projections exceed projection_count_limit")
        if self.total_chars != sum(item.char_count for item in self.projections):
            raise ValueError("total_chars must equal disclosed projection content lengths")
        if self.total_chars > self.max_total_chars:
            raise ValueError("disclosed projection content exceeds max_total_chars")
        if any(item.char_count > self.max_projection_chars for item in self.projections):
            raise ValueError("a disclosed projection exceeds max_projection_chars")
        ids = [item.agent_skill_id for item in self.projections]
        if len(ids) != len(set(ids)):
            raise ValueError("disclosed Agent Skill projections must have unique IDs")
        for item in self.projections:
            if item.selection_id != self.selection_id:
                raise ValueError("disclosed projection selection_id mismatch")
            if item.selected_by_agent_role != self.agent_role:
                raise ValueError("disclosed projection Agent role mismatch")
        if self.status == "loaded" and not self.projections:
            raise ValueError("status=loaded requires at least one projection")
        if self.status == "partial" and (not self.projections or not self.failures):
            raise ValueError("status=partial requires projections and failures")
        if self.status in {"no_skill", "unavailable"} and self.projections:
            raise ValueError(f"status={self.status} must not contain projections")
        if self.status == "no_skill" and self.failures:
            raise ValueError("status=no_skill must not contain projection failures")
        if self.status == "unavailable" and not self.failures:
            raise ValueError("status=unavailable requires at least one projection failure")
        expected_digest = self.compute_disclosure_digest(
            selection_id=self.selection_id,
            agent_role=self.agent_role,
            status=self.status,
            projections=self.projections,
            failures=self.failures,
            max_projection_chars=self.max_projection_chars,
            max_total_chars=self.max_total_chars,
            projection_count_limit=self.projection_count_limit,
        )
        if self.disclosure_digest != expected_digest:
            raise ValueError("disclosure_digest does not match the disclosure contents")
        return self


class AgentSkillLoadFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: AgentSkillLoadFailureReason
    source: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=1000)
    agent_skill_id: str | None = None


class AgentSkillRegistrySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    roots: tuple[str, ...] = Field(default_factory=tuple)
    package_files: tuple[str, ...] = Field(default_factory=tuple)
    summaries: tuple[AgentSkillSummary, ...] = Field(default_factory=tuple)
