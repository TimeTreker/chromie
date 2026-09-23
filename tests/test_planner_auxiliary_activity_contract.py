from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from agent.app.capabilities.catalog import CapabilityMatch
from agent.app.planner_context import (
    auxiliary_social_capability_payloads,
    auxiliary_social_prompt_context,
    trusted_target_prompt_context,
)
from agent.app.planner_schema import (
    canonical_plan_response_schema,
)
from orchestrator.runtime.capability_runtime import CapabilityDefinition
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from shared.chromie_contracts.interaction import InteractionResponse, InteractionSpeech
from shared.chromie_contracts.plan import (
    AuxiliaryPlanActivity,
    CanonicalPlan,
    GoalSatisfactionAssessment,
    canonical_plan_fingerprint,
)


class _Runtime:
    def __init__(self, definitions: list[CapabilityDefinition]) -> None:
        self.definitions = {item.capability_id: item for item in definitions}
        self.executed: list[tuple[InteractionResponse, str]] = []

    async def ensure_capability_definitions(self, capability_ids):
        for capability_id in capability_ids:
            if capability_id not in self.definitions:
                raise ValueError(capability_id)

    def capability_definition(self, capability_id):
        return self.definitions[capability_id]

    async def submit_response(self, response, *, session_id):
        self.executed.append((response, session_id))
        return SimpleNamespace(response=response, session_id=session_id)

    async def wait_dispatch(self, _dispatch):
        return SimpleNamespace(status="completed")


def _definition(
    capability_id: str = "soridormi.blink_eyes",
    *,
    domains: list[str] | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        provider_id="soridormi.mcp",
        input_schema={
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 3}},
            "required": ["count"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"completed": {"type": "boolean"}},
            "required": ["completed"],
            "additionalProperties": False,
        },
        available=True,
        requires_confirmation=False,
        can_run_parallel=True,
        exclusive_group="face_expression",
        metadata={
            "behavior_domains": domains or ["social_attention"],
            "effects": ["social_expression"],
            "parallel_metadata_declared": True,
            "resource_claims": ["face"],
        },
    )


def _plan(*, capability_id: str = "soridormi.blink_eyes") -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-social",
        planner_tier="deep",
        disposition="respond",
        coverage="complete",
        confidence=0.95,
        goal_ids=["goal-1"],
        goal_summary="greet the user",
        response_text="Hello!",
        auxiliary_activities=[
            AuxiliaryPlanActivity(
                auxiliary_activity_id="aux-blink",
                anchor_kind="plan_response",
                anchor_id="response",
                capability_id=capability_id,
                args={"count": 1},
                social_function="engagement",
                reason_summary="A small greeting acknowledgement.",
            )
        ],
        goal_satisfaction=GoalSatisfactionAssessment(
            score=1.0,
            status="exact",
            satisfied_goal_ids=["goal-1"],
            rationale="The response answers the conversational Goal.",
        ),
    )


