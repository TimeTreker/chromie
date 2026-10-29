"""Social Cognition's read-only input and complete outward-interaction decision.

Goal, Work, Evidence and Situation remain owned by their existing stores. These
DTOs carry a versioned projection, not a second state store or execution permit.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .core_interpretation import CognitiveResponsibilityProposal, UserMeaningUncertainty
from .interaction import reject_forbidden_low_level_fields
from .semantic_artifact import SemanticArtifactLineage, semantic_artifact_ref
from .text import normalize_whitespace
from .user_turn import user_turn_prohibits_speech
from .plan import (
    AuxiliaryPlanActivity, CommunicativeTruthStage, FastProgressKind, SocialCommunicationNeed,
    validate_communicative_activity_identity,
)
from .situation import (
    CognitiveOpportunity, SituationProjection, SituationalRelationshipMemoryCandidate, SituationalSelfMemoryCandidate,
    trusted_target_evidence,
)


class SocialCognitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=160)
    trigger: Literal["interpretation", "goal_state", "work_state", "evidence", "situation"]
    source_refs: list[str] = Field(min_length=1, max_length=64)
    language: str = "auto"
    responsibilities: list[CognitiveResponsibilityProposal] = Field(default_factory=list)
    meaning_uncertainties: list[UserMeaningUncertainty] = Field(default_factory=list)
    source_turn: dict[str, Any] = Field(default_factory=dict)
    goal_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    situation: SituationProjection | None = None
    opportunity: CognitiveOpportunity | None = None
    communication_needs: list[SocialCommunicationNeed] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    @property
    def semantic_artifact_lineage(self) -> SemanticArtifactLineage:
        raw = self.context.get("semantic_artifact_lineage") if isinstance(self.context, dict) else None
        if raw is None:
            return SemanticArtifactLineage()
        return SemanticArtifactLineage.model_validate(raw)

    @model_validator(mode="after")
    def validate_source_scope(self) -> "SocialCognitionRequest":
        reject_forbidden_low_level_fields(self.context)
        reject_forbidden_low_level_fields(self.source_turn)
        interaction = self.context.get("interaction_context", {})
        if not isinstance(interaction, dict):
            raise ValueError("Social Cognition interaction context must be an object")
        for name in (
            "events", "already_spoken", "pending_speech", "prior_delivered_speech"
        ):
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
        if self.trigger == "interpretation" and not self.source_turn:
            raise ValueError("interpretation-triggered communication requires source provenance")
        refs = {item.local_ref for item in self.responsibilities}
        if len(refs) != len(self.responsibilities):
            raise ValueError("Social Cognition Responsibility refs must be unique")
        for uncertainty in self.meaning_uncertainties:
            if set(uncertainty.responsibility_refs) - refs:
                raise ValueError(
                    "Social Cognition meaning uncertainty widens Responsibility scope"
                )
        lineage = self.semantic_artifact_lineage
        responsibility_lineage = lineage.by_kind("responsibility")
        if responsibility_lineage and self.responsibilities:
            turn_id = str(self.source_turn.get("turn_id") or "").strip()
            if not turn_id:
                raise ValueError("Social Cognition lineage requires source turn identity")
            for item in self.responsibilities:
                lineage.require(semantic_artifact_ref(
                    item, artifact_kind="responsibility",
                    artifact_id=f"{turn_id}:{item.local_ref}",
                ))
        plan_projection = self.context.get("canonical_plan_resolution")
        if lineage.refs and isinstance(plan_projection, dict):
            plan_id = str(plan_projection.get("plan_id") or "").strip()
            if plan_id and not any(
                item.artifact_kind == "planner_plan" and item.artifact_id == plan_id
                for item in lineage.refs
            ):
                raise ValueError("Social Cognition lineage is missing its canonical Plan")
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
    auxiliary_activities: list[AuxiliaryPlanActivity] = Field(default_factory=list)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        # The same words every transport stage carries (ResponseStage normalizes too):
        # live 2026-10-15 a trailing space made the exact-words join reject a correct
        # answer as "changed words" and the person heard nothing.
        return normalize_whitespace(value)

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


class SocialPreferenceMemoryCandidate(BaseModel):
    """A lasting preference the person stated about how Chromie talks or acts with them.

    Owner decision 2026-10-23: Social Cognition, which owns how Chromie communicates, keeps it;
    Host stores it as session Memory and later turns read it from Active Memory (live: "以后先用
    中文回答我" was agreed aloud, then an English question was answered in English).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    text: str = Field(min_length=3, max_length=160)
    source_responsibility_refs: list[str] = Field(min_length=1, max_length=4)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_preference_text(cls, value: Any) -> str:
        return " ".join(str(value or "").split())


MEMORY_KEY_PATTERN = r"^[a-z][a-z_]{1,40}$"


class SocialPersonalFact(BaseModel):
    """Whether the person's own words told a lasting fact about their life, such as where they work.

    Owner decisions 2026-10-26/27: Chromie keeps it as that person's Memory, the way a friend
    remembers, without asking; `stated` is decided first so a turn without such a fact writes
    nothing else.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    stated: bool
    key: str | None = Field(default=None, pattern=MEMORY_KEY_PATTERN)
    text: str | None = Field(default=None, min_length=3, max_length=160)
    source_responsibility_refs: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_stated_fact(self) -> "SocialPersonalFact":
        if self.stated != bool(self.key and self.text and self.source_responsibility_refs):
            raise ValueError("a stated personal fact has a key, text and source; an unstated one has none")
        return self


ATTEND_TO_PERSON_CAPABILITY_ID = "soridormi.attend_to_person"
SOCIAL_SKILL_CONTEXT_KEY = "long_running_social_skill"


class LongRunningSocialSkillDecision(BaseModel):
    """Start, re-pose, keep or stop the long-running social skill (owner decisions 2026-10-25/28).

    Soridormi runs the skill across the conversation (it follows the person every frame and
    means nothing by itself); Social Cognition chooses only the skill, the person and when it
    starts and stops. While it runs, keep leaves it as it is; otherwise no decision does.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["attend", "keep", "stop"]
    capability_id: Literal["soridormi.attend_to_person"] | None = None
    target_ref: str | None = Field(default=None, min_length=1, max_length=120)
    posture: Literal["listening", "thinking"] | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "LongRunningSocialSkillDecision":
        attending = (self.capability_id, self.target_ref, self.posture)
        if self.action == "attend" and None in attending:
            raise ValueError("attending names the skill, the person and a posture")
        if self.action != "attend" and attending != (None, None, None):
            raise ValueError(f"{self.action} names nothing else")
        return self


def social_skill_options(context: Any) -> dict[str, Any]:
    """What Social Cognition may decide about the long-running social skill now.

    The Host's lifecycle state says whether Soridormi offers the skill and what runs; a
    person can be attended to only as trusted live perception shows them.
    """

    context = context if isinstance(context, dict) else {}
    state = context.get(SOCIAL_SKILL_CONTEXT_KEY)
    state = state if isinstance(state, dict) else {}
    target = trusted_target_evidence(context) if state.get("available") is True else {}
    refs = [str(target["target"]["target_ref"])] if (
        target.get("available") and target.get("source") == "live_perception"
        and (target.get("target") or {}).get("target_ref")
    ) else []
    return {"attend_target_refs": refs, "can_stop": state.get("active") is True}


def social_skill_decision_error(decision: LongRunningSocialSkillDecision, context: Any) -> str | None:
    options = social_skill_options(context)
    if decision.action != "attend":
        return None if options["can_stop"] else f"no long-running social skill is running to {decision.action}"
    if decision.target_ref not in options["attend_target_refs"]:
        return "the long-running social skill attends only to a person trusted perception shows"
    return None


class SocialCognitionOutput(BaseModel):
    """One primary semantic result; a depth request cannot contain a decision."""

    model_config = ConfigDict(extra="forbid")
    disposition: Literal["communicate", "silence", "deliberate"]
    activities: list[SocialCommunicativeAct] = Field(default_factory=list)
    reason_summary: str = Field(max_length=600)
    need_outcomes: dict[str, Literal["covered", "pending"]] = Field(default_factory=dict)
    memory_candidates: list[SituationalRelationshipMemoryCandidate] = Field(default_factory=list, max_length=4)
    self_memory_candidates: list[SituationalSelfMemoryCandidate] = Field(default_factory=list, max_length=4)
    preference_memory_candidates: list[SocialPreferenceMemoryCandidate] = Field(default_factory=list, max_length=2)
    personal_fact: SocialPersonalFact | None = None
    social_skill: LongRunningSocialSkillDecision | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "SocialCognitionOutput":
        if (self.disposition == "communicate") != bool(self.activities):
            raise ValueError("only communicate may carry a nonempty complete act decision")
        if self.disposition == "deliberate" and self.social_skill is not None:
            raise ValueError("unresolved cognition cannot decide the long-running social skill")
        if self.disposition == "deliberate" and (
            self.memory_candidates or self.self_memory_candidates or self.preference_memory_candidates
            or (self.personal_fact and self.personal_fact.stated)
        ):
            raise ValueError("unresolved cognition cannot author a Memory decision")
        if self.disposition == "deliberate" and self.need_outcomes:
            raise ValueError("unresolved cognition cannot commit communication coverage")
        ids = [act.activity_id for act in self.activities]
        if len(ids) != len(set(ids)):
            raise ValueError("communicative Activity IDs must be unique")
        auxiliary_ids = [item.auxiliary_activity_id for act in self.activities for item in act.auxiliary_activities]
        if len(auxiliary_ids) != len(set(auxiliary_ids)):
            raise ValueError("social-expression IDs must be unique across the complete decision")
        return self


def previously_addressed_need_ids(context: Any) -> set[str]:
    """Needs that an earlier pending or delivered communicative act already addressed."""

    interaction = context.get("interaction_context") if isinstance(context, dict) else None
    addressed: set[str] = set()
    for key in ("events", "already_spoken", "pending_speech", "prior_delivered_speech"):
        for row in (interaction or {}).get(key, []) if isinstance(interaction, dict) else []:
            metadata = row.get("metadata") if isinstance(row, dict) else None
            for source in (metadata, row):
                ids = source.get("addressed_need_ids") if isinstance(source, dict) else None
                if isinstance(ids, list):
                    addressed.update(item for item in ids if isinstance(item, str))
    return addressed


def earlier_act_need_bindings(context: Any) -> dict[str, set[str]]:
    """Each pending or delivered communicative act's identity and the needs it was bound to."""

    interaction = context.get("interaction_context") if isinstance(context, dict) else None
    bindings: dict[str, set[str]] = {}
    for key in ("events", "already_spoken", "pending_speech", "prior_delivered_speech"):
        for row in (interaction or {}).get(key, []) if isinstance(interaction, dict) else []:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            ids = metadata.get("communicative_activity_ids") or row.get("communicative_activity_ids") or []
            addressed = metadata.get("addressed_need_ids")
            for identity in ids if isinstance(ids, list) else []:
                bindings.setdefault(str(identity).strip(), set()).update(
                    item for item in addressed or [] if isinstance(item, str))
    return bindings


def earlier_acknowledgement_ids(context: Any) -> set[str]:
    """Identities of pending or delivered acts spoken as an acknowledgement or wordless expression.

    Said before an answer existed, such an act cannot later become that answer (live 2026-10-25:
    the ingress "嗯，我看看。" was reused to cover "家里还有水吗？").
    """

    interaction = context.get("interaction_context") if isinstance(context, dict) else None
    found: set[str] = set()
    for key in ("events", "already_spoken", "pending_speech", "prior_delivered_speech"):
        for row in (interaction or {}).get(key, []) if isinstance(interaction, dict) else []:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            if (row.get("speech_act") or metadata.get("speech_act")) in {"acknowledge", "nonverbal"}:
                ids = metadata.get("communicative_activity_ids") or row.get("communicative_activity_ids") or []
                found.update(str(identity).strip() for identity in ids if isinstance(ids, list))
    return found


def earlier_speech_replies(request: "SocialCognitionRequest") -> dict[str, set[str]]:
    """Earlier acknowledgements that replied to speech Responsibilities only, with the refs they cited.

    Replying to what the person said ("辛苦了，快休息一下吧。" for "我今天好累啊。") is the whole
    answer to that speech Responsibility, not a receipt said before an answer existed. Live
    2026-10-29: barred from covering the Planner's answer need for it, the same words were
    spoken again as a new act in 19 of 156 turns with speech.
    """

    speech_refs = {item.local_ref for item in request.responsibilities if item.output_mode == "speech"}
    acknowledgements = earlier_acknowledgement_ids(request.context)
    interaction = request.context.get("interaction_context")
    replies: dict[str, set[str]] = {}
    for key in ("events", "already_spoken", "pending_speech"):
        for row in (interaction or {}).get(key, []) if isinstance(interaction, dict) else []:
            metadata = row.get("metadata") if isinstance(row, dict) else None
            if not isinstance(metadata, dict):
                continue
            cited = {str(ref) for ref in metadata.get("source_responsibility_refs") or []}
            if cited and cited <= speech_refs:
                for identity in metadata.get("communicative_activity_ids") or []:
                    if str(identity).strip() in acknowledgements:
                        replies.setdefault(str(identity).strip(), set()).update(cited)
    return replies


def acknowledgement_answers(need: Any, identity: str, replies: dict[str, set[str]]) -> bool:
    """Whether an earlier acknowledgement may cover this answer need (see earlier_speech_replies)."""

    return need.kind == "answer" and bool(need.source_responsibility_refs) and set(
        need.source_responsibility_refs) <= replies.get(identity, set())


def completed_work_need_ids(request: "SocialCognitionRequest") -> set[str]:
    """Needs that report Work Evidence; only words written with that Evidence can cover them.

    Live 2026-10-24: a progress line said "Monday" before the clock Evidence reached Social
    Cognition, then was reused unchanged to cover the clock answer (Saturday).
    """

    return {need.need_id for need in request.communication_needs
            if need.facts.get("completed_work_dependencies")}


def must_say_now_need_ids(request: "SocialCognitionRequest") -> set[str]:
    """Limitations and value questions Social Cognition must say in this turn.

    A Planner result whose Goal is unavailable or refused, Chromie's own value
    decline, or the value question that replaces a withheld answer is the reply the
    person is waiting for: leaving it pending left them with only an acknowledgement
    (live 2026-10-11). A need an earlier act already said is not repeated, and a
    protective silence request is honored.
    """

    if user_turn_prohibits_speech(request.context.get("user_turn_envelope")):
        return set()
    said = previously_addressed_need_ids(request.context)
    return {
        need.need_id for need in request.communication_needs
        if need.kind == "result" and need.need_id not in said and (
            (need.owner == "planner" and need.facts.get("disposition") in {"unavailable", "refused"})
            or (need.owner == "runtime" and bool(need.facts.get("value_declined")))
        )
    } | {
        need.need_id for need in request.communication_needs
        if need.kind == "input" and need.owner == "runtime" and need.need_id not in said
        and bool(need.facts.get("value_question"))
    }


def value_withheld_need_ids(request: "SocialCognitionRequest") -> set[str]:
    """Answers Chromie's Value Judgment withheld: they are not said this turn."""

    return {need.need_id for need in request.communication_needs if need.facts.get("value_withheld") is True}


def value_review_responsibility_refs(request: "SocialCognitionRequest") -> set[str]:
    """Speech UMI marked value_review: answered only after Value Judgment.

    Live 2026-10-10: a requested pretense was performed at the interpretation trigger
    before any Planner or Value Judgment decision. Unmarked speech stays immediate.
    """

    return {item.local_ref for item in request.responsibilities if item.value_review}


def uncertain_task_responsibility_refs(request: "SocialCognitionRequest") -> set[str]:
    """Task Responsibilities whose meaning UMI left uncertain: SC may ask about them at ingress.

    Owner decision 2026-10-22: a person who says "把那个拿给我" with two bottles in view is
    asked "which one?" right away, as a person would. The question claims no Work result and is
    context-grounded. A turn waiting for Value Judgment still receives only an acknowledgement.
    """

    if value_review_responsibility_refs(request):
        return set()
    task_refs = {item.local_ref for item in request.responsibilities if item.output_mode != "speech"}
    named = {ref for item in request.meaning_uncertainties for ref in item.responsibility_refs}
    return task_refs & named


def asks_about_uncertain_meaning(act: "SocialCommunicativeAct", request: "SocialCognitionRequest") -> bool:
    """The act is the question that settles task meaning UMI left uncertain."""

    cited = set(act.source_responsibility_refs)
    return act.function == "ask" and bool(cited) and cited <= uncertain_task_responsibility_refs(request)


def need_asks_uncertain_meaning(need: Any) -> bool:
    """An input need whose every gap is meaning UMI left uncertain.

    The ingress question about that meaning may already have asked it (owner decision
    2026-10-22), before the Planner's need existed.
    """

    gaps = need.facts.get("information_gaps") if need.kind == "input" else None
    return isinstance(gaps, list) and bool(gaps) and all(
        isinstance(gap, dict) and gap.get("source_kind") == "unresolved_meaning" for gap in gaps)


def answer_awaited(prior: "SocialCognitionResolution", request: "SocialCognitionRequest") -> bool:
    """A same-turn SC result already asked about every Responsibility of this request.

    The question stands until the person answers; committed Goal state adds nothing to say
    (live 2026-10-22: a goal_state SC read "你是说那个牛奶瓶吗？" as the answer, "是的，就是那个。").
    """

    asked = {ref for act in prior.activities if asks_about_uncertain_meaning(act, request)
             for ref in act.source_responsibility_refs}
    return bool(asked) and {item.local_ref for item in request.responsibilities} <= asked


def pre_evidence_act_violation(act: "SocialCommunicativeAct", request: "SocialCognitionRequest") -> str | None:
    """After ingress, words about task Work without its Evidence or a supplied need are pre-evidence.

    Owner decision 2026-10-22: before Evidence Chromie says only that a request is received,
    being checked or in progress. Live, a work-state turn said "It's Wednesday" before the clock
    read, then repeated it after Evidence said Thursday. Interpretation ingress keeps its own rule.
    """

    if request.trigger == "interpretation" or act.function in {"nonverbal", "acknowledge"} or act.addressed_need_ids:
        return None
    if not any(item.output_mode != "speech" for item in request.responsibilities):
        return None
    if act.truth_stage in {"pre_evidence", "post_evidence"}:
        return None
    speech_refs = {item.local_ref for item in request.responsibilities if item.output_mode == "speech"}
    cited = set(act.source_responsibility_refs)
    if cited and cited.issubset(speech_refs):
        return None
    return "before its Evidence, task Work is spoken of only as received, being checked or in progress"


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
        required_failure_need_ids = {
            need.need_id for need in request.communication_needs
            if need.owner == "runtime" and need.kind == "result"
            and need.facts.get("status") == "failed"
            and need.facts.get("required_result_update") is True
        }
        if required_failure_need_ids and (
            self.disposition != "communicate"
            or any(self.need_outcomes.get(need_id) != "covered" for need_id in required_failure_need_ids)
        ):
            raise ValueError("terminal Work failure result update must be communicated and covered")
        limitation_need_ids = must_say_now_need_ids(request)
        if limitation_need_ids and (
            self.disposition != "communicate"
            or any(self.need_outcomes.get(need_id) != "covered" for need_id in limitation_need_ids)
        ):
            raise ValueError("a limitation or declined result must be said and covered in this turn")
        if any(self.need_outcomes.get(need_id) == "covered" for need_id in value_withheld_need_ids(request)):
            raise ValueError("an answer withheld by Value Judgment cannot be said")
        reviewed_refs = value_review_responsibility_refs(request)
        if any(act.function not in {"acknowledge", "nonverbal"} and not act.addressed_need_ids
               and set(act.source_responsibility_refs) & reviewed_refs for act in self.activities):
            raise ValueError("speech marked value_review is said only through a reviewed communication need")
        for need_id, outcome in self.need_outcomes.items():
            if outcome == "covered" and not any(
                need_id in act.addressed_need_ids and act.text.strip() for act in self.activities
            ):
                raise ValueError("covered communication needs require an explicit verbal act")
        if self.preference_memory_candidates and (request.trigger != "interpretation" or any(
            not set(item.source_responsibility_refs) <= {resp.local_ref for resp in request.responsibilities}
            for item in self.preference_memory_candidates
        )):
            raise ValueError("a stated preference is kept only at ingress from the person's own Responsibility")
        if self.social_skill is not None:
            skill_error = social_skill_decision_error(self.social_skill, request.context)
            if skill_error:
                raise ValueError(skill_error)
        own_refs = {resp.local_ref for resp in request.responsibilities}
        fact = self.personal_fact if self.personal_fact and self.personal_fact.stated else None
        if fact and (request.trigger != "interpretation" or not set(fact.source_responsibility_refs) <= own_refs):
            raise ValueError("a personal fact is kept only at ingress from the person's own Responsibility")
        evidence_need_ids = completed_work_need_ids(request)
        earlier_bindings_all = earlier_act_need_bindings(request.context)
        earlier_bindings = earlier_bindings_all if evidence_need_ids else {}
        acknowledgements = earlier_acknowledgement_ids(request.context)
        speech_replies = earlier_speech_replies(request)
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
            early = pre_evidence_act_violation(act, request)
            if early:
                raise ValueError(early)
            if request.trigger == "interpretation" and not request.communication_needs and act.function in {"respond", "ask"}:
                turn_local_refs = {
                    item.local_ref
                    for item in request.responsibilities
                    if item.continuity_scope == "turn"
                }
                cited_refs = set(act.source_responsibility_refs)
                if not asks_about_uncertain_meaning(act, request) and (
                    not cited_refs or not cited_refs.issubset(turn_local_refs - value_review_responsibility_refs(request))
                ):
                    raise ValueError(
                        "interpretation-triggered respond/ask cannot fulfill an unestablished "
                        "Work communication need unless it cites only turn-local "
                        "Responsibility provenance"
                    )
            for name, values in scopes.items():
                if not set(getattr(act, name)).issubset(values):
                    raise ValueError(f"Social Cognition widened {name}")
            validate_communicative_activity_identity(
                activity_id=act.activity_id, text=act.text,
                interaction_context=request.context.get("interaction_context"),
                repair_of_activity_ids=act.repair_of_activity_ids,
            )
            if act.activity_id in earlier_bindings and (
                set(act.addressed_need_ids) & evidence_need_ids) - earlier_bindings[act.activity_id]:
                raise ValueError("words said before Work Evidence cannot report it")
            for need_id in act.addressed_need_ids:
                need = needs[need_id]
                if not set(need.source_goal_ids).issubset(act.source_goal_ids):
                    raise ValueError("communication omitted its required Goal binding")
                if not set(need.source_responsibility_refs).issubset(act.source_responsibility_refs):
                    raise ValueError("communication omitted its required Responsibility binding")
                if need.kind in {"input", "confirmation"} and act.function != "ask":
                    raise ValueError("an input or confirmation need requires a question")
                if (need.kind in {"answer", "result"} and act.activity_id in acknowledgements
                        and need_id not in earlier_bindings_all.get(act.activity_id, set())
                        and not acknowledgement_answers(need, act.activity_id, speech_replies)):
                    raise ValueError("an earlier acknowledgement cannot be reused as an answer or result")
                if need.delivery_phase is not None and act.delivery_phase != need.delivery_phase:
                    raise ValueError("communication changed an upstream delivery-order requirement")


class SocialStartupGreetingRequest(BaseModel):
    """Startup context for Social Cognition's optional wake-up line.

    Startup has no user turn, Goal, Work or Evidence. The Host supplies only the
    owner-approved Mind (``context.mind``), trusted local clock facts and the
    delivery bounds; Social Cognition alone decides whether to speak and what.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=160)
    language: str = Field(min_length=1, max_length=32)
    max_chars: int = Field(default=24, ge=4, le=80)
    local_time: dict[str, str] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scope(self) -> "SocialStartupGreetingRequest":
        reject_forbidden_low_level_fields(self.context)
        mind = self.context.get("mind")
        if not isinstance(mind, dict) or mind.get("owner_approved") is not True:
            raise ValueError("the startup greeting requires the owner-approved Mind")
        return self


class SocialStartupGreetingOutput(BaseModel):
    """Social Cognition's model-authored startup decision."""

    model_config = ConfigDict(extra="forbid")

    disposition: Literal["communicate", "silence"]
    text: str = Field(default="", max_length=80)
    reason_summary: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def validate_text(self) -> "SocialStartupGreetingOutput":
        self.text = normalize_whitespace(self.text)
        if self.disposition == "communicate" and not self.text:
            raise ValueError("a startup greeting must carry its exact words")
        if self.disposition == "silence" and self.text:
            raise ValueError("startup silence carries no words")
        return self


class SocialStartupGreetingResolution(SocialStartupGreetingOutput):
    request_id: str = Field(min_length=1, max_length=160)
    semantic_owner: Literal["social_cognition"] = "social_cognition"
    model_call_count: int = Field(ge=1, le=1)

    def validate_request(self, request: SocialStartupGreetingRequest) -> None:
        if self.request_id != request.request_id:
            raise ValueError("Social Cognition changed the startup request identity")
        if len(self.text) > request.max_chars:
            raise ValueError("Social Cognition exceeded the startup greeting length bound")
