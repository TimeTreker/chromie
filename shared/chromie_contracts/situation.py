from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SituationSourceKind = Literal[
    "evidence",
    "runtime_state",
    "interaction_state",
    "memory",
    "other",
]


class SituationConditionRef(BaseModel):
    """Reference to one unresolved condition owned by an existing Goal/context artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_id: str = Field(min_length=1, max_length=160)
    condition_id: str = Field(min_length=1, max_length=200)
    resolution: str = Field(default="unknown", min_length=1, max_length=120)

    @field_validator("goal_id", "condition_id", "resolution", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class SituationSourceRef(BaseModel):
    """Reference to an authority-owned source used by current Situation.

    Situation may be grounded by immutable Evidence or by independently trusted
    live state such as provider Runtime state.  The source remains authoritative;
    Situation keeps only the bounded reference needed to reconstruct its current
    interpretation and never promotes live state into Evidence by naming it here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SituationSourceKind = "other"
    reference_id: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=160)

    @field_validator("reference_id", "owner", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


SituationEpistemicStatus = Literal[
    "established",
    "provisional",
    "conflicted",
    "stale",
    "unknown",
]


class SituationInterpretation(BaseModel):
    """One bounded, revisable current implication of authority-owned state.

    The tuple is intentionally small.  ``subject_ref`` identifies what the
    interpretation is about, ``relation`` says which current aspect matters, and
    ``value`` records only the bounded implication needed for cognition.  The
    source objects themselves stay in their existing owners.

    This contract does not authorize Goal changes, Work, speech, or effects.  A
    provisional interpretation can disappear on the next reconstruction without
    rewriting the source that grounded it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation_id: str = Field(min_length=1, max_length=200)
    subject_ref: str = Field(min_length=1, max_length=200)
    relation: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=240)
    epistemic_status: SituationEpistemicStatus = "provisional"
    relevance_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    source_refs: list[str] = Field(min_length=1, max_length=8)

    @field_validator(
        "interpretation_id",
        "subject_ref",
        "relation",
        "value",
        mode="before",
    )
    @classmethod
    def normalize_interpretation_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("relevance_goal_ids", "source_refs", mode="before")
    @classmethod
    def normalize_interpretation_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Situation interpretation list fields must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out


class SituationProjection(BaseModel):
    """Bounded, revisable, reconstructable live cognitive interpretation.

    Situation does not own the referenced Goal, Evidence, Memory, provider, or
    runtime facts.  It records both the bounded working-set identity and the
    current implications that matter to cognition, with exact source provenance.
    Multiple cognitive roles can therefore reason from one current interpretation
    without copying source payloads or inventing a second truth owner.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[3] = 3
    turn_id: str = Field(min_length=1, max_length=160)
    revision: int = Field(default=1, ge=1)
    focus_goal_ids: list[str] = Field(default_factory=list, max_length=8)
    discourse_focus_ids: list[str] = Field(default_factory=list, max_length=8)
    unresolved_conditions: list[SituationConditionRef] = Field(
        default_factory=list,
        max_length=12,
    )
    source_refs: list[SituationSourceRef] = Field(default_factory=list, max_length=16)
    interpretations: list[SituationInterpretation] = Field(
        default_factory=list,
        max_length=12,
    )
    digest: str = Field(min_length=64, max_length=64)

    @field_validator("turn_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator(
        "focus_goal_ids",
        "discourse_focus_ids",
        mode="before",
    )
    @classmethod
    def normalize_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Situation ID fields must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @staticmethod
    def calculate_digest(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"digest"})

    @model_validator(mode="after")
    def validate_digest(self) -> "SituationProjection":
        source_refs = {item.reference_id for item in self.source_refs}
        focus_goals = set(self.focus_goal_ids)
        for interpretation in self.interpretations:
            if not set(interpretation.source_refs).issubset(source_refs):
                raise ValueError(
                    "Situation interpretations must reference projection source refs"
                )
            if not set(interpretation.relevance_goal_ids).issubset(focus_goals):
                raise ValueError(
                    "Situation interpretation Goal IDs must be in projection focus"
                )
        expected = self.calculate_digest(self.semantic_payload())
        if self.digest != expected:
            raise ValueError("Situation digest does not match projection content")
        return self

    @classmethod
    def create(cls, **kwargs: Any) -> "SituationProjection":
        payload = cls.model_construct(digest="0" * 64, **kwargs).model_dump(
            mode="json",
            exclude={"digest"},
        )
        return cls(digest=cls.calculate_digest(payload), **kwargs)

    def prompt_projection(self) -> dict[str, Any]:
        """Return the complete bounded projection; referenced sources stay external."""

        return self.model_dump(mode="json")

    def interpretation_signature(self) -> str:
        """Return semantic identity for the current interpretations only.

        Turn IDs, revisions, source-event identities, and Goal relevance are deliberately
        excluded.  Two trusted observations that restate the same current social/world
        meaning therefore share one signature even when their transport revisions differ.
        The signature is delivery/readiness accounting only; it is not Evidence and does
        not make the interpretation true.
        """

        payload = sorted(
            (
                {
                    "subject_ref": item.subject_ref,
                    "relation": item.relation,
                    "value": item.value,
                    "epistemic_status": item.epistemic_status,
                }
                for item in self.interpretations
            ),
            key=lambda item: (
                item["subject_ref"],
                item["relation"],
                item["value"],
                item["epistemic_status"],
            ),
        )
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class SituationRevisionObservation(BaseModel):
    """Trusted external Situation delta admitted for continuous cognition.

    The observation names its independently trusted source and the bounded source
    references used by the supplied projection.  Those sources can include Evidence
    or live Runtime state; live state is never relabeled as Evidence merely to wake
    cognition. Runtime may derive a CognitiveOpportunity only when the projection
    actually changed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    observation_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=160)
    source_revision: int = Field(ge=1)
    goal_ids: list[str] = Field(default_factory=list, max_length=8)
    source_refs: list[str] = Field(min_length=1, max_length=16)
    projection: SituationProjection

    @field_validator("observation_id", "source_id", mode="before")
    @classmethod
    def normalize_observation_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("goal_ids", "source_refs", mode="before")
    @classmethod
    def normalize_observation_lists(cls, value: Any) -> list[str]:

        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected an array")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in out:
                out.append(text)
        return out

    @model_validator(mode="after")
    def validate_projection_binding(self) -> "SituationRevisionObservation":
        projection_goals = set(self.projection.focus_goal_ids)
        if not set(self.goal_ids).issubset(projection_goals):
            raise ValueError("Situation observation Goal IDs must be in projection focus")
        projection_sources = {
            item.reference_id for item in self.projection.source_refs
        }
        if not set(self.source_refs).issubset(projection_sources):
            raise ValueError(
                "Situation observation source refs must be present in projection"
            )
        interpretation_sources = {
            source_ref
            for item in self.projection.interpretations
            for source_ref in item.source_refs
        }
        if not interpretation_sources.issubset(projection_sources):
            raise ValueError(
                "Situation interpretations must reference projection source refs"
            )
        return self


class GoalTimeCondition(BaseModel):
    """Durable Planner-authored wake condition for one existing Goal.

    The condition is structured provenance, never a deadline parsed by Host from
    free-form Goal text. ConversationState owns persistence/consumption while the
    same Planner owns what to do when the condition becomes due.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    condition_id: str = Field(min_length=1, max_length=200)
    goal_id: str = Field(min_length=1, max_length=160)
    due_at_ms: int = Field(ge=1)
    source_plan_id: str = Field(min_length=1, max_length=200)
    source_responsibility_refs: list[str] = Field(min_length=1, max_length=8)
    reason_code: str = Field(default="planner_time_condition", min_length=1, max_length=120)

    @field_validator("condition_id", "goal_id", "source_plan_id", "reason_code", mode="before")
    @classmethod
    def normalize_condition_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("source_responsibility_refs", mode="before")
    @classmethod
    def normalize_responsibility_refs(cls, value: Any) -> list[str]:

        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("expected an array")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in out:
                out.append(text)
        return out

