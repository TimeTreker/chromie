from __future__ import annotations

import json
from typing import Any

try:
    from chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerFirstResponseTruthCertificate,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import (
        CanonicalPlan,
        FastPlannerFirstResponseTruthCertificate,
    )

from .clients.ollama_client import LayeredPrompt
from .planner_context import planner_goal_context
from .planner_model_contract import PlannerCommunicationReview, PlannerCoverageReview
from .planner_schema import (
    fast_truth_certificate_response_schema,
    planner_communication_review_response_schema,
    planner_coverage_review_response_schema,
)
from .prompt_projection import bounded_json


async def qualify_evidence_response_truth(
    client: Any,
    *,
    request: Any,
    plan: CanonicalPlan,
    num_ctx: int,
    num_predict: int,
    prompt_family: str,
) -> FastPlannerFirstResponseTruthCertificate:
    """Accept or reject terminal Planner wording against immutable Evidence.

    This audit is shared by Fast and Deep Planner because escalation must not
    create a path around the post-Evidence truth contract. It never rewrites a
    response or authorizes execution.
    """

    context = request.context if isinstance(request.context, dict) else {}
    goal_context = planner_goal_context(
        context,
        reentry_scope=request.planner_reentry_scope,
    )
    contract = (
        "Planner post-Evidence Epistemic Qualification contract: inspect every "
        "candidate response string against only the admitted trusted terminal "
        "Evidence and authoritative Goal scope. Return decision=accept only when "
        "every material claim preserves the Evidence values, scope, and epistemic "
        "strength. Apply the audit fields to their distinct claim classes instead "
        "of using one flag as a generic rejection reason. First determine the "
        "candidate's execution-state claim for each scoped Goal: completed, ongoing, "
        "future, failed/cancelled/timed-out, or status-neutral. Compare that claim "
        "only with trusted_execution_outcome. Next determine whether completion "
        "qualification is required and established. When a scoped source-Plan step "
        "is completed and its required qualification is established, exact completion "
        "wording for that step is supported; do not mark it as an epistemic-strength "
        "contradiction merely because the provider payload does not repeat the "
        "Planner-owned count, duration, direction, or other immutable step arguments. "
        "When completion qualification is required but not established, a completion "
        "claim is unverified even if the provider returned completed; status-neutral "
        "wording may still be valid. Preserve uncertainty and qualification exactly: probabilistic, "
        "forecast, estimated, bounded, partial, conditional, or otherwise qualified "
        "Evidence must remain qualified. For every numeric probability p where "
        "0 < p < 100 percent, categorical wording that the event will happen or "
        "will not happen is an epistemic-strength contradiction, even when another "
        "Evidence field has a categorical condition label. Reject wording that "
        "strengthens probability, confidence, causal implication, temporal scope, "
        "or certainty beyond the admitted Evidence, and set "
        "has_epistemic_strength_contradiction=true for that exact defect. "
        "Do not set that flag when the candidate makes no probability, forecast, "
        "estimate, confidence, causal, qualification, or temporal-scope claim. "
        "Reject unsupported duration, severity, advice, reassurance, or facts from another "
        "period. Do not rewrite the response, choose a Capability, or add an "
        "explanation. The typed re-entry scope is exact: reject claims about a "
        "sibling Goal outside that scope. A completed Evidence record supports only "
        "the source-Plan step bound to its scoped Goal; use that immutable source "
        "Plan to verify the requested arguments rather than demanding that the "
        "provider repeat Planner-owned arguments in its terminal payload. The source "
        "Plan is historical requested-Work truth only: its disposition and executable "
        "steps never state the current execution status and must not determine tense. "
        "Only the trusted execution outcome is authoritative for current execution "
        "status. The scope "
        "excludes every sibling Goal not listed there: reject any wording that names, "
        "imitates, counts, or claims an effect from an excluded sibling, even when "
        "the originating user turn or broader history mentions it. The dedicated "
        "has_out_of_scope_goal_claim flag must be true for that case; compare the "
        "candidate clause-by-clause with the authoritative scoped Goal description "
        "and its one source-Plan step. It must be false only when every claimed effect "
        "belongs to that scoped Goal. The trusted execution outcome is the mechanical "
        "authority for completion status and completion qualification; accept an "
        "exact scoped completion claim when that outcome marks the Goal completed, "
        "its Evidence IDs match, and required qualification is established (or no "
        "completion qualification is required). In that condition, an exact "
        "past-tense statement that Chromie performed the scoped source-Plan effect is "
        "consistent and has_execution_status_contradiction must be false. Audit "
        "execution tense against that same outcome. When it says the scoped Goal is "
        "completed, wording that says Chromie will perform, is starting, or is still "
        "performing that completed effect contradicts execution state; set "
        "has_execution_status_contradiction=true. When it says the scoped Goal failed, "
        "cancelled, timed out, or otherwise did not complete, wording that commands, "
        "promises, or implies successful completion contradicts execution state. A "
        "completed outcome may be described as completed, or the response may state "
        "only the observed result. Classify whether the response has an unsupported "
        "material claim or a semantic-perspective contradiction, execution-status "
        "contradiction, or out-of-scope Goal claim, then return only decision=accept "
        "when none is present. Otherwise return decision=reject. A rejection must "
        "identify at least one exact violation flag; never reject with every flag false."
    )
    candidate = {
        "response_text": plan.response_text,
        "goal_outcome_response_texts": [
            {
                "goal_id": outcome.goal_id,
                "response_text": outcome.response_text,
            }
            for outcome in plan.goal_outcomes
            if getattr(outcome, "response_text", "")
        ],
    }
    source_plan = context.get("canonical_plan_resolution") or {}
    source_plan_projection = {
        "plan_id": source_plan.get("plan_id"),
        "steps": [
            {
                "step_id": step.get("step_id"),
                "capability_id": step.get("capability_id"),
                "args": step.get("args") or {},
                "expected_outcome": step.get("expected_outcome") or "",
                "source_goal_ids": step.get("source_goal_ids") or [],
            }
            for step in source_plan.get("steps") or []
            if isinstance(step, dict)
        ],
    }
    claim_boundary = (
        "Execution-status claims are only claims about whether Chromie or a "
        "provider performed the requested source-Plan step. Tense inside the "
        "Evidence-owned world proposition is not execution status. In particular, "
        "an information answer about whether rain will happen, what a forecast "
        "predicts, or what time it is is status-neutral with respect to completion "
        "of the lookup step. Audit that proposition only against Evidence and "
        "epistemic strength. Conversely, wording that Chromie walked, blinked, "
        "looked up, or finished does claim execution status. Do not compare a "
        "future weather/event proposition with the completed lookup status. Return "
        "all six boolean fields and decision explicitly; omission is an invalid "
        "certificate."
    )
    rendered = (
        contract
        + "\n\nCritical claim-type boundary:\n"
        + claim_boundary
        + "\n\nImmutable candidate response JSON:\n"
        + json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n\nAdmitted trusted terminal Evidence JSON:\n"
        + bounded_json(context.get("trusted_terminal_evidence") or [], 6000)
        + "\n\nImmutable typed Planner re-entry scope JSON:\n"
        + bounded_json(
            (
                request.planner_reentry_scope.model_dump(mode="json")
                if request.planner_reentry_scope is not None
                else {}
            ),
            2400,
        )
        + "\n\nMinimal authoritative source-Plan projection "
        "(requested step/argument/Goal binding only; it carries no current "
        "execution status):\n"
        + bounded_json(source_plan_projection, 2600)
        + "\n\nTrusted execution outcome JSON (mechanical completion and qualification):\n"
        + bounded_json(context.get("trusted_execution_outcome") or {}, 5000)
        + "\n\nAuthoritative canonical Goal JSON:\n"
        + bounded_json(list(goal_context.authoritative_goals), 3000)
        + "\n\nCurrent user turn (context only; typed scope above is authoritative):\n"
        + str(request.original_user_text or "")[:700]
    )
    raw = await client.generate(
        LayeredPrompt.promote(rendered, operating_contract=(contract,)),
        system=(
            "You are the current Planner's bounded post-Evidence Epistemic "
            "Qualification, not a response author. Accept or reject the immutable "
            "candidate. Set has_out_of_scope_goal_claim explicitly by comparing each "
            "claimed effect with the exact scoped Goal. Never repair, replace, or "
            "expand it. Set has_execution_status_contradiction explicitly by comparing "
            "candidate tense with the trusted execution outcome. Set "
            "has_epistemic_strength_contradiction explicitly by comparing every "
            "probability, estimate, forecast, or qualification with Evidence; leave "
            "that flag false when no such claim exists. Reject only with at least one "
            "specific true violation flag. An Evidence-world proposition such as "
            "whether rain will happen is not a claim about whether the lookup step "
            "executed. Return all six booleans and decision explicitly."
        ),
        options={
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": max(2048, int(num_ctx)),
            "num_predict": max(64, min(int(num_predict), 256)),
        },
        response_format=fast_truth_certificate_response_schema(),
        prompt_family=prompt_family,
        turn_id=request.sid,
        attempt=1,
    )
    return FastPlannerFirstResponseTruthCertificate.model_validate(raw)

