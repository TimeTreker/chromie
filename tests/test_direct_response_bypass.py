from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agent.app.response_composer import ResponseComposerResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveEvidenceRecorder,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import FastPlannerAdvance, FastPlannerVocalActivity
from shared.chromie_contracts.response_composition import (
    DirectResponseComposition,
    goal_association_fingerprint,
)
from shared.chromie_contracts.semantic_task import (
    ResponsePlan,
    ResponseStage,
    SemanticGoal,
)


class ScriptedOllama:
    def __init__(self, response: dict):
        self.response = response
        self.calls = 0
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        return self.response


class NoopInteractionRuntime:
    async def ensure_skill_definitions(self, skill_ids):
        if list(skill_ids):
            raise AssertionError("direct speech should not require capability lookup")

    def skill_definition(self, skill_id):
        raise AssertionError(f"unexpected skill lookup: {skill_id}")


class DirectRuntimeClient:
    def __init__(
        self,
        association: GoalAssociationResolution,
        composition: DirectResponseComposition,
        advance: FastPlannerAdvance | None = None,
    ) -> None:
        self.association = association
        self.composition = composition
        self.advance = advance
        self.calls: list[str] = []

    async def resolve_fast_advance(self, *args, **kwargs):
        self.calls.append("advance")
        if self.advance is None:
            raise AssertionError("unexpected pre-Goal Fast Planner advance")
        return self.advance

    async def resolve_goal_association(self, *args, **kwargs):
        self.calls.append("association")
        return self.association

    async def resolve_fast_plan(self, *args, **kwargs):
        raise AssertionError("canonical Fast Planner must be bypassed for direct speech")

    async def resolve_deep_plan(self, *args, **kwargs):
        raise AssertionError("Deep Planner must be bypassed for direct speech")

    async def compose_response_plan(self, *args, **kwargs):
        self.calls.append("compose")
        self.assert_direct_context(kwargs.get("context") or {})
        from shared.chromie_contracts.response_composition import (
            ResponseCompositionResolution,
        )

        return ResponseCompositionResolution(
            status="resolved",
            composition=self.composition,
        )

    def assert_direct_context(self, context: dict) -> None:
        if "canonical_plan_resolution" in context:
            raise AssertionError("direct speech must not synthesize a fake CanonicalPlan")
        if "direct_goal_association_resolution" not in context:
            raise AssertionError("direct Goal Association was not provided to Composer")


def direct_association() -> GoalAssociationResolution:
    return GoalAssociationResolution(
        turn_id="turn-direct",
        new_goals=[
            SemanticGoal(
                goal_id="goal-direct",
                description="Respond naturally to the user's greeting.",
                source_text="你好",
                metadata={
                    "responsibility_kind": "vocal_output",
                    "execution_lane": "vocal",
                    "output_mode": "speech",
                    "provider_required": False,
                    "media_operation": "none",
                },
            )
        ],
        confidence=0.98,
        reason_summary="One direct conversational responsibility.",
        metadata={"status": "resolved"},
    )


def direct_composition(
    association: GoalAssociationResolution,
) -> DirectResponseComposition:
    return DirectResponseComposition(
        composition_id="composition-direct",
        goal_association_fingerprint=goal_association_fingerprint(association),
        goal_association=association,
        response_plan=ResponsePlan(
            final=ResponseStage(
                text="你好呀！",
                speech_act="greeting",
                commitment_state="completed",
                must_not_claim_completion=False,
                covers_goal_ids=["goal-direct"],
            )
        ),
        confidence=0.95,
    )


