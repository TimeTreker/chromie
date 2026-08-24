from __future__ import annotations

import json
from typing import Any

from .agent_skills import agent_skill_prompt_section
from .clients.ollama_client import LayeredPrompt
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
    owner_approved_identity_context,
    owner_approved_personality_context,
)
from .goal_progress_communication import goal_progress_communication_prompt
from .prompt_projection import bounded_json
from .planner_context import (
    canonical_goal_grounding,
    evidence_bound_dialogue,
    expected_goal_ids,
    goal_association_prompt_projection,
    goal_cancellation_evidence_reentry_goal_ids,
    planner_goal_execution_requirements,
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
    "whose argument schema can represent the supplied value. Catalog "
    "defaults are only for parameters the user did not supply. If the "
    "units, argument mapping, or validity are uncertain, clarify or "
    "escalate according to the planner tier instead of claiming exact "
    "coverage. A material adjustment must use a non-exact plan_relation, "
    "require confirmation, and explain the change. For each numeric "
    "literal in an executable authoritative Goal's text or typed bindings, "
    "include a user_supplied "
    "parameter_resolution tied to the owned step and goal. The parameter "
    "field must be the exact bare key in that step's args object, never a "
    "step- or capability-qualified name. Its value must equal the step "
    "argument and its source_goal_ids must identify the authoritative Goal "
    "containing that same number. A typed binding is the model-owned canonical "
    "provenance for a quantity stated in words by the user. Use those stable "
    "Goal IDs as provenance. Never borrow a numeric literal or typed binding from "
    "a sibling Goal to fill another step. When an optional catalog argument was not "
    "supplied by the owning Goal, omit that argument and its resolution so the "
    "provider applies its declared default, or copy the exact catalog default with "
    "strategy=schema_default and no source_goal_ids. Never label a catalog default "
    "as user_supplied. "
    "do not copy, paraphrase, or annotate Goal text into another field. "
)

# Planner prompt/projection mechanics only. This module does not invoke a model,
# validate or commit a Plan, mutate Goal/Work state, or authorize effects.

def first_response_target_goal_grounding(
    context: dict[str, Any],
    responsibilities: list[CognitiveResponsibilityProposal],
) -> list[dict[str, Any]]:
    """Project retained Goal meaning needed by the pre-GA fast speech pass."""

    target_goal_ids = {
        str(goal_id).strip()
        for responsibility in responsibilities
        for goal_id in responsibility.target_goal_ids
        if str(goal_id).strip()
    }
    if not target_goal_ids:
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [
        *(context.get("active_goal_snapshots") or []),
        *(context.get("recent_goal_snapshots") or []),
    ]:
        if not isinstance(item, dict):
            continue
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        goal_id = " ".join(
            str(item.get("goal_id") or goal.get("goal_id") or "").split()
        )
        if not goal_id or goal_id not in target_goal_ids or goal_id in seen:
            continue
        seen.add(goal_id)
        result.append(
            {
                "goal_id": goal_id,
                "description": goal.get("description") or item.get("last_user_update") or "",
                "source_text": goal.get("source_text") or item.get("last_user_update") or "",
                "object": goal.get("object") or {},
                "constraints": goal.get("constraints") or {},
                "success_criteria": goal.get("success_criteria") or [],
            }
        )
    return result


def fast_first_response_truth_system_prompt() -> str:
    return (
        "Classify one immutable Fast Planner sentence; do not rewrite it. Return "
        "only the four audit fields required by the JSON schema. Set each violation "
        "flag explicitly, then accept only when all three are false. Before action or Evidence, a "
        "present acknowledgement or future intention is supported, while an "
        "already-started/completed action, result, invented method, or invented fact is "
        "not. An onset or progressive predicate saying execution starts, has "
        "started, or is underway is an already-started claim even when an immediacy "
        "marker appears before it. Resolve grammatical roles: in a human command addressed to Chromie, "
        "Chromie is the commanded actor. Chromie's first-person subject is the "
        "correct actor; the user's second-person command does not make that reply "
        "a perspective contradiction. A reply telling the human to do Chromie's "
        "action does. Never choose a Capability or change Goal meaning."
    )


def fast_first_response_truth_prompt(
    request: CognitiveWorkRequest,
    *,
    activity: Any,
    responsibilities: list[CognitiveResponsibilityProposal],
    trusted_evidence: list[Any],
) -> LayeredPrompt:
    contract = (
        "Judge the exact immutable activity.text, not its label. At pre_evidence, "
        "a present acknowledgement or prospective intention is valid; future-oriented "
        "grammar may announce intended checking or action without claiming execution. "
        "Onset, progressive, perfect, completion, and result predicates claim a later "
        "truth stage and must be rejected when that stage is not established. "
        "Reject only when the sentence contains an unverified result, changed-world "
        "claim, already-started/completed claim, or when it invents a physical "
        "instrument, source, sensor, observation, action, personal fact, or world "
        "fact absent from Responsibility/context; never say Chromie will "
        "look at a phone, camera, or look outside or use direct perception unless "
        "supplied. Also reject a real speaker, experiencer, actor, addressee, "
        "polarity, referent, or semantic relationship reversal. The sentence "
        "must preserve each authoritative Responsibility's concrete outcome and "
        "relationship. In particular, relationship=continue must sound like "
        "continuing or resuming the resolved work rather than starting it as a "
        "new action, and it must not fall back to a generic thing, matter, or "
        "action after the target meaning is supplied. "
        "For a command addressed to Chromie, first-person self-reference may be the "
        "correct actor; reject only when the wording actually assigns Chromie's owed "
        "action to the human or otherwise reverses the grounded semantic roles. "
        "A human's feeling must remain the human's, and repeating Chromie's last utterance "
        "must use the supplied assistant utterance. A progress question that asks "
        "the human to supply or reconfirm information without an InformationGap "
        "also reverses responsibility. For context_grounded text, reject invented "
        "facts; for post_evidence text, require cited Evidence. Set each of the "
        "three audit flags explicitly. A missing continue/resume relationship in "
        "wording for relationship=continue is a semantic-perspective contradiction. "
        "Accept when none applies; otherwise reject. Never supply replacement wording."
    )
    rendered = (
        contract
        + "\n\nImmutable Communicative Activity JSON:\n"
        + json.dumps(
            activity.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n\nAuthoritative Responsibility evidence JSON:\n"
        + bounded_json(
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in responsibilities
            ],
            3000,
        )
        + "\n\nAdmitted trusted Evidence JSON:\n"
        + bounded_json(trusted_evidence, 2200)
        + "\n\nBounded Interaction Context JSON:\n"
        + bounded_json(
            (request.context or {}).get("interaction_context") or {}, 900
        )
        + "\n\nCurrent user turn (context only, never external-result Evidence):\n"
        + str(request.original_user_text or "")[:700]
    )
    return LayeredPrompt.promote(
        rendered,
        operating_contract=(contract,),
    )


def fast_first_response_system_prompt() -> str:
    return (
        "You are Chromie's low-latency Fast Planner deciding whether there is one "
        "immediately useful Communicative Activity. You own whether to communicate, "
        "its communicative function, and exact natural wording. Silence is valid when "
        "no still-needed user-facing semantic delta exists. You own its communicative "
        "function and exact natural wording. Do not select a Capability, resolve "
        "parameters, ask a clarification, claim execution, or invent external "
        "Evidence in this latency phase. This is a method-blind phase: never name "
        "where or how Chromie will check or act, including an instrument, device, "
        "screen, sensor, source, or implementation, unless that exact method is "
        "already explicit in Responsibility evidence. Name only the user-level "
        "outcome Chromie will check or do. Return only schema-constrained JSON."
    )


