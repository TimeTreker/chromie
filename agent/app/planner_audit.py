from __future__ import annotations

import json
from typing import Any

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

from .planner_model_contract import PlannerCommunicationReview, PlannerCoverageReview
from .planner_schema import planner_communication_review_response_schema, planner_coverage_review_response_schema

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
            "num_predict": 384,
        },
        response_format=planner_coverage_review_response_schema(),
    )
    if not isinstance(raw, dict):
        raise ValueError("planner coverage review response is not a JSON object")
    return PlannerCoverageReview.model_validate(raw)
