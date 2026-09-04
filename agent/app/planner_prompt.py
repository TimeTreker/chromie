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
from .prompt_projection import bounded_json
from .planner_context import (
    canonical_goal_grounding,
    evidence_bound_dialogue,
    goal_association_prompt_projection,
    planner_goal_context,
    planner_provider_vocal_goal_ids,
    situation_prompt_projection,
)

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
    if what_authority == "GI Responsibilities":
        projection = json.dumps(
            {"original_text": source["original_text"]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            "IMMUTABLE SOURCE TURN JSON (exact/read-only; GI Responsibilities "
            "own WHAT):\n"
            f"{projection}"
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
        f"{projection}"
    )


def auxiliary_social_planning_prompt_section(context: dict[str, Any]) -> str:
    """Describe Planner-owned optional decoration without creating another owner."""

    payload = context.get("planner_auxiliary_social_context")
    if not isinstance(payload, dict):
        payload = {
            "eligible_capabilities": [],
            "target_evidence": {"available": False},
            "social_interaction_style": {},
            "recent_auxiliary_behavior_evidence": [],
            "max_activities": 0,
        }
    eligible = payload.get("eligible_capabilities")
    if not isinstance(eligible, list) or not eligible:
        return "No auxiliary candidates; use [].\n"
    return (
        "Planner-owned auxiliary social Activity context JSON:\n"
        f"{bounded_json(payload, 5000)}\n"
        "auxiliary_activities is an optional non-Goal list in this same primary "
        "Planner result. Empty is normal. Add an item only when a small body expression "
        "materially improves one real primary communicative act, plan response, or plan "
        "step and remains non-disruptive. Select only an eligible capability shown here, "
        "use schema-valid semantic args, timing=parallel, execution_role=social_decoration, "
        "and cite the exact primary anchor. Never create an auxiliary item for an internal "
        "cognition milestone, never move explicit user-requested behavior out of Goal-owned "
        "steps, never repeat a recent decoration, and never invent target/perception facts. "
        "Do not create a communicative Activity merely to provide an anchor for decoration. "
        "Do not copy a Goal-owned count, duration, direction, distance, or other modifier "
        "into decoration args just because it is present on the primary Responsibility; "
        "auxiliary args must be independently justified by the selected social function, "
        "candidate schema, and trusted target evidence. "
        "If target freshness is absent, use an untargeted eligible expression or return an "
        "empty list. Auxiliary Activities never satisfy, block, cancel, clarify, or create a "
        "Goal and never justify response wording.\n\n"
    )


def trusted_target_evidence_prompt_section(context: dict[str, Any]) -> str:
    """Expose one already-owned target reference for primary targeted Work.

    The same bounded context may also qualify optional decoration, but target
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
        f"{bounded_json(target_evidence, 1400)}\n"
        "This evidence may ground a primary targeted Capability only when its exact "
        "semantic target matches the owning Responsibility and the Capability declares "
        "the corresponding argument_realization. Copy the supplied target_ref exactly. "
        "Never replace it with a pronoun surface, invent another target, infer yaw/pitch, "
        "or use this evidence for an unrelated Responsibility. Provider and Runtime "
        "retain target-resolution and safety authority.\n\n"
    )


def fast_plan_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
) -> str:
    context = request.context if isinstance(request.context, dict) else {}
    goal_context = planner_goal_context(
        context,
        reentry_scope=request.planner_reentry_scope,
    )
    skill_section = agent_skill_prompt_section(
        context,
        agent_role="fast_planner",
    )
    skill_section += trusted_target_evidence_prompt_section(context)
    skill_section += auxiliary_social_planning_prompt_section(context)
    identity_json = bounded_identity_json(context)
    personality_json = bounded_personality_json(context)
    stable_mind_json = bounded_stable_mind_json(context)
    association = goal_association_prompt_projection(
        context,
        goal_ids=(
            goal_context.expected_goal_ids if request.planner_reentry_scope is not None else None
        ),
    )
    grounding = list(goal_context.authoritative_goals)
    # Re-entry may close an originally effectful Goal from trusted terminal
    # Evidence.  Use the shared scoped Goal context instead of reclassifying the
    # original Goal shape, which would contradict the re-entry schema and tell
    # the model to execute already-completed Work again.
    response_only = goal_context.response_only
    requires_execution = goal_context.requires_execution
    argument_grounding_contract = (
        EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT
        + "For chromie.memory.retrieve_verified_tool_result, all resolved "
        "material Goal bindings belong inside the single material_args object. "
        "Nested material fields are not missing direct step arguments, so do "
        "not emit separate parameter_resolutions for them. "
        "If a resolution for that nested object is useful, its parameter "
        "must be material_args and its value must equal the complete "
        "step.args.material_args object. "
    )
    result_evidence_contract = (
        "Host-bound terminal Evidence records the trusted state transition for the "
        "exact canonical Goals. Reconsider the still-open Responsibility from the "
        "current Goal, Situation, actual Work, and trusted_terminal_evidence. You "
        "may answer from that Evidence, author genuinely new follow-up Work when it "
        "is now necessary, clarify/wait, or produce no new Activity. Do not repeat "
        "the Capability Activity that just completed merely because Evidence "
        "arrived. Preserve Evidence values, scope, and epistemic strength: an "
        "observation, forecast, estimate, and probability are different claims, and "
        "a probability below 100% must remain uncertain. trusted_execution_outcome "
        "contains mechanical terminal/qualification truth only; provider_retryability "
        "is a bounded provider-declared execution fact, not Host permission or a retry "
        "recommendation. Interpret these facts yourself, never expose internal reason-code "
        "or workflow vocabulary. Before authoring response_text, read each scoped "
        "trusted_execution_outcome.goal_outcomes item. If status=completed and required "
        "completion_qualification is established, describe that exact source-Plan effect "
        "as completed or remain status-neutral; never describe it as future, starting, or "
        "ongoing. Exact completed step arguments remain grounded by the immutable source "
        "Plan even when the provider payload does not repeat them. If status=completed but "
        "required completion qualification is not established, do not claim completed, "
        "ongoing, or future execution; remain silent unless a natural status-neutral "
        "qualification materially helps. If status is failed, cancelled, or timed_out, "
        "state only that actual outcome or remain status-neutral and never promise the old "
        "Work. The typed Planner re-entry scope and FINAL CANONICAL "
        "GOALS are exact; do not claim completion of sibling effects found only in "
        "the original turn or source_text. The original user turn and source Plan "
        "are historical provenance, not a fresh command. A completed source-Plan "
        "step is prior Work and must not be copied into the new steps array. When "
        "trusted Evidence completes every scoped Goal and a completion response is "
        "still useful, use respond outcomes with exact Evidence-grounded wording, "
        "zero steps, exact satisfaction, and no sibling unmet requirements. Author "
        "new steps only for a distinct still-open requirement made necessary by the "
        "new state. Correlate terminal Evidence with the authoritative source Plan "
        "before interpreting its exact completed Work. Failed, cancelled, or timed-out "
        "Evidence cannot satisfy an information or effect Goal that still asks for the "
        "missing result. If Fast has no genuinely distinct exact Work for that open Goal, "
        "escalate the whole scoped plan with non-exact satisfaction; never mark a failure "
        "explanation as a complete respond result. "
        if isinstance(context.get("result_evidence_reentry"), dict)
        else ""
    )
    control_evidence_contract = (
        "Host-bound Goal cancellation Evidence records the factual result of "
        "deterministic cancellation control. Treat status, target_goal_ids, "
        "coaffected_goal_ids, released_confirmation_goal_ids, and reconciliation "
        "flags as trusted facts. A released confirmation sibling is still an open "
        "Responsibility that needs fresh planning, not a cancelled Goal. Do not "
        "re-execute a Goal whose cancellation status is cancelled, do not claim "
        "a failed or uncertain cancellation succeeded, and do not invent control "
        "effects. Decide only the still-needed conversational or independent Work "
        "delta from the current Goal/Work/Situation state. "
        if isinstance(context.get("goal_cancellation_reentry"), dict)
        else ""
    )
    goal_execution_contract = (
        "The canonical Goals are provider-free direct speech responsibilities. "
        "This plan is response-only: do not select executable capabilities or plan steps. "
        if response_only
        else (
            "At least one canonical Goal requires provider/effect evidence. The Plan "
            "must execute exact supplied Capability work for every such Goal or return "
            "a truthful escalation/clarification/unavailable/refused outcome. Do not "
            "close provider-required work with model memory or response text. "
            if requires_execution
            else ""
        )
    )
    semantic_scope_contract = "For a Goal with resource_responsibility, keep the entire acquire-and-deliver outcome as one semantic responsibility while treating the current capability catalog as the dynamic decomposition boundary. Fast Planner may terminally execute the Goal only when one exact registered Capability is a complete one-step cover. A provider's resource_contract.plan_requires/plan_provides declares public composition state; provider-internal stages remain private unless exposed as capabilities. If the catalog has only partial resource capabilities that could form a multi-step chain, escalate to Deep Planner rather than inventing hidden provider stages or claiming a partial primitive is complete. The Goal is provider-neutral: choose from the catalog by declared semantic scope and resource contract, never from capability-name conventions or a hardcoded provider rule. When resource_responsibility.source.status=unknown and the selected complete capability cannot resolve the source itself, return a specific context request and zero executable steps. Capability semantic_scope and resource_contract metadata are authoritative applicability evidence. Capability domains are not interchangeable merely because several capabilities share a read/effect class. Eligibility requires the selected Capability's declared information_domain and semantic scope to cover the exact Goal; never substitute the nearest read-only Capability from another domain. When the selected Capability accepts resource, source, or recipient objects, copy each accepted object exactly from the canonical resource_responsibility, including nested quantity, source bindings, and recipient fields. Those complete structured arguments are already grounded by the Goal contract; do not emit parameter_resolutions for their nested fields or invent a top-level quantity/distance argument that the Capability does not accept. Canonical Goal typed semantics are authoritative: non-resource Goals use object.bindings, while resource Goals use resource_responsibility directly with no persisted flat compatibility copy. Every material tool argument that directly represents one canonical binding must preserve that binding exactly; never reinterpret an original pronoun or replace a binding with older memory. When a Capability declares argument_realization, use the original user turn plus the canonical human-semantic binding to realize only the declared provider arguments. The model owns that HOW transformation and the exact step values; trusted code projects semantic_realization provenance only from the selected Capability's declared contract, step ownership, and those immutable values. Do not add a conflicting provenance row or relabel a transformed value as user_supplied/schema_default. This is Planner-owned HOW and must never rewrite the Goal. Preserve every canonical-goal qualifier, including temporal scope, comparison period, answer shape, ordering, and concurrency; never use a Capability default to silently narrow an explicit human scope. Never silently rewrite simultaneous independent actions as before/after actions. An explicit ordered relation must remain sequential. Capability parallel-safety is permission to honor user-requested concurrency, never evidence that concurrency was requested. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; in particular, a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech whose exact wording you own. A user-requested spoken response or performance may still be simultaneous with an Activity-lane step. Preserve that relation without inventing a chromie.speak plan step: keep the spoken Goal as a respond outcome, set each participating Activity step to timing=parallel only when its provider declares safe parallel execution, and leave cross-lane scheduling to trusted Runtime. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, escalate or propose an explicit safe adjustment rather than silently serializing the request. Never silently narrow a goal to fit a capability or its enum defaults. If the goal falls outside a capability's supported scope, escalate for clarification, another capability, or an honest unavailable result with zero steps. "
    semantic_scope_contract += (
        "Response text is audible language, never a stage direction or a substitute "
        "execution channel. In mixed speech with body or tool work, a respond outcome "
        "may author only the requested vocal content for its own Goal; it must not "
        "narrate, role-play, or claim another executable Goal's action. Keep that "
        "effect exclusively in its Capability step until trusted post-Evidence "
        "re-entry may describe completion. "
    )
    current_turn_communication_contract = (
        "The current canonical Goals own WHAT, with the immutable admitted source "
        "turn available only as exact read-only provenance. Retained Goals, delivered "
        "evidence-bound dialogue, and verified memory may support the response, but "
        "they must not replace the current Goal meaning. For a reaction, feeling, "
        "acknowledgement, evaluation, or practical "
        "decision, answer that latest act directly and naturally. Do not replay the "
        "previous task answer unless the latest turn actually asks for repetition, "
        "verification, explanation, comparison, or another answer from it. For a "
        "decision-shaped follow-up, make the first sentence directly state the "
        "requested decision, recommendation, or yes/no answer; never begin by "
        "restating prior evidence. Include at most one short supporting clause "
        "after that answer, and omit previously delivered sentences, measurements, "
        "or conditions that do not change the decision. "
    )
    supportive_speech_grounding_contract = (
        "Supportive, encouraging, empathic, or relational response_text may be warm, "
        "but it must not state or imply an unprovided user history, duration of effort, "
        "emotional state, circumstance, preference, relationship history, or likely "
        "future success as fact; express support without inventing familiarity or evidence. "
    )
    concise_output_contract = (
        "Keep goal summaries, step reasons, satisfaction rationales, and "
        "outcome rationales concise: one short sentence each. Do not "
        "repeat the user goal, catalog description, arguments, or the same "
        "justification across multiple fields. "
    )
    provisional_fast_activities = context.get("existing_work_activities")
    provisional_work_contract = (
        "The listed retained or provisional Runtime Activities may already be "
        "running or completed. Decide from the canonical Goals whether their Work "
        "is still required. To preserve and reuse the complete provisional plan, "
        "set each corresponding step.reuse_activity_id to the supplied stable "
        "activity_id and preserve the same Capability ID, exact arguments, Goal "
        "ownership, and timing. Omitting reuse_activity_id means that Activity is "
        "not selected for reuse. The Host will validate the explicit selection "
        "mechanically and will not execute selected Work twice. If any Work is no "
        "longer applicable or additional/different Work is required, author the "
        "correct complete canonical Plan instead; Runtime will then cancel only "
        "pending/cancellable provisional Work. Do not treat provisional execution "
        "as Goal Evidence before Host binding. Reusing retained_runtime Work is a "
        "reconciliation-only Plan and cannot add steps; when additional Work is "
        "needed, omit all reuse_activity_id values and author the complete replacement "
        "Plan so Runtime can cancel the old group before dispatch. When the retained "
        "Activity is chromie.work_dag.execute, its args.dag is the current Planner-authored "
        "WorkDAG. If its topology remains valid, reuse that exact Activity and do not emit "
        "a duplicate DAG. If Goal/Evidence changes require semantic DAG modification, author "
        "a replacement chromie.work_dag.execute step with the SAME dag_id, revision exactly "
        "+1, parent_revision equal to the retained revision, updated goal_ids/source_goal_ids, "
        "and only the future topology changes actually needed. Never rewrite or remove nodes "
        "already reported completed by trusted Evidence. DAGEngine owns execution-state "
        "advancement only; Planner is the sole WorkDAG semantic mutation authority. "
        if isinstance(provisional_fast_activities, list) and provisional_fast_activities
        else "This is prospective planning: no retained or provisional Runtime Work is supplied for reconciliation. "
    )
    if len(goal_context.expected_goal_ids) > 1:
        return (
            f"Goal association advisory JSON:\n{bounded_json(association, 3000)}\n\n"
            f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
            f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
            f"Owner-approved Stable Mind worldview/values JSON:\n{stable_mind_json}\n\n"
            f"{skill_section}"
            f"Executable common capability catalog JSON:\n{bounded_json(capabilities, 9000)}\n\n"
            f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{bounded_json(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
            f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{bounded_json(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
            f"Host-bound terminal Evidence JSON:\n{bounded_json(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
            f"Authoritative source Plan JSON for exact re-entry correlation:\n{bounded_json(context.get('canonical_plan_resolution') or {}, 5000)}\n\n"
            f"Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning):\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
            f"Prior Planner-authored step expectations JSON (prospective hypotheses, never Evidence):\n{bounded_json(context.get('planner_reentry_expectations') or [], 3600)}\n\n"
            f"Host-bound Goal cancellation Evidence JSON:\n{bounded_json(context.get('trusted_goal_cancellation_evidence') or [], 3200)}\n\n"
            f"Active and recoverable task bindings JSON:\n{bounded_json(context.get('active_task_snapshots') or [], 5000)}\n\n"
            f"Existing retained or provisional Runtime Activities JSON:\n{bounded_json(provisional_fast_activities or [], 3500)}\n\n"
            f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{bounded_json(situation_prompt_projection(context), 3600)}\n\n"
            f"{goal_progress_communication_prompt('Planner fast pass')}\n\n"
            f"Goal-scoped Interaction Context JSON:\n{bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Use Interaction Context to plan only the still-needed conversational and effectful delta. Preserve each typed event's owner and state: generated or scheduled speech is not proof the user heard it, committed work is not completion, and only execution_closure terminal events reference trusted Activity completion evidence. Do not treat missing or undelivered speech as fulfilled communication. Decide whether any new planner response_text materially helps the current human interaction, and prefer no extra speech when it would be filler or repetition. Do not repeat an already delivered or pending semantic act, or re-plan an already completed effect, unless the current meaning requires an explicit repeat, retry after failure, correction, changed state, new evidence, or clarification. It cannot override the authoritative current Goals or Canonical Plan contract. "
            "Author one fresh complete model-authored plan object from the authoritative goals and catalog. Do not classify text with lexical rules and do not expect the host to choose a capability, arguments, ordering, ownership, response, disposition, coverage, or satisfaction for you. "
            "Every top-level field and every nested field in FastPlannerMultiGoalPlanOutput is required. Use exact catalog capability IDs and schema-valid args. The verified tool-memory index contains no answer facts. When an exact fresh index entry matches every authoritative Goal binding, execute chromie.memory.retrieve_verified_tool_result with that evidence_id, original tool_id, and the same material arguments; never use a respond outcome directly from the index. If no exact fresh entry exists, execute the supplied fresh read capability. For a scheduled, running, or recoverable safe-read goal, reuse the bound capability and exact arguments and execute or retry it; never answer from another task's result. For an executable Goal, response_text is optional prospective conversational intent, not execution evidence. Use Interaction Context to leave it empty when an equivalent acknowledgement or commitment is already delivered or pending and nothing new needs saying. When there is a genuinely new acknowledgement, limitation, correction, confirmation need, or other conversational delta, author it naturally without predicting an external result or claiming execution/completion. A response_text never satisfies the executable Goal; post-execution factual claims require matching evidence. "
            f"{argument_grounding_contract}"
            f"{semantic_scope_contract}"
            f"{current_turn_communication_contract}"
            f"{supportive_speech_grounding_contract}"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            f"{STABLE_MIND_SEMANTIC_CONTRACT}"
            f"{result_evidence_contract}{control_evidence_contract}{goal_execution_contract}"
            f"{concise_output_contract}"
            f"{provisional_work_contract}"
            "Author stable non-empty step_id values, exact source_goal_ids, and matching outcome step_ids yourself. "
            "A planned step or response counts as satisfying its goal if it would succeed. For each keyed goal outcome, judge only that one goal; never put sibling goals or pending execution in unmet_goal_ids or unmet_requirements. Complete terminal outcomes use exact satisfaction with both unmet lists empty. "
            "Fast terminal scope permits at most one executable step per goal. A count argument performs repetition inside one skill call; never duplicate a step to implement repeated blinks, nods, or similar motions. Respond goals have no executable step. "
            "For a terminal plan, every per-goal outcome is execute or respond, coverage is complete, and the top-level disposition exactly aggregates the outcome dispositions. A respond outcome contains the actual answer now and references no steps. An execute outcome references every and only the model-authored steps owned by that goal. "
            "For semantic escalation, author disposition=escalate, coverage=partial or uncertain, steps=[], a non-empty top-level escalation_reason, and one escalate outcome for every canonical goal. Each escalate outcome must explain its own unresolved need, reference no steps, carry no response_text, and include a non-exact prospective satisfaction judgment. Do not mix escalation outcomes with executable or response outcomes. "
            "goal_satisfaction and every per-goal satisfaction are model judgments about prospective plan adequacy. A score from 0.95 through 1.0 requires status=exact. Escalation cannot claim exact satisfaction and therefore every escalation satisfaction score must be below 0.95. "
            "Generic response transport is not a task-plan step, so chromie.speak is never a plan step. Do not replace a conversational answer with a gesture or attention action. "
            "Use plan_relation=exact unless the plan materially changes the request; safe_adjustment or alternative requires user_confirmation_required=true and explanatory response_text. "
            "The host adds only plan_id, planner_tier, schema_version, and the authoritative top-level goal_ids after validating your output. It does not compile semantic decisions or generate step ownership. This primary result must contain complete per-Goal coverage, exact response truth, step ownership, satisfaction, and unresolved-work decisions; no later model will audit or repair its semantics. Return JSON only.\n\n"
            f"{immutable_source_turn_prompt(request)}\n\n"
            f"FINAL CANONICAL GOALS JSON:\n{bounded_json(grounding, 4500)}\n\n"
            f"FINAL TRUSTED EXECUTION OUTCOME JSON:\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
            f"FINAL RESULT-EVIDENCE WORDING CONTRACT:\n{result_evidence_contract or 'not_applicable'}\n\n"
            f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{bounded_json([item['capability_id'] for item in capabilities], 2500)}"
        )
    return (
        f"Goal association advisory JSON:\n{bounded_json(association, 3000)}\n\n"
        f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
        f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
        f"Owner-approved Stable Mind worldview/values JSON:\n{stable_mind_json}\n\n"
        f"{skill_section}"
        f"Executable common capability catalog JSON:\n{bounded_json(capabilities, 9000)}\n\n"
        f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{bounded_json(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
        f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{bounded_json(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
        f"Host-bound terminal Evidence JSON:\n{bounded_json(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
        f"Authoritative source Plan JSON for exact re-entry correlation:\n{bounded_json(context.get('canonical_plan_resolution') or {}, 5000)}\n\n"
        f"Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning):\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
        f"Prior Planner-authored step expectations JSON (prospective hypotheses, never Evidence):\n{bounded_json(context.get('planner_reentry_expectations') or [], 3600)}\n\n"
        f"Host-bound Goal cancellation Evidence JSON:\n{bounded_json(context.get('trusted_goal_cancellation_evidence') or [], 3200)}\n\n"
        f"Active and recoverable task bindings JSON:\n{bounded_json(context.get('active_task_snapshots') or [], 5000)}\n\n"
        f"Existing retained or provisional Runtime Activities JSON:\n{bounded_json(provisional_fast_activities or [], 3500)}\n\n"
        f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{bounded_json(situation_prompt_projection(context), 3600)}\n\n"
        f"{goal_progress_communication_prompt('Planner fast pass')}\n\n"
        f"Goal-scoped Interaction Context JSON:\n{bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
        "Use Interaction Context to plan only the still-needed conversational and effectful delta. Preserve each typed event's owner and state: generated or scheduled speech is not proof the user heard it, committed work is not completion, and only execution_closure terminal events reference trusted Activity completion evidence. Do not treat missing or undelivered speech as fulfilled communication. Decide whether any new planner response_text materially helps the current human interaction, and prefer no extra speech when it would be filler or repetition. Do not repeat an already delivered or pending semantic act, or re-plan an already completed effect, unless the current meaning requires an explicit repeat, retry after failure, correction, changed state, new evidence, or clarification. It cannot override the authoritative current Goals or Canonical Plan contract. "
        "Author one fresh complete object from the authoritative turn, goals, and catalog. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
        "Decide whether the executable common catalog completely covers every independent responsibility in the current user turn. A verified tool-memory index entry is only metadata that an exact prior result may be retrievable; it is never answer evidence. After Goal Association has fixed all material bindings, select chromie.memory.retrieve_verified_tool_result only when one index entry exactly matches the required tool_id and material arguments and is fresh enough for the user request. Otherwise select the fresh read capability. A status follow-up for a scheduled, running, or recoverable safe read must resume or retry the bound skill with its exact arguments when no matching completed memory entry exists. Never invent any external, private, or runtime result from model memory or index metadata. "
        "There are three legal aggregate shapes for one or many goals. A terminal plan uses coverage=complete, a goal_outcomes entry keyed exactly once by every canonical Goal ID, and non-null prospective satisfaction. A user-resolvable clarification uses disposition=clarify, coverage=partial or uncertain, steps=[], an exact natural question, one clarify outcome per affected Goal, and non-exact satisfaction. A semantic escalation uses disposition=escalate, coverage=partial or uncertain, steps=[], one escalate outcome for every canonical Goal ID, non-exact prospective satisfaction, and a specific non-empty escalation_reason. "
        "Finding one matching capability is not complete coverage. If any responsibility, ordering, concurrency relation, safety judgment, or semantic composition is unresolved beyond Fast, use the complete model-authored semantic-escalation shape; if only material user-suppliable input is missing, use clarification instead. A clarification question for a schema-bounded value must state the authoritative allowed range or choices so one valid user answer can resolve the blocker. Never return an empty outcome map or null satisfaction. "
        "Fast Planner may emit disposition=mixed only for a completely accounted simple combination with at least one common unlocked execute goal and direct conversational respond or user-resolvable clarify goals. Preserve exact step ownership; execute/respond outcomes are complete and exact, while clarify outcomes remain partial or uncertain with non-exact satisfaction. "
        "For complete direct execution, use exact supplied capability IDs and schema-valid args. "
        f"{argument_grounding_contract}"
        f"{semantic_scope_contract}"
        f"{current_turn_communication_contract}"
        f"{supportive_speech_grounding_contract}"
        f"{IDENTITY_SEMANTIC_CONTRACT}"
        f"{PERSONALITY_SEMANTIC_CONTRACT}"
        f"{STABLE_MIND_SEMANTIC_CONTRACT}"
        f"{result_evidence_contract}{control_evidence_contract}{goal_execution_contract}"
        f"{concise_output_contract}"
        f"{provisional_work_contract}"
        "Generic speech transport is not a plan step. Read canonical Goal output_mode as provider-neutral WHAT, then decide HOW from current trusted context, Evidence, and the qualified Capability catalog. output_mode=speech is directly authored conversation: use disposition=respond with the actual response_text now. output_mode=information may also respond immediately when the supplied trusted context or Evidence already grounds the requested answer; otherwise select exact information Work from the catalog, or escalate when Fast cannot resolve the need. output_mode=stateful_effect, body_action, media_playback, and provider-backed vocal performance modes cannot be completed merely by response_text. For styled_speech, recitation, singing, humming, or nonverbal_vocalization, execute only when exact capability_id chromie.vocal.perform advertises the authoritative mode; otherwise escalate with a truthful unavailable/refused/clarification outcome. For media_playback, use exactly one `chromie.media.<media_operation>` capability copied from the qualified catalog and preserve the requested lifecycle operation. For stateful_effect, select only an exact Capability whose declared semantics can cause the requested durable or future state change; never infer provider requirement or execution lane from Goal metadata. Executable outcomes may also carry response_text when it is a still-needed prospective conversational delta; use Interaction Context to omit equivalent delivered or pending speech, and never treat that text as execution evidence. Playback of existing music, recordings, streams, or sound effects is never evidence for singing. Greeting wording and length are ordinary model-authored conversational choices governed by the supplied scene, relationship context, and owner-approved personality. "
        "A safe-read information acquisition step prospectively covers an acquire-and-deliver Goal when trusted result re-entry will give Planner the Evidence needed to author final delivery; never pre-author an unknown result. Direct conversational responses must address the exact focal object requested: acknowledge or evaluate a stated plan as a plan, a feeling as a feeling, and a decision as a decision rather than substituting generic adjacent support. When the source names a plan without giving its details, refer naturally to that plan or arrangement without inventing details; do not praise, criticize, or characterize its quality, feasibility, progress, or contents. "
        "Every executable step must use capability_id plus source_goal_ids copied from the canonical goals. Do not use catalog-only parameters, action, input_schema, route, or step_type fields. "
        "When reality can resolve uncertainty more cheaply than guessing, ordinary Planner Work may use step_purpose=acquire_information with expected_outcome describing the concrete observation that would make progress possible. Select only an exact registered Capability whose declared semantics actually acquire that information; gaze/body/perception is eligible only when advertised by that Capability and remains subject to normal Runtime safety. For all steps, expected_outcome is a prospective, falsifiable expectation rather than Evidence. On trusted result re-entry compare actual Evidence with that expectation and revise Work/Situation when they disagree; never rewrite Evidence to match the Plan. "
        "goal_satisfaction measures prospective plan adequacy: planned steps count as satisfying their goals if successful, so pending execution alone is never an unmet requirement. A score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. Escalation cannot claim exact satisfaction and therefore every escalation satisfaction score must be below 0.95. If steps are present, top-level disposition cannot be respond. "
        "For every terminal or escalation result, goal_outcomes must be keyed exactly once by every supplied canonical Goal ID. Each execute outcome needs its real step_ids; each respond outcome needs non-empty response_text and step_ids=[]; each escalation outcome needs its unresolved reason and non-exact satisfaction. "
        "State an escalation obstacle precisely and consistently in escalation_reason, unresolved, every outcome rationale, and satisfaction text. If a matching component Capability is listed, treat it as present everywhere and name only the unresolved conditional or multi-stage composition; never say that component is missing or cannot acquire its declared result. When the requested semantic scope has no match, say that scope is unsupported without naming an absent capability ID, and never call the nonempty catalog or allowed list empty merely because its other Capabilities are inapplicable. Keep response_text, rationale, and reason_summary prospective and consistent with exact canonical dates; omit optional wording rather than introduce relative-time drift or claim an Activity already happened. "
        "Valid examples: execute uses owned steps and execute outcomes; mixed uses owned steps plus respond outcomes; escalation uses steps=[], one escalate outcome per Goal, and non-null non-exact goal_satisfaction. "
        "Use plan_relation=exact for an exact plan. For safe_adjustment or alternative, set user_confirmation_required=true and both top-level and per-Goal satisfaction to substantial with score >=0.75 and <0.95. When an authoritative Goal or trusted context explicitly permits proposing a concrete supported alternative, author that alternative as executable Work with a short explanation that explicitly asks the user to confirm it, and set user_confirmation_required=true; downstream confirmation holds execution, so the proposal is not unresolved meaning and is not a reason to escalate. "
        "When an existing Goal should become cognitively ready at a known future wall-clock time, author time_conditions with that exact canonical goal_id and due_at_ms. Use time_conditions only for future readiness; never encode timers as fake executable capabilities, response text, or Host-parsed Goal prose. "
        "The Ollama decoder enforces the exact flat FastPlannerModelOutput schema out-of-band. "
        "The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. "
        "This primary result must contain complete per-Goal coverage, exact response truth, step ownership, satisfaction, and unresolved-work decisions; no later model will audit or repair its semantics. Return JSON only. The final grounding below is authoritative and overrides previous output or advisory text.\n\n"
        f"{immutable_source_turn_prompt(request)}\n\n"
        f"FINAL CANONICAL GOALS JSON:\n{bounded_json(grounding, 4500)}\n\n"
        f"FINAL TRUSTED EXECUTION OUTCOME JSON:\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
        f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{bounded_json([item['capability_id'] for item in capabilities], 2500)}\n\n"
        f"FINAL RESULT-EVIDENCE WORDING CONTRACT:\n{result_evidence_contract or 'not_applicable'}\n"
        f"FINAL CONTROL-EVIDENCE WORDING CONTRACT:\n{control_evidence_contract or 'not_applicable'}"
    )


def fast_advance_layered_prompt(
    request: CognitiveWorkRequest,
    *,
    responsibilities: list[CognitiveResponsibilityProposal],
    capabilities: list[dict[str, Any]],
    response_schema: dict[str, Any] | None = None,
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    advance_contract = (
        "Responsibility evidence is authoritative contextual WHAT. Fast Planner owns "
        "the first complete HOW decision over that evidence: speaking and Capability "
        "Activities plus their sequential/parallel timing. Goal Association runs at "
        "the same time from the same GI result and alone commits Canonical Goal state. "
        "A speaking Activity is a Communicative Act: select its function, exact natural "
        "wording, truth stage, and semantic provenance. The Host validates and realizes "
        "that immutable act; Trusted Capability Runtime alone authorizes execution."
    )
    responsibility_decision_json = json.dumps(
        fast_responsibility_decision_projection(responsibilities),
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    )
    active_goals = bounded_json(context.get("active_goal_snapshots") or [], 600)
    interaction_context = bounded_json(
        context.get("interaction_context") or {},
        1200,
    )
    capability_json = json.dumps(
        fast_advance_streaming_capability_prompt_projection(capabilities),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    has_physical_resource_capability = any(
        str(((item.get("hints") or {}).get("semantic_scope") or {}).get("responsibility_type"))
        == "acquire_and_deliver_resource"
        and "physical_object"
        in set(((item.get("hints") or {}).get("semantic_scope") or {}).get("resource_kinds") or [])
        for item in capabilities
        if isinstance(item, dict)
    )
    physical_resource_instruction = (
        "For a structured physical-resource Capability, preserve exact resource "
        "identity in resource.description, recipient surface in recipient.description, "
        "and each source location, direction, distance, or route as a separate key in "
        "source.bindings. General template: entity/item=R, recipient=P, location=L, "
        "distance=D becomes resource.description=R, recipient.description=P, and "
        "source.bindings containing location=L and distance=D. Compare every semantic "
        "binding before closing terminal_plan; never collapse a numeric binding into "
        "location prose.\n\n"
        if has_physical_resource_capability
        else ""
    )
    presentation_schema_json = ""
    terminal_schema_json = ""
    if response_schema:
        properties = response_schema.get("properties") or {}
        presentation_schema_json = json.dumps(
            properties.get("presentation_commit") or {},
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
        )
        terminal_schema_json = json.dumps(
            properties.get("terminal_result") or {},
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
        )
    terminal_activity_limit = max(1, len(responsibilities))
    final_decision_checklist = (
        "FINAL DECISION CHECKLIST (apply after reading the schemas):\n"
        "1. Explicitly requested observable behavior is primary Goal Work. Put it in "
        "terminal_plan.activities, never presentation_commit.auxiliary_activities or "
        "terminal_plan.auxiliary_activities. Auxiliary social decoration is optional, "
        "normally [], and must not use a Capability whose effect overlaps any "
        "Responsibility or terminal Capability Activity.\n"
        "2. Cover every authoritative Responsibility exactly once by one Capability, "
        "complete_response, or clarification owner. Immediate direct speech may be "
        "completed in presentation_commit; speech ordered after or parallel with Work "
        "must remain a terminal complete_response Activity. Never complete the same ref "
        "in both frames. Do not omit a sibling and do not invent a new one.\n"
        "3. Scheduling is mechanical. If any Responsibility says parallel_with a "
        "sibling, every participating Capability Activity is timing=parallel and those "
        "Activities are adjacent. For before/after, emit the Activities in that order "
        "and mark every participant sequential. With no concurrency relation, use "
        "sequential. A lone parallel Activity is always invalid.\n"
        "4. Args are sparse. Copy every explicit binding to its matching required or "
        "semantically corresponding catalog arg. Do not add optional tuning args that "
        "the Responsibility did not request; provider defaults own omitted optional "
        "values.\n"
        "5. Examples: requested blink r1 => one terminal Activity owned by r1; concurrent r1+r2 "
        "=> two adjacent parallel Activities; ordered r1 then r2 => two sequential "
        "Activities in that order.\n"
        "6. Presentation speech is prospective, not the work itself. "
        "It never satisfies body, information, media, vocal-performance, or state-change "
        "Responsibilities. If no useful immediate speech is needed, emit the whole "
        "activity value as null. Never emit an Activity object with text=null or any "
        "other null required member. A silent commit has auxiliary_activities=[]; never "
        "invent speech only to anchor optional decoration. If the useful speech is an "
        "ordered terminal complete_response, keep the presentation silent and put any "
        "independently justified decoration in terminal_plan.auxiliary_activities with "
        "that terminal Activity as its exact anchor.\n"
        if presentation_schema_json and terminal_schema_json
        else ""
    )
    auxiliary_social_section = auxiliary_social_planning_prompt_section(context)
    trusted_target_section = trusted_target_evidence_prompt_section(context)
    source_turn_prompt = immutable_source_turn_prompt(
        request,
        what_authority="GI Responsibilities",
    )
    communication_instruction = (
        "In this one streaming call, author presentation_commit.activity as useful "
        "immediate progress, a complete conversational response, or null for silence. "
        "Give it a short stable activity_id; any auxiliary anchor_id must match. Close "
        "the frame, then continue the same decision in terminal_plan without repeating "
        "or contradicting it. terminal_plan.activities may contain "
        "still-needed Capability, complete_response, or genuine clarification Activities, "
        "but never another progress Activity. Emit only "
        "properties visible in the supplied payload schema for the selected object branch. "
        "If any ref needs Deep: stay silent, emit no Activities, and escalate all "
        "refs to it."
    )
    streaming_contract = (
        "STREAMING PRESENTATION COMMIT CONTRACT: Return exactly two tagged frames "
        "from this one invocation. The first frame is <presentation_commit> followed "
        "by one JSON payload object and </presentation_commit>. The second frame is "
        "<terminal_plan> followed by one JSON payload object and </terminal_plan>. "
        "Do not wrap them in a top-level object. Keep this order so the first validated "
        "frame may be realized before generation ends. "
        "The presentation payload "
        "must contain both activity and auxiliary_activities. It may contain one "
        "complete_response only for ordinary speech already grounded by trusted context "
        "and immediately deliverable without violating requested order or concurrency; "
        "otherwise it may contain one short "
        "pre-evidence progress Activity, or activity=null when speaking now adds no "
        "useful semantic delta. Progress is prospective and method-blind: it must "
        "not ask a question, claim execution/result/completion, or name an instrument, "
        "source, screen, sensor, implementation, or Capability unless supplied as "
        "authoritative Responsibility evidence. Preserve speaker and actor ownership "
        "and use the requested language naturally. presentation_commit auxiliary "
        "Activities may only be optional social decoration anchored to that exact "
        "communicative Activity; a silent commit has none. terminal_plan is the "
        "rest of the same HOW decision. It must not emit another progress Activity or "
        "repeat presentation decoration. It may author distinct optional decoration only "
        "for an exact primary Activity in terminal_plan.activities. It must emit a "
        "complete_response for still-needed "
        "ordinary speech that is ordered after or parallel with other terminal Work, and "
        "must not repeat a Responsibility already completed by the presentation. "
        "FIELD PLACEMENT IS EXACT: presentation_commit.activity owns only the "
        "model-visible activity_id, progress_kind when applicable, text, and "
        "source_responsibility_refs when the schema asks for them. Never put "
        "reason_summary, truth_stage, evidence_refs, role, timing, speech_act, or "
        "semantic_provenance there. terminal_plan alone owns disposition, coverage, "
        "covered_responsibility_refs, activities, auxiliary_activities, continuations, "
        "confidence, unresolved, and reason_summary. A terminal Capability Activity "
        "uses only role, capability_id, activity_id, args, timing, and "
        "source_responsibility_refs. Never use arguments, effects, resource_claims, "
        "or terminal-level decision fields inside an Activity. Every terminal Activity "
        "activity_id must differ from the committed presentation activity_id. "
        "reason_summary exists only once, at terminal_plan.reason_summary. "
        "No partial string, token, opening tag, or unclosed payload is a commitment; "
        "only the complete validated first tagged frame is."
    )
    wire_skeleton = (
        "MECHANICAL TWO-FRAME SKELETON (replace values; do not omit keys):\n"
        "<presentation_commit>\n"
        '{"activity":null,"auxiliary_activities":[]}\n'
        "</presentation_commit>\n"
        "<terminal_plan>\n"
        '{"disposition":"...","coverage":"...",'
        '"covered_responsibility_refs":[],"activities":[],'
        '"auxiliary_activities":[],"continuations":[],"confidence":0.0,'
        '"unresolved":[],"reason_summary":"..."}\n'
        "</terminal_plan>\n"
        f"terminal_plan.activities may contain at most {terminal_activity_limit} "
        "items for this request. Use only the minimum Work needed to satisfy the "
        "Responsibilities; social decoration belongs only in auxiliary_activities."
    )
    rendered = (
        advance_contract
        + "\n\n"
        + streaming_contract
        + "\n\n"
        + wire_skeleton
        + "\n\n"
        + source_turn_prompt
        + "\nLanguage hint: "
        + str(request.language or "auto")[:32]
        + "\n\nAUTHORITATIVE FAST DECISION TABLE (one row must receive exactly one "
        "terminal owner unless direct speech is completed by the presentation):\n"
        + responsibility_decision_json
        + "\n\nGI unresolved-meaning evidence (exact strings or empty):\n"
        + bounded_json(request.interpretation_unresolved, 1200)
        + "\n\nActive Goal continuity summary only:\n"
        + active_goals
        + "\n\nAlready-spoken/pending interaction summary only:\n"
        + interaction_context
        + "\n\n"
        + communication_instruction
        + "\n\nExecutable common Capability catalog JSON:\n"
        + capability_json
        + "\n\n"
        + trusted_target_section
        + "\n"
        + auxiliary_social_section
        + "\n\nThe catalog projection is complete for this Fast decision. Compare each "
        "Responsibility with capability_id, description, when_to_use, effects, "
        "semantic_type, semantic_scope, and the one args_schema shown for that Capability. "
        "Select only a direct semantic match. This catalog is the single exact argument "
        "authority; the terminal payload schema defines only common Activity placement. "
        "The absence of fresh result "
        "Evidence is the reason to execute a matching "
        "read Capability, never a reason to clarify. For a read request, physical-object "
        "acquisition, handover, body gestures, or attention motions cannot acquire external "
        "information. "
        "Match required arguments from GI "
        "bindings by meaning, not only by identical field name. GI bindings are resolved "
        "human-semantic input evidence; named entities and supplied temporal scopes are "
        "not missing just because provider vocabulary differs. Use argument_realization "
        "when declared. Preserve every binding and explicit temporal dimension. Emit "
        "optional args when an explicit binding overrides a default; omit only unused "
        "defaults.\n\n"
        + physical_resource_instruction
        + "When one matching Capability has all required input, set disposition=execute, "
        "coverage=complete, continuations=[], unresolved=[], and emit its schema-valid "
        "Capability Activity. Cover every Responsibility ref exactly. Use parallel only "
        "for genuine overlap without declared resource/safety conflict; dependent work "
        "is sequential, and a parallel group needs at least two Capability Activities. "
        "Never fuse progress wording into Capability work.\n\n"
        "For fresh information, presentation progress_kind=check_information. Use "
        "perform_action for an embodied, media, vocal, or state-changing effect such as "
        "walking or blinking. Otherwise use acknowledge_work. Progress is short, exact, "
        "prospective, and never claims execution, result, or completion. Use natural "
        "requested-language wording; zh/zh-CN must be Chinese, not English or pinyin. "
        "A complete_response is only for ordinary conversation needing no fresh Evidence.\n\n"
        "Clarify only a user-resolvable material blocker after considering authoritative "
        "context, trusted observation/query, owner preference, schema default, and a safe "
        "bounded default. Its InformationGap must cite unresolved_meaning exactly, or for "
        "execution_input cite the selected capability_id and absent required arg keys. Every "
        "InformationGap must also include non-empty required_for naming the exact missing "
        "meaning or execution input; "
        "record resolution_sources_considered. Never ask the user for an external result "
        "Chromie was asked to obtain; when GI unresolved evidence is empty, do not invent "
        "a semantic clarification or send a missing execution arg to Deep Planner. When "
        "the clear Goal has no exact matching Capability, clarification cannot create "
        "provider support: stay silent and escalate every ref; never ask to substitute "
        "a different action.\n\n"
        "Auxiliary Activities are normally empty and never primary work. If justified, "
        "use only auxiliary_activity_id, anchor_kind, anchor_id, capability_id, args, "
        "execution_role, timing, social_function, and target; never activity_id or "
        "reason_summary. Preserve speaker/actor ownership: a human report about their own "
        "state is not a robot action. Keep terminal_plan.reason_summary to one clause. "
        "It is prospective; never say speech or action completed. "
        "Escalate to deep_planner only when HOW exceeds the Fast budget, with no Capability "
        "Activities. Goal Association is concurrent, never a continuation.\n\n"
        + (
            "EXACT MODEL-VISIBLE TAGGED WIRE FORMAT:\n"
            "<presentation_commit>\n"
            "{one JSON object matching PRESENTATION PAYLOAD SCHEMA}\n"
            "</presentation_commit>\n"
            "<terminal_plan>\n"
            "{one JSON object matching TERMINAL PLAN PAYLOAD SCHEMA}\n"
            "</terminal_plan>\n\n"
            "PRESENTATION PAYLOAD SCHEMA:\n"
            + presentation_schema_json
            + "\n\nTERMINAL PLAN PAYLOAD SCHEMA:\n"
            + terminal_schema_json
            + "\n\n"
            if presentation_schema_json and terminal_schema_json
            else ""
        )
        + final_decision_checklist
        + "\nThis one call owns the complete decision; no later model audits or repairs it. "
        "Return exactly the two fresh tagged frames above with no Markdown or extra "
        "content. Stop immediately after </terminal_plan>."
    )
    return LayeredPrompt.promote(
        rendered,
        operating_contract=(advance_contract,),
    )


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

    Tagged streaming does not use Ollama's JSON constrained decoder, so repeating
    a full Activity union in the terminal payload schema only distracts the model.
    The catalog carries each input schema once; strict runtime validation remains
    unchanged after the tagged document is parsed.
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
    """Keep every bounded catalog choice visible without slicing JSON mid-item."""

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
                    argument[key] = value[:12] if isinstance(value, list) else value
            arguments.append(argument)

        hints = capability.get("hints") or {}
        semantic_scope = hints.get("semantic_scope") or {}
        bounded_scope = {
            key: value[:12] if isinstance(value, list) else value
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
        bounded_realization_contract = {
            str(name): {
                key: (
                    value[:12]
                    if isinstance(value, list)
                    else str(value)[:900]
                    if key == "contract"
                    else value
                )
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
        bounded_resource_contract = {
            key: value[:12] if isinstance(value, list) else value
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
                "description": str(capability.get("description") or "")[:360],
                "args_schema": arguments,
                "requires_confirmation": bool(capability.get("requires_confirmation")),
                "can_run_parallel": bool(capability.get("can_run_parallel")),
                "parallel_metadata_declared": bool(capability.get("parallel_metadata_declared")),
                "resource_claims": list(capability.get("resource_claims") or [])[:12],
                "effects": list(capability.get("effects") or [])[:12],
                "safety_class": str(capability.get("safety_class") or ""),
                "side_effect_free": bool(capability.get("side_effect_free")),
                "when_to_use": str(hints.get("when_to_use") or "")[:360],
                "when_not_to_use": str(hints.get("when_not_to_use") or "")[:360],
                "semantic_type": str(hints.get("semantic_type") or ""),
                "semantic_scope": bounded_scope,
                "argument_realization": bounded_realization_contract,
                "resource_contract": bounded_resource_contract,
            }
        )
    return projected


def fast_streaming_advance_system_prompt() -> str:
    """System authority for one Fast invocation with an early typed commit."""

    return (
        "You are Chromie's low-latency Fast Planner. Produce one complete semantic "
        "result as exactly two tagged frames in one continuous output stream. Emit "
        "<presentation_commit>...</presentation_commit> first and "
        "<terminal_plan>...</terminal_plan> second. Each frame contains exactly one "
        "JSON payload object matching its printed schema; the whole output is not a "
        "top-level JSON document. presentation_commit owns the exact wording and "
        "optional social decoration that may be realized as soon as that complete "
        "typed frame validates; terminal_plan continues the same decision and "
        "must not duplicate or contradict it. Accept Goal Interpretation's "
        "Responsibility evidence as authoritative contextual WHAT. Goal Association "
        "separately owns longitudinal association and Canonical Goal commits. Trusted "
        "Capability Runtime alone authorizes Work. Do not claim Work, fresh Evidence, "
        "or completion in the early presentation. Use no Markdown, code fence, "
        "explanation, self-check, repeated frame, or extra text. Stop immediately "
        "after </terminal_plan>."
    )


def fast_layered_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
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
        + auxiliary_social_planning_prompt_section(context)
        + "Executable common capability catalog JSON:\n"
        + bounded_json(capabilities, 9000)
        + "\n\n"
    )
    rendered = fast_plan_prompt(
        request,
        capabilities,
        response_schema=response_schema,
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
    return (
        "You are Chromie's Fast Planner. Plan only the final authoritative user turn and canonical goals at the end of the prompt. "
        "Author the semantic plan from the goals and executable catalog; never use phrase-to-action rules and never delegate semantic planning to the host. "
        "A verified-memory index is provenance only, never answer evidence. For a retained completed external-result Goal, a direct response may use only supplied delivered evidence-bound dialogue: preserve every measurement and condition exactly and omit unsupported embellishment. If that dialogue is absent, retrieve matching verified evidence, perform a fresh read, or escalate. "
        "Produce a complete simple response, common-skill plan, or simple execute-plus-respond mixed plan only when every responsibility is covered; otherwise author a complete per-goal semantic escalation. "
        "Do not execute, authorize, or claim completion. Return JSON only."
    )


def deep_plan_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
    expected_goal_ids: list[str],
    include_capability_catalog: bool = True,
    minimum_goal_satisfaction: float = 0.75,
) -> str:
    context = request.context if isinstance(request.context, dict) else {}
    goal_context = planner_goal_context(
        context,
        reentry_scope=request.planner_reentry_scope,
    )
    prompt_capabilities = [prompt_capability_contract(item) for item in capabilities]
    identity_json = bounded_identity_json(context)
    personality_json = bounded_personality_json(context)
    stable_mind_json = bounded_stable_mind_json(context)
    skill_section = agent_skill_prompt_section(
        context,
        agent_role="deep_planner",
    )
    skill_section += trusted_target_evidence_prompt_section(context)
    skill_section += auxiliary_social_planning_prompt_section(context)
    goals = context.get("active_goal_snapshots") or []
    if request.planner_reentry_scope is not None:
        scoped_goal_ids = set(goal_context.expected_goal_ids)
        goals = [
            item
            for item in goals
            if isinstance(item, dict)
            and " ".join(str(item.get("goal_id") or "").strip().split()) in scoped_goal_ids
        ]
    association = goal_association_prompt_projection(
        context,
        goal_ids=(
            goal_context.expected_goal_ids if request.planner_reentry_scope is not None else None
        ),
    )
    grounding = list(goal_context.authoritative_goals)
    response_only = goal_context.response_only
    requires_execution = goal_context.requires_execution
    result_evidence_contract = (
        "This is a trusted terminal-Evidence Planner re-entry, not a new user turn. "
        "Only the typed re-entry Goal scope and FINAL CANONICAL GOALS are current "
        "semantic authority; the original utterance, source_text, and source Plan "
        "are historical provenance for correlation. Never narrate, satisfy, or list "
        "an excluded sibling Goal. A source-Plan step reported completed is prior "
        "Work and must not be copied into this output's steps array. Before authoring "
        "response_text, read each scoped trusted_execution_outcome.goal_outcomes item. "
        "When status=completed and required completion_qualification is established, "
        "describe that exact source-Plan effect as completed or remain status-neutral; "
        "never describe it as future, starting, or ongoing. Exact completed arguments "
        "remain grounded by the immutable source Plan even when the provider payload "
        "does not repeat them. When status=completed but required completion qualification "
        "is not established, do not claim completed, ongoing, or future execution; remain "
        "silent unless a natural status-neutral qualification materially helps. When "
        "status is failed, refused, cancelled, or timed_out, state only that actual outcome or "
        "remain status-neutral and never promise the old Work. A provider retryability "
        "value of false means only non-retryable: do not call retry unsafe unless trusted "
        "Evidence separately establishes a safety reason. When trusted "
        "Evidence completes every scoped Goal and a completion response is still "
        "useful, author respond outcomes with exact Evidence-grounded wording, zero "
        "steps, exact satisfaction, and no sibling unmet requirements. Author new "
        "steps only for a distinct still-open requirement made necessary by the new "
        "state. A failed safe-read request is still-open recovery Work, rather than "
        "a replay of completed Work, only when the supplied Runtime task binding marks "
        "that exact request recoverable and its trusted provider outcome explicitly "
        "marks it retryable; in that case, author the exact bound Capability retry. "
        "Never replay completed Work merely because Evidence arrived. "
        if isinstance(context.get("result_evidence_reentry"), dict)
        else ""
    )
    provider_vocal_goal_ids = sorted(planner_provider_vocal_goal_ids(grounding))
    available_capability_ids = {
        str(item.get("capability_id") or "").strip()
        for item in capabilities
        if str(item.get("capability_id") or "").strip()
    }
    unavailable_provider_vocal_goal_ids = (
        provider_vocal_goal_ids
        if VOCAL_PERFORMANCE_CAPABILITY_ID not in available_capability_ids
        else []
    )
    goal_execution_contract = (
        "The canonical Goals are provider-free direct speech responsibilities. "
        "This plan is response-only: do not select executable capabilities or plan steps. "
        if response_only
        else (
            "At least one canonical Goal requires provider/effect evidence. The Plan "
            "must execute exact supplied Capability work for every such Goal or return "
            "clarify/unavailable/refused for the affected Goal. response_text may carry "
            "only a still-needed conversational delta and never proves execution. "
            if requires_execution
            else ""
        )
    )
    return (
        f"Goal association advisory JSON:\n{bounded_json(association, 3200)}\n\n"
        f"Active goals JSON:\n{bounded_json(goals, 3200)}\n\n"
        f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{bounded_json(situation_prompt_projection(context), 3600)}\n\n"
        f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
        f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
        f"Owner-approved Stable Mind worldview/values JSON:\n{stable_mind_json}\n\n"
        f"{skill_section}"
        + (
            f"Executable capability catalog JSON:\n{bounded_json(prompt_capabilities, 12000)}\n\n"
            if include_capability_catalog
            else ""
        )
        + f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{bounded_json(context.get('verified_tool_memory_index') or [], 6000)}\n\n"
        f"Host-bound terminal Evidence JSON:\n{bounded_json(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
        f"Authoritative source Plan JSON for exact re-entry correlation:\n{bounded_json(context.get('canonical_plan_resolution') or {}, 5000)}\n\n"
        f"Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning):\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
        f"Prior Planner-authored step expectations JSON (prospective hypotheses, never Evidence):\n{bounded_json(context.get('planner_reentry_expectations') or [], 3600)}\n\n"
        f"Host-bound Goal cancellation Evidence JSON:\n{bounded_json(context.get('trusted_goal_cancellation_evidence') or [], 3200)}\n\n"
        f"Active and recoverable task bindings JSON:\n{bounded_json(context.get('active_task_snapshots') or [], 6000)}\n\n"
        f"Existing retained or provisional Runtime Activities JSON:\n{bounded_json(context.get('existing_work_activities') or [], 4000)}\n\n"
        f"{goal_progress_communication_prompt('Planner deep pass')}\n\n"
        f"Goal-scoped Interaction Context JSON:\n{bounded_json(context.get('interaction_context') or {}, 8000)}\n\n"
        "Use Interaction Context to reason from what Chromie actually delivered, what trusted evidence says completed or failed, what remains pending, and what is new; produce only the still-needed conversational and effectful delta. Preserve owner and event_type evidence strength: generated or scheduled speech is not proof the user heard it, a proposal or committed request is not completion, and execution completion must retain execution_closure evidence references. Missing or undelivered communication may still leave a meaningful conversational delta; decide that from the current Goal and Interaction Context rather than from an earlier stage's private preference. Add response_text only when it materially improves the current interaction; avoid filler and repetition. Repeat an act only when the current meaning justifies it, such as an explicit repeat, retry, correction, changed state, new evidence, or clarification. The current canonical Goals and validation feedback remain authoritative. "
        f"{result_evidence_contract}"
        "The active task bindings are historical Host/runtime context. Their "
        "task_id, request_id, canonical_plan_id, and prior step IDs are not "
        "current Deep Planner step IDs. Never copy them into current "
        "steps[].step_id or goal_outcomes.*.step_ids; only IDs authored in "
        "this output's steps array are eligible.\n\n"
        "Produce the final DeepPlannerModelOutput for the complete user goal. Deep planning is terminal: never return to the Fast Planner. The current canonical Goals own WHAT; the immutable admitted source turn is exact read-only provenance, not permission to reinterpret or repair them. Retained Goals and delivered evidence may support a response, but must not replace the latest reaction, feeling, acknowledgement, evaluation, or practical decision represented by those Goals. Answer that current act directly; replay or re-explain a prior task only when the latest turn asks for it. The verified tool-memory index contains no answer facts. If one exact fresh index entry matches the authoritative Goal bindings, execute chromie.memory.retrieve_verified_tool_result with its evidence_id, original tool_id, and the exact material arguments. If no such entry exists, execute the fresh read capability. Never answer directly from index metadata, never reinterpret an unresolved reference from old memory, and never use another task's result. When a scheduled, running, or recoverable safe read has no matching completed memory entry, resume or retry its bound capability with the exact arguments. "
        "When Host-bound Goal cancellation Evidence is present, it is the trusted "
        "control result for the named cancellation: cancelled means the target Goal "
        "is terminal and must not be re-executed; not_cancelled means do not claim it "
        "stopped; uncertain means preserve that uncertainty. Coaffected Goals remain "
        "separate open/recoverable responsibilities unless their own state says otherwise. "
        "Goals listed in released_confirmation_goal_ids lost only a stale authorization "
        "token and remain open for fresh planning; never treat them as cancelled. A "
        "successful cancellation satisfies the cancellation control request, but the "
        "cancelled original effect Goal remains unsatisfied in per-Goal and top-level "
        "satisfaction; do not relabel non-execution as completion. "
        f"Required response language: {str(request.language or 'auto')[:32]}. "
        "Write every user-facing top-level and per-goal response_text naturally "
        "in that language. Do not switch languages merely because internal Goals, "
        "capability descriptions, rationales, or validation feedback use another language. "
        f"{goal_execution_contract}"
        f"{IDENTITY_SEMANTIC_CONTRACT}"
        f"{PERSONALITY_SEMANTIC_CONTRACT}"
        f"{STABLE_MIND_SEMANTIC_CONTRACT}"
        f"{EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT}"
        "Response text is audible language, never a stage direction or a substitute "
        "execution channel. In mixed speech with body or tool work, a respond outcome "
        "may author only the requested vocal content for its own Goal; it must not "
        "narrate, role-play, or claim another executable Goal's action. Keep that "
        "effect exclusively in its Capability step until trusted post-Evidence "
        "re-entry may describe completion. "
        "Use the full catalog, preserve all independent responsibilities, constraints, conditions, ordering, concurrency, temporal scope, comparison period, and requested answer shape. Never silently rewrite simultaneous independent actions as before/after actions. An explicit ordered relation must remain sequential. Capability parallel-safety is permission to honor user-requested concurrency, never evidence that concurrency was requested. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech you author exactly as a Communicative Activity. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, clarify or propose an explicit safe adjustment rather than silently serializing the request. For a Goal with resource_responsibility, keep the entire acquire-and-deliver outcome as one semantic responsibility and use the current capability catalog as the dynamic decomposition boundary. Prefer one exact capability when its declared resource_contract.plan_provides covers the complete required resource state. If no one capability covers the Goal, compose multiple advertised capabilities whose matching semantic scopes and ordered plan_requires/plan_provides form a valid chain covering the required outcome. Never invent provider-internal navigation, perception, grasp, search, retry, carrying, or handover stages that are not separately advertised capabilities. Provider-local decomposition stays inside the selected capability. The Goal is provider-neutral: choose the smallest reliable complete capability set from current declared semantics, never from capability names or a hardcoded provider rule. When source.status=unknown, the selected chain must include a capability that can resolve it internally or otherwise avoid requiring an unresolved source state; do not invent a source. Capability semantic_scope and resource_contract metadata are authoritative applicability evidence. When a selected Capability accepts resource, source, or recipient objects, copy each accepted object exactly from the canonical resource_responsibility, including nested quantity, source bindings, and recipient fields. Do not emit parameter_resolutions for nested fields of those complete structured arguments or invent top-level fields absent from the Capability schema. Never silently narrow a canonical goal to fit a capability or its enum defaults. If a goal is outside every available capability scope, clarify or report unavailable with zero steps. Resolve low-consequence "
        "parameters semantically when justified; otherwise return a specific natural clarification. Clarification is only for ambiguous user meaning or missing material information that the user can supply and whose answer can enable a matching catalog capability. When the Goal is already clear but no exact available capability covers the required outcome, return unavailable rather than asking for preferences, refinements, or details that cannot create the missing provider. Author exact natural response_text for every clarify, unavailable, or refused result; unresolved diagnostics alone are not speech. Capability domains are not interchangeable merely because several capabilities share a read/effect class. Eligibility requires the selected Capability's declared information_domain and semantic scope to cover the exact Goal; never substitute the nearest read-only Capability from another domain. Canonical Goal typed semantics are authoritative: non-resource Goals use object.bindings, while resource Goals use resource_responsibility directly with no persisted flat compatibility copy. Every material step argument that directly represents one canonical binding must preserve that binding exactly; do not replace it with older memory or re-resolve the original reference. When a Capability declares argument_realization, Deep Planner owns the semantic transformation from the original user turn plus canonical human-semantic binding into only those declared provider arguments. Trusted code may project only the duplicate semantic_realization provenance from that declared contract, immutable step ownership, and exact argument value; it never authors or changes the transformation. This transformation is HOW and never rewrites the canonical Goal or silently narrows its scope. For chromie.memory.retrieve_verified_tool_result, all resolved material Goal bindings belong inside the single material_args object. Nested material fields are not missing direct step arguments, so do not emit separate parameter_resolutions for them. If a resolution for that nested object is useful, its parameter must be material_args and its value must equal the complete step.args.material_args object. When independent goals have different terminal needs, use disposition=mixed, coverage=complete, and goal_outcomes so executable goals can proceed while only affected goals wait for clarification. Scope every blocking parameter resolution with source_goal_ids. Exact, safe-adjusted, or alternative executable plans "
        "must use coverage=complete and disposition=execute or mixed as appropriate. Every executable step must include source_goal_ids identifying exactly the goals it serves. Use plan_relation=exact for an exact plan. A safe_adjustment or material alternative must use the corresponding plan_relation, be described in response_text, set user_confirmation_required=true, and give top-level and affected per-Goal satisfaction status=substantial with score at least "
        f"{minimum_goal_satisfaction:.2f} and below 0.95, then require "
        "confirmation downstream. For every missing parameter, return parameter_resolutions with a semantic strategy, concrete value when resolved, confidence, and rationale. Use safe_default only for low-consequence reversible values inside schema bounds. Use ask_user for material or risky values. Also return goal_satisfaction as prospective plan adequacy: planned steps count as satisfying their goals if successful, and pending execution alone is never an unmet requirement. An exact complete plan therefore uses status=exact with score at least 0.95 and lists the goals it is designed to satisfy. If essential information remains missing, use coverage=partial or uncertain with disposition=clarify and zero steps. "
        "If unavailable or refused, use zero steps. Use exact supplied capability IDs and schema-valid args. "
        "Generic speech transport is never an executable Activity plan step. Treat canonical Goal output_mode as provider-neutral WHAT, not an execution declaration. output_mode=speech uses a respond outcome with the actual answer, joke, greeting, or other authored text now. output_mode=information may use a respond outcome when supplied trusted context or Evidence already grounds the answer; otherwise Planner must select exact information-acquisition Work whose declared information domain and semantic scope cover the Goal. output_mode=stateful_effect requires a real state-changing Capability or an explicit unavailable/refused/clarify outcome; response_text alone never completes a durable or future change. styled_speech, recitation, singing, humming, and nonverbal_vocalization require exact capability_id chromie.vocal.perform with the authoritative mode advertised by its input schema. response_text may explain new prospective context but never substitutes for or proves provider performance. When the exact Capability or requested mode is absent, use unavailable, refused, or a specific clarification outcome with zero step_ids and truthful limitation wording. A song verse read by ordinary TTS, chromie.speak, media playback, or body gestures is not completion evidence for a vocal-performance mode. output_mode=media_playback must use exactly one `chromie.media.<media_operation>` capability advertised by the qualified catalog; preserve persistent playback_id and the exact requested play, pause, resume, seek, stop, volume, or status operation. body_action and stateful_effect likewise require exact Capability semantics from the current catalog; Goal Association does not pre-author a provider, execution lane, or Work requirement. Executable outcomes may also carry response_text when it represents a still-needed prospective acknowledgement, limitation, correction, clarification, or other conversational delta. Use Interaction Context to omit an equivalent act already delivered or pending; repeat only when new meaning, failure/retry, correction, changed state, or explicit user intent justifies it. Media and Vocal may overlap only under declared Runtime coordination policy; overlap never mutates either Goal. Independent body Goals may still execute under an explicit mixed per-goal outcome. When direct ordinary speech overlaps Activity execution, preserve requested concurrency with a respond outcome plus parallel Activity steps only when providers declare safe overlap; author exact communicative wording and let the Host validate immutable cross-lane projection. Never silently downgrade one vocal mode to another. Greeting wording and length are ordinary model-authored conversational choices governed by supplied scene, relationship context, and owner-approved personality. "
        "An unavailable provider-backed vocal mode remains wholly unavailable: do "
        "not offer to try, approximate, imitate, or replace it with another vocal "
        "effect such as humming, melody, lyrics, noises, pleasant sounds, ordinary "
        "speech, or a weaker performance unless an exact separately supplied "
        "Capability supports that requested mode. Apply this to aggregate and "
        "per-Goal response_text alike; state the limitation and preserve independent "
        "executable Goals without promising a substitute effect. "
        "When retained or provisional Runtime Activities are supplied for Work reconciliation, decide whether they still advance the canonical Goals. Reuse is an explicit semantic choice: set reuse_activity_id to the supplied stable activity_id only while preserving its Capability ID, exact arguments, Goal ownership, and timing; omit reuse_activity_id when authoring replacement Work. Runtime validates live identity and state and never infers reuse from similarity. For retained chromie.work_dag.execute Work, reuse means NO_CHANGE to the current WorkDAG. A semantic change must be Planner-authored as the next revision of the same dag_id with revision incremented exactly once and parent_revision naming the retained revision; never ask DAGEngine to invent or recommend replacement topology. "
        "A plan step may contain only step_id, capability_id, args, timing, source_goal_ids, reuse_activity_id, step_purpose, expected_outcome, and reason_summary. When reality can resolve uncertainty more cheaply than guessing, use step_purpose=acquire_information with non-empty expected_outcome describing the concrete observation needed for progress and select only an exact registered Capability whose declared semantics acquire it. An unavailable composite Capability does not make its available component Capabilities unavailable. For a conditional effect whose predicate needs fresh safe-read Evidence, plan only that exact read first, name the predicate in expected_outcome, and wait for trusted re-entry before authoring the conditional effect; never declare the whole Goal unavailable or execute the effect unconditionally. Gaze/body/perception remains ordinary Capability Work and never bypasses normal safety or provider authority. expected_outcome is a prospective, falsifiable expectation rather than Evidence; on trusted result re-entry compare actual Evidence with it and revise the Plan/Situation when they disagree instead of rewriting Evidence. "
        "Use capability_id as the executable identity. Do not copy catalog-only fields such as input_schema, parameters, step_type, or effects into a plan step. "
        "Use exactly the supplied canonical goal IDs. Do not create goals for internal status checks, safety checks, capability lookups, or implementation preconditions; represent any justified internal operation only as a step owned by an existing user goal. "
        "When a supplied Goal requires future readiness at a known wall-clock instant, author time_conditions with the exact canonical goal_id and due_at_ms. Time conditions are cognition readiness, not provider work and not execution evidence. "
        "Keep the plan minimal: every executable step must be necessary for one concrete observable outcome in the canonical Goal that owns it. A general body_action output mode does not authorize unrelated body effects. Do not add a blink, gaze, gesture, posture, attention expression, personality flourish, social enhancement, neutral-position, reset, transition, cleanup, or other presentation step merely to seem natural or improve the interaction. An explicitly requested observable effect remains an ordinary Goal-owned step. Optional coordinated social expression may appear only in auxiliary_activities in this same primary Planner result, under the supplied closed candidate/anchor/target contract; it never enters steps or Goal outcomes. "
        "goal_outcomes is a JSON object keyed by every supplied canonical goal ID exactly once, never a list; every Deep Planner result must include it. Every outcome must explicitly author disposition, coverage, response_text, unresolved, step_ids, satisfaction, and rationale. Each value describes only that key's goal and must not repeat goal_id inside the value. Per-goal outcome invariants are mandatory: execute requires coverage=complete and at least one real plan step_id copied exactly from steps; respond requires coverage=complete, the actual answer text now (not a promise that it will be supplied later), and zero step_ids; clarify requires coverage=partial or uncertain, exact natural response_text, and zero step_ids; unavailable and refused require exact natural response_text and zero step_ids. Top-level and per-goal satisfaction are always non-null model judgments with score, status, satisfied_goal_ids, unmet_goal_ids, unmet_requirements, and rationale. A satisfaction score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. Do not assign a physical skill to a conversational answer merely because it is the nearest remaining capability. "
        "Complete plan coverage means every Goal has an explicit outcome; it does not mean every Goal can be satisfied. An unavailable, refused, or unresolved Goal must remain in unmet_goal_ids with a non-exact satisfaction status and score. The top-level satisfaction must preserve those same unmet Goals and requirements even when independent execute Goals can proceed in a coverage=complete mixed plan. "
        "An unavailable or refused outcome explicitly represents its Goal but does not satisfy it, and it is not by itself a safe adjustment or alternative. Do not promise, acknowledge as forthcoming, or otherwise claim that unavailable or refused work will occur in top-level or per-goal response_text. State the limitation truthfully while preserving exact independent executable work. "
        "Top-level disposition is the aggregate of per-goal dispositions: use mixed only when at least two different per-goal disposition values are present. Multiple goals that are all execute use top-level execute; multiple goals that are all respond use top-level respond. "
        "Every outcome step_id must name a real plan step, every plan step must be referenced by an execute outcome when goal_outcomes are present, and each step source_goal_ids must exactly match the execute outcomes that reference it. "
        "The Ollama decoder enforces the exact flat DeepPlannerModelOutput JSON Schema supplied out-of-band. The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. Populate only fields allowed by the model schema and return JSON only. "
        "The following final grounding block is authoritative and must override unrelated content in previous model output or advisory context.\n\n"
        f"{immutable_source_turn_prompt(request)}\n\n"
        f"FINAL CANONICAL GOALS JSON (copy goal IDs exactly and satisfy these meanings only):\n{bounded_json(grounding, 5000)}\n\n"
        f"FINAL TRUSTED EXECUTION OUTCOME JSON:\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
        f"FINAL RESULT-EVIDENCE WORDING CONTRACT:\n{result_evidence_contract or 'not_applicable'}\n\n"
        "FINAL PROVIDER-REQUIRED VOCAL GOALS WITH NO EXACT AVAILABLE "
        "VOCAL PROVIDER JSON (each must have a zero-step unavailable/refused "
        "outcome and truthful limitation wording; never promise, attempt, "
        "approximate, or substitute any vocal effect):\n"
        f"{bounded_json(unavailable_provider_vocal_goal_ids, 2000)}\n\n"
        f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{bounded_json([item['capability_id'] for item in capabilities], 4000)}"
    )


def deep_layered_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
    expected_goal_ids: list[str],
    minimum_goal_satisfaction: float = 0.75,
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
        + auxiliary_social_planning_prompt_section(context)
        + "Executable capability catalog JSON:\n"
        + bounded_json(prompt_capabilities, 12000)
        + "\n\n"
    )
    rendered = deep_plan_prompt(
        request,
        capabilities,
        response_schema=response_schema,
        expected_goal_ids=expected_goal_ids,
        minimum_goal_satisfaction=minimum_goal_satisfaction,
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
        when_to_use = str(hints.get("when_to_use") or "").strip()
        if when_to_use and when_to_use != str(capability.get("description") or "").strip():
            projected["when_to_use"] = when_to_use[:600]
        when_not_to_use = str(hints.get("when_not_to_use") or "").strip()
        if when_not_to_use:
            projected["when_not_to_use"] = when_not_to_use[:600]
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
    return (
        "You are Chromie's Deep Planner. Plan only the final authoritative user turn and canonical goals supplied at the end of the prompt. "
        "This is the only Deep Planner model call for the transaction; any invalid result fails closed. You never call or return to the Fast Planner. "
        "Capabilities are plan leaves, not planner ownership boundaries. This primary "
        "result must contain the complete per-Goal coverage, exact response truth, "
        "step ownership, satisfaction, and unresolved-work decision; no later model "
        "will audit or repair its semantics. Do not execute, authorize, or claim "
        "completion. Return JSON only."
    )
