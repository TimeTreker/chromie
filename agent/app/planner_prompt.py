from __future__ import annotations

import copy
import json
from typing import Any

from .agent_skills import agent_skill_prompt_section
from .clients.ollama_client import LayeredPrompt
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    STABLE_MIND_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
    bounded_stable_mind_json,
    owner_approved_identity_context,
    owner_approved_personality_context,
)
from .goal_progress_communication import goal_progress_communication_prompt
try:
    from chromie_contracts.semantic_authority import PLANNER_WORK_AUTHORITY_PROMPT
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.semantic_authority import PLANNER_WORK_AUTHORITY_PROMPT

try:
    from chromie_contracts.user_turn import user_turn_source_tokens
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.user_turn import user_turn_source_tokens

from .prompt_projection import bounded_json, required_json
from .planner_context import (
    PlannerGoalContext,
    canonical_goal_grounding,
    evidence_bound_dialogue,
    recent_dialogue_prompt_projection,
    fast_goal_continuity_projection,
    goal_association_prompt_projection,
    goal_readiness_times,
    planner_goal_context,
    planner_provider_vocal_goal_ids,
    situation_prompt_projection,
)

try:
    from chromie_contracts.memory import role_memory_context
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.memory import role_memory_context


try:
    from chromie_contracts.core_interpretation import (
        CognitiveResponsibilityProposal,
        CognitiveWorkRequest,
    )
    from chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID
    from chromie_contracts.plan import GOAL_SATISFACTION_SCORE_BANDS
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import (
        CognitiveResponsibilityProposal,
        CognitiveWorkRequest,
    )
    from shared.chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID
    from shared.chromie_contracts.plan import GOAL_SATISFACTION_SCORE_BANDS


CAPABILITY_LOOKUP_PROMPT = (
    "You have complete common Capability contracts and an index of the available library. "
    "Capability IDs are not interchangeable merely because they share output_mode, effect "
    "class, provider, or body lane. For every independently observable requested effect, "
    "select only a loaded Capability whose description and declared semantic scope actually "
    "support that effect. Never substitute an unrelated loaded Capability just to avoid a "
    "catalog lookup or to make coverage appear complete. If the loaded common contracts do "
    "not support an accepted effect and the library index contains a plausible exact ability, "
    "return only requested_capability_ids with exact index IDs, up to eight in one batch, "
    "before authoring any Plan. The Host supplies their full contracts with the original "
    "source context. One lookup batch is allowed; after it, produce the complete Plan or the "
    "existing non-executing outcome. If your reasoning identifies an indexed Capability as "
    "the correct realization but its full contract is not loaded, request that exact indexed "
    "ID first; never emit a different loaded capability_id while describing the indexed one "
    "in activity_id or reason_summary. Never guess missing schemas or use a lookup to revise a "
    "completed decision. If no loaded/lookup Capability actually covers an accepted effect, "
    "retain that unmet requirement and choose the appropriate unavailable/escalation outcome "
    "instead of fabricating substitute Work. An uncommon Capability does not itself require "
    "Deep Planner. Restricted entries remain restricted. Catalog lookup authorizes no execution. "
)

EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT = (
    "Planner owns decomposition of complete intent into Activities, Capability choice, "
    "arguments, units, dependencies and scheduling. UMI supplies complete "
    "natural-language intent, not an argument table. Preserve every requested action, "
    "modifier and relation. One Responsibility may require several Activities. "
    "Use exact numeric values when the Capability units agree; normalize number words "
    "and units only when the interpretation and conversion are unambiguous. Never "
    "substitute a default for an explicit requested value. For an intent-derived "
    "argument in Fast Activities, select its exact immutable source span as "
    "argument_sources[parameter]={source_start_token_ref,source_end_token_ref} from "
    "the supplied UserTurn source_tokens. Never copy or paraphrase the source wording. "
    "Trusted code materializes the span into canonical source_quote and Goal provenance; "
    "you remain responsible for correct mapping, conversion and coverage. "
    "Existing typed Responsibility and Goal constraints remain binding and cannot be "
    "overridden by a Planner HOW choice or a quote. Treat each Capability input schema as "
    "the action template: required fields must be supplied; an optional field with a "
    "declared default may be omitted when that default is suitable, in which case trusted "
    "Runtime/provider realization owns the default. Schema metadata such as type, enum, "
    "bounds, requiredness and default are instructions for choosing args, never fields to "
    "copy into model-authored args. Planner owns HOW and may emit a schema-valid non-default "
    "optional value when the requested Work genuinely benefits from it; briefly explain "
    "that HOW choice in the Activity reason_summary. If an argument is instead realized "
    "from the current UserTurn, cite argument_sources for that exact same argument key. "
    "Source membership is not semantic permission: cite only a span that actually expresses "
    "that parameter, never a sibling value that merely has the same number or words. Never "
    "borrow a sibling Goal's values. Do not emit optional fields merely to restate their "
    "declared defaults. Missing consequential required input must use "
    "a genuine Planner gap or the declared depth path, without invented Work. "
)

# Planner prompt/projection mechanics only. This module does not invoke a model,
# validate or commit a Plan, mutate Goal/Work state, or authorize effects.


