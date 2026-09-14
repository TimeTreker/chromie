"""Social Cognition's read-only input and complete outward-interaction decision.

Goal, Work, Evidence and Situation remain owned by their existing stores. These
DTOs carry a versioned projection, not a second state store or execution permit.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .core_interpretation import CognitiveResponsibilityProposal
from .interaction import reject_forbidden_low_level_fields
from .plan import (
    AuxiliaryPlanActivity, CommunicativeTruthStage, FastProgressKind, SocialCommunicationNeed,
    validate_communicative_activity_identity,
)
from .situation import (
    CognitiveOpportunity, SituationProjection, SituationalRelationshipMemoryCandidate, SituationalSelfMemoryCandidate,
)


class SocialCognitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=160)
    trigger: Literal["interpretation", "goal_state", "work_state", "evidence", "situation"]
    source_refs: list[str] = Field(min_length=1, max_length=64)
    language: str = "auto"
    responsibilities: list[CognitiveResponsibilityProposal] = Field(default_factory=list)
    interpretation_unresolved: list[str] = Field(default_factory=list)
    source_turn: dict[str, Any] = Field(default_factory=dict)
    goal_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    situation: SituationProjection | None = None
    opportunity: CognitiveOpportunity | None = None
    communication_needs: list[SocialCommunicationNeed] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_scope(self) -> "SocialCognitionRequest":
        reject_forbidden_low_level_fields(self.context)
        reject_forbidden_low_level_fields(self.source_turn)
        interaction = self.context.get("interaction_context", {})
        if not isinstance(interaction, dict):
            raise ValueError("Social Cognition interaction context must be an object")
        for name in ("events", "already_spoken", "pending_speech"):
            rows = interaction.get(name, [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Social Cognition interaction records must be object arrays")
            for row in rows:
                metadata = row.get("metadata", {})
                if not isinstance(metadata, dict):
                    raise ValueError("Social Cognition interaction metadata must be an object")
                ids = metadata.get("communicative_activity_ids", [])
                if not isinstance(ids, list) or any(not isinstance(value, str) or not value.strip() for value in ids):
                    raise ValueError("Social Cognition delivered Activity IDs must be nonempty strings")
        if self.trigger == "situation" and self.situation is None:
            raise ValueError("Situation-triggered communication requires trusted Situation")
        if self.trigger == "situation" and self.situation is not None:
            if not set(self.source_refs).issubset(item.reference_id for item in self.situation.source_refs):
                raise ValueError("Social Cognition source refs widen trusted Situation provenance")
        if self.opportunity is not None:
            opportunity = self.opportunity
            if not set(opportunity.goal_ids).issubset(self.goal_ids):
                raise ValueError("Social Cognition opportunity widens Goal scope")
            if not set(opportunity.source_refs).issubset(self.source_refs):
                raise ValueError("Social Cognition opportunity widens source provenance")
            if opportunity.situation_digest:
                if self.situation is None or opportunity.situation_digest != self.situation.digest:
                    raise ValueError("Social Cognition opportunity changed Situation digest")
                if opportunity.situation_signature != self.situation.interpretation_signature():
                    raise ValueError("Social Cognition opportunity changed Situation signature")
                if not set(opportunity.subject_refs).issubset(item.subject_ref for item in self.situation.interpretations):
                    raise ValueError("Social Cognition opportunity widens Situation subjects")
            if opportunity.recommended_cognition == "local":
                raise ValueError("local mechanical readiness must not invoke Social Cognition")
        if self.trigger == "interpretation" and not self.source_turn:
            raise ValueError("interpretation-triggered communication requires source provenance")
        refs = {item.local_ref for item in self.responsibilities}
        if len(refs) != len(self.responsibilities):
            raise ValueError("Social Cognition Responsibility refs must be unique")
        need_ids = [need.need_id for need in self.communication_needs]
        if len(set(need_ids)) != len(need_ids):
            raise ValueError("communication need IDs must be unique")
        for need in self.communication_needs:
            if not set(need.source_goal_ids).issubset(self.goal_ids):
                raise ValueError("communication need widens Goal scope")
            if not set(need.source_responsibility_refs).issubset(refs):
                raise ValueError("communication need widens Responsibility scope")
        return self

    def snapshot_digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SocialCommunicativeAct(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    activity_id: str = Field(min_length=1, max_length=160)
    text: str = Field(default="", max_length=2400)
    function: Literal["respond", "acknowledge", "inform", "ask", "repair", "nonverbal"]
    delivery_phase: Literal["immediate", "pre_action", "final"] = "immediate"
    truth_stage: CommunicativeTruthStage
    progress_kind: FastProgressKind | None = None
    source_responsibility_refs: list[str] = Field(default_factory=list)
    source_goal_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    addressed_need_ids: list[str] = Field(default_factory=list)
    repair_of_activity_ids: list[str] = Field(default_factory=list, max_length=8)
    auxiliary_activities: list[AuxiliaryPlanActivity] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_expression(self) -> "SocialCommunicativeAct":
        if not self.text.strip() and not self.auxiliary_activities:
            raise ValueError("communication requires language or an explicit embodied expression")
        if not self.text.strip() and self.function != "nonverbal":
            raise ValueError("a wordless act must declare its nonverbal delivery contract")
        if self.function == "nonverbal" and self.text.strip():
            raise ValueError("nonverbal acts cannot carry speech")
        if self.truth_stage == "post_evidence" and not self.evidence_refs:
            raise ValueError("post-evidence communication requires Evidence")
        if self.truth_stage == "pre_evidence" and self.evidence_refs:
            raise ValueError("prospective communication cannot cite result Evidence")
        if self.truth_stage == "pre_evidence" and self.progress_kind is None:
            raise ValueError("prospective communication requires its semantic progress kind")
        if self.truth_stage != "pre_evidence" and self.progress_kind is not None:
            raise ValueError("only prospective communication carries a progress kind")
        if bool(self.repair_of_activity_ids) != (self.function == "repair"):
            raise ValueError("only repair acts require delivered repair references")
        auxiliary_ids = [item.auxiliary_activity_id for item in self.auxiliary_activities]
        if len(set(auxiliary_ids)) != len(auxiliary_ids):
            raise ValueError("social-expression IDs must be unique")
        for item in self.auxiliary_activities:
            if item.anchor_kind != "communicative_act" or item.anchor_id != self.activity_id:
                raise ValueError("social expression must bind its exact communicative anchor")
        return self


class SocialCognitionOutput(BaseModel):
    """One primary semantic result; a depth request cannot contain a decision."""

    model_config = ConfigDict(extra="forbid")
    disposition: Literal["communicate", "silence", "deliberate"]
    activities: list[SocialCommunicativeAct] = Field(default_factory=list, max_length=8)
    reason_summary: str = Field(max_length=600)
    need_outcomes: dict[str, Literal["covered", "pending"]] = Field(default_factory=dict)
    memory_candidates: list[SituationalRelationshipMemoryCandidate] = Field(default_factory=list, max_length=4)
    self_memory_candidates: list[SituationalSelfMemoryCandidate] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_decision(self) -> "SocialCognitionOutput":
        if (self.disposition == "communicate") != bool(self.activities):
            raise ValueError("only communicate may carry a nonempty complete act decision")
        if self.disposition == "deliberate" and (self.memory_candidates or self.self_memory_candidates):
            raise ValueError("unresolved cognition cannot author a Memory decision")
        if self.disposition == "deliberate" and self.need_outcomes:
            raise ValueError("unresolved cognition cannot commit communication coverage")
        ids = [act.activity_id for act in self.activities]
        if len(ids) != len(set(ids)):
            raise ValueError("communicative Activity IDs must be unique")
        if sum(len(act.auxiliary_activities) for act in self.activities) > 3:
            raise ValueError("one Social Cognition decision permits at most three expressions")
        auxiliary_ids = [item.auxiliary_activity_id for act in self.activities for item in act.auxiliary_activities]
        if len(auxiliary_ids) != len(set(auxiliary_ids)):
            raise ValueError("social-expression IDs must be unique across the complete decision")
        return self


class SocialCognitionResolution(SocialCognitionOutput):
    request_id: str
    snapshot_digest: str = Field(min_length=64, max_length=64)
    semantic_owner: Literal["social_cognition"] = "social_cognition"
    model_call_count: int = Field(ge=1, le=2)

    @model_validator(mode="after")
    def validate_terminal_decision(self) -> "SocialCognitionResolution":
        if self.disposition == "deliberate":
            raise ValueError("resolved Social Cognition cannot defer to another owner")
        return self

    def validate_request(self, request: SocialCognitionRequest) -> None:
        """Host provenance check, independent of the Agent's own decoder checks."""
        if self.request_id != request.request_id or self.snapshot_digest != request.snapshot_digest():
            raise ValueError("Social Cognition changed the authoritative snapshot identity")
        scopes = {
            "source_responsibility_refs": {item.local_ref for item in request.responsibilities},
            "source_goal_ids": set(request.goal_ids),
            "evidence_refs": set(request.evidence_refs),
            "addressed_need_ids": {item.need_id for item in request.communication_needs},
        }
        needs = {need.need_id: need for need in request.communication_needs}
        if set(self.need_outcomes) != set(needs):
            raise ValueError("Social Cognition must account for every supplied communication need")
        for need_id, outcome in self.need_outcomes.items():
            if outcome == "covered" and not any(
                need_id in act.addressed_need_ids and act.text.strip() for act in self.activities
            ):
                raise ValueError("covered communication needs require an explicit verbal act")
        situation = request.situation
        if (self.memory_candidates or self.self_memory_candidates) and (
            request.trigger != "situation" or situation is None
        ):
            raise ValueError("this ingress grants no new Memory authorship")
        subjects = {item.subject_ref for item in situation.interpretations} if situation else set()
        for candidate in self.memory_candidates:
            if not set(candidate.source_refs).issubset(request.source_refs):
                raise ValueError("social Memory widens source provenance")
            if not set(candidate.subject_refs).issubset(subjects):
                raise ValueError("social Memory widens Situation subjects")
        for self_candidate in self.self_memory_candidates:
            if not set(self_candidate.source_refs).issubset(request.source_refs):
                raise ValueError("social self-context widens source provenance")
            if not set(self_candidate.subject_refs).issubset(subjects | {"self:chromie"}):
                raise ValueError("social self-context widens Situation subjects")
        for act in self.activities:
            if request.trigger == "interpretation" and not request.communication_needs and act.function in {"respond", "ask"}:
                raise ValueError("interpretation acknowledgement cannot fulfill an unestablished Work communication need")
            for name, values in scopes.items():
                if not set(getattr(act, name)).issubset(values):
                    raise ValueError(f"Social Cognition widened {name}")
            validate_communicative_activity_identity(
                activity_id=act.activity_id, text=act.text,
                interaction_context=request.context.get("interaction_context"),
                repair_of_activity_ids=act.repair_of_activity_ids,
            )
            for need_id in act.addressed_need_ids:
                need = needs[need_id]
                if not set(need.source_goal_ids).issubset(act.source_goal_ids):
                    raise ValueError("communication omitted its required Goal binding")
                if not set(need.source_responsibility_refs).issubset(act.source_responsibility_refs):
                    raise ValueError("communication omitted its required Responsibility binding")
                if need.kind in {"input", "confirmation"} and act.function != "ask":
                    raise ValueError("an input or confirmation need requires a question")
                if need.delivery_phase is not None and act.delivery_phase != need.delivery_phase:
                    raise ValueError("communication changed an upstream delivery-order requirement")
