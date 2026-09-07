from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from shared.chromie_contracts.interaction import InteractionResponse, InteractionSpeech
from shared.chromie_contracts.situation import (
    CognitiveOpportunity,
    GoalTimeCondition,
    SituationConditionRef,
    SituationInterpretation,
    SituationRevisionObservation,
    SituationProjection,
    SituationSourceRef,
    SituationalCognitionRequest,
)

from orchestrator.runtime.planner_reentry import suppress_already_delivered_speech
from orchestrator.runtime.session import now_ms, record_session_workflow_stage


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _bounded(value: Any, *, limit: int) -> str:
    return _normalized(value)[: max(1, int(limit))]


def _unique(values: Iterable[Any], *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalized(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _evidence_source_reference(item: dict[str, Any], index: int) -> SituationSourceRef:
    for key in (
        "evidence_id",
        "execution_outcome_id",
        "request_id",
        "tool_call_id",
        "interaction_id",
        "event_id",
    ):
        value = _normalized(item.get(key))
        if value:
            reference_id = value
            break
    else:
        encoded = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        reference_id = f"situation_evidence_{hashlib.sha256(encoded).hexdigest()[:20]}"

    source = _normalized(item.get("source") or item.get("owner") or "")
    owner = source or "orchestrator.conversation_state"
    return SituationSourceRef(
        kind="evidence",
        reference_id=reference_id or f"evidence_{index}",
        owner=owner,
    )


def _source_refs(
    values: Iterable[SituationSourceRef],
    *,
    limit: int,
) -> list[SituationSourceRef]:
    out: list[SituationSourceRef] = []
    seen: set[str] = set()
    for item in values:
        if item.reference_id in seen:
            continue
        seen.add(item.reference_id)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _interpretation_id(
    *,
    subject_ref: str,
    relation: str,
    value: str,
    source_ref: str,
) -> str:
    encoded = json.dumps(
        {
            "subject_ref": subject_ref,
            "relation": relation,
            "value": value,
            "source_ref": source_ref,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"situation_interpretation_{hashlib.sha256(encoded).hexdigest()[:20]}"


def _provider_state_interpretations(
    *,
    request_id: str,
    goal_ids: list[str],
    source_ref: str,
    provider_state: dict[str, Any],
) -> list[SituationInterpretation]:
    """Project only source-stated provider implications into current Situation.

    This deliberately performs no semantic inference about the Goal.  A provider
    saying a request is blocked/waiting/degraded can become a current Situation
    interpretation because that state is directly relevant to active Work; Host
    does not infer user intent, Goal satisfaction, recovery policy, or next Work.
    """

    subject_ref = f"capability_request:{_normalized(request_id)}"
    if len(subject_ref) > 200:
        subject_ref = (
            "capability_request:"
            f"{hashlib.sha256(subject_ref.encode('utf-8')).hexdigest()[:32]}"
        )
    interpretations: list[SituationInterpretation] = []

    def add(relation: str, value: Any, *, subject: str = subject_ref) -> None:
        if len(interpretations) >= 12:
            return
        normalized_value = _bounded(value, limit=240)
        if not normalized_value:
            return
        interpretations.append(
            SituationInterpretation(
                interpretation_id=_interpretation_id(
                    subject_ref=subject,
                    relation=relation,
                    value=normalized_value,
                    source_ref=source_ref,
                ),
                subject_ref=subject,
                relation=relation,
                value=normalized_value,
                epistemic_status="established",
                relevance_goal_ids=goal_ids,
                source_refs=[source_ref],
            )
        )

    for key in ("status", "state", "phase", "condition", "waiting_for"):
        if key in provider_state:
            add(f"runtime.{key}", provider_state.get(key))
    for key in ("blocked", "degraded", "paused", "recovering"):
        if provider_state.get(key) is True:
            add("runtime.condition", key)

    member_status = provider_state.get("member_status")
    if isinstance(member_status, dict):
        for member_id, member_state in member_status.items():
            member_subject = (
                f"{subject_ref}:member:{_normalized(member_id)}"
                if _normalized(member_id)
                else subject_ref
            )
            if len(member_subject) > 200:
                member_subject = (
                    f"{subject_ref[:150]}:member:"
                    f"{hashlib.sha256(member_subject.encode('utf-8')).hexdigest()[:32]}"
                )
            add(
                "runtime.member_status",
                member_state,
                subject=member_subject,
            )
    return interpretations


def build_situation_projection(
    *,
    context: dict[str, Any] | None,
    turn_id: str,
    focus_goal_ids: Iterable[str] | None = None,
    revision: int = 1,
    source_refs: Iterable[SituationSourceRef] | None = None,
    interpretations: Iterable[SituationInterpretation] | None = None,
) -> SituationProjection:
    """Reconstruct one bounded live Situation from current authoritative projections.

    This function has no persistence and owns no source facts.  Goal/Evidence/
    Memory/provider objects remain authoritative in their existing owners.  The
    returned Situation may retain only their bounded references plus current
    implications explicitly supplied by a trusted ingress.
    """

    current = context if isinstance(context, dict) else {}
    active = current.get("active_goal_snapshots")
    if not isinstance(active, list):
        active = []

    active_goal_ids: list[str] = []
    conditions: list[SituationConditionRef] = []
    for snapshot in active:
        if not isinstance(snapshot, dict):
            continue
        goal_id = _normalized(snapshot.get("goal_id"))
        if goal_id:
            active_goal_ids.append(goal_id)
        gaps = snapshot.get("open_information_gaps")
        if not isinstance(gaps, list) or not goal_id:
            continue
        for gap in gaps:
            if len(conditions) >= 12:
                break
            if not isinstance(gap, dict) or gap.get("resolved") is True:
                continue
            condition_id = _normalized(gap.get("gap_id") or gap.get("description"))
            if not condition_id:
                continue
            conditions.append(
                SituationConditionRef(
                    goal_id=goal_id,
                    condition_id=condition_id,
                    resolution=_normalized(gap.get("preferred_resolution") or "unknown"),
                )
            )

    discourse_focus = current.get("discourse_focus")
    if not isinstance(discourse_focus, list):
        discourse_focus = []

    recent_evidence = current.get("recent_tool_evidence")
    if not isinstance(recent_evidence, list):
        recent_evidence = []
    evidence_sources = [
        _evidence_source_reference(item, index)
        for index, item in enumerate(recent_evidence[-8:])
        if isinstance(item, dict)
    ]

    explicit_sources = list(source_refs or [])
    bounded_sources = _source_refs(
        [*explicit_sources, *evidence_sources],
        limit=16,
    )
    allowed_source_refs = {item.reference_id for item in bounded_sources}
    bounded_interpretations = [
        item
        for item in list(interpretations or [])[:12]
        if set(item.source_refs).issubset(allowed_source_refs)
    ]

    selected_goals = (
        _unique(focus_goal_ids, limit=8)
        if focus_goal_ids is not None
        else _unique(active_goal_ids, limit=8)
    )
    return SituationProjection.create(
        turn_id=_normalized(turn_id),
        revision=max(1, int(revision)),
        focus_goal_ids=selected_goals,
        discourse_focus_ids=_unique(discourse_focus[-8:], limit=8),
        unresolved_conditions=conditions,
        source_refs=bounded_sources,
        interpretations=bounded_interpretations,
    )


def build_provider_state_situation_observation(
    *,
    context: dict[str, Any] | None,
    turn_id: str,
    goal_ids: Iterable[str],
    dispatch_id: str,
    request_id: str,
    capability_id: str,
    provider_id: str,
    sequence: int,
    provider_state: dict[str, Any],
) -> SituationRevisionObservation:
    """Admit one bounded live provider-state transition as Situation input.

    Provider progress is independently trusted for its own Runtime state domain but
    is not Evidence of Goal satisfaction or of external-world facts.  The ingress
    therefore records it as ``runtime_state`` provenance and creates only direct,
    revisable interpretations of the source-stated request state.
    """

    normalized_goals = _unique(goal_ids, limit=8)
    if not normalized_goals:
        raise ValueError("provider Situation ingress requires at least one Goal")
    normalized_request_id = _normalized(request_id)
    if not normalized_request_id:
        raise ValueError("provider Situation ingress requires request_id")
    normalized_dispatch_id = _normalized(dispatch_id)
    source_ref_id = (
        f"runtime-state:{normalized_dispatch_id or 'dispatch'}:"
        f"{normalized_request_id}:{max(1, int(sequence))}"
    )
    if len(source_ref_id) > 200:
        encoded = source_ref_id.encode("utf-8")
        source_ref_id = (
            f"runtime-state:{hashlib.sha256(encoded).hexdigest()[:32]}"
        )
    source = SituationSourceRef(
        kind="runtime_state",
        reference_id=source_ref_id,
        owner=(
            _bounded(provider_id, limit=160)
            or "orchestrator.interaction_runtime"
        ),
    )
    provider_interpretations = _provider_state_interpretations(
        request_id=normalized_request_id,
        goal_ids=normalized_goals,
        source_ref=source_ref_id,
        provider_state=dict(provider_state),
    )
    if not provider_interpretations:
        raise ValueError("provider Situation ingress requires meaningful state")
    projection = build_situation_projection(
        context=context,
        turn_id=turn_id,
        focus_goal_ids=normalized_goals,
        revision=max(1, int(sequence)),
        source_refs=[source],
        interpretations=provider_interpretations,
    )
    observation_id = (
        f"situation_observation:{normalized_dispatch_id or 'dispatch'}:"
        f"{normalized_request_id}:{max(1, int(sequence))}"
    )
    if len(observation_id) > 200:
        encoded = observation_id.encode("utf-8")
        observation_id = (
            f"situation_observation:{hashlib.sha256(encoded).hexdigest()[:32]}"
        )
    return SituationRevisionObservation(
        observation_id=observation_id,
        source_id=(
            _bounded(provider_id, limit=160)
            or _bounded(capability_id, limit=160)
            or "orchestrator.interaction_runtime"
        ),
        source_revision=max(1, int(sequence)),
        goal_ids=normalized_goals,
        source_refs=[source_ref_id],
        projection=projection,
    )


def situation_revision_cognition_mode(
    observation: SituationRevisionObservation,
) -> str:
    """Select cognition depth from the admitted Situation delta, not its trigger name.

    This is a bounded mechanical readiness judgment.  It does not choose Work or
    interpret user meaning.  No-op is represented by no CognitiveOpportunity;
    ``local`` means the trusted owner state is worth retaining/logging but does
    not justify an LLM pass.
    """

    values = {
        _normalized(item.value).casefold()
        for item in observation.projection.interpretations
        if item.source_refs
    }
    relations = {
        _normalized(item.relation).casefold()
        for item in observation.projection.interpretations
    }
    severe = {"blocked", "degraded", "failed", "error", "unsafe"}
    if values.intersection(severe):
        return "slow"
    if values.intersection({"paused", "needs_attention"}):
        return "fast"
    if values.intersection({"waiting", "recovering", "running"}):
        return "local"
    if relations and relations.issubset({"runtime.phase", "runtime.member_status"}):
        return "local"
    return "fast"


GoalFreeSalienceMode = Literal["local", "fast", "slow"]


@dataclass(frozen=True)
class GoalFreeSituationSalience:
    """Cheap derived readiness for one Goal-free Situation change.

    This is not durable Mind state, a priority engine, or a semantic owner.  It only
    decides whether the already-admitted Situation warrants no model pass, one bounded
    fast cognition pass, or fail-quiet slow/deeper handling.  Relationship Memory is
    consumed only after the Memory owner's disclosure gate.
    """

    mode: GoalFreeSalienceMode
    reason_codes: tuple[str, ...]


_SOCIAL_HIGH_SALIENCE_TERMS = {
    "addressed",
    "arrival",
    "arrived",
    "calling",
    "departure",
    "distress",
    "greeting",
    "help",
    "invitation",
    "needs_attention",
    "unexpected",
}
_SOCIAL_LOW_SALIENCE_TERMS = {
    "ambient",
    "background",
    "nearby",
    "pass_by",
    "presence",
    "present",
    "routine",
    "unchanged",
    "visible",
}
_SOCIAL_DEFER_TERMS = {
    "busy",
    "occupied",
    "private_conversation",
    "sleeping",
    "do_not_interrupt",
}
_SOCIAL_CONSEQUENTIAL_TERMS = {
    "danger",
    "emergency",
    "injured",
    "unsafe",
}
_RELATIONAL_KINDS = {
    "person_identity",
    "person_relationship",
    "relationship_interpretation",
    "shared_experience",
}
_SITUATIONAL_RESPONSE_COOLDOWN_S = 300.0


def _social_terms(observation: SituationRevisionObservation) -> set[str]:
    terms: set[str] = set()
    for item in observation.projection.interpretations:
        for raw in (item.relation, item.value):
            normalized = _normalized(raw).casefold()
            if not normalized:
                continue
            terms.add(normalized)
            terms.update(
                part
                for part in normalized.replace("/", ".").replace(":", ".").split(".")
                if part
            )
    return terms


def goal_free_situation_salience(
    observation: SituationRevisionObservation,
    *,
    activated_memory_entries: Iterable[dict[str, Any]] = (),
    interaction_context: dict[str, Any] | None = None,
    situation_signature: str = "",
    now: datetime | None = None,
) -> GoalFreeSituationSalience:
    """Select Goal-free cognition readiness without an LLM or a new state owner.

    The policy intentionally uses coarse, inspectable signals.  Unknown/private Memory
    has already been excluded by the Memory owner.  A relationship can raise relevance,
    but can never grant disclosure, factual-trust, Goal, Capability, or effect authority.
    """

    if observation.goal_ids or observation.projection.focus_goal_ids:
        raise ValueError("goal-free salience cannot evaluate Goal-bound Situation")

    interpretations = list(observation.projection.interpretations)
    if not interpretations:
        return GoalFreeSituationSalience("local", ("no_current_interpretation",))

    statuses = {item.epistemic_status for item in interpretations}
    if statuses.intersection({"conflicted", "stale", "unknown"}):
        return GoalFreeSituationSalience(
            "local",
            ("uncertain_or_conflicted_situation",),
        )

    context = interaction_context if isinstance(interaction_context, dict) else {}
    if context.get("pending_speech"):
        return GoalFreeSituationSalience("local", ("speech_already_pending",))

    normalized_signature = _normalized(situation_signature)
    if normalized_signature:
        reference_time = now or datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        for item in context.get("already_spoken") or []:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            if str(metadata.get("delivery_role") or "") != "situational_response":
                continue
            if _normalized(metadata.get("situation_signature")) != normalized_signature:
                continue
            occurred_at = _normalized(item.get("occurred_at"))
            try:
                occurred = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=timezone.utc)
            age_s = (reference_time - occurred).total_seconds()
            if 0.0 <= age_s <= _SITUATIONAL_RESPONSE_COOLDOWN_S:
                return GoalFreeSituationSalience(
                    "local",
                    ("same_situation_already_acknowledged",),
                )

    terms = _social_terms(observation)
    if terms.intersection(_SOCIAL_CONSEQUENTIAL_TERMS):
        return GoalFreeSituationSalience(
            "slow",
            ("consequential_goal_free_situation",),
        )
    if terms.intersection(_SOCIAL_DEFER_TERMS):
        return GoalFreeSituationSalience(
            "local",
            ("social_context_prefers_non_interruption",),
        )

    direct_social_change = bool(terms.intersection(_SOCIAL_HIGH_SALIENCE_TERMS))
    routine_or_ambient = bool(terms.intersection(_SOCIAL_LOW_SALIENCE_TERMS))
    reasons: list[str] = []
    if direct_social_change:
        reasons.append("direct_social_change")
    if routine_or_ambient:
        reasons.append("routine_or_ambient_change")

    subjects = {
        item.subject_ref for item in interpretations if _normalized(item.subject_ref)
    }
    known_relationship_relevant = False
    shared_experience_relevant = False
    for entry in activated_memory_entries:
        if not isinstance(entry, dict):
            continue
        kind = _normalized(entry.get("kind")).casefold()
        if kind not in _RELATIONAL_KINDS:
            continue
        entry_subjects = {
            _normalized(value)
            for value in entry.get("subject_refs") or []
            if _normalized(value)
        }
        if not subjects.intersection(entry_subjects):
            continue
        if kind == "shared_experience":
            shared_experience_relevant = True
        else:
            known_relationship_relevant = True
    if known_relationship_relevant:
        reasons.append("known_relationship_relevant")
    if shared_experience_relevant:
        reasons.append("shared_experience_relevant")

    # A routine/ambient observation does not become worth a model call merely
    # because the subject is close to Chromie.  A direct social change is
    # independently salient; otherwise established relationship/shared-experience
    # context may make a non-routine current change worth one bounded Fast pass.
    if routine_or_ambient and not direct_social_change:
        return GoalFreeSituationSalience("local", tuple(reasons))
    if direct_social_change:
        return GoalFreeSituationSalience("fast", tuple(reasons))
    if (
        "established" in statuses
        and (known_relationship_relevant or shared_experience_relevant)
    ):
        return GoalFreeSituationSalience(
            "fast",
            tuple([*reasons, "relationship_context_makes_change_relevant"]),
        )
    return GoalFreeSituationSalience("local", tuple(reasons or ["low_salience_change"]))


def derive_situation_revision_opportunity(
    observation: SituationRevisionObservation,
    *,
    previous_situation_digest: str = "",
) -> CognitiveOpportunity | None:
    """Derive Planner readiness from one trusted live-Situation observation.

    The producer is delta-driven: replaying the same Situation digest is a no-op.
    Source trust/admission belongs to the caller that constructs the typed observation;
    this function neither observes the world nor invents Evidence.
    """

    previous = _normalized(previous_situation_digest)
    if previous and previous == observation.projection.digest:
        return None
    source_by_ref = {
        item.reference_id: item for item in observation.projection.source_refs
    }
    evidence_refs = [
        source_ref
        for source_ref in observation.source_refs
        if source_by_ref[source_ref].kind == "evidence"
    ]
    observation_source_set = set(observation.source_refs)
    subject_refs = _unique(
        (
            item.subject_ref
            for item in observation.projection.interpretations
            if observation_source_set.intersection(item.source_refs)
        ),
        limit=16,
    )
    return CognitiveOpportunity.create(
        trigger="situation_revision",
        goal_ids=list(observation.goal_ids),
        evidence_refs=evidence_refs,
        source_refs=list(observation.source_refs),
        subject_refs=subject_refs,
        reason_codes=["trusted_situation_revision"],
        recommended_cognition=situation_revision_cognition_mode(observation),
        situation_digest=observation.projection.digest,
        situation_signature=observation.projection.interpretation_signature(),
    )


async def apply_goal_free_situation_opportunity(
    host: Any,
    observation: SituationRevisionObservation,
    *,
    previous_situation_digest: str = "",
    session_id: str | None = None,
    language: str = "auto",
) -> str:
    """Run one bounded Goal-free current-Situation cognition opportunity.

    The typed observation is the trusted ingress boundary. This function never
    fabricates a UserTurn, Responsibility, or Goal. It derives readiness from an
    actual Situation delta, invokes the same Cognitive Core through its bounded
    Goal-free situational-cognition contract, and may deliver only speech.
    Capability Work and effect authorization are structurally unavailable here.
    """

    if observation.goal_ids or observation.projection.focus_goal_ids:
        raise ValueError(
            "goal-free Situation cognition cannot carry Goal bindings"
        )
    opportunity = derive_situation_revision_opportunity(
        observation,
        previous_situation_digest=previous_situation_digest,
    )
    if opportunity is None:
        return "no_change"
    if opportunity.goal_ids:
        raise ValueError("goal-free Situation opportunity unexpectedly carries Goals")
    if opportunity.recommended_cognition == "local":
        if hasattr(host, "session_log"):
            host.session_log(
                session_id,
                "goal_free_situation_cognition_local: opportunity_id=%s",
                opportunity.opportunity_id,
            )
        return "local_only"

    response = await resolve_goal_free_situation_response(
        host,
        observation=observation,
        opportunity=opportunity,
        session_id=session_id,
        language=_normalized(language) or "auto",
    )
    if response is None:
        return "silence"
    if getattr(response, "capabilities", None):
        raise ValueError(
            "goal-free situational cognition must never emit Capability Work"
        )
    deliver = getattr(host, "_execute_cognitive_outcome_response", None)
    if not callable(deliver):
        return "delivery_unavailable"
    return await deliver(
        response,
        session_id=session_id,
        detached_delivery=True,
    )


async def resolve_goal_free_situation_response(
    host: Any,
    *,
    observation: SituationRevisionObservation,
    opportunity: CognitiveOpportunity,
    session_id: str | None,
    language: str,
) -> InteractionResponse | None:
    """Resolve one Goal-free Situation opportunity without expanding Host ownership.

    This stateless helper coordinates the existing Memory, Interaction Ledger, Agent
    client, and playback-facing response contracts.  The only semantic author remains
    the bounded situational-cognition invocation inside the same Cognitive Core.
    """

    if observation.goal_ids or observation.projection.focus_goal_ids:
        raise ValueError("situational cognition cannot carry Goal bindings")
    if opportunity.goal_ids:
        raise ValueError("situational cognition opportunity cannot carry Goals")
    if opportunity.trigger != "situation_revision":
        raise ValueError("situational cognition requires situation_revision trigger")
    if opportunity.situation_digest != observation.projection.digest:
        host.session_log(
            session_id,
            "situational_cognition_rejected: reason=situation_digest_mismatch",
        )
        return None
    if set(opportunity.source_refs) != set(observation.source_refs):
        host.session_log(
            session_id,
            "situational_cognition_rejected: reason=source_provenance_mismatch",
        )
        return None

    context = host.build_context(session_id)
    context["situation"] = observation.projection.prompt_projection()
    context["cognitive_opportunity"] = opportunity.prompt_projection()
    situation_activation_texts: list[str] = []
    opportunity_subjects = set(opportunity.subject_refs)
    for interpretation in observation.projection.interpretations:
        if opportunity_subjects and interpretation.subject_ref not in opportunity_subjects:
            continue
        situation_activation_texts.extend(
            [
                interpretation.subject_ref,
                interpretation.relation,
                interpretation.value,
            ]
        )
    relational_memory = host.conversation_state.activated_memory_context(
        activation_texts=situation_activation_texts,
        activation_subject_refs=list(opportunity.subject_refs),
        # PSM-2 does not infer who can hear a Goal-free utterance. Until a trusted
        # multi-person presence/identity adapter supplies the complete audience,
        # Memory entries requiring audience resolution stay hidden.
        audience_refs=[],
        limit=12,
    )
    context["memory_summary"] = relational_memory["summary"]
    context["extracted_memory"] = relational_memory["entries"]
    context["relational_memory_selection"] = relational_memory["selection"]
    interaction_ledger = getattr(
        getattr(host, "cognitive_runtime", None),
        "interaction_ledger",
        None,
    )
    ledger_scope = str(
        session_id
        or getattr(host, "session_id", "")
        or context.get("conversation_id")
        or "goal-free-situation"
    ).strip()
    if interaction_ledger is not None:
        context["interaction_context"] = interaction_ledger.context(
            ledger_scope,
            goal_ids=[],
            turn_id=observation.observation_id,
        ).model_dump(mode="json")

    salience = goal_free_situation_salience(
        observation,
        activated_memory_entries=relational_memory["entries"],
        interaction_context=(
            context.get("interaction_context")
            if isinstance(context.get("interaction_context"), dict)
            else {}
        ),
        situation_signature=opportunity.situation_signature,
    )
    opportunity = opportunity.model_copy(
        update={
            "recommended_cognition": salience.mode,
            "reason_codes": list(
                dict.fromkeys([*opportunity.reason_codes, *salience.reason_codes])
            )[:8],
        }
    )
    context["cognitive_opportunity"] = opportunity.prompt_projection()
    context["situational_salience"] = {
        "mode": salience.mode,
        "reason_codes": list(salience.reason_codes),
    }
    if salience.mode != "fast":
        host.session_log(
            session_id,
            "situational_cognition_salience_suppressed: opportunity_id=%s "
            "mode=%s reasons=%s",
            opportunity.opportunity_id,
            salience.mode,
            ",".join(salience.reason_codes),
        )
        return None

    request = SituationalCognitionRequest(
        opportunity=opportunity,
        situation=observation.projection,
        language=language or "auto",
        context=context,
    )
    cognition_call = getattr(
        host.agent_client,
        "resolve_situational_cognition",
        None,
    )
    if not callable(cognition_call):
        host.session_log(
            session_id,
            "situational_cognition_unavailable: opportunity_id=%s",
            opportunity.opportunity_id,
        )
        return None
    session = await host.get_http_session()
    started_ms = now_ms()
    resolution = await cognition_call(
        session,
        request=request,
        timeout_ms=host.cognitive_runtime_policy.fast_planner_timeout_ms,
    )
    record_session_workflow_stage(
        host,
        session_id,
        stage="situational_cognition",
        started_monotonic_ms=started_ms,
        finished_monotonic_ms=now_ms(),
        status="resolved",
        input_payload={
            "opportunity_id": opportunity.opportunity_id,
            "situation_digest": observation.projection.digest,
            "source_refs": list(observation.source_refs),
        },
        output_payload=resolution,
        errors=[],
        metadata={
            "wording_owner": "cognitive_core",
            "authority_scope": "goal_free_situation",
        },
    )
    if (
        resolution.opportunity_id != opportunity.opportunity_id
        or resolution.situation_digest != observation.projection.digest
        or set(resolution.source_refs) != set(observation.source_refs)
    ):
        raise ValueError(
            "situational cognition result changed trusted readiness provenance"
        )
    if resolution.disposition == "silence":
        host.session_log(
            session_id,
            "situational_cognition_silence: opportunity_id=%s",
            opportunity.opportunity_id,
        )
        return None
    activity = resolution.activity
    if activity is None:
        raise ValueError("communicate situational cognition has no Activity")

    response = InteractionResponse(
        speech=[
            InteractionSpeech(
                id=f"situational_speech_{activity.activity_id}"[:160],
                text=activity.text,
                timing="immediate",
                style="brief",
                priority="normal",
                interruptible=True,
                metadata={
                    "source": "situational_cognition",
                    "wording_owner": "cognitive_core",
                    "authority_scope": "goal_free_situation",
                    "truth_stage": "context_grounded",
                    "speech_act": activity.speech_act,
                    "delivery_role": "situational_response",
                    "goal_completion_authority": False,
                    "cognitive_opportunity_id": opportunity.opportunity_id,
                    "situation_digest": observation.projection.digest,
                    "situation_signature": opportunity.situation_signature,
                    "source_situation_refs": list(observation.source_refs),
                    "subject_refs": list(resolution.subject_refs),
                    "communicative_activity_ids": [activity.activity_id],
                    "turn_id": observation.observation_id,
                    "language": language or "auto",
                    "wait_for_playback_start": True,
                    "playback_start_required_for_delivery": True,
                },
            )
        ],
        capabilities=[],
        metadata={
            "source": "situational_cognition",
            "authority_scope": "goal_free_situation",
            "cognitive_opportunity": opportunity.prompt_projection(),
            "situation": observation.projection.prompt_projection(),
            "situational_salience": context["situational_salience"],
            "source_situation_refs": list(observation.source_refs),
            "goal_ids": [],
            "language": language or "auto",
        },
    )
    if ledger_scope:
        response, suppressed = suppress_already_delivered_speech(
            response,
            (
                item.get("text") or ""
                for item in host._delivered_turn_speech_events(ledger_scope)
            ),
        )
        if suppressed:
            host.session_log(
                session_id,
                "situational_cognition_duplicate_speech_suppressed: count=%s",
                suppressed,
            )
    return response if response.speech else None


async def apply_due_time_condition_opportunity(
    host: Any,
    due_item: dict[str, Any],
) -> str:
    """Reactivate the same Planner for one due structured time condition.

    Wall-clock readiness is a trusted mechanical state transition, not Evidence and
    not a fabricated user turn. The due item must therefore retain exact Planner/Goal
    binding plus original GI Responsibility provenance. Missing provenance fails
    closed after the one-shot condition is consumed; Host never reconstructs WHAT
    from Goal prose and never authors a response or Activity.
    """

    try:
        condition = GoalTimeCondition.model_validate(due_item.get("condition") or {})
        opportunity = CognitiveOpportunity.model_validate(
            due_item.get("opportunity") or {}
        )
        responsibilities = [
            CognitiveResponsibilityProposal.model_validate(item)
            for item in due_item.get("responsibilities") or []
            if isinstance(item, dict)
        ]
    except (TypeError, ValueError) as exc:
        host.session_log(
            None,
            "time_condition_reentry_rejected: reason=invalid_due_payload "
            "error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        return "invalid_due_payload"

    if opportunity.trigger != "time_condition":
        host.session_log(
            None,
            "time_condition_reentry_rejected: reason=wrong_trigger trigger=%s",
            opportunity.trigger,
        )
        return "wrong_trigger"
    if condition.goal_id not in opportunity.goal_ids:
        host.session_log(
            None,
            "time_condition_reentry_rejected: reason=goal_binding_mismatch "
            "condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "goal_binding_mismatch"
    if not responsibilities:
        host.session_log(
            None,
            "time_condition_reentry_suppressed: reason=missing_responsibility_provenance "
            "condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "missing_responsibility_provenance"

    source_text = _normalized(due_item.get("source_text"))
    if not source_text:
        host.session_log(
            None,
            "time_condition_reentry_suppressed: reason=missing_source_text "
            "condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "missing_source_text"

    planner_response = await host._planner_state_reentry_response(
        source_response=None,
        canonical_plan=None,
        user_request=source_text,
        language=_normalized(due_item.get("language")) or "auto",
        goal_ids=list(opportunity.goal_ids),
        evidence_goal_ids=[],
        evidence_refs=[],
        session_id=None,
        phase="time_condition_reentry",
        context_updates={
            "time_condition": condition.model_dump(mode="json"),
            "cognitive_opportunity": opportunity.prompt_projection(),
        },
        fast_workflow_stage="fast_planner_time_condition_reentry",
        deep_workflow_stage="planner_deep_pass_time_condition_reentry",
        response_source="fast_planner_time_condition_reentry",
        responsibilities_override=responsibilities,
    )
    if planner_response is None:
        host.session_log(
            None,
            "time_condition_reentry_no_change: condition_id=%s goal_id=%s",
            condition.condition_id,
            condition.goal_id,
        )
        return "no_change"

    apply_status = await host._apply_planner_reentry_response(
        planner_response,
        session_id=None,
    )
    host.session_log(
        None,
        "time_condition_reentry_done: condition_id=%s goal_id=%s apply=%s",
        condition.condition_id,
        condition.goal_id,
        apply_status,
    )
    return str(apply_status or "applied")


async def drain_due_time_conditions_once(
    host: Any,
    *,
    now_ms: int | None = None,
) -> list[str]:
    """Consume and process the currently due structured wake conditions once."""

    due = host.conversation_state.due_time_condition_opportunities(now_ms=now_ms)
    statuses: list[str] = []
    for item in due:
        try:
            statuses.append(await apply_due_time_condition_opportunity(host, item))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            host.session_log(
                None,
                "time_condition_reentry_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            statuses.append("planner_reentry_failed")
    return statuses


async def run_time_condition_wake_loop(
    host: Any,
    *,
    max_idle_sleep_s: float = 0.5,
) -> None:
    """Mechanically wake cognition when a durable Goal time condition becomes due.

    This is deliberately not an ambient thinking loop. With no due condition it
    performs no cognition, model call, Goal interpretation, or world polling. It
    only checks ConversationState's structured wall-clock records and sleeps.
    """

    idle_sleep = max(0.05, float(max_idle_sleep_s))
    while True:
        next_due = host.conversation_state.next_time_condition_due_ms()
        now = int(time.time() * 1000.0)
        if next_due is None:
            await asyncio.sleep(idle_sleep)
            continue
        delay_s = max(0.0, (int(next_due) - now) / 1000.0)
        if delay_s > 0.0:
            await asyncio.sleep(min(idle_sleep, delay_s))
            continue
        await drain_due_time_conditions_once(host, now_ms=now)


__all__ = [
    "apply_due_time_condition_opportunity",
    "build_provider_state_situation_observation",
    "build_situation_projection",
    "derive_situation_revision_opportunity",
    "drain_due_time_conditions_once",
    "GoalFreeSituationSalience",
    "goal_free_situation_salience",
    "resolve_goal_free_situation_response",
    "run_time_condition_wake_loop",
    "situation_revision_cognition_mode",
]
