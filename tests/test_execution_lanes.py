from __future__ import annotations

import asyncio
import time
import unittest

from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.skill_runtime import (
    MockSkillProvider,
    RuntimeAuthorization,
    SkillDefinition,
    SkillRegistry,
    SkillResult,
    SkillRuntime,
    local_speech_definition,
    vocal_performance_definition,
)
from shared.chromie_contracts.interaction import (
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    VocalModeEvidence,
    VocalProviderArtifact,
    VocalProviderDeclaration,
    VocalProviderProvenance,
)
from shared.chromie_contracts.execution_lanes import LaneCoordinationGroup
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
from shared.chromie_contracts.social_attention import (
    SocialAttentionBehavior,
    SocialAttentionPlan,
)


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"completed": {"type": "boolean"}},
    "required": ["completed"],
    "additionalProperties": False,
}


def _definition(
    skill_id: str,
    *,
    provider_id: str = "body",
    group: str,
    resources: list[str],
    safety_class: str = "physical_motion",
) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        version="1.0.0",
        provider_id=provider_id,
        description=skill_id,
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        output_schema=_OUTPUT_SCHEMA,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=True,
        exclusive_group=group,
        metadata={
            "effects": [
                "social_expression" if safety_class == "low_risk_action" else "physical_motion"
            ],
            "safety_class": safety_class,
            "parallel_metadata_declared": True,
            "resource_claims": resources,
            "execution_lane": "activity",
            "provider_local_activity_compilation": skill_id.startswith("soridormi."),
        },
    )


class _GroupedBodyProvider(MockSkillProvider):
    def __init__(self, *, delay_s: float = 0.0) -> None:
        super().__init__("body", delay_s=delay_s)
        self.group_calls: list[list[str]] = []

    async def execute_group(self, items):
        self.group_calls.append([request.request_id for request, _, _ in items])
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return [
            SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="completed",
                provider_id=self.provider_id,
                output={"completed": True},
            )
            for request, definition, _ in items
        ]


class _InteractionRuntimeView:
    def __init__(self, definitions: list[SkillDefinition]) -> None:
        self.definitions = {item.skill_id: item for item in definitions}

    async def ensure_skill_definitions(self, skill_ids: list[str]) -> None:
        for skill_id in skill_ids:
            if skill_id not in self.definitions:
                raise ValueError(skill_id)

    def skill_definition(self, skill_id: str) -> SkillDefinition:
        return self.definitions[skill_id]


class ExecutionLaneContractTests(unittest.TestCase):
    def _plan(self, *, timing: str = "parallel") -> CanonicalPlan:
        return CanonicalPlan(
            plan_id="lane-plan",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=0.95,
            goal_ids=["goal-walk"],
            goal_summary="walk while speaking and blinking",
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {},
                    "timing": timing,
                    "source_goal_ids": ["goal-walk"],
                }
            ],
        )

    def _composition(self, plan: CanonicalPlan) -> CoordinatedResponsePlan:
        return CoordinatedResponsePlan(
            composition_id="lane-composition",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="我一边走一边和你说话。",
                    speech_act="inform",
                    commitment_state="heard",
                    must_not_claim_completion=True,
                    covers_goal_ids=["goal-walk"],
                    coordination_id="together-1",
                    delivery_role="activity_companion",
                )
            ),
            social_attention_plan=SocialAttentionPlan(
                decision="express",
                behaviors=[
                    SocialAttentionBehavior(
                        capability_id="soridormi.blink_eyes",
                        args={},
                        timing="parallel",
                        social_function="engagement",
                        coordination_id="together-1",
                    )
                ],
                metadata={"auxiliary_social_attention": True},
            ),
            lane_coordination=[
                LaneCoordinationGroup(
                    coordination_id="together-1",
                    lanes=["speaking", "activity", "social_attention"],
                    activity_step_ids=["walk"],
                    reason_summary="The user requested overlapping behavior.",
                )
            ],
            metadata={
                "social_attention_policy": {
                    "mode": "on",
                    "execution_enabled": True,
                }
            },
        )

    def test_three_lane_contract_accepts_explicit_parallel_members(self) -> None:
        composition = self._composition(self._plan())

        self.assertEqual(
            composition.lane_coordination[0].lanes,
            ["speaking", "activity", "social_attention"],
        )

    def test_three_lane_contract_rejects_serial_activity_step(self) -> None:
        with self.assertRaisesRegex(ValueError, "timing=parallel"):
            self._composition(self._plan(timing="sequential"))

    def test_confirmation_speech_cannot_overlap_activity(self) -> None:
        plan = self._plan()
        with self.assertRaisesRegex(ValueError, "cannot overlap"):
            CoordinatedResponsePlan(
                composition_id="confirmation-composition",
                canonical_plan_id=plan.plan_id,
                canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
                canonical_plan=plan,
                response_plan=ResponsePlan(
                    immediate=ResponseStage(
                        text="现在开始吗？",
                        speech_act="ask_confirmation",
                        commitment_state="waiting_for_user",
                        must_not_claim_completion=True,
                        covers_goal_ids=["goal-walk"],
                        coordination_id="together-1",
                        delivery_role="activity_companion",
                    )
                ),
                social_attention_plan=SocialAttentionPlan(
                    decision="none",
                    metadata={"auxiliary_social_attention": True},
                ),
                lane_coordination=[
                    LaneCoordinationGroup(
                        coordination_id="together-1",
                        lanes=["speaking", "activity"],
                        activity_step_ids=["walk"],
                    )
                ],
            )


class ExecutionLaneRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def _response(self):
        walk = _definition(
            "soridormi.walk_forward",
            group="soridormi.base_motion",
            resources=["base_motion", "balance_control"],
        )
        blink = _definition(
            "soridormi.blink_eyes",
            group="soridormi.eye_expression",
            resources=["eye_expression"],
            safety_class="low_risk_action",
        )
        view = _InteractionRuntimeView([walk, blink])
        adapter = CanonicalPlanRuntimeAdapter(view, social_attention_mode="on")
        contract = ExecutionLaneContractTests()
        plan = contract._plan()
        composition = contract._composition(plan)
        return (
            await adapter.build_response(
                plan=plan,
                composition=composition,
                session_id="lane-session",
                language="zh-CN",
                context={},
            ),
            walk,
            blink,
        )

    async def test_adapter_materializes_three_distinct_lane_members(self) -> None:
        response, _, _ = await self._response()

        self.assertEqual(response.speech[0].timing, "parallel")
        self.assertFalse(response.speech[0].metadata["wait_for_playback_start"])
        self.assertEqual(response.speech[0].metadata["execution_lane"], "speaking")
        self.assertEqual(response.speech[0].metadata["coordination_id"], "together-1")

        by_id = {item.skill_id: item for item in response.skills}
        self.assertEqual(
            by_id["soridormi.walk_forward"].metadata["execution_lane"],
            "activity",
        )
        self.assertEqual(
            by_id["soridormi.walk_forward"].metadata["coordination_id"],
            "together-1",
        )
        self.assertEqual(
            by_id["soridormi.blink_eyes"].metadata["execution_lane"],
            "social_attention",
        )
        self.assertEqual(
            by_id["soridormi.blink_eyes"].metadata["coordination_id"],
            "together-1",
        )
        self.assertEqual(len(response.metadata["lane_coordination_groups"]), 1)

    async def test_adapter_rejects_cross_lane_activity_without_provider_metadata(self) -> None:
        walk = _definition(
            "soridormi.walk_forward",
            group="soridormi.base_motion",
            resources=["base_motion"],
        )
        walk.metadata.pop("parallel_metadata_declared", None)
        blink = _definition(
            "soridormi.blink_eyes",
            group="soridormi.eye_expression",
            resources=["eye_expression"],
            safety_class="low_risk_action",
        )
        adapter = CanonicalPlanRuntimeAdapter(
            _InteractionRuntimeView([walk, blink]),
            social_attention_mode="on",
        )
        contract = ExecutionLaneContractTests()
        plan = contract._plan()

        with self.assertRaisesRegex(ValueError, "lacks explicit parallel metadata"):
            await adapter.build_response(
                plan=plan,
                composition=contract._composition(plan),
                session_id="lane-session",
                language="zh-CN",
                context={},
            )

    async def test_vocal_provider_step_remains_speaking_when_parallel_with_activity(self) -> None:
        vocal = vocal_performance_definition(
            VocalProviderDeclaration(
                provider_id="fake.vocal.lane-test",
                supported_modes=["singing"],
                native_text_streaming=True,
                native_audio_streaming=True,
                request_cancellation=True,
                timing_mark_types=[],
                sample_formats=["pcm_s16le"],
                sample_rates=[24000],
                max_concurrency=1,
                provenance=VocalProviderProvenance(
                    implementation="Fake lane-test provider",
                    software_source="https://example.invalid/vocal-lane",
                    software_revision="0123456789abcdef",
                    software_license_id="Apache-2.0",
                    license_review_status="source_test_only",
                    model_artifacts=[
                        VocalProviderArtifact(
                            kind="fixture",
                            artifact_id="fake/vocal-lane",
                            revision="sha256:" + "2" * 64,
                            license_id="Apache-2.0",
                        )
                    ],
                ),
                mode_evidence={
                    "singing": VocalModeEvidence(
                        level="source_test",
                        artifact_refs=["tests/test_execution_lanes.py#vocal-provider-step"],
                        claim_summary="Fake source test only.",
                    )
                },
            )
        )
        walk = _definition(
            "soridormi.walk_forward",
            group="soridormi.base_motion",
            resources=["base_motion", "balance_control"],
        )
        plan = CanonicalPlan(
            plan_id="vocal-activity-lane-plan",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-sing", "goal-walk"],
            goal_summary="Sing while walking.",
            steps=[
                {
                    "step_id": "sing",
                    "capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
                    "args": {"text": "Hello.", "mode": "singing"},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-sing"],
                },
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-walk"],
                },
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-sing",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["sing"],
                },
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
            ],
        )
        composition = CoordinatedResponsePlan(
            composition_id="vocal-activity-lane-composition",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="I can do those together.",
                    speech_act="inform",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=plan.goal_ids,
                )
            ),
            lane_coordination=[
                LaneCoordinationGroup(
                    coordination_id="vocal-with-walk",
                    lanes=["speaking", "activity"],
                    speaking_step_ids=["sing"],
                    activity_step_ids=["walk"],
                )
            ],
            confidence=1.0,
        )

        response = await CanonicalPlanRuntimeAdapter(
            _InteractionRuntimeView([vocal, walk])
        ).build_response(
            plan=plan,
            composition=composition,
            session_id="vocal-activity-lane-session",
            language="en-US",
            context={},
        )

        by_id = {item.capability_id: item for item in response.skills}
        self.assertEqual(
            by_id[VOCAL_PERFORMANCE_CAPABILITY_ID].metadata["execution_lane"],
            "speaking",
        )
        self.assertTrue(by_id[VOCAL_PERFORMANCE_CAPABILITY_ID].metadata["parallel_with_activity"])
        self.assertEqual(
            by_id["soridormi.walk_forward"].metadata["execution_lane"],
            "activity",
        )
        self.assertTrue(by_id["soridormi.walk_forward"].metadata["parallel_with_speech"])

    async def test_skill_runtime_overlaps_speech_walk_and_blink(self) -> None:
        response, walk, blink = await self._response()
        registry = SkillRegistry()
        registry.register(local_speech_definition())
        registry.register(walk)
        registry.register(blink)
        runtime = SkillRuntime(registry, max_concurrency=3)
        speech_provider = MockSkillProvider(
            local_speech_definition().provider_id,
            delay_s=0.08,
        )
        body_provider = _GroupedBodyProvider(delay_s=0.08)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)

        started = time.perf_counter()
        result = await runtime.execute(
            response,
            authorization=RuntimeAuthorization(),
        )
        elapsed = time.perf_counter() - started

        self.assertEqual(result.status, "completed")
        self.assertLess(elapsed, 0.20)
        self.assertEqual(len(speech_provider.calls), 1)
        self.assertEqual(body_provider.calls, [])
        self.assertEqual(
            body_provider.group_calls,
            [
                [
                    response.skills[0].request_id,
                    response.skills[1].request_id,
                ]
            ],
        )
        self.assertEqual(
            speech_provider.calls[0].metadata["execution_lane"],
            "speaking",
        )
        self.assertEqual(
            speech_provider.calls[0].metadata["coordination_id"],
            "together-1",
        )

    def test_soridormi_import_preserves_provider_body_lanes(self) -> None:
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "walk_forward",
                    "concurrency": {
                        "ability_class": "locomotion_whole_body",
                        "control_coupling": "primary_body_controller",
                        "write_resources": ["body.primary_motion"],
                    },
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                {
                    "skill_id": "blink_eyes",
                    "concurrency": {
                        "ability_class": "subtle_expression",
                        "control_coupling": "independent_output",
                        "write_resources": ["visual.eyes"],
                    },
                    "parameters_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            ]
        )

        walk = registry.get("soridormi.walk_forward")
        blink = registry.get("soridormi.blink_eyes")
        self.assertTrue(walk.can_run_parallel)
        self.assertTrue(blink.can_run_parallel)
        self.assertEqual(walk.metadata["body_lane"], "locomotion")
        self.assertEqual(blink.metadata["body_lane"], "subtle_expression")
        self.assertEqual(walk.metadata["resource_claims"], ["body.primary_motion"])
        self.assertEqual(blink.metadata["resource_claims"], ["visual.eyes"])
        self.assertNotEqual(walk.exclusive_group, blink.exclusive_group)


if __name__ == "__main__":
    unittest.main()
