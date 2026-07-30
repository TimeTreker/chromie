from __future__ import annotations

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