def immutable_source_turn_prompt(
    request: CognitiveWorkRequest,
    *,
    what_authority: str = "FINAL CANONICAL GOALS",
) -> str:
    """Expose exact source evidence without letting Planner re-author WHAT."""

    source = request.source_turn_provenance
    unresolved = (
        "\n\nUMI semantic uncertainty evidence (exact objects or empty):\n"
        + required_json(
            [item.model_dump(mode="json") for item in request.meaning_uncertainties],
            None,
            label="UMI semantic uncertainty evidence",
        )
    )
    original_text = str(source["original_text"])
    projection = json.dumps(
        {
            "original_text": original_text,
            "source_tokens": user_turn_source_tokens(original_text),
            "authority": "immutable_user_turn_source",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "IMMUTABLE SOURCE TURN JSON (read-only; "
        f"{what_authority} own WHAT; Planner may use complete intent and exact source "
        "to realize HOW, never reinterpret or repair WHAT, add omitted outcomes or resolve UMI ambiguity):\n"
        f"{projection}{unresolved}"
    )




def trusted_target_evidence_prompt_section(context: dict[str, Any]) -> str:
    """Expose one already-owned target reference for primary targeted Work.

    Target Evidence is not a social-expression affordance. Planner may copy an exact trusted reference
    into a provider-declared target argument; it may never infer a direction or
    synthesize a target when this projection is unavailable.
    """

    payload = context.get("planner_target_evidence_context")
    target_evidence = payload.get("target_evidence") if isinstance(payload, dict) else None
    if not isinstance(target_evidence, dict) or not target_evidence.get("available"):
        return "No trusted semantic target evidence is available.\n"
    return (
        "Trusted semantic target evidence JSON:\n"
        f"{required_json(target_evidence, None, label='Planner target Evidence')}\n"
        "This evidence may ground a primary targeted Capability only when its exact "
        "semantic target matches the owning Responsibility and the Capability declares "
        "the corresponding argument_realization. Copy the supplied target_ref exactly. "
        "Never replace it with a pronoun surface, invent another target, infer yaw/pitch, "
        "or use this evidence for an unrelated Responsibility. Provider and Runtime "
        "retain target-resolution and safety authority.\n\n"
    )


def future_readiness_contract(goal_context: PlannerGoalContext) -> str:
    goal_times = dict(goal_context.future_goal_times)
    reached_times = {
        goal_id: due_ms
        for goal_id, due_ms in goal_readiness_times(goal_context.authoritative_goals).items()
        if goal_id not in goal_times
        and goal_id not in goal_context.cancellation_reentry_goal_ids
    }
    reached_contract = (
        "The Host's clock comparison for this invocation confirms that these exact "
        "canonical ready_at times have ALREADY ARRIVED (Goal ID to due_at_ms): "
        + required_json(reached_times, None, label="Planner reached Goal readiness")
        + ". Their original source wording may still describe a future intention; "
        "that wording does not override the current Host readiness fact. Do not wait "
        "for or reschedule the same readiness time again. Evaluate the next Plan "
        "now under the existing Goal, catalog, evidence, safety and confirmation "
        "contracts. Readiness alone does not grant execution permission or prove "
        "that acquisition, effects or delivery have occurred.\n"
        if reached_times else ""
    )
    if not goal_times:
        return reached_contract
    return reached_contract + (
        "These exact canonical Goals are not yet ready; their typed ready_at is in the future: "
        + required_json(goal_times, None, label="Planner future Goal readiness")
        + ". For each, author a respond outcome acknowledging future reconsideration and "
        "one time_condition with the exact goal_id and due_at_ms. Author no current step, "
        "reuse, cancellation, confirmation, or auxiliary action on that Goal's behalf. "
        "A time_condition wakes cognition later; it does not delay an executable step "
        "listed now. Keep the original Goal and its remaining effect/answer unmet in "
        "both per-Goal and aggregate satisfaction. The acknowledgement does not fulfill "
        "the future request. Do not claim that retrieval, execution, or delivery already "
        "occurred, or promise success before later planning and Runtime evidence. "
        "Current catalog availability remains factual, but grants no early execution. "
        "Independent ready Goals retain their ordinary contracts. A future monitor "
        "of already-running work is distinct from a Goal whose ready_at forbids starting now.\n"
    )


def cancellation_reporting_contract(context: dict[str, Any], goal_ids: frozenset[str]) -> str:
    if not goal_ids:
        return ""
    return (
        "This invocation reports trusted cancellation control only for these original Goals: "
        + required_json(sorted(goal_ids), None, label="Planner cancellation scope")
        + ". Their WHAT remains unchanged. Use respond for the factual report, including "
        "an unsuccessful or uncertain cancellation. Complete coverage means the report "
        "accounts for the control result; it does not fulfill the original effect Goal. "
        "Keep each original effect Goal and its remaining requirements unmet in per-Goal "
        "and aggregate satisfaction. Do not inflate satisfaction for a good acknowledgment. "
        "A released stale confirmation leaves that Goal open, without authorizing execution. "
        "Report that it remains pending; do not solicit a new confirmation or promise "
        "automatic later execution in this reporting invocation. No new, reused, auxiliary, "
        "scheduled, or cancelled Work belongs to these Goals. Independent Goals retain "
        "their own authority. An empty executable list reflects this invocation's permission, "
        "not missing provider support. Catalog facts below describe availability only; "
        "they never grant Work or confirmation permission. Do not claim a provider is "
        "absent when available=true, or universal inability from available=false. "
        "Distinguish cancelled, not_cancelled, and uncertain exactly as the trusted Evidence "
        "records; never claim a successful stop from an attempt or released token.\n"
        "Catalog facts for control reporting JSON:\n"
        + required_json(context.get("planner_cancellation_capability_facts") or [], None,
                        label="Planner cancellation catalog facts")
        + "\n"
    )


def planner_reentry_source_work_projection(
    plan: Any, *, goal_ids: set[str],
) -> dict[str, Any]:
    """Project historical source Work without exposing an obsolete output envelope.

    Re-entry is a new Planner decision. The prior Plan is correlation provenance,
    not a template for the current model DTO. Exposing its aggregate disposition,
    coverage, satisfaction, and goal-outcome envelope encouraged the model to copy
    that already-materialized CanonicalPlan shape instead of the current flat
    PlannerModelOutput contract. Keep only exact Work identities/arguments needed to
    correlate terminal Evidence and reject replay.
    """

    if not isinstance(plan, dict):
        return {}
    scoped = {str(item).strip() for item in goal_ids if str(item).strip()}
    steps: list[dict[str, Any]] = []
    for item in plan.get("steps") or []:
        if not isinstance(item, dict):
            continue
        source_goal_ids = [
            str(goal_id).strip()
            for goal_id in item.get("source_goal_ids") or []
            if str(goal_id).strip()
        ]
        if scoped and not scoped.intersection(source_goal_ids):
            continue
        projected = {
            key: copy.deepcopy(item[key])
            for key in (
                "step_id",
                "capability_id",
                "args",
                "timing",
                "source_goal_ids",
                "step_purpose",
                "expected_outcome",
            )
            if key in item
        }
        steps.append(projected)
    return {
        "plan_id": plan.get("plan_id"),
        "goal_ids": [
            goal_id
            for goal_id in plan.get("goal_ids") or []
            if not scoped or str(goal_id).strip() in scoped
        ],
        "steps": steps,
    }


def planner_reentry_execution_truth_projection(
    truth: Any, *, goal_ids: set[str],
) -> dict[str, Any]:
    """Project Runtime execution facts without resembling a Planner output DTO.

    ``trusted_execution_outcome`` is Host-owned evidence state. Its historical shape
    contains names such as ``goal_outcomes`` and ``planned_satisfaction`` that closely
    resemble older Planner envelopes and can become an accidental few-shot template.
    Re-entry needs the facts, not that representation. Rename and narrow the surface so
    the model receives terminal/retryability truth while the current response schema
    remains the only output shape in the transaction.
    """

    if not isinstance(truth, dict):
        return {}
    scoped = {str(item).strip() for item in goal_ids if str(item).strip()}

    evidence_facts: list[dict[str, Any]] = []
    for item in truth.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        item_goal_ids = [
            str(goal_id).strip()
            for goal_id in item.get("source_goal_ids") or []
            if str(goal_id).strip()
        ]
        if scoped and not scoped.intersection(item_goal_ids):
            continue
        row: dict[str, Any] = {
            "evidence_ref": item.get("evidence_id"),
            "capability_ref": item.get("capability_id"),
            "goal_refs": item_goal_ids,
            "execution_state": item.get("status"),
            "observation_state": item.get("observation_status"),
        }
        retryability = item.get("provider_retryability")
        if isinstance(retryability, dict) and retryability:
            row["provider_retryability"] = copy.deepcopy(retryability)
        reason_code = str(item.get("reason_code") or "").strip()
        if reason_code:
            row["reason_code"] = reason_code
        evidence_facts.append({
            key: value for key, value in row.items()
            if value not in (None, "", [], {})
        })

    goal_execution_facts: list[dict[str, Any]] = []
    for item in truth.get("goal_outcomes") or []:
        if not isinstance(item, dict):
            continue
        goal_id = str(item.get("goal_id") or "").strip()
        if not goal_id or (scoped and goal_id not in scoped):
            continue
        row: dict[str, Any] = {
            "goal_ref": goal_id,
            "execution_state": item.get("status"),
            "evidence_refs": [
                str(evidence_id).strip()
                for evidence_id in item.get("evidence_ids") or []
                if str(evidence_id).strip()
            ],
            "runtime_continuation_required": bool(
                item.get("requires_planner_continuation")
            ),
        }
        qualification = item.get("completion_qualification")
        if isinstance(qualification, dict):
            gate: dict[str, Any] = {
                "required": bool(qualification.get("required")),
                "established": bool(qualification.get("established")),
            }
            qualification_evidence = [
                str(entry.get("evidence_id") or "").strip()
                for entry in qualification.get("qualifications") or []
                if isinstance(entry, dict)
                and str(entry.get("evidence_id") or "").strip()
            ]
            if qualification_evidence:
                gate["evidence_refs"] = qualification_evidence
            row["completion_gate"] = gate
        reason_codes = [
            str(code).strip()
            for code in item.get("reason_codes") or []
            if str(code).strip()
        ]
        if reason_codes:
            row["reason_codes"] = reason_codes
        goal_execution_facts.append({
            key: value for key, value in row.items()
            if value not in (None, "", [], {})
        })

    return {
        "execution_outcome_ref": truth.get("outcome_id"),
        "aggregate_execution_state": truth.get("aggregate_status"),
        "goal_execution_facts": goal_execution_facts,
        "evidence_facts": evidence_facts,
    }


def _canonical_work_prompt(
    request: CognitiveWorkRequest, capabilities: list[dict[str, Any]], *,
    tier: str, goal_context: PlannerGoalContext | None = None,
    include_capability_catalog: bool = True, minimum_goal_satisfaction: float = 0.75,
) -> str:
    """Project complete Work facts once; SC receives its own interaction context."""
    context = request.context
    goals = goal_context or planner_goal_context(context, reentry_scope=request.planner_reentry_scope)
    scope = list(goals.expected_goal_ids)
    catalog_label = "Executable common capability catalog JSON" if tier == "fast" else "Executable capability catalog JSON"
    catalog = capabilities if tier == "fast" else [prompt_capability_contract(item) for item in capabilities]
    sections = [
        "Owner-approved Chromie identity JSON:\n" + bounded_identity_json(context) + "\n\n",
        "Owner-approved Personality Expression JSON:\n" + bounded_personality_json(context) + "\n\n",
        "Owner-approved Stable Mind worldview/values JSON:\n" + bounded_stable_mind_json(context) + "\n\n",
        IDENTITY_SEMANTIC_CONTRACT, PERSONALITY_SEMANTIC_CONTRACT, STABLE_MIND_SEMANTIC_CONTRACT,
        EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
        agent_skill_prompt_section(context, agent_role=tier + "_planner"),
        trusted_target_evidence_prompt_section(context),
    ]
    if include_capability_catalog:
        sections.append(catalog_label + ":\n" + json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n\n")
    projections = {
        "Goal association": goal_association_prompt_projection(context, goal_ids=scope if request.planner_reentry_scope else None),
        "Scoped canonical Goals": list(goals.authoritative_goals),
        "Original Responsibilities": [item.model_dump(mode="json") for item in request.responsibilities],
        "UMI semantic uncertainty": [
            item.model_dump(mode="json") for item in request.meaning_uncertainties
        ],
        "Re-entry scope": request.planner_reentry_scope.model_dump(mode="json") if request.planner_reentry_scope else None,
        "Prior dialogue": recent_dialogue_prompt_projection(request.history),
        "language": request.language,
        "minimum_goal_satisfaction": minimum_goal_satisfaction,
        "Evidence-bound delivered dialogue": evidence_bound_dialogue(context, fallback_history=request.history),
        "Situation": situation_prompt_projection(context),
        "Future readiness": dict(goals.future_goal_times),
    }
    # Preserve required Work context, including accumulated execution evidence.
    # The transport admits the complete prompt against the configured model
    # context budget; independent character quotas reject valid re-entry inputs.
    required_sections = (
        ("trusted_terminal_evidence", "Host-bound terminal Evidence JSON"),
        ("canonical_plan_resolution", "Authoritative source Plan JSON for exact re-entry correlation"),
        ("trusted_execution_outcome", "Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning)"),
        ("planner_reentry_expectations", "Prior Planner-authored step expectations JSON (prospective hypotheses, never Evidence)"),
        ("trusted_goal_cancellation_evidence", "Host-bound Goal cancellation Evidence JSON"),
        ("active_task_snapshots", "Active and recoverable task bindings JSON"),
        ("existing_work_activities", "Existing retained or provisional Runtime Activities JSON"),
        ("interaction_context", "Goal-scoped Interaction Context JSON"),
        ("verified_tool_memory_index", "Verified tool-memory index JSON (provenance and bound arguments only; no result contents)"),
    )
    for key, label in required_sections:
        if key in context:
            value = context[key]
            if key == "canonical_plan_resolution" and request.planner_reentry_scope:
                label = (
                    "Historical source Work correlation JSON "
                    "(provenance only; never copy its envelope into current output)"
                )
                value = planner_reentry_source_work_projection(
                    value, goal_ids=set(request.planner_reentry_scope.goal_ids),
                )
            elif key == "trusted_execution_outcome" and request.planner_reentry_scope:
                label = (
                    "Trusted execution fact rows JSON "
                    "(input facts only; never an output template)"
                )
                value = planner_reentry_execution_truth_projection(
                    value, goal_ids=set(request.planner_reentry_scope.goal_ids),
                )
            sections.append("\n" + label + ":\n" + required_json(
                value, None, label=label,
            ) + "\n")
    if context.get("active_goal_snapshots"):
        sections.append("\nActive goals JSON:\n" + required_json(
            context["active_goal_snapshots"], None, label="Active goals",
        ) + "\n")
    projections.update({key: context.get(key) for key in (
        "result_evidence_reentry", "planner_cancellation_capability_facts",
        "provisional_safe_work",
    )})
    sections.append("Trusted Work planning facts JSON:\n" + required_json(
        projections, None, label=tier + " Planner complete Work facts",
    ))
    if request.planner_reentry_scope:
        sections.append(
            "\nPLANNER RE-ENTRY CONTRACT:\n"
            "This is a new bounded Planner decision over current trusted state, not a replay "
            "or repair of the historical source Plan. The historical source Work projection "
            "exists only to correlate completed/recoverable Activities with Evidence. Never "
            "copy its CanonicalPlan envelope or any historical Runtime/result envelope into "
            "the current result. Execution fact rows are input evidence, not a DTO example; "
            "never rename/copy them back into goal_outcomes, satisfaction, respond, or steps. "
            "Return "
            "only the current flat Work DTO required by the decoder. Never replay a completed "
            "Activity merely to report its result. When trusted terminal Evidence is sufficient "
            "for an information Goal, establish a respond outcome with zero steps; Social "
            "Cognition will author the actual words from the supplied Evidence. If Evidence is "
            "insufficient, plan only genuinely new Work or expose the real remaining gap.\n"
        )

    sections.append(
        "\n" + PLANNER_WORK_AUTHORITY_PROMPT + CAPABILITY_LOOKUP_PROMPT +
        "Capability library index JSON:\n" + required_json(context.get("capability_index", []), None, label="Capability index") +
        "Loaded capability details JSON:\n" + json.dumps(context.get("capability_details_loaded", [])) +
        "\nTrusted admitted clock JSON:\n" + json.dumps(
            request.turn_envelope.received_at.isoformat()
            if request.turn_envelope is not None
            else (context.get("user_turn_envelope") or {}).get("received_at")
        ) +
        "Read output_mode as provider-neutral WHAT, not permission or an execution lane. "
        "Ordinary language generation, creative/social responses and answers grounded in "
        "supplied context use respond with no Capability: SC will compose the actual words. "
        "This does not require prewritten response content or a speech Capability. Never "
        "invent a placeholder physical step for a communication Goal. Absent fresh facts require an exact "
        "information-acquisition Capability or an unresolved disposition. A verified tool-memory "
        "index contains provenance and arguments, not answers: retrieve only an exact fresh "
        "match of every material binding before treating its contents as Evidence. Never answer "
        "from another task's result. Physical or durable effects, media playback and provider-backed "
        "vocal performance require the qualified Capability; prose and social gestures cannot "
        "satisfy them. Preserve exact advertised semantic scope, resource contracts, input schema, "
        "effect class, lifecycle operation and target provenance. Singing requires a provider "
        "advertising that mode; playing a recording is not singing. No raw motor fields, new "
        "Capabilities, chromie.speak transport steps, or model-authored stop/emergency controls. "
        "Requested gestures are task Work; optional expression belongs to SC.\n"
        "For every scoped Goal, author exactly one keyed goal_outcome. execute references every "
        "and only its owned step_ids with complete coverage. respond establishes that the scoped "
        "communication can fulfill its obligation from supplied context/Evidence, with zero steps. "
        "It provides no words and no delivery claim. clarify records the actual unresolved input "
        "need after considering authoritative context, schema defaults and qualified acquisition. "
        "A missing provider or unsupported output mode is unavailable, not an input gap "
        "that the user can repair by selecting content. SC asks a genuine input question; "
        "do not write that question in rationale. unavailable/refused retain "
        "the unmet requirement and its grounded limitation. Compute top-level disposition from "
        "the set of current per-Goal dispositions: if the set has one value, use that value; "
        "use mixed only when the set has multiple distinct values. Goal count, multiple "
        "completed actions and earlier Work do not make current identical outcomes mixed. "
        "This aggregate never changes a per-Goal judgment or drops an independent sibling. "
        "An input gap does not erase an independent answer obligation. No field authorizes user "
        "consent. Set user_confirmation_required=true for provider-gated Work or a material "
        "safe_adjustment/alternative; explain that material change as a planning fact, not a "
        "user-facing utterance. Non-executable dispositions keep plan_relation=exact and "
        "user_confirmation_required=false. Proposed, scheduled and running Work are not completed effects.\n"
        "Omit optional IDs when absent; never use literal strings such as none/null as "
        "reuse_activity_id or an invented reference. Empty escalation_reason is the default. "
        "parameter_resolutions may be empty when Host can derive exact user-supplied "
        "provenance from the step and its owning Goal. If authoring a resolved parameter "
        "record, include its concrete value; unresolved ask_user records have no value.\n"
        "Include precedes_step_ids and follows_step_ids on every respond outcome; empty means no "
        "ordering obligation. precedes_step_ids lists Work that must wait until this communication "
        "finishes; follows_step_ids lists Work that must finish before this communication. A response "
        "following an action belongs in follows_step_ids, never precedes_step_ids. "
        "For an ordered communication outcome, name exact precedes_step_ids and follows_step_ids "
        "of the sibling Work it must precede or follow. These are ordering obligations, not "
        "execution steps or utterances. Omit both lists only when no such order is required. "
        "Preserve source Goal IDs on each step and do not borrow sibling bindings. Preserve "
        "before/after/parallel_with requirements. An answer after task Work requires follows_step_ids "
        "on that respond outcome, even though its own step_ids is empty. Every step_id occurs "
        "exactly once in steps; never repeat the same step object for a communication outcome. "
        "Construct steps as the union of the per-Goal step_ids you chose, with one object "
        "per distinct ID. A respond outcome contributes no object to steps. Check this "
        "accounting as part of your primary construction, not an extra review call. "
        "A fully adequate outcome has no unmet_goal_ids or unmet_requirements. "
        "Physical Work remains sequential. Repetitions "
        "use an advertised count argument rather than duplicated steps. Retained Work stays "
        "unchanged unless you explicitly select its exact reuse_activity_id or cancel_activity_ids. "
        "Never both cancel and reuse the same Activity. Do not replay completed Work.\n"
        "Satisfaction measures prospective Goal fulfillment if this Work and required communication "
        "succeed, not confidence, refusal quality or observed completion. Use 0=unsatisfied, "
        "0.01-0.749999=partial, 0.75-0.949999=substantial, 0.95-1=exact. Keep each per-Goal "
        "assessment local, and conserve every unmet Goal in the aggregate. Pending execution alone "
        "does not reduce adequacy. Complete coverage is complete accounting, not whole-Goal success. "
        "For acquire_information, name a falsifiable expected_outcome and retain deferred requirements "
        "as unmet; do not mix a prerequisite read with that Goal's still-ungrounded effect. Acquisition "
        "completion leaves the Goal open. Use exact qualified Evidence on re-entry to plan the next "
        "branch or establish a result communication need. Missing, failed, stale or unrelated "
        "Evidence establishes neither successful effect nor a conditional branch.\n"
        "Re-entry scope is exact: the original turn and source Plan are historical provenance, "
        "not permission to reopen excluded siblings. Prior expected_outcome is a hypothesis, not "
        "Evidence. Preserve epistemic strength and qualification in all decisions and rationales. "
        "Only the exact recoverable Runtime binding plus explicit retryable provider outcome may "
        "justify retrying failed Work; nonretryable does not itself mean unsafe. Cancellation "
        "attempts, resource release and speech completion are not physical stop Evidence.\n"
        "Planner owns new scheduling interpretation. For new future readiness, time_conditions "
        "must cite the exact owned time phrase in source_quote and realize due_at_ms. An exact "
        "ISO timestamp must retain its timezone and instant; relative time requires the supplied "
        "Gateway received_at clock. Missing timezone/clock is a real input gap. For retained "
        "ready_at, copy its exact typed due_at_ms. While not yet due, "
        "respond with no current Goal-owned steps and retain its future requirement as unmet; "
        "a timer cannot postpone an already executable step. Never parse deadlines into fake "
        "capabilities or put executable scheduling in prose.\n"
        + (
            "Fast may compose at most four executable steps per Goal. If HOW requires unresolved "
            "composition, delegate once with escalate, no steps, no committed outcome or "
            "communication, and an explicit unresolved need for every scoped Goal. Existing "
            "Capabilities remain present when composition is the gap; do not call them missing. "
            "Do not mix execute and clarify in a terminal canonical Fast result.\n"
            if tier == "fast" else
            "This is the sole Deep decision. Compose at most four exact steps per Goal when "
            "supported; do not escalate or request another model review. Unresolved input, "
            "unavailable scope or refused Work stays unmet.\n"
        )
        + "Return only the closed Work DTO required by the decoder. Host supplies Plan identity, "
        "tier, exact Goal IDs and communication-need identities after validation.\n\n"
        + immutable_source_turn_prompt(request)
        + "\nFINAL CANONICAL GOALS JSON:\n"
        + required_json(list(goals.authoritative_goals), None, label="Planner exact final Goal scope")
    )
    sections.append(future_readiness_contract(goals))
    sections.append(cancellation_reporting_contract(context, goals.cancellation_reentry_goal_ids))
    return "".join(sections)



def fast_evidence_reentry_goal_projection(
    goals: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """Project only canonical WHAT needed for a post-execution decision."""

    projected: list[dict[str, Any]] = []
    for goal in goals:
        if not isinstance(goal, dict):
            continue
        metadata = goal.get("metadata") if isinstance(goal.get("metadata"), dict) else {}
        item = {
            "goal_id": goal.get("goal_id"),
            "description": goal.get("description"),
            "success_criteria": goal.get("success_criteria"),
            "bindings": (goal.get("object") or {}).get("bindings")
            if isinstance(goal.get("object"), dict)
            else None,
            "constraints": goal.get("constraints"),
            "resource_responsibility": goal.get("resource_responsibility"),
            "output_mode": metadata.get("output_mode"),
        }
        projected.append({
            key: value for key, value in item.items()
            if value not in (None, "", [], {})
        })
    return projected


def fast_evidence_reentry_evidence_projection(
    context: dict[str, Any], *, evidence_refs: set[str], goal_ids: set[str],
) -> list[dict[str, Any]]:
    """Keep fresh trusted observations verbatim enough for Planner judgment."""

    rows: list[dict[str, Any]] = []
    for item in context.get("trusted_terminal_evidence") or []:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "").strip()
        if evidence_id not in evidence_refs:
            continue
        source_goal_ids = [
            str(goal_id).strip()
            for goal_id in item.get("source_goal_ids") or []
            if str(goal_id).strip()
        ]
        if goal_ids and source_goal_ids and not goal_ids.intersection(source_goal_ids):
            continue
        row = {
            "evidence_ref": evidence_id,
            "capability_ref": item.get("tool_id") or item.get("capability_id"),
            "status": item.get("status"),
            "goal_refs": source_goal_ids,
            "data": copy.deepcopy(item.get("data")),
            "reason_code": item.get("reason_code"),
        }
        rows.append({
            key: value for key, value in row.items()
            if value not in (None, "", [], {})
        })
    return rows


def fast_evidence_reentry_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    goal_context: PlannerGoalContext,
    allow_new_work: bool,
) -> LayeredPrompt:
    """Minimal post-execution Planner prompt, deliberately unlike Plan DTOs."""

    if request.planner_reentry_scope is None:
        raise ValueError("evidence re-entry prompt requires typed re-entry scope")
    context = request.context if isinstance(request.context, dict) else {}
    scope = request.planner_reentry_scope
    goal_ids = set(scope.goal_ids)
    evidence_refs = set(scope.evidence_refs)
    score_bands = "; ".join(
        f"{status}={minimum:g}..{maximum:g}"
        for status, (minimum, maximum) in GOAL_SATISFACTION_SCORE_BANDS.items()
    )
    contract = (
        "You are Chromie's Fast Planner handling a trusted post-execution Evidence re-entry. "
        "There is no new user meaning and no new Goal Association decision. Decide only what "
        "the already-owned scoped Goals need next after the supplied Runtime/Evidence facts. "
        "Return exactly the FastPlannerEvidenceReentryOutput decoder shape. This contract is "
        "intentionally different from CanonicalPlan and PlannerModelOutput: never emit "
        "goal_outcomes, steps, disposition, coverage, unmet_goal_ids, unmet_requirements, "
        "response_text, or any historical envelope key at the top level. For every scoped Goal "
        "emit exactly one goal_decisions item. next_action=respond means fresh trusted Evidence "
        "is sufficient and no new Work is needed; cite the exact evidence_refs and put nothing "
        "in new_work for that Goal. next_action=execute means genuinely new Work is required; "
        "author it only in new_work and never replay a completed source Activity. clarify is "
        "only for a real user-resolvable blocker; unavailable/refused are terminal limitations; "
        "escalate delegates unresolved HOW without Work. SC owns all user-facing wording. "
        "satisfaction_score/status assess how fully the selected next action covers the Goal; "
        f"the score must lie in the selected status band: {score_bands}. "
        "Use an empty escalation_reason unless at least one Goal actually chooses escalate; "
        "an escalation needs a nonblank reason and no new_work. "
        "pending execution alone does not lower prospective adequacy. Preserve uncertainty and "
        "epistemic strength from Evidence. Historical source Work and execution facts are input "
        "provenance only, never examples of the output shape. plan_relation normally stays exact; "
        "safe_adjustment/alternative requires confirmation and executable new Work."
    )
    source_work = context.get("canonical_plan_resolution") or {}
    facts = {
        "reentry_scope": scope.model_dump(mode="json"),
        "canonical_goals": fast_evidence_reentry_goal_projection(
            list(goal_context.authoritative_goals)
        ),
        "responsibilities": [
            {
                "local_ref": item.local_ref,
                "outcome": item.outcome,
                "output_mode": item.output_mode,
                "bindings": copy.deepcopy(item.bindings),
            }
            for item in request.responsibilities
        ],
        "fresh_evidence": fast_evidence_reentry_evidence_projection(
            context, evidence_refs=evidence_refs, goal_ids=goal_ids,
        ),
        "source_work_provenance": planner_reentry_source_work_projection(
            source_work, goal_ids=goal_ids,
        ),
        "execution_facts": planner_reentry_execution_truth_projection(
            context.get("trusted_execution_outcome"), goal_ids=goal_ids,
        ),
        "available_new_work_capabilities": (
            fast_advance_semantic_capability_projection(capabilities)
            if allow_new_work else []
        ),
        "original_user_text": request.original_user_text,
    }
    rendered = (
        contract
        + "\n\nTrusted post-execution facts JSON:\n"
        + required_json(facts, None, label="Fast Planner Evidence re-entry facts")
    )
    return LayeredPrompt.promote(rendered, operating_contract=(contract,))


def fast_evidence_reentry_system_prompt() -> str:
    return (
        "You are Chromie's Fast Planner at the post-execution Evidence boundary. "
        "Judge only the next Work state for the exact scoped Goals. Fresh trusted Evidence is "
        "fact; historical Plan/Runtime objects are provenance, not output templates. Return only "
        "FastPlannerEvidenceReentryOutput JSON. Do not write user-facing language."
    )


def fast_plan_prompt(
    request: CognitiveWorkRequest, capabilities: list[dict[str, Any]], *,
    response_schema: dict[str, Any], goal_context: PlannerGoalContext | None = None,
) -> str:
    return _canonical_work_prompt(request, capabilities, tier="fast", goal_context=goal_context)


def fast_advance_layered_prompt(
    request: CognitiveWorkRequest, *, responsibilities: list[CognitiveResponsibilityProposal],
    capabilities: list[dict[str, Any]], response_schema: dict[str, Any] | None = None,
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    contract = PLANNER_WORK_AUTHORITY_PROMPT + (
        "UMI owns WHAT. This Fast invocation decides Work over exact Responsibility refs while "
        "GA independently binds canonical Goals. The responsibilities array below is the complete "
        "task scope of THIS invocation; it may contain only part of the original turn. Use the "
        "immutable source, history and identity to ground HOW, not to add tasks absent from that "
        "array. SC independently handles interaction outside this task scope. For each Activity, "
        "identify the listed outcome it realizes or the necessary prerequisite it supplies; explain "
        "that connection in reason_summary. A valid Responsibility ref alone does not justify an "
        "unrelated Activity. Once those outcomes have their required Work, end the Activities list. "
        "Produce one complete Work DTO. No presentation wording or decoration. A Capability whose "
        "declared behavior_domains contain social_attention is task Work only when it realizes "
        "its own explicitly requested Responsibility; never append it to another Responsibility as "
        "acknowledgement, politeness, personality, or decoration. SC owns optional social expression. "
        "Use role=capability for direct executable task Work: activity_id, exact capability_id, "
        "args, source_responsibility_refs and timing. Use role=complete_response only for a "
        "language response. Use role=clarification only when a required input is actually missing; "
        "if no input is missing, create capability Work, never an empty clarification. Each "
        "activity_id is unique. List each Responsibility once in covered_responsibility_refs; "
        "several necessary Activities may share that ref to realize its complete outcome. "
        "Do not add a response for Work whose result is not available yet. The top disposition is "
        "execute for capability-only Work, respond for response-only Work, clarify for input-only "
        "needs, mixed when distinct Responsibilities require different roles, or escalate. "
        "complete_response establishes a context-grounded speech obligation, never delivered speech; "
        "include its rationale. clarification supplies typed information_gaps, never wording. "
        "Ordinary requested speech admits complete_response; a mixed-mode other Responsibility may include it alongside Capability Work only when the source Responsibility itself explicitly contains a communicative result. Never add complete_response just to acknowledge, confirm, narrate or announce a physical Work sequence; SC decides that interaction independently. Information acquisition, "
        "physical/durable effects, vocal performance and media need their qualified providers. "
        "Do not confuse the person's intended activity with a robot action. "
        "Match each whole requested outcome against Capability semantic_scope, effects and "
        "resource_contract; select only a complete realization with valid arguments. "
        "A prerequisite is not fulfillment. If several steps are needed "
        "compose them within the Fast budget or delegate once to Deep before dispatch; "
        "never mark a partial first action as complete or leave intended later Work only in reason_summary. "
        "Preserve every numeric and named binding through declared argument_realization; "
        "repetition requires a supported count argument. A required non-numeric string may "
        "copy a literal in both its owning outcome and original input without a duplicate "
        "binding; never borrow sibling values or contradict bindings. Realize the complete "
        "query scope into provider date/period without changing meaning. Never invent an argument, "
        "target or low-level control. Target references require exact trusted target Evidence. "
        "Fresh information without Evidence requires an exact acquisition Capability, not asking "
        "the user for the result. A Capability Activity's step_purpose follows its provider's "
        "resource_contract, not its position in the Plan. Use acquire_information only for a "
        "provider declared to acquire information or to acquire a resource for "
        "planner_communicative_activity delivery; include expected_outcome describing the required "
        "Evidence. Other physical or state-changing Activities use achieve_effect, including "
        "intermediate prerequisites. Their completion fulfills only their own effect, not the "
        "whole Responsibility. Do not add a second lookup/read "
        "Capability as a surrogate for reporting its result. Acquisition completion is staged Work, "
        "not whole-Responsibility completion; Evidence re-entry will decide the remaining answer or "
        "Work. An Activity you are authoring now has no result Evidence yet: "
        "never consume or retrieve that same-Work future result as verified memory. A verified-memory "
        "Activity may cite only an exact evidence_id/tool_id already supplied in "
        "verified_tool_memory_index; when that index is empty, verified-memory Work is unavailable. "
        "Generic speech and stop/emergency are not task Capabilities. "
        "Clarification requires a real user-resolvable blocker after considering authoritative "
        "context, observation/query, preference, schema defaults and safe bounded defaults. "
        "Each gap cites exact unresolved_meaning or execution_input Capability, required_for and "
        "resolution_sources_considered. Supplied bindings/defaults are not missing. "
        "Preserve every UMI unresolved item; independent siblings may proceed as mixed. "
        "Cover every source ref exactly and give each terminal Responsibility one outcome. "
        "Preserve before/after/precedes/follows/parallel_with in Activity order and timing. "
        "Ordered Activities, including communication Needs, use timing=sequential. Physical Work "
        "stays sequential unless the accepted Responsibilities explicitly require concurrency. Every "
        "Capability Activity in one requested concurrent group must use timing=parallel; never mark "
        "only one member parallel or emit a singleton parallel marker. Parallel Work still requires "
        "a compatible Capability/resource group. Preserve requested speech "
        "order even though SC realizes it later. Execute only direct, fully grounded Work within "
        "Fast budget; unsupported capability or unresolved composition delegates once to Deep "
        "with escalate, deep_planner continuation and no Activities. No same-decision reviewer. "
        "Runtime retains authorization, confirmation, resource safety and delivery authority. "
        "Planning or satisfaction is prospective, never proof of execution or delivery."
    )
    facts = {
        "responsibilities": [item.model_dump(mode="json", exclude_defaults=True) for item in responsibilities],
        "meaning_uncertainties": [
            item.model_dump(mode="json") for item in request.meaning_uncertainties
        ],
        "goal_continuity": fast_goal_continuity_projection(context),
        "context": {key: context.get(key) for key in (
            "interaction_context", "existing_work_activities", "active_task_snapshots",
            "verified_tool_memory_index", "trusted_terminal_evidence", "result_evidence_reentry",
            "trusted_execution_outcome", "planner_reentry_expectations", "trusted_goal_cancellation_evidence",
        ) if key in context},
        "history": recent_dialogue_prompt_projection(request.history),
        "language": request.language,
        "situation": situation_prompt_projection(context),
        "capabilities": fast_advance_streaming_capability_prompt_projection(capabilities),
        "capability_index": context.get("capability_index", []),
        "capability_details_loaded": context.get("capability_details_loaded", []),
    }
    rendered = (
        role_memory_context(context, role="planner") + contract + EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT + CAPABILITY_LOOKUP_PROMPT
        + "\nOwner-approved Chromie identity JSON:\n" + bounded_identity_json(context)
        + "\nOwner-approved Personality Expression JSON:\n" + bounded_personality_json(context)
        + "\nOwner-approved Stable Mind JSON:\n" + bounded_stable_mind_json(context)
        + "\n" + IDENTITY_SEMANTIC_CONTRACT + PERSONALITY_SEMANTIC_CONTRACT + STABLE_MIND_SEMANTIC_CONTRACT
        + agent_skill_prompt_section(context, agent_role="fast_planner")
        + trusted_target_evidence_prompt_section(context)
        + "\nTrusted source facts JSON:\n" + required_json(facts, None, label="Fast complete Work source facts")
        + "\n" + immutable_source_turn_prompt(request, what_authority="UMI Responsibilities")
    )
    return LayeredPrompt.promote(rendered, operating_contract=(contract,))


def _normalized_sibling_refs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def fast_responsibility_decision_projection(
    responsibilities: list[CognitiveResponsibilityProposal],
) -> list[dict[str, Any]]:
    """Pass complete owned intent without imposing an Activity count or lane."""
    return [
        {"ref": item.local_ref, "outcome": item.outcome, "output_mode": item.output_mode,
         "source_evidence": item.source_evidence.model_dump() if item.source_evidence else None}
        for item in responsibilities
    ]


def fast_advance_semantic_capability_projection(
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the non-duplicated semantic index used before the exact schema.

    The terminal response schema already carries the only legal per-Capability arg
    branches.  Repeating those branches in the catalog made two overlapping sources
    look authoritative to the model and inflated the Fast prompt substantially.
    """

    return [
        {key: value for key, value in capability.items() if key != "args_schema"}
        for capability in fast_advance_capability_prompt_projection(capabilities)
    ]


def _fast_streaming_prompt_input_schema(input_schema: dict[str, Any]) -> dict[str, Any]:
    """Preserve the canonical Capability action template for Fast Planner.

    Planner needs the same requiredness, types, enums, bounds and defaults that trusted
    validation uses. A declared default describes omission behavior; it is capability
    metadata and never an extra field in Planner output.
    """

    return copy.deepcopy(input_schema)


def fast_advance_streaming_capability_prompt_projection(
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one argument contract beside each semantic catalog entry.

    The prompt and native response schema share the same Capability action template. Planner
    sees defaults so it knows what omission means, while its output remains only the actual
    selected arguments and provenance/rationale fields defined by the Planner DTO.
    """

    return [
        {
            **{key: value for key, value in capability.items() if key != "input_schema"},
            "args_schema": _fast_streaming_prompt_input_schema(
                capability.get("input_schema") or {}
            ),
        }
        for capability in capabilities
    ]


def fast_advance_capability_prompt_projection(
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep every admitted catalog choice and applicability constraint exact."""

    projected: list[dict[str, Any]] = []
    for capability in capabilities:
        input_schema = capability.get("input_schema") or {}
        properties = input_schema.get("properties") or {}
        required = {str(item) for item in (input_schema.get("required") or [])}
        arguments: list[dict[str, Any]] = []
        for name, raw_schema in properties.items():
            if not isinstance(raw_schema, dict):
                continue
            argument: dict[str, Any] = {
                "name": str(name),
                "required": str(name) in required,
            }
            for key in (
                "type",
                "enum",
                "const",
                "default",
                "minimum",
                "maximum",
                "minLength",
                "maxLength",
            ):
                if key in raw_schema:
                    value = raw_schema[key]
                    argument[key] = value
            arguments.append(argument)

        hints = capability.get("hints") or {}
        semantic_scope = hints.get("semantic_scope") or {}
        projected_scope = {
            key: value
            for key in (
                "responsibility_type",
                "resource_kinds",
                "delivery_modes",
                "domain",
                "acquisition",
                "supported_temporal_scopes",
                "unsupported_temporal_scopes",
            )
            if (value := semantic_scope.get(key)) not in (None, "", [])
        }
        realization_contract = hints.get("argument_realization") or {}
        projected_realization_contract = {
            str(name): {
                key: value
                for key, value in dict(contract).items()
                if key
                in {
                    "source_entity_type",
                    "planner_owned",
                    "arguments",
                    "minimum_arguments",
                    "contract",
                }
            }
            for name, contract in realization_contract.items()
            if isinstance(contract, dict)
        }
        resource_contract = hints.get("resource_contract") or {}
        projected_resource_contract = {
            key: value
            for key in (
                "provider_role",
                "plan_requires",
                "plan_provides",
                "completion_requires",
            )
            if (value := resource_contract.get(key)) not in (None, "", [])
        }
        projected.append(
            {
                "capability_id": str(capability.get("capability_id") or ""),
                "description": str(capability.get("description") or ""),
                "args_schema": arguments,
                "requires_confirmation": bool(capability.get("requires_confirmation")),
                "can_run_parallel": bool(capability.get("can_run_parallel")),
                "parallel_metadata_declared": bool(capability.get("parallel_metadata_declared")),
                "resource_claims": list(capability.get("resource_claims") or []),
                "effects": list(capability.get("effects") or []),
                "safety_class": str(capability.get("safety_class") or ""),
                "side_effect_free": bool(capability.get("side_effect_free")),
                "when_to_use": str(hints.get("when_to_use") or ""),
                "when_not_to_use": str(hints.get("when_not_to_use") or ""),
                "semantic_type": str(hints.get("semantic_type") or ""),
                "semantic_scope": projected_scope,
                "argument_realization": projected_realization_contract,
                "resource_contract": projected_resource_contract,
            }
        )
    return projected


def fast_streaming_advance_system_prompt() -> str:
    return PLANNER_WORK_AUTHORITY_PROMPT + (
        "Return one complete Work JSON object, with no extra text.\n"
        "Serialize each Capability args object in the lexicographic property order shown in "
        "args_schema, including nested objects. Decide all needed arguments before writing "
        "that object: after emitting a later property, the constrained decoder cannot return "
        "to an earlier property. This is only serialization order; retain every supplied "
        "material binding."
    )


def fast_layered_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
    goal_context: PlannerGoalContext | None = None,
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    identity_world = (
        "Owner-approved Chromie identity JSON:\n"
        f"{bounded_identity_json(context)}\n\n"
        "Owner-approved Personality Expression JSON:\n"
        f"{bounded_personality_json(context)}\n\n"
        "Owner-approved Stable Mind worldview/values JSON:\n"
        f"{bounded_stable_mind_json(context)}\n\n"
    )
    capability_contract = (
        agent_skill_prompt_section(context, agent_role="fast_planner")
        + trusted_target_evidence_prompt_section(context)
        + "Executable common capability catalog JSON:\n"
        + json.dumps(capabilities, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n\n"
    )
    rendered = role_memory_context(context, role="planner") + fast_plan_prompt(
        request,
        capabilities,
        response_schema=response_schema,
        goal_context=goal_context,
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_world,),
        operating_contract=(
            IDENTITY_SEMANTIC_CONTRACT,
            PERSONALITY_SEMANTIC_CONTRACT,
            STABLE_MIND_SEMANTIC_CONTRACT,
            EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
        ),
        capability_contract=(capability_contract,),
    )


def fast_system_prompt() -> str:
    return PLANNER_WORK_AUTHORITY_PROMPT + "This is Fast planning; delegate unresolved HOW once. Return only the complete Work DTO."


def deep_plan_prompt(
    request: CognitiveWorkRequest, capabilities: list[dict[str, Any]], *,
    response_schema: dict[str, Any], expected_goal_ids: list[str],
    include_capability_catalog: bool = True, minimum_goal_satisfaction: float = 0.75,
    goal_context: PlannerGoalContext | None = None,
) -> str:
    return _canonical_work_prompt(request, capabilities, tier="deep", goal_context=goal_context,
                                  include_capability_catalog=include_capability_catalog,
                                  minimum_goal_satisfaction=minimum_goal_satisfaction)


def deep_layered_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
    expected_goal_ids: list[str],
    minimum_goal_satisfaction: float = 0.75,
    goal_context: PlannerGoalContext | None = None,
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    prompt_capabilities = [prompt_capability_contract(item) for item in capabilities]
    identity_world = (
        "Owner-approved Chromie identity JSON:\n"
        f"{bounded_identity_json(context)}\n\n"
        "Owner-approved Personality Expression JSON:\n"
        f"{bounded_personality_json(context)}\n\n"
        "Owner-approved Stable Mind worldview/values JSON:\n"
        f"{bounded_stable_mind_json(context)}\n\n"
    )
    capability_contract = (
        agent_skill_prompt_section(context, agent_role="deep_planner")
        + trusted_target_evidence_prompt_section(context)
        + "Executable capability catalog JSON:\n"
        + json.dumps(prompt_capabilities, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n\n"
    )
    rendered = role_memory_context(context, role="planner") + deep_plan_prompt(
        request,
        capabilities,
        response_schema=response_schema,
        expected_goal_ids=expected_goal_ids,
        minimum_goal_satisfaction=minimum_goal_satisfaction,
        goal_context=goal_context,
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_world,),
        operating_contract=(
            IDENTITY_SEMANTIC_CONTRACT,
            PERSONALITY_SEMANTIC_CONTRACT,
            STABLE_MIND_SEMANTIC_CONTRACT,
            EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
        ),
        capability_contract=(capability_contract,),
    )


def prompt_capability_contract(
    capability: dict[str, Any],
) -> dict[str, Any]:
    """Project the full executable catalog without duplicate provider prose.

    Deep Planner still receives every current capability's exact argument
    schema and safety/resource contract. Provider hints duplicate most of
    that data and previously pushed later capabilities beyond the bounded
    catalog serialization, making the advertised "full catalog" false in
    deployed prompts.
    """

    projected = {
        key: capability.get(key)
        for key in (
            "capability_id",
            "description",
            "input_schema",
            "requires_confirmation",
            "effects",
            "safety_class",
            "can_run_parallel",
            "parallel_metadata_declared",
            "exclusive_group",
            "resource_claims",
        )
    }
    hints = capability.get("hints")
    if isinstance(hints, dict):
        semantic_scope = hints.get("semantic_scope")
        if semantic_scope:
            projected["semantic_scope"] = semantic_scope
        argument_realization = hints.get("argument_realization")
        if argument_realization:
            projected["argument_realization"] = argument_realization
        resource_contract = hints.get("resource_contract")
        if resource_contract:
            projected["resource_contract"] = resource_contract
        when_to_use = str(hints.get("when_to_use") or "")
        if when_to_use and when_to_use != str(capability.get("description") or "").strip():
            projected["when_to_use"] = when_to_use
        when_not_to_use = str(hints.get("when_not_to_use") or "")
        if when_not_to_use:
            projected["when_not_to_use"] = when_not_to_use
    constraints = capability.get("execution_constraints")
    if isinstance(constraints, dict):
        retained_constraints = {
            key: constraints[key]
            for key in ("locomotion_envelope", "parallel_allowed_with_lanes")
            if constraints.get(key)
        }
        if retained_constraints:
            projected["execution_constraints"] = retained_constraints
    return projected


def deep_system_prompt() -> str:
    return PLANNER_WORK_AUTHORITY_PROMPT + "This is the sole Deep decision; never recurse or return to Fast. Return only the complete Work DTO."