CognitiveOpportunityTrigger = Literal[
    "execution_outcome",
    "situation_revision",
    "time_condition",
    "provider_state",
]
CognitiveOpportunityMode = Literal["local", "fast", "slow"]


class CognitiveOpportunity(BaseModel):
    """Ephemeral readiness signal derived from a meaningful trusted state transition.

    This is not durable Mind state and is never an authority over the referenced
    Goal, Evidence, Situation, or next Activity. Goal-bound opportunities retain exact
    Goal provenance. Goal-free Situation opportunities instead retain exact trusted
    Situation/source provenance; they must never fabricate a Goal or UserTurn merely
    to wake cognition. The object lives only long enough to decide whether no cognition,
    local handling, fast cognition, or slower/deeper cognition is useful. A Runtime
    callback never becomes a response/action decision merely by creating this object.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    opportunity_id: str = Field(min_length=1, max_length=200)
    trigger: CognitiveOpportunityTrigger
    goal_ids: list[str] = Field(default_factory=list, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
    source_refs: list[str] = Field(default_factory=list, max_length=16)
    subject_refs: list[str] = Field(default_factory=list, max_length=16)
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    recommended_cognition: CognitiveOpportunityMode = "slow"
    situation_digest: str = Field(default="", max_length=64)
    situation_signature: str = Field(default="", max_length=64)

    @field_validator(
        "opportunity_id",
        "situation_digest",
        "situation_signature",
        mode="before",
    )
    @classmethod
    def normalize_opportunity_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator(
        "goal_ids",
        "evidence_refs",
        "source_refs",
        "subject_refs",
        "reason_codes",
        mode="before",
    )
    @classmethod
    def normalize_opportunity_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("CognitiveOpportunity list fields must be arrays")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @model_validator(mode="after")
    def validate_readiness_provenance(self) -> "CognitiveOpportunity":
        if self.trigger == "situation_revision" and not self.goal_ids:
            if not self.situation_digest:
                raise ValueError(
                    "goal-free Situation opportunity requires situation_digest"
                )
            if len(self.situation_signature) != 64:
                raise ValueError(
                    "goal-free Situation opportunity requires situation_signature"
                )
            if not self.source_refs:
                raise ValueError(
                    "goal-free Situation opportunity requires trusted source_refs"
                )
        if not self.goal_ids and not self.evidence_refs and not self.source_refs:
            raise ValueError(
                "CognitiveOpportunity requires Goal, Evidence, or Situation provenance"
            )
        return self

    @classmethod
    def create(
        cls,
        *,
        trigger: CognitiveOpportunityTrigger,
        goal_ids: list[str],
        evidence_refs: list[str] | None = None,
        source_refs: list[str] | None = None,
        subject_refs: list[str] | None = None,
        reason_codes: list[str] | None = None,
        recommended_cognition: CognitiveOpportunityMode = "slow",
        situation_digest: str = "",
        situation_signature: str = "",
    ) -> "CognitiveOpportunity":
        payload = {
            "trigger": trigger,
            "goal_ids": goal_ids,
            "evidence_refs": list(evidence_refs or []),
            "source_refs": list(source_refs or []),
            "subject_refs": list(subject_refs or []),
            "reason_codes": list(reason_codes or []),
            "recommended_cognition": recommended_cognition,
            "situation_digest": situation_digest,
            "situation_signature": situation_signature,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return cls(
            opportunity_id=(
                f"cognitive_opportunity_{hashlib.sha256(encoded).hexdigest()[:20]}"
            ),
            trigger=trigger,
            goal_ids=goal_ids,
            evidence_refs=list(evidence_refs or []),
            source_refs=list(source_refs or []),
            subject_refs=list(subject_refs or []),
            reason_codes=list(reason_codes or []),
            recommended_cognition=recommended_cognition,
            situation_digest=situation_digest,
            situation_signature=situation_signature,
        )

    def prompt_projection(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


SituationalCognitionDisposition = Literal["silence", "communicate"]
SituationalSpeechAct = Literal[
    "greeting",
    "acknowledge",
    "inquire",
    "inform",
    "respond",
]


class SituationalCommunicativeAct(BaseModel):
    """One bounded goal-free communicative act authored by the same Cognitive Core.

    The act is deliberately incapable of carrying Capability Work, Goal mutation, or
    effect authorization. Trusted Runtime binds Situation provenance around this exact
    model-authored wording; the Host may validate or suppress it but never rewrite it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    activity_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=600)
    speech_act: SituationalSpeechAct

    @field_validator("activity_id", "text", mode="before")
    @classmethod
    def normalize_activity_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class SituationalCognitionRequest(BaseModel):
    """One bounded Goal-free cognition invocation from trusted current Situation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    opportunity: CognitiveOpportunity
    situation: SituationProjection
    language: str = Field(default="auto", min_length=1, max_length=32)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: Any) -> str:
        return " ".join(str(value or "auto").strip().split()) or "auto"

    @model_validator(mode="after")
    def validate_goal_free_binding(self) -> "SituationalCognitionRequest":
        if self.opportunity.trigger != "situation_revision":
            raise ValueError(
                "Situational cognition requires a situation_revision opportunity"
            )
        if self.opportunity.goal_ids:
            raise ValueError(
                "Situational cognition is only for Goal-free readiness"
            )
        if self.situation.focus_goal_ids:
            raise ValueError(
                "Situational cognition Situation must not carry focused Goals"
            )
        if self.opportunity.situation_digest != self.situation.digest:
            raise ValueError(
                "Situational cognition opportunity must bind the supplied Situation digest"
            )
        if (
            self.opportunity.situation_signature
            != self.situation.interpretation_signature()
        ):
            raise ValueError(
                "Situational cognition opportunity must bind the supplied Situation signature"
            )
        situation_sources = {item.reference_id for item in self.situation.source_refs}
        if not self.opportunity.source_refs:
            raise ValueError(
                "Situational cognition requires trusted Situation source provenance"
            )
        if not set(self.opportunity.source_refs).issubset(situation_sources):
            raise ValueError(
                "Situational cognition source_refs must exist in supplied Situation"
            )
        situation_subjects = {
            item.subject_ref for item in self.situation.interpretations
        }
        if self.opportunity.subject_refs and not set(
            self.opportunity.subject_refs
        ).issubset(situation_subjects):
            raise ValueError(
                "Situational cognition subject_refs must exist in supplied Situation"
            )
        return self


class SituationalCognitionResolution(BaseModel):
    """Canonical result of one Goal-free situational cognition invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    opportunity_id: str = Field(min_length=1, max_length=200)
    situation_digest: str = Field(min_length=64, max_length=64)
    source_refs: list[str] = Field(min_length=1, max_length=16)
    subject_refs: list[str] = Field(default_factory=list, max_length=16)
    disposition: SituationalCognitionDisposition
    activity: SituationalCommunicativeAct | None = None
    reason_summary: str = Field(default="", max_length=600)

    @field_validator(
        "opportunity_id",
        "situation_digest",
        "reason_summary",
        mode="before",
    )
    @classmethod
    def normalize_resolution_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("source_refs", "subject_refs", mode="before")
    @classmethod
    def normalize_resolution_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("situational cognition refs must be arrays")
        out: list[str] = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in out:
                out.append(text)
        return out

    @model_validator(mode="after")
    def validate_disposition_activity(self) -> "SituationalCognitionResolution":
        if self.disposition == "silence" and self.activity is not None:
            raise ValueError("silence situational cognition must not carry an activity")
        if self.disposition == "communicate" and self.activity is None:
            raise ValueError("communicate situational cognition requires an activity")
        return self
