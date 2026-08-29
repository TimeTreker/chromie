from __future__ import annotations

from tests.capability_runtime_test_support import submit_and_wait_terminal

import asyncio
import time
import unittest

from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.capability_runtime import (
    MockCapabilityProvider,
    RuntimeAuthorization,
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityResult,
    CapabilityRuntime,
    local_speech_definition,
    vocal_performance_definition,
)
from orchestrator.runtime.soridormi_capability_provider import (
    import_soridormi_capability_catalog,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    VocalModeEvidence,
    VocalProviderArtifact,
    VocalProviderDeclaration,
    VocalProviderProvenance,
)
from shared.chromie_contracts.execution_lanes import LaneCoordinationGroup
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.planner_response import PlannerResponseProjection
from shared.chromie_contracts.plan import canonical_plan_fingerprint
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage


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
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=skill_id,
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


class _GroupedBodyProvider(MockCapabilityProvider):
    def __init__(self, *, delay_s: float = 0.0) -> None:
        super().__init__("body", delay_s=delay_s)
        self.group_calls: list[list[str]] = []

    async def execute_group(self, items):
        self.group_calls.append([request.request_id for request, _, _ in items])
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return [
            CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="completed",
                provider_id=self.provider_id,
                output={"completed": True},
            )
            for request, definition, _ in items
        ]