async def review_retained_evidence_response(
    client: Any,
    *,
    request_text: str,
    language: str,
    association: dict[str, Any],
    authoritative_goals: list[dict[str, Any]],
    delivered_evidence: list[dict[str, Any]],
    plan: CanonicalPlan,
    num_ctx: int,
    turn_id: str,
) -> PlannerCommunicationReview:
    """Ask the planner model to accept or revise follow-up communication.

    This review can change only model-authored response text. It cannot create
    Goals, choose Capabilities, add steps, authorize execution, or reinterpret
    provider evidence. An accepted response must be returned byte-for-byte so
    the Host cannot silently treat an unrequested rewrite as acceptance.
    """

    response_goal_ids = [
        item.goal_id for item in plan.goal_outcomes if item.disposition == "respond"
    ] or list(plan.goal_ids)
    proposed_goal_responses = {
        item.goal_id: item.response_text
        for item in plan.goal_outcomes
        if item.disposition == "respond"
    }
    if not proposed_goal_responses and len(response_goal_ids) == 1:
        proposed_goal_responses[response_goal_ids[0]] = plan.response_text
    prompt = json.dumps(
        {
            "responsibility": (
                "Review whether the proposed response answers the latest user turn's "
                "communicative act directly while using retained delivered evidence only "
                "as support. Judge meaning across languages rather than matching phrases. "
                "First determine whether the latest turn is a reaction, feeling, "
                "acknowledgement, evaluation, practical decision, recommendation request, "
                "or yes/no question about the retained result. A practical decision, "
                "recommendation, or yes/no follow-up must state that answer in its first "
                "sentence and may then include at most one short supporting clause. It "
                "must not begin by replaying prior evidence, and must omit previously "
                "delivered measurements or conditions that do not change the decision. "
                "Other follow-ups must likewise answer the latest act instead of replacing "
                "it with the old task answer. Preserve the requested language and every "
                "retained fact that is actually used; never invent, infer, strengthen, or "
                "contradict an external fact. Choose accept only when the proposed text "
                "already satisfies this contract. Otherwise choose revise and author the "
                "smallest natural correction."
            ),
            "latest_user_turn": request_text,
            "language": language,
            "goal_association": association,
            "authoritative_goals": authoritative_goals,
            "delivered_evidence_bound_dialogue": delivered_evidence,
            "proposed_response_text": plan.response_text,
            "proposed_goal_responses": proposed_goal_responses,
            "output_contract": {
                "decision": "accept or revise",
                "accept": (
                    "Return proposed_response_text and every proposed_goal_response "
                    "exactly unchanged."
                ),
                "revise": (
                    "Return one corrected aggregate response_text and exactly one "
                    "corrected response for every supplied response Goal ID."
                ),
                "response_goal_ids": response_goal_ids,
                "execution_authority": "none",
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    raw = await client.generate(
        prompt,
        system=(
            "You are the current Planner's bounded conversational-contract reviewer. "
            "Review the latest communicative act against the model-authored Goal "
            "Association and trusted delivered evidence. Do not use phrase rules, add "
            "facts, create actions, or authorize execution. Return only the required "
            "JSON object."
        ),
        options={
            "temperature": 0,
            "top_p": 0.8,
            "num_ctx": max(4096, int(num_ctx)),
            "num_predict": 512,
        },
        response_format=planner_communication_review_response_schema(response_goal_ids),
        prompt_family="fast_planner.communication_review",
        turn_id=turn_id,
        attempt=1,
    )
    if not isinstance(raw, dict):
        raise ValueError("planner communication review response is not a JSON object")
    review = PlannerCommunicationReview.model_validate(raw)
    reviewed_by_goal = {item.goal_id: item.response_text for item in review.goal_responses}
    if set(reviewed_by_goal) != set(response_goal_ids):
        raise ValueError(
            "communication review responses must cover exactly the response Goal IDs"
        )
    if review.decision == "accept" and (
        review.response_text != plan.response_text
        or reviewed_by_goal != proposed_goal_responses
    ):
        raise ValueError("accepted communication review must preserve proposed text exactly")
    return review

async def review_coordinated_action_plan_coverage(
    client: Any,
    *,
    request_text: str,
    language: str,
    authoritative_goals: list[dict[str, Any]],
    plan: CanonicalPlan,
    capabilities: list[dict[str, Any]],
    num_ctx: int,
) -> PlannerCoverageReview:
    """Ask the planner model to audit a structured coordinated-action Plan.

    The review can only accept or reject. It cannot add steps, choose a
    Capability, authorize execution, or rewrite the Plan. A rejection therefore
    sends Fast Planning to Deep Planning, or makes Deep Planning fail closed.
    """

    plan_payload = plan.model_dump(
        mode="json",
        exclude={"metadata", "selected_agent_skills"},
    )
    terminal_non_effect_outcomes = [
        item
        for item in plan_payload.get("goal_outcomes", [])
        if isinstance(item, dict)
        and item.get("disposition") in {"unavailable", "refused"}
    ]
    effect_claim_outcomes = [
        item
        for item in plan_payload.get("goal_outcomes", [])
        if isinstance(item, dict)
        and item.get("disposition") not in {"unavailable", "refused"}
    ]
    effect_claim_goal_ids = {
        str(item.get("goal_id") or "").strip()
        for item in effect_claim_outcomes
        if str(item.get("goal_id") or "").strip()
    }
    if not plan_payload.get("goal_outcomes"):
        # The compact single-Goal Fast contract can omit the redundant outcome
        # envelope.  In that shape the Plan's authoritative goal_ids identify
        # the effect claims to audit.
        effect_claim_goal_ids.update(
            str(item or "").strip()
            for item in plan_payload.get("goal_ids", [])
            if str(item or "").strip()
        )
    effect_claim_goals = [
        item
        for item in authoritative_goals
        if str(item.get("goal_id") or "").strip() in effect_claim_goal_ids
    ]
    authoritative_goals_by_id = {
        str(item.get("goal_id") or "").strip(): item
        for item in authoritative_goals
        if str(item.get("goal_id") or "").strip()
    }
    terminal_non_effect_accounting = [
        {
            "authoritative_goal": authoritative_goals_by_id.get(
                str(item.get("goal_id") or "").strip(),
                {"goal_id": str(item.get("goal_id") or "").strip()},
            ),
            "terminal_outcome": item,
        }
        for item in terminal_non_effect_outcomes
    ]
    proposed_effect_claim_plan = {
        "disposition": plan_payload.get("disposition"),
        "coverage": plan_payload.get("coverage"),
        "goal_ids": sorted(effect_claim_goal_ids),
        "goal_outcomes": effect_claim_outcomes,
        "steps": plan_payload.get("steps", []),
        "response_text": plan_payload.get("response_text", ""),
        "parameter_resolutions": plan_payload.get("parameter_resolutions", []),
    }
    selected_capability_ids = {
        str(item.get("capability_id") or "").strip()
        for item in proposed_effect_claim_plan["steps"]
        if isinstance(item, dict)
        and str(item.get("capability_id") or "").strip()
    }
    selected_capabilities = [
        item
        for item in capabilities
        if str(item.get("capability_id") or "").strip()
        in selected_capability_ids
    ]
    prompt = json.dumps(
        {
            "responsibility": (
                "Audit whether the proposed Plan completely represents every "
                "material responsibility in the authoritative Goals. Judge semantics "
                "using ordinary world knowledge together with the supplied Capability "
                "contracts; do not match phrases or treat capability names as answers. "
                "A Plan may claim exact coverage only when every material Goal "
                "requirement is entailed by the declared semantics and arguments of "
                "its selected Capabilities, or by trusted evidence explicitly supplied "
                "to this review. Do not broaden a Capability from its name, rationale, "
                "identity/personality context, shared argument names, or superficial "
                "similarity. Do not infer undeclared effects, guarantees, resources, "
                "state transitions, or completion of another responsibility. Preserve "
                "authoritative typed bindings, requested ordering/concurrency, output "
                "modes, and resource responsibilities. Capability parallel-safety is "
                "permission to honor requested concurrency, never evidence that "
                "concurrency was requested. A response_text may communicate a new "
                "prospective acknowledgement, limitation, clarification, or other "
                "conversational delta, but it never substitutes for an effectful or "
                "provider-backed responsibility and never proves execution. A direct "
                "vocal_output Goal is completed by its respond outcome rather than "
                "a response-transport task step. Audit effect claims only against the "
                "Goals listed in effect_claim_goals. Every proposed step must be "
                "necessary for a concrete observable outcome in one of those Goals. "
                "Reject optional decoration, personality flourishes, social enhancement, "
                "or attention/body expression that the Goal did not request; those "
                "effects belong to a separate Social Attention owner. A broad body_action "
                "mode alone never authorizes arbitrary body Capabilities. Audit only the "
                "explicit Goal meaning, not a rationale claiming an extra step helps. "
                "The supplied executable_capabilities list contains only Capabilities "
                "actually selected by the immutable Plan. Never substitute, compare, "
                "or name an unlisted alternative Capability. Judge the exact selected "
                "capability_id and arguments as written. Runtime owns confirmation, "
                "provider enablement, bounds, monitoring, interruption, and safety "
                "preemption; do not invent a missing Planner step for those Runtime "
                "duties and do not reject an otherwise exact Plan merely because "
                "execution could later be interrupted. "
                "An explicit unavailable or refused "
                "outcome is terminal non-effect accounting, not a claim that a provider "
                "will perform that Goal: do not reject it merely because no matching "
                "Capability exists. It represents the unmet Goal only when it owns no "
                "step, satisfaction remains non-exact, and the aggregate and per-Goal "
                "wording truthfully disclose the limitation without promising the work. "
                "Do not treat coverage=complete on a mixed Plan as a claim that every "
                "Goal is satisfied: it means every Goal is explicitly accounted for, "
                "including terminal unavailable/refused outcomes that remain unmet. "
                "Each authoritative Goal item is atomic even when its source_text repeats "
                "the whole multi-effect turn; sibling Goal descriptions and IDs preserve "
                "the split, so repeated source_text never merges their satisfaction. "
                "Reject terminal accounting that violates those conditions. For a material "
                "adjustment or alternative, require the explicit confirmation-bound "
                "plan relation. Reject any exact Plan that omits or contradicts one of "
                "these semantic responsibilities. Do not propose or authorize "
                "replacement steps."
            ),
            "user_text": request_text,
            "language": language,
            "effect_claim_goals": effect_claim_goals,
            "proposed_effect_claim_plan": proposed_effect_claim_plan,
            "terminal_non_effect_accounting": terminal_non_effect_accounting,
            "proposed_adjustment_contract": {
                "plan_relation": plan.metadata.get("plan_relation", "exact"),
                "user_confirmation_required": bool(
                    plan.metadata.get("user_confirmation_required", False)
                ),
                "response_text": plan.response_text,
            },
            "executable_capabilities": selected_capabilities,
            "output_contract": {
                "decision": "accept or reject",
                "semantic_mismatch_found": (
                    "Set true when any selected Capability's declared effect does not "
                    "entail the Goal effect it claims, including an approximate, "
                    "symbolic, personality-based, or merely natural-looking substitute. "
                    "A true value requires decision=reject."
                ),
                "accept": (
                    "Only when every effect claim is semantically supported and every "
                    "other Goal has truthful explicit terminal non-effect accounting; "
                    "uncovered_requirements must be empty."
                ),
                "reject": (
                    "List each omitted or contradicted responsibility in uncovered_requirements."
                ),
                "execution_authority": "none",
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    raw = await client.generate(
        prompt,
        system=(
            "You are the current Planner's bounded semantic completeness auditor. "
            "Use the authoritative Goals, proposed Plan, and supplied Capability "
            "semantics. Do not use phrase rules, invent Capabilities, revise the "
            "Plan, or authorize execution. Return only the required JSON object."
        ),
        options={
            "temperature": 0,
            "top_p": 0.8,
            "num_ctx": max(4096, int(num_ctx)),
            # The bounded DTO permits twelve findings plus a rationale.  Leave
            # enough output budget to finish that contract instead of turning a
            # semantic rejection into truncated JSON.
            "num_predict": 4096,
        },
        response_format=planner_coverage_review_response_schema(),
    )
    if not isinstance(raw, dict):
        raise ValueError("planner coverage review response is not a JSON object")
    return PlannerCoverageReview.model_validate(raw)