class DirectResponseComposerTests(unittest.TestCase):
    def test_model_composes_spoken_goal_without_canonical_plan(self) -> None:
        association = direct_association()
        ollama = ScriptedOllama(
            {
                "response_plan": {
                    "final": {
                        "text": "你好呀！",
                        "speech_act": "greeting",
                        "commitment_state": "completed",
                        "must_not_claim_completion": False,
                        "covers_goal_ids": ["goal-direct"],
                        "claims": [],
                        "metadata": {},
                    },
                    "progress": [],
                },
                "confidence": 0.96,
                "rationale": "A direct greeting completes the spoken goal.",
            }
        )
        request = AgentRunRequest(
            sid="sid-direct",
            text="你好",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat",
                intent="greeting",
                confidence=0.95,
                source="llm",
            ),
            context={
                "direct_goal_association_resolution": association.model_dump(
                    mode="json"
                ),
                "history": [],
                "social_attention_policy": {
                    "mode": "off",
                    "planning_enabled": False,
                    "execution_enabled": False,
                    "embodiment_independent": True,
                },
            },
            history=[],
        )

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request))

        self.assertEqual(result.status, "resolved")
        self.assertIsInstance(result.composition, DirectResponseComposition)
        self.assertEqual(result.composition.response_plan.final.text, "你好呀！")
        self.assertIn("without a planning transport stage", result.reason_summary)
        self.assertIn("six-year-old", ollama.prompts[0])
        self.assertIn("Do not invent the user's plans, schedule", ollama.prompts[0])

    def test_social_attention_context_does_not_change_direct_response_authority(self) -> None:
        association = direct_association()
        ollama = ScriptedOllama(
            {
                "response_plan": {
                    "final": {
                        "text": "我会认真照顾好家里的每一个人！",
                        "speech_act": "answer",
                        "commitment_state": "completed",
                        "must_not_claim_completion": False,
                        "covers_goal_ids": ["goal-direct"],
                        "claims": [],
                        "metadata": {},
                    },
                    "progress": [],
                },
                "lane_coordination": [],
                "confidence": 0.96,
                "rationale": "The spoken answer completes the direct goal.",
            }
        )
        request = AgentRunRequest(
            sid="sid-direct-optional-expression",
            text="你以后会怎么帮助家里人？",
            language="zh-CN",
            route_decision=RouteDecision(
                route="chat",
                intent="family_help",
                confidence=0.95,
                source="llm",
            ),
            context={
                "direct_goal_association_resolution": association.model_dump(mode="json"),
                "history": [],
                "social_attention_policy": {"mode": "on"},
                "social_attention_candidates": [
                    {"capability_id": "soridormi.nod_head", "description": "Nod once."}
                ],
            },
            history=[],
        )

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(request))

        self.assertEqual(result.status, "resolved")
        assert result.composition is not None
        self.assertEqual(
            result.composition.response_plan.final.text,
            "我会认真照顾好家里的每一个人！",
        )
        self.assertNotIn(
            "social_attention_plan",
            result.composition.model_dump(mode="json", exclude_none=True),
        )
        self.assertEqual(ollama.calls, 1)


class DirectResponseRuntimeTests(unittest.TestCase):
    def test_runtime_lets_fast_planner_complete_greeting_before_goal_association(self) -> None:
        association = direct_association()
        composition = direct_composition(association)
        advance = FastPlannerAdvance(
            turn_id="turn-direct",
            covered_responsibility_refs=["greeting"],
            immediate_vocal_activity=FastPlannerVocalActivity(
                activity_id="activity-greeting",
                role="complete_response",
                response_text="你好呀！",
                speech_act="greeting",
                source_responsibility_refs=["greeting"],
            ),
            continuations=[],
            confidence=0.98,
            reason_summary="Clear greeting can be completed immediately.",
        )
        client = DirectRuntimeClient(association, composition, advance)
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(NoopInteractionRuntime()),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"chat"}),
            ),
        )
        route = type(
            "Decision",
            (),
            {
                "route": "chat",
                "intent": "greeting",
                "language": "zh-CN",
            },
        )()

        result = asyncio.run(
            coordinator.resolve(
                object(),
                text="你好",
                sid="sid-direct",
                route_decision=route,
                context={
                    "history": [],
                    "active_goal_snapshots": [],
                    "responsibility_proposals": [
                        {
                            "local_ref": "greeting",
                            "outcome": "Socially reciprocate the user's greeting.",
                            "bindings": {},
                            "completion_requires_work": True,
                            "completion_requires_fresh_evidence": False,
                            "confidence": 0.98,
                        }
                    ],
                },
                history=[],
                language="zh-CN",
            )
        )

        self.assertEqual(result.status, "applied")
        self.assertEqual(client.calls, ["advance"])
        self.assertIsNotNone(result.fast_advance)
        self.assertIsNone(result.goal_association)
        self.assertIsNone(result.fast_plan)
        self.assertIsNone(result.terminal_plan)
        self.assertIsNone(result.response_composition)
        self.assertEqual(result.interaction_response.speech[0].text, "你好呀！")
        self.assertTrue(result.metadata["fast_planner_terminal_without_goal"])

    def test_direct_response_evidence_uses_goal_association_fingerprint(self) -> None:
        association = direct_association()
        composition = direct_composition(association)
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=DirectRuntimeClient(association, composition),
            adapter=CanonicalPlanRuntimeAdapter(NoopInteractionRuntime()),
            policy=CognitiveRuntimePolicy(
                mode="apply",
                apply_lanes=frozenset({"chat"}),
            ),
        )
        route = type(
            "Decision",
            (),
            {
                "route": "chat",
                "intent": "greeting",
                "language": "zh-CN",
            },
        )()
        result = asyncio.run(
            coordinator.resolve(
                object(),
                text="你好",
                sid="sid-direct-evidence",
                route_decision=route,
                context={"history": [], "active_goal_snapshots": []},
                history=[],
                language="zh-CN",
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cognitive.jsonl"
            CognitiveEvidenceRecorder(path).record(
                result,
                sid="sid-direct-evidence",
                text="你好",
            )
            payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

        summary = payload["composition"]
        self.assertEqual(summary["phase"], "direct")
        self.assertIsNone(summary["canonical_plan_fingerprint"])
        self.assertEqual(
            summary["goal_association_fingerprint"],
            composition.goal_association_fingerprint,
        )
