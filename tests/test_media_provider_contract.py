from __future__ import annotations

from tests.capability_runtime_test_support import submit_and_wait_terminal

import asyncio
import json
import unittest

from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.local import chromie_manifests
from agent.app.capabilities.models import CapabilityBundle, CapabilityRegistry as AgentCapabilityRegistry
from agent.app.goal_association_contract import GoalAssociationModelGoal
from agent.app.planner_contract import (
    PlannerModelOutput,
    canonical_plan_response_schema,
    validate_goal_responsibility_outcomes,
)
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.runtime.capability_runtime import (
    LocalSpeechCapabilityProvider,
    MediaPlaybackCapabilityProvider,
    CapabilityRegistry as RuntimeCapabilityRegistry,
    CapabilityRuntime,
    local_speech_definition,
    media_playback_definitions,
)
from shared.chromie_contracts.interaction import (
    MEDIA_CAPABILITY_IDS,
    MEDIA_OPERATIONS,
    InteractionResponse,
    MediaOperationEvidence,
    MediaPlaybackEvidence,
    MediaProviderDeclaration,
    VocalProviderArtifact,
    VocalProviderProvenance,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.execution_lanes import LaneCoordinationGroup
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.reflex import CancellationDirective, ReflexFilter
from shared.chromie_contracts.planner_response import PlannerResponseProjection
from shared.chromie_contracts.plan import canonical_plan_fingerprint
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage


def declaration(*operations: str) -> MediaProviderDeclaration:
    selected = list(operations or MEDIA_OPERATIONS)
    return MediaProviderDeclaration(
        provider_id="fake.media.backend",
        supported_operations=selected,
        supported_media_kinds=["music", "recording", "stream", "sound_effect"],
        persistent_playback=True,
        request_cancellation=True,
        progress_reporting=True,
        max_concurrency=2,
        mixer_policy="duck_media_during_vocal",
        ducking_gain_db=-12.0,
        duck_attack_ms=40,
        duck_release_ms=180,
        provenance=VocalProviderProvenance(
            implementation="Fake media source-test provider",
            software_source="https://example.invalid/fake-media",
            software_revision="0123456789abcdef",
            software_license_id="Apache-2.0",
            license_review_status="source_test_only",
            model_artifacts=[
                VocalProviderArtifact(
                    kind="fixture",
                    artifact_id="fake/media-fixture",
                    revision="sha256:" + "2" * 64,
                    license_id="Apache-2.0",
                )
            ],
        ),
        operation_evidence={
            operation: MediaOperationEvidence(
                level="source_test",
                artifact_refs=[f"tests/test_media_provider_contract.py#{operation}"],
                claim_summary=(
                    "Source-contract evidence for a fake provider only; this is "
                    "not target playback evidence."
                ),
            )
            for operation in selected
        },
    )


def media_goal(operation: str = "play") -> dict[str, object]:
    return {
        "goal_id": "goal-media",
        "description": f"Apply media operation {operation}.",
        "source_text": "Play a song.",
        "metadata": {
            "responsibility_kind": "executable_action",
            "execution_lane": "activity",
            "output_mode": "media_playback",
            "provider_required": True,
            "media_operation": operation,
        },
    }


def satisfaction() -> dict[str, object]:
    return {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": ["goal-media"],
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": "The exact media capability covers the Goal.",
    }


def media_plan(
    *,
    operation: str = "play",
    capability_id: str | None = None,
) -> PlannerModelOutput:
    capability_id = capability_id or MEDIA_CAPABILITY_IDS[operation]
    args: dict[str, object] = (
        {"media_ref": "fixture-song", "media_kind": "music"}
        if operation == "play"
        else {"playback_id": "playback-1"}
    )
    if operation == "seek":
        args["position_ms"] = 2500
    elif operation == "volume":
        args["volume"] = 0.4
    return PlannerModelOutput.model_validate(
        {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Apply the exact media lifecycle operation.",
            "response_text": "",
            "steps": [
                {
                    "step_id": "media-step",
                    "capability_id": capability_id,
                    "args": args,
                    "timing": "parallel",
                    "source_goal_ids": ["goal-media"],
                    "reason_summary": "Use the qualified peer media provider.",
                }
            ],
            "goal_outcomes": {
                "goal-media": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["media-step"],
                    "satisfaction": satisfaction(),
                    "rationale": "The exact media provider owns completion.",
                }
            },
            "goal_satisfaction": satisfaction(),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
    )


def _request_ids(bindings):  # type: ignore[no-untyped-def]
    return tuple(item.request_id for item in bindings)


class MediaDeclarationAndPlannerTests(unittest.TestCase):
    def test_advertised_operations_require_exact_retained_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "operation_evidence must match"):
            MediaProviderDeclaration(
                **{
                    **declaration("play").model_dump(mode="python"),
                    "supported_operations": ["play", "pause"],
                }
            )

    def test_default_catalog_retains_every_exact_capability_as_unavailable(self) -> None:
        media = next(item for item in chromie_manifests() if item.agent_id == "chromie.media")
        self.assertEqual(
            [tool.name for tool in media.tools],
            list(MEDIA_CAPABILITY_IDS.values()),
        )
        self.assertTrue(all(not tool.availability.available for tool in media.tools))

    def test_qualified_catalog_exposes_activity_contract_without_backend_name(self) -> None:
        qualified = declaration()
        registry = AgentCapabilityRegistry.from_bundles(
            [CapabilityBundle(agents=chromie_manifests(media_provider=qualified))]
        )
        catalog = CapabilityCatalog(registry)
        capability = asyncio.run(catalog.get_capability(MEDIA_CAPABILITY_IDS["play"]))

        self.assertIsNotNone(capability)
        assert capability is not None
        self.assertTrue(capability.available)
        self.assertEqual(capability.hints["execution_lane"], "activity")
        self.assertEqual(
            capability.hints["mixer_policy"],
            "duck_media_during_vocal",
        )
        self.assertNotIn(
            qualified.provider_id,
            json.dumps(capability.model_dump(mode="json"), sort_keys=True),
        )

    def test_goal_contract_keeps_playback_activity_and_singing_vocal(self) -> None:
        playback = GoalAssociationModelGoal(
            source_responsibility_refs=["playback"],
            description="Play a song.",
            output_mode="media_playback",
            media_operation="play",
        )
        singing = GoalAssociationModelGoal(
            source_responsibility_refs=["singing"],
            description="Sing a song a cappella.",
            output_mode="singing",
            media_operation="none",
        )

        self.assertEqual(playback.media_operation, "play")
        self.assertEqual(playback.execution_lane, "activity")
        self.assertEqual(singing.output_mode, "singing")
        with self.assertRaisesRegex(ValueError, "exact media_operation"):
            GoalAssociationModelGoal(
                source_responsibility_refs=["playback"],
                description="Play a song.",
                output_mode="media_playback",
            )

    def test_goal_projection_retains_exact_media_operation_for_planners(self) -> None:
        resolution = GoalAssociationResolution.model_validate(
            {"resolution_status": "resolved",
                "turn_id": "turn-media",
                "new_goals": [
                    {
                        "goal_id": "goal-media",
                        "description": "Play a song.",
                        "source_text": "Play a song.",
                        "metadata": media_goal()["metadata"],
                    }
                ],
                "confidence": 1.0,
            }
        )

        projection = resolution.prompt_projection()

        self.assertEqual(
            projection["new_goals"][0]["metadata"]["media_operation"],
            "play",
        )

    def test_planner_accepts_only_exact_operation_capability(self) -> None:
        validate_goal_responsibility_outcomes(
            media_plan(),
            authoritative_goals=[media_goal()],
        )
        with self.assertRaisesRegex(ValueError, "exact capability_id"):
            validate_goal_responsibility_outcomes(
                media_plan(capability_id="chromie.vocal.perform"),
                authoritative_goals=[media_goal()],
            )
        with self.assertRaisesRegex(ValueError, "exact capability_id"):
            validate_goal_responsibility_outcomes(
                media_plan(capability_id=MEDIA_CAPABILITY_IDS["pause"]),
                authoritative_goals=[media_goal("play")],
            )

    def test_deep_schema_fails_closed_without_exact_media_operation(self) -> None:
        unavailable = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-media"],
            allowed_capability_ids=[MEDIA_CAPABILITY_IDS["pause"]],
            provider_required_media_goal_operations={"goal-media": "play"},
        )
        outcome = unavailable["properties"]["goal_outcomes"]["properties"]["goal-media"]
        self.assertNotIn("execute", outcome["properties"]["disposition"]["enum"])