class _InteractionRuntimeView:
    def __init__(self, definitions: list[CapabilityDefinition]) -> None:
        self.definitions = {item.capability_id: item for item in definitions}

    async def ensure_capability_definitions(self, capability_ids: list[str]) -> None:
        for skill_id in capability_ids:
            if skill_id not in self.definitions:
                raise ValueError(skill_id)

    def capability_definition(self, skill_id: str) -> CapabilityDefinition:
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

    def _planner_response(self, plan: CanonicalPlan) -> PlannerResponseProjection:
        return PlannerResponseProjection(
            projection_id="lane-planner_response",
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
            lane_coordination=[
                LaneCoordinationGroup(
                    coordination_id="together-1",
                    lanes=["vocal", "activity"],
                    activity_step_ids=["walk"],
                    reason_summary="The user requested overlapping behavior.",
                )
            ],
        )

    def test_vocal_group_rejects_two_personal_voice_provider_steps(self) -> None:
        with self.assertRaisesRegex(ValueError, "at most one personal-voice"):
            LaneCoordinationGroup(
                coordination_id="two-mouths",
                lanes=["vocal", "activity"],
                vocal_step_ids=["sing", "hum"],
                activity_step_ids=["walk"],
            )

    def test_two_execution_lane_contract_accepts_explicit_parallel_members(self) -> None:
        planner_response = self._planner_response(self._plan())

        self.assertEqual(
            planner_response.lane_coordination[0].lanes,
            ["vocal", "activity"],
        )

    def test_two_execution_lane_contract_rejects_serial_activity_step(self) -> None:
        with self.assertRaisesRegex(ValueError, "timing=parallel"):
            self._planner_response(self._plan(timing="sequential"))

    def test_social_attention_is_not_an_execution_lane(self) -> None:
        with self.assertRaises(ValueError):
            LaneCoordinationGroup(
                coordination_id="not-a-lane",
                lanes=["vocal", "social_attention"],
            )

    def test_confirmation_speech_cannot_overlap_activity(self) -> None:
        plan = self._plan()
        with self.assertRaisesRegex(ValueError, "cannot overlap"):
            PlannerResponseProjection(
                projection_id="confirmation-planner_response",
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
                lane_coordination=[
                    LaneCoordinationGroup(
                        coordination_id="together-1",
                        lanes=["vocal", "activity"],
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
        view = _InteractionRuntimeView([walk])
        adapter = CanonicalPlanRuntimeAdapter(view)
        contract = ExecutionLaneContractTests()
        plan = contract._plan()
        planner_response = contract._planner_response(plan)
        return (
            await adapter.build_response(
                plan=plan,
                planner_response=planner_response,
                session_id="lane-session",
                language="zh-CN",
                context={},
            ),
            walk,
        )

    async def test_adapter_materializes_only_primary_execution_lanes(self) -> None:
        response, _ = await self._response()

        self.assertEqual(response.speech[0].timing, "parallel")
        self.assertFalse(response.speech[0].metadata["wait_for_playback_start"])
        self.assertEqual(response.speech[0].metadata["execution_lane"], "vocal")
        self.assertEqual(response.speech[0].metadata["coordination_id"], "together-1")

        by_id = {item.capability_id: item for item in response.capabilities}
        self.assertEqual(set(by_id), {"soridormi.walk_forward"})
        self.assertEqual(
            by_id["soridormi.walk_forward"].metadata["execution_lane"],
            "activity",
        )
        self.assertEqual(
            by_id["soridormi.walk_forward"].metadata["coordination_id"],
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
        adapter = CanonicalPlanRuntimeAdapter(
            _InteractionRuntimeView([walk]),
        )
        contract = ExecutionLaneContractTests()
        plan = contract._plan()

        with self.assertRaisesRegex(ValueError, "lacks explicit parallel metadata"):
            await adapter.build_response(
                plan=plan,
                planner_response=contract._planner_response(plan),
                session_id="lane-session",
                language="zh-CN",
                context={},
            )

    async def test_vocal_provider_step_remains_vocal_when_parallel_with_activity(self) -> None:
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
        planner_response = PlannerResponseProjection(
            projection_id="vocal-activity-lane-planner_response",
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
                    lanes=["vocal", "activity"],
                    vocal_step_ids=["sing"],
                    activity_step_ids=["walk"],
                )
            ],
            confidence=1.0,
        )

        response = await CanonicalPlanRuntimeAdapter(
            _InteractionRuntimeView([vocal, walk])
        ).build_response(
            plan=plan,
            planner_response=planner_response,
            session_id="vocal-activity-lane-session",
            language="en-US",
            context={},
        )

        by_id = {item.capability_id: item for item in response.capabilities}
        self.assertEqual(
            by_id[VOCAL_PERFORMANCE_CAPABILITY_ID].metadata["execution_lane"],
            "vocal",
        )
        self.assertTrue(by_id[VOCAL_PERFORMANCE_CAPABILITY_ID].metadata["parallel_with_activity"])
        self.assertEqual(
            by_id["soridormi.walk_forward"].metadata["execution_lane"],
            "activity",
        )
        self.assertTrue(by_id["soridormi.walk_forward"].metadata["parallel_with_vocal"])

    async def test_capability_runtime_overlaps_speech_and_walk(self) -> None:
        response, walk = await self._response()
        registry = CapabilityRegistry()
        registry.register(local_speech_definition())
        registry.register(walk)
        runtime = CapabilityRuntime(registry, max_concurrency=3)
        speech_provider = MockCapabilityProvider(
            local_speech_definition().provider_id,
            delay_s=0.08,
        )
        body_provider = _GroupedBodyProvider(delay_s=0.08)
        runtime.register_provider(speech_provider)
        runtime.register_provider(body_provider)

        started = time.perf_counter()
        result = await submit_and_wait_terminal(runtime,
            response,
            authorization=RuntimeAuthorization(),
        )
        elapsed = time.perf_counter() - started

        self.assertEqual(result.status, "completed")
        self.assertLess(elapsed, 0.20)
        self.assertEqual(len(speech_provider.calls), 1)
        self.assertEqual(
            speech_provider.calls[0].metadata["execution_lane"],
            "vocal",
        )
        self.assertEqual(
            speech_provider.calls[0].metadata["coordination_id"],
            "together-1",
        )
        self.assertEqual(len(response.capabilities), 1)
        self.assertEqual(response.capabilities[0].capability_id, "soridormi.walk_forward")

    async def test_parallel_runtime_rejects_two_personal_voice_owners(self) -> None:
        declaration = VocalProviderDeclaration(
            provider_id="fake.vocal.parallel-conflict",
            supported_modes=["singing"],
            native_text_streaming=True,
            native_audio_streaming=True,
            request_cancellation=True,
            timing_mark_types=[],
            sample_formats=["pcm_s16le"],
            sample_rates=[24000],
            max_concurrency=1,
            provenance=VocalProviderProvenance(
                implementation="Fake parallel-conflict provider",
                software_source="https://example.invalid/vocal-conflict",
                software_revision="0123456789abcdef",
                software_license_id="Apache-2.0",
                license_review_status="source_test_only",
                model_artifacts=[
                    VocalProviderArtifact(
                        kind="fixture",
                        artifact_id="fake/vocal-conflict",
                        revision="sha256:" + "3" * 64,
                        license_id="Apache-2.0",
                    )
                ],
            ),
            mode_evidence={
                "singing": VocalModeEvidence(
                    level="source_test",
                    artifact_refs=["tests/test_execution_lanes.py#parallel-vocal-conflict"],
                    claim_summary="Fake source test only.",
                )
            },
        )
        speech_definition = local_speech_definition()
        vocal_definition = vocal_performance_definition(declaration)
        registry = CapabilityRegistry()
        registry.register(speech_definition)
        registry.register(vocal_definition)
        runtime = CapabilityRuntime(registry, max_concurrency=2)
        runtime.register_provider(MockCapabilityProvider(speech_definition.provider_id))
        runtime.register_provider(MockCapabilityProvider(vocal_definition.provider_id))
        response = InteractionResponse(
            interaction_id="two-personal-voices",
            speech=[
                InteractionSpeech(
                    text="I am talking.",
                    timing="parallel",
                )
            ],
            capabilities=[
                CapabilityRequest(
                    request_id="sing-now",
                    capability_id=VOCAL_PERFORMANCE_CAPABILITY_ID,
                    args={"text": "La", "mode": "singing"},
                    timing="parallel",
                )
            ],
        )

        with self.assertRaisesRegex(ValueError, "multiple chromie.voice owners"):
            await submit_and_wait_terminal(runtime, response)

    def test_soridormi_import_preserves_provider_body_lanes(self) -> None:
        registry = CapabilityRegistry()
        import_soridormi_capability_catalog(registry,
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
