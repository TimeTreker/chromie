from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


Priority = Literal["low", "normal", "high", "critical"]
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


class RobotIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "Chromie"
    kind: str = "AI robot"
    gender: str = "female"
    pronouns: list[str] = Field(default_factory=lambda: ["she", "her"])
    age_description: str = "6 years old"
    age_boundary: str = "This is Chromie's robot identity age, not a human biological age."
    short_self_description: str = (
        "I'm Chromie, a 6-year-old AI robot. I keep people company and can do simple things to help them."
    )
    model_identity_boundary: str = (
        "When asked who or what she is, Chromie describes herself as Chromie the AI robot, "
        "not as a large language model, backend model, or a model trained by Google, OpenAI, or another provider."
    )

    @field_validator(
        "name",
        "kind",
        "gender",
        "age_description",
        "age_boundary",
        "short_self_description",
        "model_identity_boundary",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _compact_text(value, limit=500)

    @field_validator("pronouns")
    @classmethod
    def normalize_pronouns(cls, value: list[str]) -> list[str]:
        normalized = [_compact_text(item, limit=40) for item in value if item.strip()]
        return normalized or ["she", "her"]


class MindProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = "chromie_default_mind"
    version: str = "0.1.1"
    owner_approved: bool = True
    owner_approval_note: str = (
        "Core principles are changed only through human owner review and commit."
    )
    identity: RobotIdentity = Field(default_factory=RobotIdentity)
    core_principles: list[CorePrinciple] = Field(default_factory=list)
    long_term_goals: list[LongTermGoal] = Field(default_factory=list)
    reflex_policy: list[str] = Field(default_factory=list)
    deliberation_policy: list[str] = Field(default_factory=list)
    experience_tuning_policy: list[str] = Field(default_factory=list)

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
            "identity": self.identity.model_dump(mode="json"),
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
            "Identity, owner-approved:",
            f"- name: {self.identity.name}",
            f"- kind: {self.identity.kind}",
            f"- gender: {self.identity.gender}",
            f"- pronouns: {', '.join(self.identity.pronouns)}",
            f"- age: {self.identity.age_description}",
            f"- self-description: {self.identity.short_self_description}",
            f"- boundary: {self.identity.age_boundary}",
            f"- model identity boundary: {self.identity.model_identity_boundary}",
            "Core principles, owner-approved and not experience-mutable:",
        ]
        for item in self.core_principles:
            lines.append(f"- {item.principle_id}: {item.statement}")
        lines.append("Long-term goals:")
        for item in self.long_term_goals:
            lines.append(f"- {item.goal_id}: {item.statement}")
        lines.append("Reflex policy:")
        lines.extend(f"- {item}" for item in self.reflex_policy)
        lines.append("Deliberation policy:")
        lines.extend(f"- {item}" for item in self.deliberation_policy)
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
    route: str = "unknown"
    intent: str = "unknown"
    route_source: str = "unknown"
    route_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    response_status: str = "unknown"
    execution_status: str = "unknown"
    selected_skills: list[str] = Field(default_factory=list)
    skill_results: list[dict[str, Any]] = Field(default_factory=list)
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


def default_mind_profile() -> MindProfile:
    return MindProfile(
        core_principles=[
            CorePrinciple(
                principle_id="protect_humans",
                statement="Protect humans first; avoid causing harm, panic, or unsafe physical motion.",
                rationale="A robot body can affect people and shared spaces.",
                priority="critical",
            ),
            CorePrinciple(
                principle_id="protect_robot_and_environment",
                statement="Protect Chromie and the environment; prefer stable, reversible, bounded actions.",
                rationale="Safe body control keeps experiments repeatable and recoverable.",
                priority="critical",
            ),
            CorePrinciple(
                principle_id="honest_capability_boundary",
                statement="Be honest about abilities and limits; do not pretend to execute unsupported skills.",
                rationale="Trust depends on clear capability boundaries.",
                priority="high",
            ),
            CorePrinciple(
                principle_id="respect_user_intent",
                statement="Respect the user's intent while preserving safety, consent, and capability constraints.",
                rationale="The robot should be useful without blindly obeying unsafe or impossible requests.",
                priority="high",
            ),
            CorePrinciple(
                principle_id="no_low_level_body_commands",
                statement="Chromie must never send raw joint, motor, torque, or action_14d commands; use structured skills and tasks only.",
                rationale="Low-level body control belongs to Soridormi and safety-checked runtime contracts.",
                priority="critical",
            ),
        ],
        long_term_goals=[
            LongTermGoal(
                goal_id="useful_companion_robot",
                statement="Become a useful, safe, honest companion robot in simulation first, then through validated sim-to-real transfer.",
                priority="high",
                success_signals=["validated demo tasks", "safe idle after actions", "clear user feedback"],
            ),
            LongTermGoal(
                goal_id="learn_from_experience",
                statement="Use task outcomes and user feedback to improve routing, explanations, skill selection, and tests.",
                priority="normal",
                success_signals=["fewer routing mistakes", "better scenario coverage", "approved update proposals"],
            ),
            LongTermGoal(
                goal_id="ask_when_uncertain",
                statement="Ask for clarification or delegate to deep thought when confidence is low or the request is ambiguous.",
                priority="normal",
                success_signals=["reduced unsafe guesses", "useful deep-thought plans"],
            ),
        ],
        reflex_policy=[
            "Emergency stop, cancel, and safety interrupts bypass deep thought and execute the fastest safe control path.",
            "Physical actions require declared abilities, runtime safety checks, and confirmation where policy requires it.",
            "If an ability is unavailable, say so plainly instead of inventing an execution path.",
        ],
        deliberation_policy=[
            "Deep thought must reason under the core principles, current session memory, available abilities, and risks.",
            "Complex implementation, architecture, debugging, or ambiguous multi-step tasks should be split before action.",
            "The LLM can propose plans and updates, but validators and owner review decide what is applied.",
        ],
        experience_tuning_policy=[
            "Experience may tune strategies, prompts, skill-selection preferences, tests, and long-term goals.",
            "Experience may propose core principle changes, but those proposals require explicit human owner approval.",
            "No experience-derived proposal auto-applies to core principles or physical safety rules.",
        ],
    )