def fast_first_response_prompt(
    request: CognitiveWorkRequest,
    *,
    responsibilities: list[CognitiveResponsibilityProposal],
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    language = str(request.language or "auto")[:32]
    role_contract = (
        "Choose exactly one of three semantic decisions: (1) activity=null when no "
        "new user-facing delta is needed now; (2) role=complete_response only when "
        "the requested conversational content is already supportable from supplied "
        "trusted context; or (3) role=progress for a useful prospective acknowledgement "
        "when meaningful work/evidence still appears necessary. Never speak merely "
        "because a processing phase exists."
    )
    identity = owner_approved_identity_context(context).get("identity") or {}
    personality = owner_approved_personality_context(context)
    identity_projection = {
        "identity": {
            key: identity[key]
            for key in ("name",)
            if identity.get(key) not in (None, "", [], {})
        },
        "voice": {
            key: str(personality[key])[:360]
            for key in ("spoken_style", "tool_use_style")
            if personality.get(key) not in (None, "", [], {})
        },
    }
    identity_section = "Bounded owner-approved speaking style JSON:\n" + json.dumps(
        identity_projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    progress_contract = (
        "Fast Planner first-response contract: decide whether one useful spoken Main "
        "Activity is still needed and, if so, author its exact wording. Returning no "
        "Activity is correct when equivalent communication is already delivered/pending "
        "or speaking now adds no useful semantic delta. At truth_stage=pre_evidence, no check, "
        "execution, or fresh Evidence has happened. Say only a present "
        "acknowledgement or prospective intention; never claim or predict a result, "
        "completion, method, instrument, source, sensor, or screen. A progress "
        "Activity is not a clarification: never ask a question, request a choice, "
        "or ask the person to reconfirm supplied meaning. Preserve who said, felt, "
        "perceived, or did each thing: the human's first person never becomes "
        "Chromie's first person. An imperative addressed to Chromie makes Chromie "
        "the actor. Reply to a command with Chromie's first-person intention; never "
        "repeat the commanded action with the human as its subject. Do not turn a command into an "
        "observation about the human's hobbies, practice, preferences, or recent "
        "activity. For a human feeling, acknowledge the human as 你/you, never as "
        "我/I. For a request to restate Chromie's last utterance, use only the "
        "supplied assistant utterance. When a Responsibility continues, resumes, "
        "modifies, or otherwise references a supplied Goal, use the resolved "
        "target Goal meaning below. The sentence must name that concrete resolved "
        "user-level action or work in natural language and preserve the supplied "
        "relationship. For relationship=continue, the wording must semantically mark "
        "continuation or resumption rather than sounding like a new start, while "
        "preserving the resolved user-level action instead of replacing it with a "
        "generic stand-in. It may omit repeated parameter detail when brevity makes "
        "that natural. Before an embodied or state-changing action, use prospective "
        "grammar so intention is not mistaken for execution already underway; onset "
        "or progressive claims require Runtime commitment. Do not invent current activity, household "
        "work, personal state, or external facts."
    )
    responsibility_field_contract = (
        "The decoder schema omits Responsibility refs when exactly one Responsibility "
        "exists; trusted runtime restores that mechanical provenance. Otherwise use "
        "source_responsibility_refs with only supplied refs. Never invent a nested "
        "Responsibility object."
    )
    rendered = (
        identity_section
        + "\n\n"
        + progress_contract
        + "\n\nCurrent user turn:\n"
        + str(request.original_user_text or "")[:700]
        + "\nRequired response language: "
        + language
        + "\nUse that language naturally in activity.text; zh/zh-CN requires "
        "natural Chinese.\n\n"
        + role_contract
        + " Use one brief conversational sentence. Progress states the prospective "
        "check, action, or work instead of repeating the question; omit a second "
        "clause explaining what the check will reveal. "
        + responsibility_field_contract
        + "\n\n"
        "Authoritative Responsibility evidence:\n"
        + bounded_json(
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in responsibilities
            ],
            2600,
        )
        + "\n\nResolved target Goal semantics for referenced Responsibilities:\n"
        + bounded_json(
            first_response_target_goal_grounding(context, responsibilities), 1800
        )
        + "\n\nAlready delivered or pending interaction summary:\n"
        + bounded_json(context.get("interaction_context") or {}, 700)
        + "\n\nFINAL TRUTH CHECK: if role=progress, the exact sentence must remain "
        "true if no checking/execution has started and no result exists. If "
        "role=complete_response, its content must already be supported by supplied "
        "trusted context. If neither is useful, return activity=null."
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_section,),
        operating_contract=(progress_contract,),
    )


