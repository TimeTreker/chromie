from __future__ import annotations

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
    from chromie_contracts.semantic_authority import PLANNER_COMMUNICATION_AUTHORITY_PROMPT, PLANNER_WORK_AUTHORITY_PROMPT
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.semantic_authority import PLANNER_COMMUNICATION_AUTHORITY_PROMPT, PLANNER_WORK_AUTHORITY_PROMPT

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


EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT = (
    "Treat an explicit numeric value in authoritative Goal text or a typed "
    "Goal binding as a "
    "user-supplied candidate for the matching catalog argument. When "
    "the value and units are unambiguous and the value is within the "
    "catalog schema, copy it exactly; never silently replace it with "
    "a schema default or describe it only in prose. Select a capability "
    "whose argument schema can represent the supplied value. Catalog enum labels "
    "never preserve an explicit quantitative pace merely because an "
    "enum sounds qualitatively similar; when the Goal supplies a numeric pace or "
    "velocity, select a qualified numeric argument and put that exact value there. "
    "Catalog defaults are only for parameters the user did not supply. If the "
    "units, argument mapping, or validity are uncertain, clarify or "
    "escalate according to the planner tier instead of claiming exact "
    "coverage. A material adjustment must use a non-exact plan_relation, "
    "require confirmation, and explain the change. The model owns the exact "
    "argument value and source_goal_ids on its executable step. Trusted code "
    "mechanically projects the duplicate user_supplied parameter provenance "
    "only when that argument has one exact owning Goal source; the model need "
    "not restate that derivable proof. A typed binding is the model-owned canonical "
    "provenance for a quantity stated in words by the user. Never borrow a numeric "
    "literal or typed binding from "
    "a sibling Goal to fill another step. When an optional catalog argument was not "
    "supplied by the owning Goal, omit that argument and its resolution so the "
    "provider applies its declared default, or copy the exact catalog default with "
    "strategy=schema_default and no source_goal_ids. Never label a catalog default "
    "as user_supplied. "
    "do not copy, paraphrase, or annotate Goal text into another field. "
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
            1200,
            label="GI unresolved-meaning evidence",
        )
    )
    if what_authority == "GI Responsibilities":
        projection = json.dumps(
            {"original_text": source["original_text"]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            "IMMUTABLE SOURCE TURN JSON (exact/read-only; GI Responsibilities "
            "own WHAT):\n"
            f"{projection}{unresolved}"
        )
    projection = json.dumps(
        {
            "original_text": source["original_text"],
            "authority": source["authority"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "IMMUTABLE SOURCE TURN JSON (read-only; "
        f"{what_authority} own WHAT; Planner may preserve exact wording or realize "
        "bound HOW, never reinterpret or repair WHAT):\n"
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
        f"{required_json(target_evidence, 1400, label='Planner target Evidence')}\n"
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
        + required_json(reached_times, 3200, label="Planner reached Goal readiness")
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
        + required_json(goal_times, 3200, label="Planner future Goal readiness")
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
        + required_json(sorted(goal_ids), 3200, label="Planner cancellation scope")
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
        + required_json(context.get("planner_cancellation_capability_facts") or [], 24000,
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
        sections.append(catalog_label + ":\n" + required_json(
            catalog, 9000 if tier == "fast" else 12000, label=tier.title() + " Planner capability catalog",
        ) + "\n\n")
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
    # Required evidence and identity sections have independently bounded owners.
    # Reject an oversized section before inference rather than truncating a tail
    # qualifier or borrowing another section's unused capacity.
    required_sections = (
        ("trusted_terminal_evidence", "Host-bound terminal Evidence JSON", 6000, 6000),
        ("canonical_plan_resolution", "Authoritative source Plan JSON for exact re-entry correlation", 5000, 5000),
        ("trusted_execution_outcome", "Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning)", 5000, 5000),
        ("planner_reentry_expectations", "Prior Planner-authored step expectations JSON (prospective hypotheses, never Evidence)", 3600, 3600),
        ("trusted_goal_cancellation_evidence", "Host-bound Goal cancellation Evidence JSON", 3200, 3200),
        ("active_task_snapshots", "Active and recoverable task bindings JSON", 5000, 6000),
        ("existing_work_activities", "Existing retained or provisional Runtime Activities JSON", 3500, 4000),
        ("interaction_context", "Goal-scoped Interaction Context JSON", 7000, 8000),
        ("verified_tool_memory_index", "Verified tool-memory index JSON (provenance and bound arguments only; no result contents)", 5000, 6000),
    )
    for key, label, fast_budget, deep_budget in required_sections:
        if key in context:
            sections.append("\n" + label + ":\n" + required_json(
                context[key], fast_budget if tier == "fast" else deep_budget, label=label,
            ) + "\n")
    if context.get("active_goal_snapshots"):
        sections.append("\nActive goals JSON:\n" + required_json(
            context["active_goal_snapshots"], max(3200, 3200 * len(scope)), label="Active goals",
        ) + "\n")
    projections.update({key: context.get(key) for key in (
        "result_evidence_reentry", "planner_cancellation_capability_facts",
        "provisional_safe_work",
    )})
    sections.append("Trusted Work planning facts JSON:\n" + required_json(
        projections, max(30000, 6000 * len(scope)), label=tier + " Planner complete Work facts",
    ))
    sections.append(
        "\n" + PLANNER_WORK_AUTHORITY_PROMPT +
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
        "the unmet requirement and its grounded limitation. Top-level disposition must aggregate "
        "the per-Goal dispositions: execute plus respond is mixed, even if the response is "
        "realized separately by SC. mixed accounts for independent siblings without dropping any. "
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
        "Future ready_at uses its exact typed due_at_ms in time_conditions. While not yet due, "
        "respond with no current Goal-owned steps and retain its future requirement as unmet; "
        "a timer cannot postpone an already executable step. Never parse deadlines into fake "
        "capabilities or put executable scheduling in prose.\n"
        + (
            "Fast may author at most one executable step per Goal. If HOW requires unresolved "
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
        + required_json(list(goals.authoritative_goals), max(4500, 1800 * len(scope)), label="Planner exact final Goal scope")
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
        "frame, wording, progress act or optional social decoration. SC independently communicates. "
        "Use role=capability for direct executable task Work: activity_id, exact capability_id, "
        "args, source_responsibility_refs and timing. Use role=complete_response only for a "
        "language response. Use role=clarification only when a required input is actually missing; "
        "if no input is missing, create capability Work, never an empty clarification. Each "
        "activity_id is unique; each Responsibility is covered exactly once, never add a second "
        "response for a Responsibility already assigned an Activity. The top disposition is "
        "execute for capability-only Work, respond for response-only Work, clarify for input-only "
        "needs, mixed when distinct Responsibilities require different roles, or escalate. "
        "A complete_response role establishes an ordinary speech obligation from context, not an "
        "utterance or delivered result; include its grounding rationale. A clarification role "
        "establishes exact missing inputs with typed information_gaps, not question wording. "
        "Only ordinary speech Responsibilities admit complete_response; information acquisition, "
        "physical/durable effects, vocal performance and media need their qualified providers. "
        "Do not confuse the person's intended activity with a robot action. "
        "Use only available catalog Capabilities matching the full semantic scope and args schema. "
        "Preserve every numeric and named binding through declared argument_realization; "
        "repetition requires a supported count argument. Never invent an unbound required argument, "
        "target or low-level control. Target references require exact trusted target Evidence. "
        "Fresh information without Evidence requires an exact acquisition Capability, not asking "
        "the user for the result. Generic speech and stop/emergency are not task Capabilities. "
        "Clarification requires a real user-resolvable blocker after considering authoritative "
        "context, observation/query, preference, schema defaults and safe bounded defaults. "
        "Each gap cites exact GI unresolved_meaning or execution_input Capability and required_for "
        "keys; include resolution_sources_considered. A supplied binding or default is not missing. "
        "Preserve every GI unresolved item; independent siblings may proceed as mixed. "
        "Cover every source ref exactly and give each terminal Responsibility one outcome. "
        "Preserve before/after/precedes/follows/parallel_with in Activity order and timing. "
        "All ordered Activities explicitly use timing=sequential, including communication Needs. "
        "Physical Work stays sequential. Parallel provider Work must form a genuine compatible "
        "group. Requested speech before/after Work becomes an ordered obligation; do not erase "
        "that order because SC realizes it later. Execute only direct, fully grounded Work within "
        "Fast budget; unsupported capability or unresolved composition delegates once to Deep "
        "with escalate, deep_planner continuation and no Activities. No same-decision reviewer. "
        "Runtime retains authorization, confirmation, resource safety and delivery authority. "
        "Planning or satisfaction is prospective, never proof of execution or delivery."
    )
    if "interaction_context" in context:
        required_json(context["interaction_context"], 1200, label="Fast Planner Interaction Context")
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
    }
    rendered = (
        role_memory_context(context, role="planner") + contract
        + "\nOwner-approved Chromie identity JSON:\n" + bounded_identity_json(context)
        + "\nOwner-approved Personality Expression JSON:\n" + bounded_personality_json(context)
        + "\nOwner-approved Stable Mind JSON:\n" + bounded_stable_mind_json(context)
        + "\n" + IDENTITY_SEMANTIC_CONTRACT + PERSONALITY_SEMANTIC_CONTRACT + STABLE_MIND_SEMANTIC_CONTRACT
        + agent_skill_prompt_section(context, agent_role="fast_planner")
        + trusted_target_evidence_prompt_section(context)
        + "\nTrusted source facts JSON:\n" + required_json(facts, 48000, label="Fast complete Work source facts")
        + "\n" + immutable_source_turn_prompt(request)
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
    """Project GI WHAT into a small, local Planner coverage/scheduling table.

    This is a lossless mechanical rearrangement of already-authoritative GI fields.
    It neither selects a Capability nor changes a relation.  Keeping relation edges
    beside their owner makes the model's coverage and timing choice local instead of
    asking it to recover those constraints from a large DTO plus two schemas.
    """

    projected: list[dict[str, Any]] = []
    relation_names = ("before", "after", "parallel_with")
    for responsibility in responsibilities:
        bindings = dict(responsibility.bindings or {})
        relations = {
            name: _normalized_sibling_refs(bindings.pop(name, None)) for name in relation_names
        }
        projected.append(
            {
                "ref": responsibility.local_ref,
                "outcome": responsibility.outcome,
                "output_mode": responsibility.output_mode,
                "semantic_bindings": bindings,
                "relations": relations,
                "goal_relationship": responsibility.relationship,
                "target_goal_ids": list(responsibility.target_goal_ids),
                "terminal_owner_required": responsibility.output_mode != "speech",
            }
        )
    return projected


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


def fast_advance_streaming_capability_prompt_projection(
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one exact argument contract beside each semantic catalog entry.

    The native streaming schema keeps a compact common Activity shape. The prompt
    catalog carries each exact input schema once; strict runtime validation checks
    arguments against that authoritative catalog after the JSON document is parsed.
    """

    semantic_projection = fast_advance_semantic_capability_projection(capabilities)
    return [
        {
            **semantic,
            "args_schema": dict(capability.get("input_schema") or {}),
        }
        for semantic, capability in zip(semantic_projection, capabilities)
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
    return PLANNER_WORK_AUTHORITY_PROMPT + "Return one complete Work JSON object, with no extra text."


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
        + required_json(capabilities, 9000, label='Fast Planner capability catalog')
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
        + required_json(prompt_capabilities, 12000, label='Deep Planner capability catalog')
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