class StatefulFakeMediaBackend:
    def __init__(self) -> None:
        self.playback_id = "playback-1"
        self.state = "stopped"
        self.position_ms = 0
        self.volume = 0.7
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def handle(
        self,
        operation: str,
        args: dict[str, object],
    ) -> MediaPlaybackEvidence:
        self.calls.append((operation, args))
        if operation == "play":
            self.state = "playing"
            self.position_ms = int(args.get("start_position_ms") or 0)
            self.volume = float(args.get("volume") or self.volume)
        elif operation == "pause":
            self.state = "paused"
        elif operation == "resume":
            self.state = "playing"
        elif operation == "seek":
            self.position_ms = int(args["position_ms"])
        elif operation == "stop":
            self.state = "stopped"
        elif operation == "volume":
            self.volume = float(args["volume"])
        return MediaPlaybackEvidence(
            operation=operation,
            playback_id=self.playback_id,
            state=self.state,
            media_kind="music",
            media_ref="fixture-song",
            position_ms=self.position_ms,
            duration_ms=120000,
            volume=self.volume,
            delivery_evidence_id=f"evidence-{operation}-{len(self.calls)}",
            ducking_active=False,
        )


class MediaTrustedRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.declaration = declaration()
        self.backend = StatefulFakeMediaBackend()
        self.provider = MediaPlaybackCapabilityProvider(
            self.declaration,
            self.backend.handle,
        )
        self.registry = RuntimeCapabilityRegistry()
        self.registry.register(local_speech_definition())
        for definition in media_playback_definitions(self.declaration):
            self.registry.register(definition)
        self.runtime = CapabilityRuntime(self.registry)
        self.runtime.register_provider(
            LocalSpeechCapabilityProvider(lambda _args: {"scheduled": True, "playback_started": True})
        )
        self.runtime.register_provider(self.provider)

    async def execute_media(
        self,
        operation: str,
        args: dict[str, object],
    ):
        return await submit_and_wait_terminal(self.runtime,
            InteractionResponse(
                interaction_id=f"interaction-{operation}",
                capabilities=[
                    {
                        "request_id": f"request-{operation}",
                        "capability_id": MEDIA_CAPABILITY_IDS[operation],
                        "args": args,
                    }
                ],
            )
        )

    async def test_coordinator_registers_peer_without_replacing_speech(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": True, "playback_started": True},
            media_provider=self.provider,
        )

        self.assertEqual(
            coordinator.capability_definition(MEDIA_CAPABILITY_IDS["play"]).provider_id,
            self.declaration.provider_id,
        )
        self.assertEqual(
            coordinator.capability_definition(MEDIA_CAPABILITY_IDS["play"]).metadata["execution_lane"],
            "activity",
        )
        self.assertEqual(
            coordinator.capability_definition("chromie.speak").provider_id,
            "chromie.local_speech",
        )

    async def test_speech_over_media_materializes_exact_ducking_contract(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {"scheduled": True, "playback_started": True},
            media_provider=self.provider,
        )
        adapter = CanonicalPlanRuntimeAdapter(coordinator)
        plan = CanonicalPlan(
            plan_id="speech-over-media",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-media"],
            goal_summary="Play existing media while speaking.",
            steps=[
                {
                    "step_id": "play-media",
                    "capability_id": MEDIA_CAPABILITY_IDS["play"],
                    "args": {
                        "media_ref": "fixture-song",
                        "media_kind": "music",
                    },
                    "timing": "parallel",
                    "source_goal_ids": ["goal-media"],
                }
            ],
        )
        planner_response = PlannerResponseProjection(
            projection_id="speech-over-media-planner_response",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="I'll say this while the existing song starts.",
                    speech_act="inform",
                    commitment_state="heard",
                    must_not_claim_completion=True,
                    covers_goal_ids=["goal-media"],
                    coordination_id="speech-over-media",
                    delivery_role="activity_companion",
                )
            ),
            lane_coordination=[
                LaneCoordinationGroup(
                    coordination_id="speech-over-media",
                    lanes=["vocal", "activity"],
                    activity_step_ids=["play-media"],
                    reason_summary="Speech may overlap playback only through ducking.",
                )
            ],
        )

        response = await adapter.build_response(
            plan=plan,
            planner_response=planner_response,
            session_id="media-session",
            language="en-US",
            context={},
        )

        self.assertEqual(response.speech[0].timing, "parallel")
        self.assertEqual(
            response.speech[0].metadata["media_mixer_policy"],
            "duck_media_during_vocal",
        )
        self.assertTrue(response.speech[0].metadata["media_ducking_required"])
        self.assertEqual(response.speech[0].metadata["media_ducking_gain_db"], -12.0)
        media_request = response.capabilities[0]
        self.assertEqual(
            media_request.metadata["media_mixer_policy"],
            "duck_media_during_vocal",
        )
        self.assertTrue(media_request.metadata["parallel_with_vocal"])
        self.assertEqual(media_request.metadata["source_goal_ids"], ["goal-media"])

    async def test_body_and_exact_media_plan_needs_no_semantic_lane(self) -> None:
        plan = CanonicalPlan(
            plan_id="walk-and-media",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-walk", "goal-media"],
            goal_summary="Walk while playing existing media.",
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 5},
                    "timing": "parallel",
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "play-media",
                    "capability_id": MEDIA_CAPABILITY_IDS["play"],
                    "args": {
                        "media_ref": "fixture-song",
                        "media_kind": "music",
                    },
                    "timing": "parallel",
                    "source_goal_ids": ["goal-media"],
                },
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-media",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["play-media"],
                },
            ],
        )

        self.assertEqual(
            [step.capability_id for step in plan.steps],
            ["soridormi.walk_forward", MEDIA_CAPABILITY_IDS["play"]],
        )
        self.assertTrue(all(step.source_goal_ids for step in plan.steps))

    async def test_persistent_lifecycle_and_progress_are_correlated(self) -> None:
        cases = [
            ("play", {"media_ref": "fixture-song", "media_kind": "music"}, "playing"),
            ("pause", {"playback_id": "playback-1"}, "paused"),
            ("seek", {"playback_id": "playback-1", "position_ms": 2500}, "paused"),
            ("volume", {"playback_id": "playback-1", "volume": 0.4}, "paused"),
            ("resume", {"playback_id": "playback-1"}, "playing"),
            ("status", {"playback_id": "playback-1"}, "playing"),
            ("stop", {"playback_id": "playback-1"}, "stopped"),
        ]
        for operation, args, expected_state in cases:
            execution = await self.execute_media(operation, args)
            self.assertEqual(execution.status, "completed")
            result = execution.results[0]
            self.assertEqual(result.capability_id, MEDIA_CAPABILITY_IDS[operation])
            self.assertEqual(result.output["operation"], operation)
            self.assertEqual(result.output["playback_id"], "playback-1")
            self.assertEqual(result.output["state"], expected_state)
            self.assertEqual(
                result.output["mixer_policy"],
                "duck_media_during_vocal",
            )
        self.assertEqual(self.backend.position_ms, 2500)
        self.assertEqual(self.backend.volume, 0.4)

    async def test_provider_cannot_return_another_operation(self) -> None:
        async def wrong(
            _operation: str,
            _args: dict[str, object],
        ) -> MediaPlaybackEvidence:
            return MediaPlaybackEvidence(
                operation="pause",
                playback_id="playback-1",
                state="paused",
                media_kind="music",
                media_ref="fixture-song",
                position_ms=0,
                duration_ms=1000,
                volume=0.5,
                delivery_evidence_id="wrong-operation",
            )

        runtime = CapabilityRuntime(self.registry)
        runtime.register_provider(MediaPlaybackCapabilityProvider(self.declaration, wrong))
        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                interaction_id="wrong-operation",
                capabilities=[
                    {
                        "request_id": "play-request",
                        "capability_id": MEDIA_CAPABILITY_IDS["play"],
                        "args": {"media_ref": "fixture-song", "media_kind": "music"},
                    }
                ],
            )
        )
        self.assertEqual(execution.results[0].status, "failed")
        self.assertEqual(
            execution.results[0].reason_code,
            "invalid_media_lifecycle_evidence",
        )

    async def test_unsupported_media_kind_is_rejected_before_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "args.media_kind must be one of"):
            await self.execute_media(
                "play",
                {"media_ref": "fixture-video", "media_kind": "video"},
            )

        self.assertEqual(self.backend.calls, [])

    async def test_talking_media_and_stop_all_have_distinct_receipts(self) -> None:
        async def run_and_cancel(scope: str):
            speech_started = asyncio.Event()
            media_started = asyncio.Event()
            speech_cancelled: list[str] = []
            media_cancelled: list[str] = []

            async def speech(_args):  # type: ignore[no-untyped-def]
                speech_started.set()
                await asyncio.Event().wait()

            async def cancel_speech(request, _state):  # type: ignore[no-untyped-def]
                speech_cancelled.append(request.request_id)

            async def media(
                _operation: str,
                _args: dict[str, object],
            ) -> MediaPlaybackEvidence:
                media_started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled media provider resumed")

            async def cancel_media(request, _state):  # type: ignore[no-untyped-def]
                media_cancelled.append(request.request_id)

            provider = MediaPlaybackCapabilityProvider(
                self.declaration,
                media,
                cancel_media,
            )
            runtime = CapabilityRuntime(self.registry)
            runtime.register_provider(LocalSpeechCapabilityProvider(speech, cancel_speech))
            runtime.register_provider(provider)
            interaction_id = f"cancel-{scope}"
            task = asyncio.create_task(
                submit_and_wait_terminal(runtime,
                    InteractionResponse(
                        interaction_id=interaction_id,
                        capabilities=[
                            {
                                "request_id": "speech-request",
                                "capability_id": "chromie.speak",
                                "args": {"text": "Speaking over media."},
                                "timing": "parallel",
                            },
                            {
                                "request_id": "media-request",
                                "capability_id": MEDIA_CAPABILITY_IDS["play"],
                                "args": {
                                    "media_ref": "fixture-song",
                                    "media_kind": "music",
                                },
                                "timing": "parallel",
                            },
                        ],
                    )
                )
            )
            await asyncio.gather(speech_started.wait(), media_started.wait())
            receipt = await runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id=f"turn-{scope}",
                    requested_scope=scope,  # type: ignore[arg-type]
                    foreground_interaction_id=(
                        interaction_id if scope in {"output_only", "current_interaction"} else None
                    ),
                )
            )
            if scope == "output_only":
                followup = await runtime.cancel_scope(
                    CancellationDirective(
                        source_turn_id="turn-media-after-output",
                        requested_scope="media_output",
                    )
                )
                self.assertEqual(_request_ids(followup.selected_request_bindings), ("media-request",))
            elif scope == "media_output":
                followup = await runtime.cancel_scope(
                    CancellationDirective(
                        source_turn_id="turn-output-after-media",
                        requested_scope="output_only",
                        foreground_interaction_id=interaction_id,
                    )
                )
                self.assertEqual(_request_ids(followup.selected_request_bindings), ("speech-request",))
            execution = await task
            return receipt, execution, speech_cancelled, media_cancelled

        output, _, output_speech, output_media = await run_and_cancel("output_only")
        self.assertEqual(_request_ids(output.selected_request_bindings), ("speech-request",))
        self.assertEqual(output_speech, ["speech-request"])
        self.assertEqual(output_media, ["media-request"])

        media, _, media_speech, media_media = await run_and_cancel("media_output")
        self.assertEqual(_request_ids(media.selected_request_bindings), ("media-request",))
        self.assertEqual(media_speech, ["speech-request"])
        self.assertEqual(media_media, ["media-request"])

        all_receipt, _, all_speech, all_media = await run_and_cancel("current_interaction")
        self.assertEqual(
            set(_request_ids(all_receipt.selected_request_bindings)),
            {"speech-request", "media-request"},
        )
        self.assertEqual(all_speech, ["speech-request"])
        self.assertEqual(all_media, ["media-request"])

    async def test_reflex_has_distinct_talking_media_and_all_scopes(self) -> None:
        reflex = ReflexFilter()
        cases = [
            ("Stop talking.", "output_only"),
            ("Stop the music.", "media_output"),
            ("停止播放。", "media_output"),
            ("Stop everything.", "current_interaction"),
        ]
        for text, scope in cases:
            outcome = reflex.evaluate(text)
            self.assertEqual(outcome.cancellation_scope, scope)


if __name__ == "__main__":
    unittest.main()