def fast_plan_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
    previous_raw: Any = None,
    validation_errors: str = "",
) -> str:
    context = request.context if isinstance(request.context, dict) else {}
    skill_section = agent_skill_prompt_section(
        context,
        agent_role="fast_planner",
    )
    identity_json = bounded_identity_json(context)
    personality_json = bounded_personality_json(context)
    association = goal_association_prompt_projection(context)
    grounding = canonical_goal_grounding(context)
    response_only, requires_execution = planner_goal_execution_requirements(grounding)
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
        "or workflow vocabulary, and never turn a completed-but-unqualified claim into "
        "verified completion. "
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
    semantic_scope_contract = "For a Goal with resource_responsibility, keep the entire acquire-and-deliver outcome as one semantic responsibility while treating the current capability catalog as the dynamic decomposition boundary. Fast Planner may terminally execute the Goal only when one exact registered Capability is a complete one-step cover. A provider's resource_contract.plan_requires/plan_provides declares public composition state; provider-internal stages remain private unless exposed as capabilities. If the catalog has only partial resource capabilities that could form a multi-step chain, escalate to Deep Planner rather than inventing hidden provider stages or claiming a partial primitive is complete. The Goal is provider-neutral: choose from the catalog by declared semantic scope and resource contract, never from capability-name conventions or a hardcoded provider rule. When resource_responsibility.source.status=unknown and the selected complete capability cannot resolve the source itself, return a specific context request and zero executable steps. Capability semantic_scope and resource_contract metadata are authoritative applicability evidence. Capability domains are not interchangeable merely because several capabilities share a read/effect class. Eligibility requires the selected Capability's declared information_domain and semantic scope to cover the exact Goal; never substitute the nearest read-only Capability from another domain. When the selected Capability accepts resource, source, or recipient objects, copy each accepted object exactly from the canonical resource_responsibility, including nested quantity, source bindings, and recipient fields. Those complete structured arguments are already grounded by the Goal contract; do not emit parameter_resolutions for their nested fields or invent a top-level quantity/distance argument that the Capability does not accept. Canonical Goal typed semantics are authoritative: non-resource Goals use object.bindings, while resource Goals use resource_responsibility directly with no persisted flat compatibility copy. Every material tool argument that directly represents one canonical binding must preserve that binding exactly; never reinterpret an original pronoun or replace a binding with older memory. When a Capability declares argument_realization, use the original user turn plus the canonical human-semantic binding to realize only the declared provider arguments, and record those transformed arguments as semantic_realization parameter provenance. This is Planner-owned HOW and must never rewrite the Goal. Preserve every canonical-goal qualifier, including temporal scope, comparison period, answer shape, ordering, and concurrency; never use a Capability default to silently narrow an explicit human scope. Never silently rewrite simultaneous independent actions as before/after actions. An explicit ordered relation must remain sequential. Capability parallel-safety is permission to honor user-requested concurrency, never evidence that concurrency was requested. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; in particular, a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech whose exact wording you own. A user-requested spoken response or performance may still be simultaneous with an Activity-lane step. Preserve that relation without inventing a chromie.speak plan step: keep the spoken Goal as a respond outcome, set each participating Activity step to timing=parallel only when its provider declares safe parallel execution, and leave cross-lane scheduling to trusted Runtime. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, escalate or propose an explicit safe adjustment rather than silently serializing the request. Never silently narrow a goal to fit a capability or its enum defaults. If the goal falls outside a capability's supported scope, escalate for clarification, another capability, or an honest unavailable result with zero steps. "
    current_turn_communication_contract = (
        "The FINAL AUTHORITATIVE USER TURN owns the current communicative act. "
        "Retained Goals, delivered evidence-bound dialogue, and verified memory "
        "may support the response, but they must not replace what the person just "
        "meant. For a reaction, feeling, acknowledgement, evaluation, or practical "
        "decision, answer that latest act directly and naturally. Do not replay the "
        "previous task answer unless the latest turn actually asks for repetition, "
        "verification, explanation, comparison, or another answer from it. For a "
        "decision-shaped follow-up, make the first sentence directly state the "
        "requested decision, recommendation, or yes/no answer; never begin by "
        "restating prior evidence. Include at most one short supporting clause "
        "after that answer, and omit previously delivered sentences, measurements, "
        "or conditions that do not change the decision. "
    )
    concise_output_contract = (
        "Keep goal summaries, step reasons, satisfaction rationales, and "
        "outcome rationales concise: one short sentence each. Do not "
        "repeat the user goal, catalog description, arguments, or the same "
        "justification across multiple fields. "
    )
    provisional_fast_activities = context.get(
        "existing_work_activities"
    )
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
        if isinstance(provisional_fast_activities, list)
        and provisional_fast_activities
        else "This is prospective planning: no retained or provisional Runtime Work is supplied for reconciliation. "
    )
    if len(expected_goal_ids(context)) > 1:
        return (
            f"Goal association advisory JSON:\n{bounded_json(association, 3000)}\n\n"
            f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
            f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
            f"{skill_section}"
            f"Executable common capability catalog JSON:\n{bounded_json(capabilities, 9000)}\n\n"
            f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{bounded_json(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
            f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{bounded_json(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
            f"Host-bound terminal Evidence JSON:\n{bounded_json(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
            f"Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning):\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
            f"Host-bound Goal cancellation Evidence JSON:\n{bounded_json(context.get('trusted_goal_cancellation_evidence') or [], 3200)}\n\n"
            f"Active and recoverable task bindings JSON:\n{bounded_json(context.get('active_task_snapshots') or [], 5000)}\n\n"
            f"Existing retained or provisional Runtime Activities JSON:\n{bounded_json(provisional_fast_activities or [], 3500)}\n\n"
            f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{bounded_json(situation_prompt_projection(context), 3600)}\n\n"
            f"{goal_progress_communication_prompt('Planner fast pass')}\n\n"
            f"Goal-scoped Interaction Context JSON:\n{bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
            "Use Interaction Context to plan only the still-needed conversational and effectful delta. Preserve each typed event's owner and state: generated or scheduled speech is not proof the user heard it, committed work is not completion, and only execution_closure terminal events reference trusted Activity completion evidence. Do not treat missing or undelivered speech as fulfilled communication. Decide whether any new planner response_text materially helps the current human interaction, and prefer no extra speech when it would be filler or repetition. Do not repeat an already delivered or pending semantic act, or re-plan an already completed effect, unless the current meaning requires an explicit repeat, retry after failure, correction, changed state, new evidence, or clarification. It cannot override the authoritative current Goals or Canonical Plan contract. "
            f"Previous Fast Planner output when doing a mechanical DTO regeneration:\n{bounded_json(previous_raw, 3500) if previous_raw is not None else 'null'}\n\n"
            "When validation errors are present, regenerate one fresh complete model-authored plan object from the authoritative goals and catalog. Author the semantic plan directly. Do not classify text with lexical rules and do not expect the host to choose a capability, arguments, ordering, ownership, response, disposition, coverage, or satisfaction for you. "
            "Every top-level field and every nested field in FastPlannerMultiGoalPlanOutput is required. Use exact catalog capability IDs and schema-valid args. The verified tool-memory index contains no answer facts. When an exact fresh index entry matches every authoritative Goal binding, execute chromie.memory.retrieve_verified_tool_result with that evidence_id, original tool_id, and the same material arguments; never use a respond outcome directly from the index. If no exact fresh entry exists, execute the supplied fresh read capability. For a scheduled, running, or recoverable safe-read goal, reuse the bound capability and exact arguments and execute or retry it; never answer from another task's result. For an executable Goal, response_text is optional prospective conversational intent, not execution evidence. Use Interaction Context to leave it empty when an equivalent acknowledgement or commitment is already delivered or pending and nothing new needs saying. When there is a genuinely new acknowledgement, limitation, correction, confirmation need, or other conversational delta, author it naturally without predicting an external result or claiming execution/completion. A response_text never satisfies the executable Goal; post-execution factual claims require matching evidence. "
            f"{argument_grounding_contract}"
            f"{semantic_scope_contract}"
            f"{current_turn_communication_contract}"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            f"{result_evidence_contract}{control_evidence_contract}{goal_execution_contract}"
            f"{concise_output_contract}"
            f"{provisional_work_contract}"
            "Author stable non-empty step_id values, exact source_goal_ids, and matching outcome step_ids yourself. "
            "A planned step or response counts as satisfying its goal if it would succeed. For each keyed goal outcome, judge only that one goal; never put sibling goals or pending execution in unmet_goal_ids or unmet_requirements. Complete terminal outcomes use exact satisfaction with both unmet lists empty. "
            "Fast terminal scope permits at most one executable step per goal. A count argument performs repetition inside one skill call; never duplicate a step to implement repeated blinks, nods, or similar motions. Respond goals have no executable step. "
            "For a terminal plan, every per-goal outcome is execute or respond, coverage is complete, and the top-level disposition exactly aggregates the outcome dispositions. A respond outcome contains the actual answer now and references no steps. An execute outcome references every and only the model-authored steps owned by that goal. "
            "For semantic escalation, author disposition=escalate, coverage=partial or uncertain, steps=[], a non-empty top-level escalation_reason, and one escalate outcome for every canonical goal. Each escalate outcome must explain its own unresolved need, reference no steps, carry no response_text, and include a non-exact prospective satisfaction judgment. Do not mix escalation outcomes with executable or response outcomes. "
            "goal_satisfaction and every per-goal satisfaction are model judgments about prospective plan adequacy. A score from 0.95 through 1.0 requires status=exact. Escalation cannot claim exact satisfaction. "
            "Generic response transport is not a task-plan step, so chromie.speak is never a plan step. Do not replace a conversational answer with a gesture or attention action. "
            "Use plan_relation=exact unless the plan materially changes the request; safe_adjustment or alternative requires user_confirmation_required=true and explanatory response_text. "
            "The host adds only plan_id, planner_tier, schema_version, and the authoritative top-level goal_ids after validating your output. It does not compile semantic decisions or generate step ownership. Return JSON only.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}\n\n"
            f"FINAL CANONICAL GOALS JSON:\n{bounded_json(grounding, 4500)}\n\n"
            f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{bounded_json([item['capability_id'] for item in capabilities], 2500)}\n\n"
            "FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON:\n"
            f"{validation_errors or '[]'}\n"
            "When this list is non-empty, correct every listed defect in the fresh object. If an error reports an expected aggregate disposition, author exactly that disposition unless you also revise the underlying per-goal outcomes consistently."
        )
    return (
        f"Goal association advisory JSON:\n{bounded_json(association, 3000)}\n\n"
        f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
        f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
        f"{skill_section}"
        f"Executable common capability catalog JSON:\n{bounded_json(capabilities, 9000)}\n\n"
        f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{bounded_json(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
        f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{bounded_json(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
        f"Host-bound terminal Evidence JSON:\n{bounded_json(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
        f"Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning):\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
        f"Host-bound Goal cancellation Evidence JSON:\n{bounded_json(context.get('trusted_goal_cancellation_evidence') or [], 3200)}\n\n"
        f"Active and recoverable task bindings JSON:\n{bounded_json(context.get('active_task_snapshots') or [], 5000)}\n\n"
        f"Existing retained or provisional Runtime Activities JSON:\n{bounded_json(provisional_fast_activities or [], 3500)}\n\n"
        f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{bounded_json(situation_prompt_projection(context), 3600)}\n\n"
        f"{goal_progress_communication_prompt('Planner fast pass')}\n\n"
            f"Goal-scoped Interaction Context JSON:\n{bounded_json(context.get('interaction_context') or {}, 7000)}\n\n"
        "Use Interaction Context to plan only the still-needed conversational and effectful delta. Preserve each typed event's owner and state: generated or scheduled speech is not proof the user heard it, committed work is not completion, and only execution_closure terminal events reference trusted Activity completion evidence. Do not treat missing or undelivered speech as fulfilled communication. Decide whether any new planner response_text materially helps the current human interaction, and prefer no extra speech when it would be filler or repetition. Do not repeat an already delivered or pending semantic act, or re-plan an already completed effect, unless the current meaning requires an explicit repeat, retry after failure, correction, changed state, new evidence, or clarification. It cannot override the authoritative current Goals or Canonical Plan contract. "
        f"Previous Fast Planner output when doing a mechanical DTO regeneration:\n{bounded_json(previous_raw, 3500) if previous_raw is not None else 'null'}\n\n"
        "When validation errors are present and the previous output is null, regenerate one fresh complete object from the authoritative turn, goals, catalog, and every listed defect. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
        "Decide whether the executable common catalog completely covers every independent responsibility in the current user turn. A verified tool-memory index entry is only metadata that an exact prior result may be retrievable; it is never answer evidence. After Goal Association has fixed all material bindings, select chromie.memory.retrieve_verified_tool_result only when one index entry exactly matches the required tool_id and material arguments and is fresh enough for the user request. Otherwise select the fresh read capability. A status follow-up for a scheduled, running, or recoverable safe read must resume or retry the bound skill with its exact arguments when no matching completed memory entry exists. Never invent any external, private, or runtime result from model memory or index metadata. "
        "There are exactly two legal output shapes for one or many goals. A terminal plan uses coverage=complete, a goal_outcomes entry keyed exactly once by every canonical Goal ID, and non-null prospective satisfaction. A semantic escalation uses disposition=escalate, coverage=partial or uncertain, steps=[], one escalate outcome for every canonical Goal ID, non-exact prospective satisfaction, and a specific non-empty escalation_reason. "
        "Finding one matching capability is not complete coverage. If any responsibility, parameter, ordering, concurrency relation, safety judgment, or capability is unresolved, use the complete model-authored semantic-escalation shape; never return an empty outcome map or null satisfaction. "
        "Fast Planner may emit disposition=mixed only for a completely covered simple combination of common unlocked execute goals and direct conversational respond goals. A mixed plan requires at least one execute outcome, at least one respond outcome, complete per-goal satisfaction, and exact step ownership. "
        "For complete direct execution, use exact supplied capability IDs and schema-valid args. "
        f"{argument_grounding_contract}"
        f"{semantic_scope_contract}"
        f"{current_turn_communication_contract}"
        f"{IDENTITY_SEMANTIC_CONTRACT}"
        f"{PERSONALITY_SEMANTIC_CONTRACT}"
        f"{result_evidence_contract}{control_evidence_contract}{goal_execution_contract}"
        f"{concise_output_contract}"
        f"{provisional_work_contract}"
        "Generic speech transport is not a plan step. A canonical Goal with responsibility_kind=vocal_output, output_mode=speech, and provider_required=false is a direct conversational responsibility: use disposition=respond with the actual response_text now. Executable outcomes may also carry response_text when it is a still-needed prospective conversational delta; use Interaction Context to omit equivalent delivered or pending speech, and never treat that text as execution evidence. A vocal_output Goal with provider_required=true is a mode-specific vocal performance and cannot be completed by response_text, chromie.speak, ordinary TTS, media playback, or a body gesture. Execute that Goal only when the supplied catalog contains exact capability_id chromie.vocal.perform and its mode enum contains the authoritative Goal output_mode; copy that exact mode and authored content into one owned step. Otherwise escalate for an exact unavailable, refused, or clarification outcome; never invent a vocal capability ID or silently choose another mode. A canonical executable_action/activity/media_playback Goal uses exactly one `chromie.media.<media_operation>` capability copied from the qualified catalog. Playback of existing music, recordings, streams, or sound effects is never a Vocal Goal and never evidence for singing. Preserve persistent playback_id controls and do not replace play, pause, resume, seek, stop, volume, or status with another operation. Greeting wording and length are ordinary model-authored conversational choices governed by the supplied scene, relationship context, and owner-approved personality. "
        "Every executable step must use capability_id plus source_goal_ids copied from the canonical goals. Do not use catalog-only parameters, action, input_schema, route, or step_type fields. "
        "goal_satisfaction measures prospective plan adequacy: planned steps count as satisfying their goals if successful, so pending execution alone is never an unmet requirement. A score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. If steps are present, top-level disposition cannot be respond. "
        "For every terminal or escalation result, goal_outcomes must be keyed exactly once by every supplied canonical Goal ID. Each execute outcome needs its real step_ids; each respond outcome needs non-empty response_text and step_ids=[]; each escalation outcome needs its unresolved reason and non-exact satisfaction. "
        "Valid examples: execute uses owned steps and execute outcomes; mixed uses owned steps plus respond outcomes; escalation uses steps=[], one escalate outcome per Goal, and non-null non-exact goal_satisfaction. "
        "Use plan_relation=exact for an exact plan. A safe_adjustment or alternative must set user_confirmation_required=true so the host holds execution for approval. "
        "The Ollama decoder enforces the exact flat FastPlannerModelOutput schema out-of-band. "
        "The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. "
        "Return JSON only. The final grounding below is authoritative and overrides previous output or advisory text.\n\n"
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}\n\n"
        f"FINAL CANONICAL GOALS JSON:\n{bounded_json(grounding, 4500)}\n\n"
        f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{bounded_json([item['capability_id'] for item in capabilities], 2500)}\n\n"
        "FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON:\n"
        f"{validation_errors or '[]'}\n"
        "When this list is non-empty, correct every listed defect in the fresh object. If an error reports an expected aggregate disposition, author exactly that disposition unless you also revise the underlying per-goal outcomes consistently.\n"
        f"FINAL RESULT-EVIDENCE WORDING CONTRACT:\n{result_evidence_contract or 'not_applicable'}\n"
        f"FINAL CONTROL-EVIDENCE WORDING CONTRACT:\n{control_evidence_contract or 'not_applicable'}"
    )


def fast_advance_layered_prompt(
    request: CognitiveWorkRequest,
    *,
    responsibilities: list[CognitiveResponsibilityProposal],
    capabilities: list[dict[str, Any]],
    committed_communicative_activities: list[Any] | None = None,
    first_response_decided: bool = False,
    validation_errors: str = "",
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
    responsibilities_json = bounded_json(
        [item.model_dump(mode="json", exclude_none=True) for item in responsibilities],
        2200,
    )
    active_goals = bounded_json(context.get("active_goal_snapshots") or [], 600)
    interaction_context = bounded_json(
        context.get("interaction_context") or {},
        1200,
    )
    capability_json = json.dumps(
        fast_advance_capability_prompt_projection(capabilities),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    user_text = str(request.original_user_text or "")[:700]
    committed_communicative_json = bounded_json(
        [
            item.model_dump(mode="json", exclude_none=True)
            for item in (committed_communicative_activities or [])
        ],
        900,
    )
    if committed_communicative_activities:
        communication_instruction = (
            "A Fast Planner Communicative Activity has already been committed and "
            "is shown below. Do not repeat, replace, translate, or re-author it in "
            "activities. Continue the same HOW decision with only the still-needed "
            "Capability or clarification Activities."
        )
    elif first_response_decided:
        communication_instruction = (
            "The bounded first-response phase completed with no committed speech. "
            "Do not bypass that decision by authoring a replacement progress "
            "Activity. Continue with only the still-needed Capability or genuine "
            "source-grounded clarification Activities."
        )
    else:
        communication_instruction = (
            "No Fast Planner Communicative Activity decision exists yet."
        )
    rendered = (
        advance_contract
        + "\n\nCurrent user turn:\n"
        + user_text
        + "\nLanguage hint: "
        + str(request.language or "auto")[:32]
        + "\n\nAuthoritative Responsibility evidence from Goal Interpretation:\n"
        + responsibilities_json
        + "\n\nGI unresolved-meaning evidence (exact strings or empty):\n"
        + bounded_json(request.interpretation_unresolved, 1200)
        + "\n\nActive Goal continuity summary only:\n"
        + active_goals
        + "\n\nAlready-spoken/pending interaction summary only:\n"
        + interaction_context
        + "\n\nAlready committed Fast Planner Communicative Activity JSON:\n"
        + committed_communicative_json
        + "\n"
        + communication_instruction
        + "\n\nExecutable common Capability catalog JSON:\n"
        + capability_json
        + "\n\nThe catalog projection above is complete for this Fast decision; every "
        "allowed Capability has a visible capability_id, arguments, effects, and "
        "semantic scope. Compare the Responsibility outcome against all projected "
        "descriptions, when_to_use guidance, effects, semantic_type, and semantic_scope "
        "before claiming that no Capability matches. The absence of fresh result "
        "Evidence is the reason to execute a matching read Capability, never a reason "
        "to clarify. Match required arguments from GI bindings by meaning, not only by "
        "identical field name; a clearly supplied named entity, relative date, or local "
        "day part is resolved input. Optional arguments with schema defaults are not "
        "missing inputs. When one matching Capability has every required input, use "
        "disposition=execute, coverage=complete, continuations=[], unresolved=[], and "
        "emit its schema-valid Capability Activity. For an external information read, "
        "include one short progress Activity with progress_kind=check_information "
        "for fresh external information work only when no committed Fast Planner "
        "Communicative Activity is supplied above. Never fuse progress wording into "
        "a Capability Activity or use a Capability ID as a progress activity_id.\n\n"
        "Cover every Responsibility ref exactly. Activities are one ordered list. "
        "Speaking is an Activity and uses the same timing field as Capability work. "
        "Use parallel only when activities can genuinely overlap without a declared "
        "resource or safety conflict; list dependent work sequentially. A progress "
        "Activity has progress_kind, exact text, truth_stage=pre_evidence, and no "
        "evidence_refs. Its text may acknowledge or prospectively describe the "
        "check but must not state a result that has not been observed. Every "
        "Communicative Activity owns its exact natural wording; do not emit "
        "response_text inside an Activity. Use truth_stage=context_grounded for "
        "ordinary answers and clarification, and truth_stage=post_evidence with "
        "exact evidence_refs only when supplied trusted Evidence supports it. A "
        "complete_response Activity may satisfy only ordinary conversation that needs "
        "no fresh Evidence. You own execution-input completeness and planning "
        "InformationGaps. Before asking, consider authoritative context, applicable "
        "trusted observation/query, owner preference, Capability schema default, and "
        "a safe consequence-bounded default. Ask only when the user can resolve a "
        "material blocker and no safer authorized source/default is enough. A "
        "clarification must create its typed InformationGap: source_kind="
        "unresolved_meaning cites one exact interpretation_unresolved string; "
        "source_kind=execution_input cites the exact selected Capability ID in "
        "source_reference and names only its genuinely absent required input keys in "
        "required_for. Record every examined source in resolution_sources_considered. "
        "Use disposition=clarify when only clarification remains; use mixed only when "
        "independent safe Capability work also proceeds. Never ask the user for an "
        "external result Chromie was asked to obtain. Do not route a missing user "
        "parameter to Deep Planner. GI bindings are resolved human-semantic input evidence. "
        "A relative or compound temporal scope may remain in the person's original wording; "
        "when a selected Capability declares argument_realization, Fast Planner owns the "
        "mapping from that semantic scope to the Capability arguments. Never treat an "
        "already supplied temporal binding as ambiguous merely because it is not yet in "
        "provider vocabulary; when GI unresolved-meaning evidence is empty, "
        "do not invent a semantic clarification. When all required "
        "bindings are present and one exact available Capability covers the work, emit "
        "its exact capability_id and schema-valid args now. Select a Capability only "
        "when its description, effects, and projected semantic_scope directly match the "
        "Responsibility's observable outcome. A read-only information request must use "
        "an information-read Capability when one is supplied; physical-object acquisition, "
        "handover, body gestures, or attention motions cannot acquire external information. "
        "Do not add decorative Capability Activities that the Responsibility did not ask "
        "for. Preserve speaker, experiencer, and actor ownership: a human report of "
        "their feeling or state does not request any robot body state, stop, posture, "
        "gesture, or other physical effect. Preserve every GI binding, "
        "including all independent temporal dimensions. When fresh Evidence is still "
        "needed and no committed Communicative Activity is supplied above, add one "
        "concise progress speaking Activity that does not claim a result. Every "
        "Communicative Activity must use the requested response language; zh or "
        "zh-CN requires natural Chinese, never English or pinyin. Use short Activity "
        "IDs, omit optional default fields, and keep "
        "reason_summary under one brief clause. Use disposition=escalate and "
        "continuation=deep_planner only when HOW "
        "itself exceeds the Fast planning budget; emit no Capability Activities in "
        "that case. Goal Association is always concurrent and is never a continuation. "
        "Never claim execution or external results before Evidence.\n\n"
        "Validation errors from the prior Fast Plan, if any:\n"
        + (validation_errors or "[]")
        + "\nReturn one fresh complete schema-constrained JSON object only."
    )
    return LayeredPrompt.promote(
        rendered,
        operating_contract=(advance_contract,),
    )


def fast_advance_capability_prompt_projection(
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep every bounded catalog choice visible without slicing JSON mid-item."""

    projected: list[dict[str, Any]] = []
    for capability in capabilities:
        input_schema = capability.get("input_schema") or {}
        properties = input_schema.get("properties") or {}
        required = {
            str(item) for item in (input_schema.get("required") or [])
        }
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
                key: (value[:12] if isinstance(value, list) else str(value)[:900] if key == "contract" else value)
                for key, value in dict(contract).items()
                if key in {
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
                "arguments": arguments,
                "requires_confirmation": bool(
                    capability.get("requires_confirmation")
                ),
                "can_run_parallel": bool(capability.get("can_run_parallel")),
                "parallel_metadata_declared": bool(
                    capability.get("parallel_metadata_declared")
                ),
                "resource_claims": list(
                    capability.get("resource_claims") or []
                )[:12],
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


def fast_advance_system_prompt() -> str:
    return (
        "You are Chromie's low-latency Fast Planner. Accept Goal Interpretation's "
        "Responsibility evidence as authoritative contextual WHAT. Produce the first "
        "Activity Plan, including speaking and exact available Capability Activities. "
        "Speaking Activities are Communicative Acts: select their function, exact "
        "natural wording, timing, truth stage, and Responsibility/InformationGap "
        "provenance; speech_act remains a closed communicative-function enum. Ask "
        "through a clarification act when a required user-resolvable "
        "binding is genuinely absent after checking GI bindings and Capability defaults; "
        "never reinterpret a present normalized binding as missing or ambiguous. Select "
        "only a Capability whose declared description, effects, and semantic scope match "
        "the requested outcome; information reads are not physical-object delivery or "
        "decorative body motion. Delegate only genuinely complex HOW to Deep Planner. Goal "
        "Association separately owns Canonical Goal commits, and Trusted Capability "
        "Runtime owns execution authority and mechanically realizes Planner wording. "
        "Return only schema-constrained JSON."
    )


def fast_layered_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    response_schema: dict[str, Any],
    previous_raw: Any = None,
    validation_errors: str = "",
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    identity_world = (
        "Owner-approved Chromie identity JSON:\n"
        f"{bounded_identity_json(context)}\n\n"
        "Owner-approved Personality Expression JSON:\n"
        f"{bounded_personality_json(context)}\n\n"
    )
    capability_contract = (
        agent_skill_prompt_section(context, agent_role="fast_planner")
        + "Executable common capability catalog JSON:\n"
        + bounded_json(capabilities, 9000)
        + "\n\n"
    )
    rendered = fast_plan_prompt(
        request,
        capabilities,
        response_schema=response_schema,
        previous_raw=previous_raw,
        validation_errors=validation_errors,
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_world,),
        operating_contract=(
            IDENTITY_SEMANTIC_CONTRACT,
            PERSONALITY_SEMANTIC_CONTRACT,
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


def fast_repair_system_prompt() -> str:
    return (
        "You regenerate one fresh Fast Planner output using the supplied authoritative goals, executable capability catalog, complete validation errors, and schema-constrained decoder. "
        "Validation errors describe defects in the prior plan object; they are not evidence that execution occurred, that the user request became uncertain, or that a catalog capability needs confirmation. Preserve the authoritative user meaning and catalog facts while correcting every defect. "
        "Rebuild every required model-authored plan field instead of editing or splicing invalid JSON. Do not rely on host-generated steps, ownership, outcomes, disposition, or satisfaction. Return JSON only."
    )


def deep_plan_prompt(
    request: CognitiveWorkRequest,
    capabilities: list[dict[str, Any]],
    *,
    feedback: list[dict[str, Any]],
    response_schema: dict[str, Any],
    previous_raw: Any = None,
    expected_goal_ids: list[str],
) -> str:
    context = request.context if isinstance(request.context, dict) else {}
    capabilities = prioritize_capability_contracts(
        context,
        capabilities,
        feedback=feedback,
    )
    prompt_capabilities = [
        prompt_capability_contract(item) for item in capabilities
    ]
    identity_json = bounded_identity_json(context)
    personality_json = bounded_personality_json(context)
    skill_section = agent_skill_prompt_section(
        context,
        agent_role="deep_planner",
    )
    fast_plan = (
        context.get("fast_plan_resolution") or context.get("fast_planner_resolution") or {}
    )
    goals = context.get("active_goal_snapshots") or []
    association = goal_association_prompt_projection(context)
    grounding = canonical_goal_grounding(context)
    runtime_feedback = context.get("runtime_validator_feedback") or []
    combined_feedback = [
        *feedback,
        *(runtime_feedback if isinstance(runtime_feedback, list) else []),
    ]
    feedback_section = bounded_json(combined_feedback, 5000) if combined_feedback else "[]"
    previous_section = bounded_json(previous_raw, 5000) if previous_raw is not None else "null"
    response_only, requires_execution = planner_goal_execution_requirements(grounding)
    cancellation_reentry_goal_ids = goal_cancellation_evidence_reentry_goal_ids(context)
    if cancellation_reentry_goal_ids:
        capability_goal_ids = {
            str(goal.get("goal_id") or "").strip()
            for goal in grounding
            if isinstance(goal, dict)
            and isinstance(goal.get("metadata"), dict)
            and str(goal["metadata"].get("responsibility_kind") or "").strip()
            == "capability_dependent"
        }
        requires_execution = bool(capability_goal_ids - cancellation_reentry_goal_ids)
        if cancellation_reentry_goal_ids == set(expected_goal_ids):
            response_only = True
    provider_vocal_goal_ids = sorted(
        planner_provider_vocal_goal_ids(grounding)
    )
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
        f"Fast-plan advisory JSON:\n{bounded_json(fast_plan, 1800)}\n\n"
        f"Goal association advisory JSON:\n{bounded_json(association, 3200)}\n\n"
        f"Active goals JSON:\n{bounded_json(goals, 3200)}\n\n"
        f"Bounded live Situation projection JSON (soft/revisable relevance only; referenced owners remain authoritative):\n{bounded_json(situation_prompt_projection(context), 3600)}\n\n"
        f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
        f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
        f"{skill_section}"
        f"Executable capability catalog JSON:\n{bounded_json(prompt_capabilities, 12000)}\n\n"
        f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{bounded_json(context.get('verified_tool_memory_index') or [], 6000)}\n\n"
        f"Host-bound terminal Evidence JSON:\n{bounded_json(context.get('trusted_terminal_evidence') or [], 6000)}\n\n"
        f"Trusted execution outcome truth JSON (mechanical status/qualification only; Planner owns meaning):\n{bounded_json(context.get('trusted_execution_outcome') or {}, 5000)}\n\n"
        f"Host-bound Goal cancellation Evidence JSON:\n{bounded_json(context.get('trusted_goal_cancellation_evidence') or [], 3200)}\n\n"
        f"Active and recoverable task bindings JSON:\n{bounded_json(context.get('active_task_snapshots') or [], 6000)}\n\n"
        f"Existing retained or provisional Runtime Activities JSON:\n{bounded_json(context.get('existing_work_activities') or [], 4000)}\n\n"
        f"{goal_progress_communication_prompt('Planner deep pass')}\n\n"
        f"Goal-scoped Interaction Context JSON:\n{bounded_json(context.get('interaction_context') or {}, 8000)}\n\n"
        "Use Interaction Context to reason from what Chromie actually delivered, what trusted evidence says completed or failed, what remains pending, and what is new; produce only the still-needed conversational and effectful delta. Preserve owner and event_type evidence strength: generated or scheduled speech is not proof the user heard it, a proposal or committed request is not completion, and execution completion must retain execution_closure evidence references. Missing or undelivered communication may still leave a meaningful conversational delta; decide that from the current Goal and Interaction Context rather than from an earlier stage's private preference. Add response_text only when it materially improves the current interaction; avoid filler and repetition. Repeat an act only when the current meaning justifies it, such as an explicit repeat, retry, correction, changed state, new evidence, or clarification. The current canonical Goals and validation feedback remain authoritative. "
        "The active task bindings are historical Host/runtime context. Their "
        "task_id, request_id, canonical_plan_id, and prior step IDs are not "
        "current Deep Planner step IDs. Never copy them into current "
        "steps[].step_id or goal_outcomes.*.step_ids; only IDs authored in "
        "this output's steps array are eligible.\n\n"
        f"Previous Deep Planner model output JSON, when doing a mechanical DTO regeneration:\n{previous_section}\n\n"
        f"Deterministic validation feedback from the previous deep-plan or trusted host-runtime attempt:\n{feedback_section}\n\n"
        "When validation feedback is present but the previous output is null, regenerate one fresh complete object from the authoritative turn, goals, catalog, and all listed defects. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
        "When validation feedback reports parallel_step_count=1, the parallel label has no peer and is a malformed scheduling annotation rather than a user-visible concurrency plan; regenerate that exact one-step plan with timing=sequential. When validation feedback says multi-step parallel execution is not affirmatively safe, never silently change those parallel steps to an exact sequential plan. Either author plan_relation=safe_adjustment or alternative with user_confirmation_required=true and response_text explaining the timing change, or return a zero-step clarification/unavailable result. "
        "Produce the final DeepPlannerModelOutput for the complete user goal. Deep planning is terminal: never return to the Fast Planner. The FINAL AUTHORITATIVE USER TURN owns the current communicative act. Retained Goals and delivered evidence may support a response, but must not replace the latest reaction, feeling, acknowledgement, evaluation, or practical decision. Answer that current act directly; replay or re-explain a prior task only when the latest turn asks for it. The verified tool-memory index contains no answer facts. If one exact fresh index entry matches the authoritative Goal bindings, execute chromie.memory.retrieve_verified_tool_result with its evidence_id, original tool_id, and the exact material arguments. If no such entry exists, execute the fresh read capability. Never answer directly from index metadata, never reinterpret an unresolved reference from old memory, and never use another task's result. When a scheduled, running, or recoverable safe read has no matching completed memory entry, resume or retry its bound capability with the exact arguments. "
        "When Host-bound Goal cancellation Evidence is present, it is the trusted "
        "control result for the named cancellation: cancelled means the target Goal "
        "is terminal and must not be re-executed; not_cancelled means do not claim it "
        "stopped; uncertain means preserve that uncertainty. Coaffected Goals remain "
        "separate open/recoverable responsibilities unless their own state says otherwise. "
        "Goals listed in released_confirmation_goal_ids lost only a stale authorization "
        "token and remain open for fresh planning; never treat them as cancelled. "
        f"Required response language: {str(request.language or 'auto')[:32]}. "
        "Write every user-facing top-level and per-goal response_text naturally "
        "in that language. Do not switch languages merely because internal Goals, "
        "capability descriptions, rationales, or validation feedback use another language. "
        f"{goal_execution_contract}"
        f"{IDENTITY_SEMANTIC_CONTRACT}"
        f"{PERSONALITY_SEMANTIC_CONTRACT}"
        f"{EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT}"
        "Use the full catalog, preserve all independent responsibilities, constraints, conditions, ordering, concurrency, temporal scope, comparison period, and requested answer shape. Never silently rewrite simultaneous independent actions as before/after actions. An explicit ordered relation must remain sequential. Capability parallel-safety is permission to honor user-requested concurrency, never evidence that concurrency was requested. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech you author exactly as a Communicative Activity. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, clarify or propose an explicit safe adjustment rather than silently serializing the request. For a Goal with resource_responsibility, keep the entire acquire-and-deliver outcome as one semantic responsibility and use the current capability catalog as the dynamic decomposition boundary. Prefer one exact capability when its declared resource_contract.plan_provides covers the complete required resource state. If no one capability covers the Goal, compose multiple advertised capabilities whose matching semantic scopes and ordered plan_requires/plan_provides form a valid chain covering the required outcome. Never invent provider-internal navigation, perception, grasp, search, retry, carrying, or handover stages that are not separately advertised capabilities. Provider-local decomposition stays inside the selected capability. The Goal is provider-neutral: choose the smallest reliable complete capability set from current declared semantics, never from capability names or a hardcoded provider rule. When source.status=unknown, the selected chain must include a capability that can resolve it internally or otherwise avoid requiring an unresolved source state; do not invent a source. Capability semantic_scope and resource_contract metadata are authoritative applicability evidence. When a selected Capability accepts resource, source, or recipient objects, copy each accepted object exactly from the canonical resource_responsibility, including nested quantity, source bindings, and recipient fields. Do not emit parameter_resolutions for nested fields of those complete structured arguments or invent top-level fields absent from the Capability schema. Never silently narrow a canonical goal to fit a capability or its enum defaults. If a goal is outside every available capability scope, clarify or report unavailable with zero steps. Resolve low-consequence "
        "parameters semantically when justified; otherwise return a specific natural clarification. Clarification is only for ambiguous user meaning or missing material information that the user can supply and whose answer can enable a matching catalog capability. When the Goal is already clear but no exact available capability covers the required outcome, return unavailable rather than asking for preferences, refinements, or details that cannot create the missing provider. Author exact natural response_text for every clarify, unavailable, or refused result; unresolved diagnostics alone are not speech. Capability domains are not interchangeable merely because several capabilities share a read/effect class. Eligibility requires the selected Capability's declared information_domain and semantic scope to cover the exact Goal; never substitute the nearest read-only Capability from another domain. Canonical Goal typed semantics are authoritative: non-resource Goals use object.bindings, while resource Goals use resource_responsibility directly with no persisted flat compatibility copy. Every material step argument that directly represents one canonical binding must preserve that binding exactly; do not replace it with older memory or re-resolve the original reference. When a Capability declares argument_realization, Deep Planner owns the semantic transformation from the original user turn plus canonical human-semantic binding into only those declared provider arguments, and must record semantic_realization parameter provenance. This transformation is HOW and never rewrites the canonical Goal or silently narrows its scope. For chromie.memory.retrieve_verified_tool_result, all resolved material Goal bindings belong inside the single material_args object. Nested material fields are not missing direct step arguments, so do not emit separate parameter_resolutions for them. If a resolution for that nested object is useful, its parameter must be material_args and its value must equal the complete step.args.material_args object. When independent goals have different terminal needs, use disposition=mixed, coverage=complete, and goal_outcomes so executable goals can proceed while only affected goals wait for clarification. Scope every blocking parameter resolution with source_goal_ids. Exact, safe-adjusted, or alternative executable plans "
        "must use coverage=complete and disposition=execute or mixed as appropriate. Every executable step must include source_goal_ids identifying exactly the goals it serves. Use plan_relation=exact for an exact plan. A safe_adjustment or material alternative must use the corresponding plan_relation, be described in response_text, set user_confirmation_required=true, and require "
        "confirmation downstream. For every missing parameter, return parameter_resolutions with a semantic strategy, concrete value when resolved, confidence, and rationale. Use safe_default only for low-consequence reversible values inside schema bounds. Use ask_user for material or risky values. Also return goal_satisfaction as prospective plan adequacy: planned steps count as satisfying their goals if successful, and pending execution alone is never an unmet requirement. An exact complete plan therefore uses status=exact with score at least 0.95 and lists the goals it is designed to satisfy. If essential information remains missing, use coverage=partial or uncertain with disposition=clarify and zero steps. "
        "If unavailable or refused, use zero steps. Use exact supplied capability IDs and schema-valid args. "
        "Generic speech transport is never an executable Activity plan step. A canonical Goal with responsibility_kind=vocal_output, output_mode=speech, and provider_required=false uses a respond outcome with the actual answer, joke, greeting, or other authored text now. Executable and provider-backed outcomes may also carry response_text when it represents a still-needed prospective acknowledgement, limitation, correction, clarification, or other conversational delta. Use Interaction Context to omit an equivalent act already delivered or pending; repeat only when new meaning, failure/retry, correction, changed state, or explicit user intent justifies it. A vocal_output Goal with provider_required=true requests a mode-specific vocal performance such as expressive speech, recitation, singing, humming, or nonverbal vocalization. Execute that Goal only when the supplied maintained planning surface contains exact capability_id chromie.vocal.perform and its input mode enum advertises the authoritative Goal output_mode. Use one owned Vocal-lane step and copy that exact mode and authored content. response_text may explain new prospective context but never substitutes for or proves the provider performance. When the exact capability or requested mode is absent, use unavailable, refused, or a specific clarification outcome with zero step_ids and state any still-needed limitation truthfully rather than promising the unavailable work. A song verse read by ordinary TTS, chromie.speak, media playback, and body gestures are not completion evidence for that mode. A canonical executable_action/activity/media_playback Goal must use exactly one `chromie.media.<media_operation>` capability advertised by the qualified catalog. Existing music, recordings, streams, and sound effects remain Activity work; preserve persistent playback_id and choose play, pause, resume, seek, stop, volume, or status exactly as authored by Goal Association. Media and Vocal may overlap only under the declared duck-media mixer policy; overlap never mutates either Goal or makes playback a vocal result. Independent body Goals may still execute under an explicit mixed per-goal outcome. When direct ordinary speech overlaps Activity execution, preserve the requested concurrency with a respond outcome plus parallel Activity steps only when providers declare safe overlap; author the exact communicative wording and let the Host validate the immutable cross-lane projection. Never silently downgrade one vocal mode to another. Greeting wording and length are ordinary model-authored conversational choices governed by the supplied scene, relationship context, and owner-approved personality. "
        "An unavailable provider-backed vocal mode remains wholly unavailable: do "
        "not offer to try, approximate, imitate, or replace it with another vocal "
        "effect such as humming, melody, lyrics, noises, pleasant sounds, ordinary "
        "speech, or a weaker performance unless an exact separately supplied "
        "Capability supports that requested mode. Apply this to aggregate and "
        "per-Goal response_text alike; state the limitation and preserve independent "
        "executable Goals without promising a substitute effect. "
        "When retained or provisional Runtime Activities are supplied for Work reconciliation, decide whether they still advance the canonical Goals. Reuse is an explicit semantic choice: set reuse_activity_id to the supplied stable activity_id only while preserving its Capability ID, exact arguments, Goal ownership, and timing; omit reuse_activity_id when authoring replacement Work. Runtime validates live identity and state and never infers reuse from similarity. For retained chromie.work_dag.execute Work, reuse means NO_CHANGE to the current WorkDAG. A semantic change must be Planner-authored as the next revision of the same dag_id with revision incremented exactly once and parent_revision naming the retained revision; never ask DAGEngine to invent or recommend replacement topology. "
        "A plan step may contain only step_id, capability_id, args, timing, source_goal_ids, reuse_activity_id, and reason_summary. "
        "Use capability_id as the executable identity. Do not copy catalog-only fields such as input_schema, parameters, step_type, or effects into a plan step. "
        "Use exactly the supplied canonical goal IDs. Do not create goals for internal status checks, safety checks, capability lookups, or implementation preconditions; represent any justified internal operation only as a step owned by an existing user goal. "
        "Keep the plan minimal: every executable step must be necessary for one concrete observable outcome in the canonical Goal that owns it. A general body_action output mode does not authorize unrelated body effects. Do not add a blink, gaze, gesture, posture, attention expression, personality flourish, social enhancement, neutral-position, reset, transition, cleanup, or other presentation step merely to seem natural or improve the interaction. Optional coordinated expression belongs to the separate Social Attention owner; it enters the main Plan only when the user explicitly requested that exact observable effect or a supplied capability execution constraint explicitly requires it. "
        "goal_outcomes is a JSON object keyed by every supplied canonical goal ID exactly once, never a list; every Deep Planner result must include it. Every outcome must explicitly author disposition, coverage, response_text, unresolved, step_ids, satisfaction, and rationale. Each value describes only that key's goal and must not repeat goal_id inside the value. Per-goal outcome invariants are mandatory: execute requires coverage=complete and at least one real plan step_id copied exactly from steps; respond requires coverage=complete, the actual answer text now (not a promise that it will be supplied later), and zero step_ids; clarify requires coverage=partial or uncertain, exact natural response_text, and zero step_ids; unavailable and refused require exact natural response_text and zero step_ids. Top-level and per-goal satisfaction are always non-null model judgments with score, status, satisfied_goal_ids, unmet_goal_ids, unmet_requirements, and rationale. A satisfaction score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. Do not assign a physical skill to a conversational answer merely because it is the nearest remaining capability. "
        "Complete plan coverage means every Goal has an explicit outcome; it does not mean every Goal can be satisfied. An unavailable, refused, or unresolved Goal must remain in unmet_goal_ids with a non-exact satisfaction status and score. The top-level satisfaction must preserve those same unmet Goals and requirements even when independent execute Goals can proceed in a coverage=complete mixed plan. "
        "An unavailable or refused outcome explicitly represents its Goal but does not satisfy it, and it is not by itself a safe adjustment or alternative. Do not promise, acknowledge as forthcoming, or otherwise claim that unavailable or refused work will occur in top-level or per-goal response_text. State the limitation truthfully while preserving exact independent executable work. "
        "Top-level disposition is the aggregate of per-goal dispositions: use mixed only when at least two different per-goal disposition values are present. Multiple goals that are all execute use top-level execute; multiple goals that are all respond use top-level respond. "
        "Every outcome step_id must name a real plan step, every plan step must be referenced by an execute outcome when goal_outcomes are present, and each step source_goal_ids must exactly match the execute outcomes that reference it. "
        "The Ollama decoder enforces the exact flat DeepPlannerModelOutput JSON Schema supplied out-of-band. The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. Populate only fields allowed by the model schema and return JSON only. "
        "The following final grounding block is authoritative and must override unrelated content in previous model output or advisory context.\n\n"
        f"FINAL AUTHORITATIVE USER TURN:\n{request.original_user_text}\n\n"
        f"FINAL CANONICAL GOALS JSON (copy goal IDs exactly and satisfy these meanings only):\n{bounded_json(grounding, 5000)}\n\n"
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
    feedback: list[dict[str, Any]],
    response_schema: dict[str, Any],
    previous_raw: Any = None,
    expected_goal_ids: list[str],
) -> LayeredPrompt:
    context = request.context if isinstance(request.context, dict) else {}
    prioritized = prioritize_capability_contracts(
        context,
        capabilities,
        feedback=feedback,
    )
    prompt_capabilities = [
        prompt_capability_contract(item) for item in prioritized
    ]
    identity_world = (
        "Owner-approved Chromie identity JSON:\n"
        f"{bounded_identity_json(context)}\n\n"
        "Owner-approved Personality Expression JSON:\n"
        f"{bounded_personality_json(context)}\n\n"
    )
    capability_contract = (
        agent_skill_prompt_section(context, agent_role="deep_planner")
        + "Executable capability catalog JSON:\n"
        + bounded_json(prompt_capabilities, 12000)
        + "\n\n"
    )
    rendered = deep_plan_prompt(
        request,
        capabilities,
        feedback=feedback,
        response_schema=response_schema,
        previous_raw=previous_raw,
        expected_goal_ids=expected_goal_ids,
    )
    return LayeredPrompt.promote(
        rendered,
        identity_world=(identity_world,),
        operating_contract=(
            IDENTITY_SEMANTIC_CONTRACT,
            PERSONALITY_SEMANTIC_CONTRACT,
            EXPLICIT_NUMERIC_ARGUMENT_GROUNDING_PROMPT,
        ),
        capability_contract=(capability_contract,),
    )


def prioritize_capability_contracts(
    context: dict[str, Any],
    capabilities: list[dict[str, Any]],
    *,
    feedback: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    referenced_ids: list[str] = []

    def retain(value: Any) -> None:
        if isinstance(value, dict):
            capability_id = str(
                value.get("capability_id") or ""
            ).strip()
            if capability_id and capability_id not in referenced_ids:
                referenced_ids.append(capability_id)
            for nested in value.values():
                retain(nested)
        elif isinstance(value, list):
            for nested in value:
                retain(nested)

    retain(context.get("runtime_validator_feedback") or [])
    retain(feedback or [])
    retain(
        context.get("fast_plan_resolution")
        or context.get("fast_planner_resolution")
        or {}
    )
    by_id = {str(item.get("capability_id") or ""): item for item in capabilities}
    prioritized = [by_id[item] for item in referenced_ids if item in by_id][:12]
    prioritized_ids = {
        str(item.get("capability_id") or "") for item in prioritized
    }
    return [
        *prioritized,
        *[
            item
            for item in capabilities
            if str(item.get("capability_id") or "") not in prioritized_ids
        ],
    ]


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
        if when_to_use and when_to_use != str(
            capability.get("description") or ""
        ).strip():
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
        "A same-tier regeneration is allowed only once for a mechanically malformed DTO; semantic rejection is terminal. You never call or return to the Fast Planner. "
        "Capabilities are plan leaves, not planner ownership boundaries. Do not execute, authorize, or claim completion. Return JSON only."
    )


def deep_revision_system_prompt() -> str:
    return (
        "You regenerate one fresh Deep Planner DTO only because the previous object was mechanically invalid under the supplied exact flat DeepPlannerModelOutput JSON Schema. "
        "Rebuild every required field from the authoritative user turn, goals, and capabilities; do not edit or splice the invalid JSON. "
        "Return only the corrected DeepPlannerModelOutput JSON object. Do not add commentary, markdown, annotations, local field mappings, or hidden reasoning."
    )
