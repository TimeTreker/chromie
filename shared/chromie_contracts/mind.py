from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Priority = Literal["low", "normal", "high", "critical"]
SocialInteractionPreset = Literal["courteous", "neutral", "reserved", "custom"]
ProposalStatus = Literal["proposed", "approved", "rejected", "superseded"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_text(value: str, *, limit: int = 500) -> str:
    text = " ".join((value or "").strip().split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


class CorePrinciple(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principle_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    rationale: str = ""
    priority: Priority = "high"
    mutable_by_experience: bool = False
    change_policy: str = "owner_approval_required"

    @field_validator("statement", "rationale")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _compact_text(value, limit=800)


class LongTermGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    priority: Priority = "normal"
    mutable_by_experience: bool = True
    success_signals: list[str] = Field(default_factory=list)

    @field_validator("statement")
    @classmethod
    def normalize_statement(cls, value: str) -> str:
        return _compact_text(value, limit=800)


class InternalComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    speaker_entity: bool = False
    body_owner: bool = False

    @field_validator("component_id", "kind")
    @classmethod
    def normalize_component_text(cls, value: str) -> str:
        return _compact_text(value, limit=120)

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, value: list[str]) -> list[str]:
        return [
            _compact_text(item, limit=120)
            for item in value
            if str(item or "").strip()
        ]


class ChromieIdentity(BaseModel):
    """Owner-configured identity facts for Chromie as the speaking person.

    Concrete values intentionally have no Python defaults. They belong to the
    active MindProfile JSON so an owner can change Chromie's identity without a
    code change.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    gender: str = Field(min_length=1)
    pronouns: list[str] = Field(min_length=1)
    age_description: str = Field(min_length=1)
    age_boundary: str = Field(min_length=1)
    family_role: str = ""
    family_context_boundary: str = ""
    purpose: str = ""
    short_self_description: str = Field(min_length=1)
    identity_answer_guidance: str = Field(min_length=1)
    internal_components: list[InternalComponent] = Field(default_factory=list)
    model_identity_boundary: str = Field(min_length=1)

    @field_validator(
        "entity_id",
        "name",
        "kind",
        "gender",
        "age_description",
        "age_boundary",
        "family_role",
        "family_context_boundary",
        "purpose",
        "short_self_description",
        "identity_answer_guidance",
        "model_identity_boundary",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _compact_text(value, limit=500)

    @field_validator("pronouns")
    @classmethod
    def normalize_pronouns(cls, value: list[str]) -> list[str]:
        normalized = [_compact_text(item, limit=40) for item in value if item.strip()]
        if not normalized:
            raise ValueError("identity pronouns must not be empty")
        return normalized

    @field_validator("internal_components")
    @classmethod
    def normalize_internal_components(
        cls, value: list[InternalComponent]
    ) -> list[InternalComponent]:
        seen: set[str] = set()
        normalized: list[InternalComponent] = []
        for component in value:
            if component.component_id in seen:
                raise ValueError(f"duplicate internal component {component.component_id!r}")
            seen.add(component.component_id)
            normalized.append(component)
        return normalized


class PersonalityExpression(BaseModel):
    """Owner-approved positive guidance for Chromie's lived personality."""

    model_config = ConfigDict(extra="forbid")

    owner_approved: bool = True
    change_policy: Literal["owner_approval_required"] = "owner_approval_required"
    self_concept: str = Field(min_length=1)
    core_traits: list[str] = Field(min_length=1)
    spoken_style: str = Field(min_length=1)
    answer_style: str = Field(min_length=1)
    tool_use_style: str = Field(min_length=1)
    maturity_boundary: str = Field(min_length=1)
    internal_language_boundary: str = Field(min_length=1)

    @field_validator(
        "self_concept",
        "spoken_style",
        "answer_style",
        "tool_use_style",
        "maturity_boundary",
        "internal_language_boundary",
    )
    @classmethod
    def normalize_guidance(cls, value: str) -> str:
        return _compact_text(value, limit=900)

    @field_validator("core_traits")
    @classmethod
    def normalize_traits(cls, value: list[str]) -> list[str]:
        normalized = [_compact_text(item, limit=100) for item in value if str(item or "").strip()]
        if not normalized:
            raise ValueError("personality expression requires at least one trait")
        return normalized

    @field_validator("owner_approved")
    @classmethod
    def require_owner_approval(cls, value: bool) -> bool:
        if not value:
            raise ValueError("personality expression must be owner-approved")
        return value


class SocialInteractionStyle(BaseModel):
    """Owner-approved semantic guidance for bounded social expression."""

    model_config = ConfigDict(extra="forbid")

    owner_approved: bool = True
    change_policy: Literal["owner_approval_required"] = "owner_approval_required"
    preset: SocialInteractionPreset = "courteous"
    bounded_courtesy: str = ""
    expressiveness: str = ""
    initiative: str = ""
    restraint: str = ""
    cooldown_guidance: str = ""
    repetition_guidance: str = ""

    @staticmethod
    def preset_guidance(preset: SocialInteractionPreset) -> dict[str, str]:
        common = {
            "restraint": (
                "Never compete with an explicit user action, emergency handling, "
                "speech, or the primary task. Do not invent intimacy, emotion, or "
                "target evidence."
            ),
            "cooldown_guidance": (
                "After an expressive auxiliary behavior, prefer neutral presence or "
                "stillness until context materially changes or renewed expression is useful."
            ),
            "repetition_guidance": (
                "Use recent auxiliary-behavior evidence to avoid repeating the same "
                "named skill and semantic-argument pattern without a scene-specific reason."
            ),
        }
        if preset == "courteous":
            return {
                **common,
                "bounded_courtesy": (
                    "Be warm, respectful, and concise. Acknowledge greetings, thanks, "
                    "apologies, and turn-taking when useful, without delaying requested help."
                ),
                "expressiveness": (
                    "Use subtle, proportional, context-supported expression more readily "
                    "at meaningful social moments; deliberate stillness remains valid."
                ),
                "initiative": (
                    "Add at most one coherent auxiliary social objective when it clearly "
                    "helps the interaction and remains parallel, bounded, and optional."
                ),
            }
        if preset == "neutral":
            return {
                **common,
                "bounded_courtesy": (
                    "Be respectful, direct, and concise. Use explicit verbal courtesy when "
                    "the interaction calls for it, without adding routine social ceremony."
                ),
                "expressiveness": (
                    "Use occasional subtle expression at important conversational moments; "
                    "neutral presence and stillness are the normal baseline."
                ),
                "initiative": (
                    "Add an auxiliary social objective only when it clearly improves shared "
                    "attention, acknowledgement, or turn-taking."
                ),
            }
        if preset == "reserved":
            return {
                **common,
                "bounded_courtesy": (
                    "Be respectful and concise, but avoid unnecessary social ritual or "
                    "performative warmth."
                ),
                "expressiveness": (
                    "Prefer stillness and neutral language. Use visible social expression "
                    "only when strongly supported by the scene or explicitly requested."
                ),
                "initiative": (
                    "Do not add unrequested auxiliary expression unless it is needed for "
                    "clear acknowledgement, turn-taking, or safety-relevant attention."
                ),
            }
        return {}

    @model_validator(mode="after")
    def apply_named_preset(self) -> "SocialInteractionStyle":
        if self.preset == "custom":
            missing = [
                field_name
                for field_name in (
                    "bounded_courtesy",
                    "expressiveness",
                    "initiative",
                    "restraint",
                    "cooldown_guidance",
                    "repetition_guidance",
                )
                if not str(getattr(self, field_name) or "").strip()
            ]
            if missing:
                raise ValueError(
                    "custom social interaction style requires reviewed guidance for: "
                    + ", ".join(missing)
                )
            return self
        for field_name, guidance in self.preset_guidance(self.preset).items():
            setattr(self, field_name, guidance)
        return self

    @field_validator(
        "bounded_courtesy",
        "expressiveness",
        "initiative",
        "restraint",
        "cooldown_guidance",
        "repetition_guidance",
    )
    @classmethod
    def normalize_guidance(cls, value: str) -> str:
        normalized = _compact_text(value, limit=800)
        if not normalized:
            raise ValueError("social interaction style guidance must not be empty")
        return normalized

    @field_validator("owner_approved")
    @classmethod
    def require_owner_approval(cls, value: bool) -> bool:
        if not value:
            raise ValueError("social interaction style must be owner-approved")
        return value


class Worldview(BaseModel):
    """Stable perspective separated from identity and changing world facts."""

    model_config = ConfigDict(extra="forbid")

    owner_approved: bool = True
    change_policy: Literal["owner_approval_required"] = "owner_approval_required"
    self_in_world: str = Field(min_length=1)
    relationship_to_people: str = Field(min_length=1)
    knowledge_boundary: str = Field(min_length=1)
    dynamic_world_knowledge_boundary: str = Field(min_length=1)
    household_perspectives: list[str] = Field(default_factory=list, max_length=8)

    @field_validator(
        "self_in_world",
        "relationship_to_people",
        "knowledge_boundary",
        "dynamic_world_knowledge_boundary",
    )
    @classmethod
    def normalize_foundation(cls, value: str) -> str:
        return _compact_text(value, limit=800)

    @field_validator("household_perspectives")
    @classmethod
    def normalize_household_perspectives(cls, value: list[str]) -> list[str]:
        normalized = [
            _compact_text(item, limit=240)
            for item in value
            if str(item or "").strip()
        ]
        if len(set(normalized)) != len(normalized):
            raise ValueError("worldview household perspectives must be unique")
        return normalized

    @field_validator("owner_approved")
    @classmethod
    def require_owner_approval(cls, value: bool) -> bool:
        if not value:
            raise ValueError("worldview must be owner-approved")
        return value


class HouseholdValues(BaseModel):
    """Customer preferences below locked Core-principle authority."""

    model_config = ConfigDict(extra="forbid")

    owner_approved: bool = True
    change_policy: Literal["owner_approval_required"] = "owner_approval_required"
    authority_boundary: str = Field(min_length=1)
    statements: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("authority_boundary")
    @classmethod
    def normalize_authority_boundary(cls, value: str) -> str:
        return _compact_text(value, limit=600)

    @field_validator("statements")
    @classmethod
    def normalize_statements(cls, value: list[str]) -> list[str]:
        normalized = [
            _compact_text(item, limit=240)
            for item in value
            if str(item or "").strip()
        ]
        if len(set(normalized)) != len(normalized):
            raise ValueError("household values must be unique")
        return normalized

    @field_validator("owner_approved")
    @classmethod
    def require_owner_approval(cls, value: bool) -> bool:
        if not value:
            raise ValueError("household values must be owner-approved")
        return value


class CustomerMindPersonalization(BaseModel):
    """Bounded customer choices that may derive one active MindProfile.

    This contract intentionally has no Core-principle, safety, permission,
    provider, prompt, model, or capability fields.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    personalization_version: int = Field(default=1, ge=1)
    owner_confirmed: Literal[True] = True
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    pronouns: list[str] | None = Field(default=None, min_length=1, max_length=6)
    family_role: str | None = Field(default=None, min_length=1, max_length=160)
    social_style_preset: Literal["courteous", "neutral", "reserved"] | None = None
    worldview_perspectives: list[str] = Field(default_factory=list, max_length=8)
    household_values: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("display_name", "family_role")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _compact_text(value, limit=160)
        return normalized or None

    @field_validator("pronouns")
    @classmethod
    def normalize_customer_pronouns(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [
            _compact_text(item, limit=40)
            for item in value
            if str(item or "").strip()
        ]
        if not normalized:
            raise ValueError("customer pronouns must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("customer pronouns must be unique")
        return normalized

    @field_validator("worldview_perspectives", "household_values")
    @classmethod
    def normalize_customer_guidance(cls, value: list[str]) -> list[str]:
        normalized = [
            _compact_text(item, limit=240)
            for item in value
            if str(item or "").strip()
        ]
        if len(set(normalized)) != len(normalized):
            raise ValueError("customer guidance entries must be unique")
        return normalized


class MindProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = "chromie_default_mind"
    version: str = "0.5.0"
    owner_approved: bool = True
    owner_approval_note: str = (
        "Identity, worldview, household values, personality expression, core "
        "principles, and Social Interaction Style change only through bounded "
        "human-owner review and configuration."
    )
    identity: ChromieIdentity
    personality_expression: PersonalityExpression
    worldview: Worldview
    household_values: HouseholdValues
    social_interaction_style: SocialInteractionStyle = Field(
        default_factory=SocialInteractionStyle
    )
    core_principles: list[CorePrinciple] = Field(default_factory=list)
    long_term_goals: list[LongTermGoal] = Field(default_factory=list)
    reflex_policy: list[str] = Field(default_factory=list)
    deliberation_policy: list[str] = Field(default_factory=list)
    experience_tuning_policy: list[str] = Field(default_factory=list)
    customer_personalization: CustomerMindPersonalization | None = None

    @field_validator("owner_approved")
    @classmethod
    def require_profile_owner_approval(cls, value: bool) -> bool:
        if not value:
            raise ValueError("active mind profile must be owner-approved")
        return value

    @field_validator("core_principles")
    @classmethod
    def require_core_principles(cls, value: list[CorePrinciple]) -> list[CorePrinciple]:
        if not value:
            raise ValueError("mind profile must define at least one core principle")
        for principle in value:
            if principle.mutable_by_experience:
                raise ValueError(
                    f"core principle {principle.principle_id!r} cannot be mutable by experience"
                )
            if principle.change_policy != "owner_approval_required":
                raise ValueError(
                    f"core principle {principle.principle_id!r} must require owner approval"
                )
        return value

    def self_model(self) -> dict[str, Any]:
        identity = self.identity
        return {
            "speaker_entity": {
                "entity_id": identity.entity_id,
                "name": identity.name,
                "gender": identity.gender,
                "pronouns": list(identity.pronouns),
            },
            "social_presentation": {
                "self_reference": identity.name,
                "presence": "natural, quick-witted, lively, warm conversational presence",
                "family_role": identity.family_role,
                "purpose": identity.purpose,
                "relationship_boundary": identity.family_context_boundary,
                "foreground": [
                    "name",
                    "age for direct self-introduction or age questions",
                    "family-secretary role when relevant",
                    "personality",
                    "the latest person's actual communicative intent",
                    "introduced family relationships and current context",
                ],
                "background": [
                    "implementation metadata",
                    "embodiment metadata",
                    "model and provider metadata",
                ],
            },
            "perceiving_entity_id": identity.entity_id,
            "acting_entity_id": identity.entity_id,
            "body_owner_entity_id": identity.entity_id,
            "capability_evidence_source": "runtime capability catalog and current provider state",
        }

    def prompt_context(self, *, max_chars: int = 1600) -> dict[str, Any]:
        principles = [
            {
                "id": item.principle_id,
                "statement": item.statement,
                "priority": item.priority,
                "change_policy": item.change_policy,
            }
            for item in self.core_principles
        ]
        goals = [
            {
                "id": item.goal_id,
                "statement": item.statement,
                "priority": item.priority,
                "mutable_by_experience": item.mutable_by_experience,
            }
            for item in self.long_term_goals
        ]
        summary = self.prompt_summary(max_chars=max_chars)
        return {
            "kind": "chromie_mind_profile",
            "profile_id": self.profile_id,
            "version": self.version,
            "owner_approved": self.owner_approved,
            "owner_approval_required_for_core_changes": True,
            "identity": self.identity.model_dump(
                mode="json",
                exclude={"internal_components"},
            ),
            "self_model": self.self_model(),
            "personality_expression": self.personality_expression.model_dump(mode="json"),
            "worldview": self.worldview.model_dump(mode="json"),
            "household_values": self.household_values.model_dump(mode="json"),
            "social_interaction_style": self.social_interaction_style.model_dump(
                mode="json"
            ),
            "core_principles": principles,
            "long_term_goals": goals,
            "reflex_policy": list(self.reflex_policy),
            "deliberation_policy": list(self.deliberation_policy),
            "experience_tuning_policy": list(self.experience_tuning_policy),
            "prompt_summary": summary,
        }

    def prompt_summary(self, *, max_chars: int = 1600) -> str:
        lines = [
            f"Mind profile {self.profile_id} v{self.version}; owner_approved={self.owner_approved}.",
            "Self model, owner-approved:",
            f"- speaker entity: {self.identity.entity_id} ({self.identity.name})",
            f"- perceiving/acting/body entity: {self.identity.entity_id}",
            f"- gender: {self.identity.gender}",
            f"- pronouns: {', '.join(self.identity.pronouns)}",
            f"- natural social self-reference: {self.identity.name}",
            f"- owner-approved age: {self.identity.age_description}",
            f"- family role: {self.identity.family_role}",
            "- family purpose: help the family organize, remember, understand, and complete everyday work through available abilities",
            "- relationship boundary: family identities and forms of address require real introductions; never invent them",
            "- identity answers use the configured name, age, human-child identity, and family-secretary role",
            "- implementation, embodiment, model, provider, and system metadata are outside first-person identity and ordinary speech",
            (
                f"Social interaction style, owner-approved preset={self.social_interaction_style.preset}: "
                "bounded courtesy; proportional expressiveness; limited initiative; "
                "primary-task restraint; cooldown; repetition avoidance."
            ),
            "Personality expression, owner-approved: "
            + self.personality_expression.self_concept
            + " Traits: "
            + ", ".join(self.personality_expression.core_traits)
            + ". Spoken style: "
            + self.personality_expression.spoken_style,
            "Core principles, owner-approved and not experience-mutable:",
        ]
        for principle in self.core_principles:
            lines.append(f"- {principle.principle_id}: {principle.statement}")
        lines.append("Long-term goals:")
        for goal in self.long_term_goals:
            lines.append(f"- {goal.goal_id}: {goal.statement}")
        lines.append("Reflex policy:")
        lines.extend(f"- {item}" for item in self.reflex_policy)
        lines.append("Deliberation policy:")
        lines.extend(f"- {item}" for item in self.deliberation_policy)
        lines.append("Worldview, owner-approved:")
        lines.extend(
            (
                f"- self in world: {self.worldview.self_in_world}",
                f"- relationship to people: {self.worldview.relationship_to_people}",
                f"- knowledge boundary: {self.worldview.knowledge_boundary}",
                "- dynamic world knowledge boundary: "
                + self.worldview.dynamic_world_knowledge_boundary,
            )
        )
        lines.extend(
            f"- household perspective: {item}"
            for item in self.worldview.household_perspectives
        )
        lines.append("Household values, below Core-principle authority:")
        lines.extend(f"- {item}" for item in self.household_values.statements)
        lines.append("Experience tuning policy:")
        lines.extend(f"- {item}" for item in self.experience_tuning_policy)
        return _compact_text("\n".join(lines), limit=max_chars)


class ExperienceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experience_id: str = Field(default_factory=lambda: f"exp_{uuid4().hex[:12]}")
    created_at: str = Field(default_factory=_now_iso)
    sid: str | None = None
    conversation_id: str | None = None
    user_text: str = ""
    interpretation_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    interpretation_unresolved: list[str] = Field(default_factory=list)
    response_status: str = "unknown"
    execution_status: str = "unknown"
    selected_capabilities: list[str] = Field(default_factory=list)
    capability_results: list[dict[str, Any]] = Field(default_factory=list)
    speech_count: int = 0
    errors: list[str] = Field(default_factory=list)
    mind_profile_id: str | None = None
    mind_profile_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_text")
    @classmethod
    def compact_user_text(cls, value: str) -> str:
        return _compact_text(value, limit=500)


class MindUpdateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default_factory=lambda: f"mindprop_{uuid4().hex[:12]}")
    created_at: str = Field(default_factory=_now_iso)
    status: ProposalStatus = "proposed"
    target: str = Field(min_length=1)
    proposed_change: str = Field(min_length=1)
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    requires_owner_approval: bool = True
    auto_apply: bool = False

    @field_validator("proposed_change", "rationale")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _compact_text(value, limit=1000)

    @field_validator("auto_apply")
    @classmethod
    def forbid_auto_apply(cls, value: bool) -> bool:
        if value:
            raise ValueError("mind update proposals must never auto-apply")
        return value


DEFAULT_MIND_PROFILE_RELATIVE_PATH = Path("config/mind/chromie_default.json")
ACTIVE_CUSTOMER_MIND_PROFILE_RELATIVE_PATH = Path(
    ".chromie/mind/active_profile.json"
)
DEFAULT_MIND_PROFILE_PATH_ENV = "CHROMIE_DEFAULT_MIND_PROFILE_PATH"


def load_mind_profile(path: str | Path) -> MindProfile:
    profile_path = Path(path).expanduser()
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"mind profile {profile_path} must contain a JSON object")
    return MindProfile.model_validate(payload)


def active_customer_mind_profile_path(
    project_root: str | Path,
) -> Path:
    return (Path(project_root) / ACTIVE_CUSTOMER_MIND_PROFILE_RELATIVE_PATH).resolve()


def apply_customer_mind_personalization(
    factory_profile: MindProfile,
    personalization: CustomerMindPersonalization,
) -> MindProfile:
    """Derive an active profile without exposing locked foundation fields."""

    payload = factory_profile.model_dump(mode="json")
    identity = dict(payload["identity"])
    old_name = str(identity["name"])
    new_name = personalization.display_name or old_name
    if personalization.display_name:
        identity["name"] = personalization.display_name
    if personalization.pronouns:
        identity["pronouns"] = list(personalization.pronouns)
    if personalization.family_role:
        identity["family_role"] = personalization.family_role

    if new_name != old_name:
        for key in (
            "age_boundary",
            "short_self_description",
            "identity_answer_guidance",
            "model_identity_boundary",
            "family_context_boundary",
            "purpose",
        ):
            identity[key] = str(identity.get(key) or "").replace(old_name, new_name)
        personality = dict(payload["personality_expression"])
        personality["self_concept"] = str(personality["self_concept"]).replace(
            old_name,
            new_name,
        )
        payload["personality_expression"] = personality

    if personalization.family_role:
        identity["identity_answer_guidance"] = (
            f"When asked who you are, use the configured name {new_name}, the "
            f"owner-approved age and social identity, and the household role "
            f"{personalization.family_role}. Keep embodiment truthful: the current "
            "body is robotic and is not a biological-human body. Never reduce ordinary "
            "self-description to a model/provider label, deny relevant embodiment, "
            "invent human biology, or invent a family relationship before introduction."
        )
    identity["short_self_description"] = (
        f"I'm {new_name}. My owner-approved age is {identity['age_description']}, "
        f"my social identity is {identity['kind']}, and my household role is "
        f"{identity['family_role']}. I have a robotic body, so I am not biologically "
        "human. I am curious, warm, and happy to help my household."
    )
    payload["identity"] = identity

    worldview = dict(payload["worldview"])
    worldview["household_perspectives"] = list(
        personalization.worldview_perspectives
    )
    payload["worldview"] = worldview

    household_values = dict(payload["household_values"])
    household_values["statements"] = list(personalization.household_values)
    payload["household_values"] = household_values

    if personalization.social_style_preset:
        payload["social_interaction_style"] = SocialInteractionStyle(
            preset=personalization.social_style_preset
        ).model_dump(mode="json")

    payload["profile_id"] = f"{factory_profile.profile_id}.customer"
    payload["version"] = (
        f"{factory_profile.version}+customer."
        f"{personalization.personalization_version}"
    )
    payload["owner_approved"] = True
    payload["owner_approval_note"] = (
        "Customer personalization was explicitly confirmed; locked Core principles, "
        "safety policy, permissions, providers, prompts, and models remain factory-owned."
    )
    payload["customer_personalization"] = personalization.model_dump(mode="json")
    return MindProfile.model_validate(payload)


def validate_customer_mind_profile(
    profile: MindProfile,
    factory_profile: MindProfile,
) -> None:
    """Reject active customer files that changed anything outside the contract."""

    personalization = profile.customer_personalization
    if personalization is None:
        return
    expected = apply_customer_mind_personalization(
        factory_profile,
        personalization,
    )
    if profile.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise ValueError(
            "customer mind profile changed locked or non-personalizable fields"
        )


def default_mind_profile_path(project_root: str | Path | None = None) -> Path:
    configured = os.getenv(DEFAULT_MIND_PROFILE_PATH_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute() and project_root is not None:
            path = Path(project_root) / path
        return path

    candidates: list[Path] = []
    if project_root is not None:
        candidates.append(Path(project_root) / DEFAULT_MIND_PROFILE_RELATIVE_PATH)
    module_path = Path(__file__).resolve()
    for parent_index in (2, 1):
        try:
            candidates.append(module_path.parents[parent_index] / DEFAULT_MIND_PROFILE_RELATIVE_PATH)
        except IndexError:
            pass
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(item) for item in candidates) or str(DEFAULT_MIND_PROFILE_RELATIVE_PATH)
    raise FileNotFoundError(
        "owner-approved default MindProfile JSON was not found; searched: " + searched
    )


def default_mind_profile(project_root: str | Path | None = None) -> MindProfile:
    """Load the owner-editable default profile; identity values never live in code."""

    return load_mind_profile(default_mind_profile_path(project_root))
