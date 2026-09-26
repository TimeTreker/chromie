from __future__ import annotations

import json

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryKind = Literal[
    "preference", "fact", "note", "instruction", "constraint", "relationship", "other"
]
MemoryCognitiveRole = Literal["umi", "ga", "planner"]

_UMI_DEFAULT_MEMORY_KINDS = frozenset({
    "preference",
    "instruction",
    "constraint",
    "relationship",
    "correction",
    "entity",
    "ownership",
    "person_identity",
    "person_relationship",
    "shared_experience",
    "relationship_interpretation",
    "interaction_boundary",
})


def resolve_memory_cognitive_roles(
    *,
    kind: str,
    cognitive_roles: list[str] | tuple[str, ...] | None = None,
) -> tuple[MemoryCognitiveRole, ...]:
    """Resolve which cognitive roles may consume one already-activated entry.

    Persistence and activation remain separate from role visibility.  Planner and GA
    may consume the broad Active Memory projection; UMI is conservative by default
    and receives only memory classes that can help resolve human meaning.  A trusted
    producer can opt a semantically meaningful fact/note into UMI explicitly.
    """

    if cognitive_roles is not None:
        normalized: list[MemoryCognitiveRole] = []
        for raw in cognitive_roles:
            role = str(raw or "").strip().casefold()
            if role not in {"umi", "ga", "planner"}:
                continue
            if role not in normalized:
                normalized.append(cast(MemoryCognitiveRole, role))
        if normalized:
            return tuple(normalized)
    normalized_kind = str(kind or "note").strip().casefold()
    roles: list[MemoryCognitiveRole] = ["ga", "planner"]
    if normalized_kind in _UMI_DEFAULT_MEMORY_KINDS:
        roles.insert(0, "umi")
    return tuple(roles)


def project_active_memory_for_role(
    entries: list[dict[str, Any]],
    *,
    role: MemoryCognitiveRole,
) -> list[dict[str, Any]]:
    """Return whole Active Memory entries visible to one cognitive role."""

    projected: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        roles = resolve_memory_cognitive_roles(
            kind=str(entry.get("kind") or "note"),
            cognitive_roles=(
                list(entry.get("cognitive_roles") or [])
                if isinstance(entry.get("cognitive_roles"), list)
                else None
            ),
        )
        if role in roles:
            projected.append(entry)
    return projected


class MemoryUpdateProposal(BaseModel):
    """Model-authored, Host-validated memory mutation proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["remember", "forget", "clear_profile"] = "remember"
    scope: Literal["session", "profile"] = "session"
    kind: MemoryKind
    text: str = Field(min_length=1, max_length=1000)
    key: str | None = Field(default=None, max_length=160)
    persistence_policy: Literal["ephemeral", "durable_with_explicit_consent"] = "ephemeral"
    consent_basis: Literal["explicit_current_turn"] | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_memory_authority(self) -> "MemoryUpdateProposal":
        durable = self.persistence_policy == "durable_with_explicit_consent"
        if self.scope == "session":
            if self.operation != "remember" or durable:
                raise ValueError("session memory supports only ephemeral remember")
            if self.consent_basis is not None or self.retention_days is not None:
                raise ValueError("session memory must not carry durable consent fields")
            return self
        if not durable or self.consent_basis != "explicit_current_turn":
            raise ValueError(
                "profile memory requires durable_with_explicit_consent and explicit_current_turn"
            )
        if self.operation == "forget" and not self.key:
            raise ValueError("profile forget requires a stable memory key")
        if self.operation == "remember" and not self.key:
            raise ValueError("durable profile memory requires a stable memory key")
        if self.operation == "remember" and self.retention_days is None:
            raise ValueError("durable profile memory requires bounded retention_days")
        if self.operation != "remember" and self.retention_days is not None:
            raise ValueError("forget and clear_profile must not set retention_days")
        return self

    @field_validator("text", "key", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.strip().split())
        return normalized or None


def role_memory_context(context: dict[str, Any], *, role: Literal["umi", "ga", "planner"]) -> str:
    """Project whole entries already activated and privacy-filtered by Memory.

    Cognitive scope and persistence remain independent. Never read raw stores or
    reconstruct missing facts from a summary at this model-facing boundary.
    """
    memory = context.get("session_memory")
    entries = []
    if isinstance(memory, dict):
        active = memory.get("active_memory")
        if isinstance(active, dict) and isinstance(active.get("entries"), list):
            entries = active["entries"]
        else:
            # Compatibility for snapshots produced before Active Memory became an
            # explicit cognitive projection. This is not a second semantic path:
            # extracted_memory already contains the same relevance-ranked entries.
            entries = memory.get("extracted_memory", [])
    entries = project_active_memory_for_role(
        entries if isinstance(entries, list) else [],
        role=role,
    )
    selected: list[dict[str, Any]] = []
    budget = 2400 if role == "umi" else 4800
    fields = (
        "id", "scope", "kind", "key", "text", "confidence", "relation",
        "subject_refs", "source_person_refs", "source_ref_ids", "source_turn_ids",
        "source_sids", "audience_refs", "disclosure_scope", "persistence_policy",
        "consent_basis", "expires_ms", "memory_tier", "memory_backing",
        "cognitive_roles",
    )
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or not entry.get("text"):
            continue
        item = {key: entry[key] for key in fields if key in entry}
        encoded = json.dumps([*selected, item], ensure_ascii=False, separators=(",", ":"))
        if len(encoded) <= budget:
            selected.append(item)
        if len(selected) >= (4 if role == "umi" else 8):
            break
    if not selected:
        return ""
    purpose = {
        "umi": (
            "Interpret only what the current user expression means. Use this role-scoped Memory "
            "for referent/entity identity, stable semantic preferences, corrections, discourse continuity, "
            "and other human-meaning context. Do not promote remembered world state, object location, "
            "task outcome, or old observation into current WHAT unless the current expression actually "
            "refers to that remembered meaning."
        ),
        "ga": "Relate authoritative UMI Responsibilities to current and lasting Goal continuity.",
        "planner": (
            "Plan from canonical meaning, current Runtime Work and Evidence, with relevant remembered context. "
            "Consider relevant activated Memory before creating new Work, but require current trusted Evidence or exact verified-memory retrieval for factual completion."
        ),
    }[role]
    return (
        "Active Memory JSON (activated context only):\n"
        + json.dumps(selected, ensure_ascii=False, separators=(",", ":"))
        + "\n" + purpose
        + " Active Memory is a relevance projection, not a persistence tier or a new store. "
        "memory_tier describes whether an activated item came from volatile working RAM or "
        "long-term durable storage; cognitive_roles describes which cognitive owners may consume "
        "the entry after activation; scope describes relevance and persistence_policy describes "
        "retention policy. A long-term item is intentionally more stable, not more authoritative. "
        "Neither memory nor its confidence replaces current meaning, Goal state, Runtime state, "
        "execution Evidence, or authorization. Never turn remembered context into a new Responsibility or infer completion from it.\n\n"
    )