class PlannerAuxiliaryActivityContractTests(unittest.TestCase):
    def test_auxiliary_activity_is_fingerprinted_but_not_goal_owned(self) -> None:
        plan = _plan()
        dumped = plan.prompt_projection()
        auxiliary = dumped["auxiliary_activities"][0]
        self.assertNotIn("source_goal_ids", auxiliary)
        self.assertNotIn("affects_goal_satisfaction", auxiliary)
        changed = plan.model_copy(
            update={
                "auxiliary_activities": [
                    plan.auxiliary_activities[0].model_copy(
                        update={"args": {"count": 2}}
                    )
                ]
            }
        )
        self.assertNotEqual(
            canonical_plan_fingerprint(plan),
            canonical_plan_fingerprint(changed),
        )

    def test_auxiliary_anchor_must_reference_primary_plan_activity(self) -> None:
        payload = _plan().model_dump(mode="python")
        payload["auxiliary_activities"][0]["anchor_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "existing primary Plan Activity"):
            CanonicalPlan.model_validate(payload)

    def test_work_schema_has_no_auxiliary_writer(self):
        schema = canonical_plan_response_schema(planner_tier="deep", expected_goal_ids=[], allowed_capability_ids=[])
        self.assertNotIn("auxiliary_activities", schema["properties"])

    def test_social_schema_binds_auxiliary_capability_and_args(self) -> None:
        from agent.app.social_cognition import social_cognition_response_schema
        from shared.chromie_contracts.social_cognition import SocialCognitionRequest
        candidate = {
            "capability_id": "soridormi.blink_eyes",
            "input_schema": {
                "type": "object",
                "properties": {"count": {"type": "integer", "minimum": 1}},
                "required": ["count"], "additionalProperties": False,
            },
        }
        schema = social_cognition_response_schema(
            SocialCognitionRequest(request_id="sc-test", trigger="goal_state", source_refs=["goal-1"]),
            [candidate],
        )
        definition = schema["$defs"]["AuxiliaryPlanActivity"]
        import jsonschema
        proposal = {"auxiliary_activity_id": "gesture", "anchor_kind": "communicative_act",
                    "anchor_id": "greeting", "capability_id": candidate["capability_id"],
                    "args": {"count": 1}, "social_function": "engagement",
                    "reason_summary": "A coherent greeting expression."}
        jsonschema.validate(proposal, definition)
        for change in ({"args": {"count": 0}}, {"capability_id": "unknown"}):
            with self.subTest(change=change), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate({**proposal, **change}, definition)


    def test_catalog_filter_is_mechanical_and_social_context_names_sc_owner(self) -> None:
        eligible = CapabilityMatch(
            capability_id="soridormi.blink_eyes",
            agent_id="soridormi.skill",
            description="Blink softly.",
            input_schema={"type": "object", "properties": {}},
            available=True,
            interaction_executable=True,
            behavior_domains=["social_attention"],
            requires_confirmation=False,
            can_run_parallel=True,
            parallel_metadata_declared=True,
            score=1.0,
        )
        ineligible = eligible.model_copy(
            update={
                "capability_id": "soridormi.walk",
                "behavior_domains": ["locomotion"],
            }
        )
        candidates = auxiliary_social_capability_payloads([eligible, ineligible])
        self.assertEqual(
            [item["capability_id"] for item in candidates],
            ["soridormi.blink_eyes"],
        )
        context = auxiliary_social_prompt_context({}, candidates)
        self.assertEqual(context["eligible_capabilities"][0]["capability_id"], "soridormi.blink_eyes")
        self.assertNotIn("max_activities", context)
        self.assertNotIn("max_auxiliary_expressions", context)

        target_context = trusted_target_prompt_context({
            "active_user_target": {
                "target_ref": "opaque-current-speaker",
                "relative_direction": "front",
            }
        })
        self.assertEqual(set(target_context), {"target_evidence"})
        self.assertEqual(
            target_context["target_evidence"]["target"]["target_ref"],
            "opaque-current-speaker",
        )
        self.assertNotIn("eligible_capabilities", target_context)
        self.assertNotIn("social_interaction_style", target_context)
        self.assertNotIn("recent_auxiliary_behavior_evidence", target_context)

    def test_runtime_executes_exact_proposal_without_goal_authority(self) -> None:
        runtime = _Runtime([_definition()])
        adapter = CanonicalPlanRuntimeAdapter(runtime)
        outcome = asyncio.run(
            adapter.execute_auxiliary_activities(
                social_cognition=_decision(),
                session_id="session-1",
                turn_id="turn-1",
                interaction=InteractionResponse(
                    interaction_id="primary",
                    status="ok",
                    speech=[InteractionSpeech(id="primary-speech", text="Hello!", metadata={"communicative_activity_ids": ["greeting"]})],
                ),
                context={},
            )
        )
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["materialized_count"], 1)
        request = runtime.executed[0][0].capabilities[0]
        self.assertEqual(request.capability_id, "soridormi.blink_eyes")
        self.assertEqual(request.args, {"count": 1})
        self.assertEqual(request.metadata["source_goal_ids"], [])
        self.assertEqual(request.metadata["execution_role"], "social_decoration")
        self.assertFalse(
            runtime.executed[0][0].metadata["cognitive_reentry_eligible"]
        )

    def test_runtime_suppresses_expression_without_primary_launch(self):
        runtime = _Runtime([_definition()])
        outcome = asyncio.run(CanonicalPlanRuntimeAdapter(runtime).execute_auxiliary_activities(
            social_cognition=_decision(), session_id="session-1", turn_id="turn-social",
            interaction=None, context={}))
        self.assertEqual(outcome["materialized_count"], 0)
        self.assertEqual(runtime.executed, [])

    def test_runtime_drops_non_social_capability_instead_of_reselecting(self) -> None:
        runtime = _Runtime([_definition(domains=["locomotion"])])
        outcome = asyncio.run(
            CanonicalPlanRuntimeAdapter(runtime).execute_auxiliary_activities(
                social_cognition=_decision(),
                session_id="session-1",
                turn_id="turn-1",
                interaction=InteractionResponse(
                    interaction_id="primary",
                    status="ok",
                    speech=[InteractionSpeech(id="primary-speech", text="Hello!", metadata={"communicative_activity_ids": ["greeting"]})],
                ),
                context={},
            )
        )
        self.assertEqual(outcome["materialized_count"], 0)
        self.assertIn("not_social_attention:soridormi.blink_eyes", outcome["reasons"])
        self.assertEqual(runtime.executed, [])


if __name__ == "__main__":
    unittest.main()


def _decision():
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    return SocialCognitionResolution(request_id="sc-expression", snapshot_digest="a" * 64,
        disposition="communicate", reason_summary="Greet with an expression.", model_call_count=1,
        activities=[{"activity_id": "greeting", "text": "Hello!", "function": "acknowledge",
            "truth_stage": "context_grounded", "auxiliary_activities": [{
                "auxiliary_activity_id": "blink", "anchor_kind": "communicative_act",
                "anchor_id": "greeting", "capability_id": "soridormi.blink_eyes", "args": {"count": 1},
                "social_function": "engagement"}]}])
