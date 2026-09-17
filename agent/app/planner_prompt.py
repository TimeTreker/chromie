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
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.core_interpretation import (
        CognitiveResponsibilityProposal,
        CognitiveWorkRequest,
    )
    from shared.chromie_contracts.interaction import VOCAL_PERFORMANCE_CAPABILITY_ID


CAPABILITY_LOOKUP_PROMPT = (
    "You have complete common Capability contracts and an index of the available library. "
    "If planning needs another Capability's details, return only requested_capability_ids "
    "with exact index IDs, up to eight in one batch, before authoring any Plan. "
    "The Host supplies their full contracts with the original source context. One lookup "
    "batch is allowed; after it, produce the complete Plan or the existing non-executing "
    "outcome. Never guess missing schemas or use a lookup to revise a completed decision. "
    "An uncommon Capability does not itself require Deep Planner. Restricted entries "
    "remain restricted. Catalog lookup authorizes no execution. "
)

EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT = (
    "Planner owns decomposition of complete intent into Activities, Capability choice, "
    "arguments, units, dependencies and scheduling. GI supplies complete "
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
    "Existing typed Goal constraints remain binding and cannot be overridden by a "
    "quote. Omit every optional input that is not bound by the Responsibility, canonical "
    "Goal, exact source evidence, or trusted context, even when its schema declares a "
    "default. Do not copy, choose, modify or restate schema defaults in model-authored "
    "Work, and do not replace omission with a minimum, maximum, conservative, guessed, "
    "or otherwise ungrounded value for a default-owned optional input. Trusted Runtime/"
    "provider realization applies declared defaults after Planner output. Never borrow a "
    "sibling Goal's values. Missing consequential input must use "
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
        "\n\nGI unresolved-meaning evidence (exact strings or empty):\n"
        + required_json(
            request.interpretation_unresolved,
            None,
            label="GI unresolved-meaning evidence",
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
        "to realize HOW, never reinterpret or repair WHAT, add omitted outcomes or resolve GI ambiguity):\n"
        f"{projection}{unresolved}"
    )




def trusted_target_evidence_prompt_section(context: dict[str, Any]) -> str:
    """Expose one already-owned target reference for primary targeted Work.

    The same evidence may also qualify optional decoration, but target
    Evidence is not auxiliary-only. Planner may copy an exact trusted reference
    into a provider-declared target argument; it may never infer a direction or
    synthesize a target when this projection is unavailable.
    """

    payload = context.get("planner_auxiliary_social_context")
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
        "Unresolved interpretation": list(request.interpretation_unresolved),
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
            sections.append("\n" + label + ":\n" + required_json(
                context[key], None, label=label,
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
        "GI owns WHAT. This Fast invocation decides Work over exact Responsibility refs while "
        "GA independently binds canonical Goals. Produce one complete Work DTO. No presentation "
        "wording or decoration; SC communicates independently. "
        "Use role=capability for direct executable task Work: activity_id, exact capability_id, "
        "args, source_responsibility_refs and timing. Use role=complete_response only for a "
        "language response. Use role=clarification only when a required input is actually missing; "
        "if no input is missing, create capability Work, never an empty clarification. Each "
        "activity_id is unique; each Responsibility is covered exactly once, never add a second "
        "response for a Responsibility already assigned an Activity. The top disposition is "
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
        "the user for the result. An Activity you are authoring now has no result Evidence yet: "
        "never consume or retrieve that same-Work future result as verified memory. A verified-memory "
        "Activity may cite only an exact evidence_id/tool_id already supplied in "
        "verified_tool_memory_index; when that index is empty, verified-memory Work is unavailable. "
        "Generic speech and stop/emergency are not task Capabilities. "
        "Clarification requires a real user-resolvable blocker after considering authoritative "
        "context, observation/query, preference, schema defaults and safe bounded defaults. "
        "Each gap cites exact unresolved_meaning or execution_input Capability, required_for and "
        "resolution_sources_considered. Supplied bindings/defaults are not missing. "
        "Preserve every GI unresolved item; independent siblings may proceed as mixed. "
        "Cover every source ref exactly and give each terminal Responsibility one outcome. "
        "Preserve before/after/precedes/follows/parallel_with in Activity order and timing. "
        "Ordered Activities, including communication Needs, use timing=sequential. Physical Work "
        "stays sequential; parallel Work requires a compatible group. Preserve requested speech "
        "order even though SC realizes it later. Execute only direct, fully grounded Work within "
        "Fast budget; unsupported capability or unresolved composition delegates once to Deep "
        "with escalate, deep_planner continuation and no Activities. No same-decision reviewer. "
        "Runtime retains authorization, confirmation, resource safety and delivery authority. "
        "Planning or satisfaction is prospective, never proof of execution or delivery."
    )
    facts = {
        "responsibilities": [item.model_dump(mode="json", exclude_defaults=True) for item in responsibilities],
        "interpretation_unresolved": list(request.interpretation_unresolved),
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
        + "\n" + immutable_source_turn_prompt(request, what_authority="GI Responsibilities")
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
    """Hide Runtime-owned optional default values from Fast's semantic view.

    The exact schema still drives constrained decoding and trusted validation. The prompt
    needs to know which optional controls exist and their legal type/range, but exposing a
    concrete provider default encourages small models to restate or dodge that value even
    when the source never requested an override. Mark that omission is Runtime-owned while
    preserving every non-default constraint needed to author an explicit grounded override.
    """

    projected = copy.deepcopy(input_schema)
    required = {str(item) for item in projected.get("required") or []}
    properties = projected.get("properties")
    if not isinstance(properties, dict):
        return projected
    for name, contract in properties.items():
        if (
            str(name) in required
            or not isinstance(contract, dict)
            or "default" not in contract
        ):
            continue
        contract.pop("default", None)
        contract["x-chromie-default-owner"] = "trusted_runtime"
        guidance = (
            "Optional default-owned input. Omit unless the Responsibility, canonical Goal, "
            "exact source evidence, or trusted context grounds an explicit override."
        )
        prior = str(contract.get("description") or "").strip()
        contract["description"] = f"{prior} {guidance}".strip()
    return projected


def fast_advance_streaming_capability_prompt_projection(
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one argument contract beside each semantic catalog entry.

    The native streaming response schema retains the exact Capability contract. The prompt
    projection differs only by withholding concrete optional defaults that belong to trusted
    Runtime/provider realization; it preserves names, requiredness, types, enums and bounds.
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
