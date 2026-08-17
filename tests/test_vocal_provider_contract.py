from __future__ import annotations

from tests.capability_runtime_test_support import submit_and_wait_terminal

import asyncio
import json
import unittest

from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.local import chromie_manifests
from agent.app.capabilities.models import CapabilityBundle, CapabilityRegistry as AgentCapabilityRegistry
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.planner_contract import (
    PlannerModelOutput,
    canonical_plan_response_schema,
    validate_goal_responsibility_outcomes,
)
from tests.cognitive_work_test_support import cognitive_work_request
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.cognitive_turn_closure import CognitiveTurnClosure
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.runtime.capability_runtime import (
    LocalSpeechCapabilityProvider,
    CapabilityRegistry as RuntimeCapabilityRegistry,
    CapabilityRuntime,
    VocalPerformanceCapabilityProvider,
    local_speech_definition,
    vocal_performance_definition,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    VocalModeEvidence,
    VocalPerformanceDelivery,
    VocalProviderArtifact,
    VocalProviderDeclaration,
    VocalProviderProvenance,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.reflex import CancellationDirective
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage


def declaration(*modes: str) -> VocalProviderDeclaration:
    return VocalProviderDeclaration(
        provider_id="fake.vocal.backend",
        supported_modes=list(modes),
        native_text_streaming=True,
        native_audio_streaming=True,
        request_cancellation=True,
        timing_mark_types=["word"],
        sample_formats=["pcm_s16le"],
        sample_rates=[24000],
        max_concurrency=1,
        provenance=VocalProviderProvenance(
            implementation="Fake vocal source-test provider",
            software_source="https://example.invalid/fake-vocal",
            software_revision="0123456789abcdef",
            software_license_id="Apache-2.0",
            license_review_status="source_test_only",
            model_artifacts=[
                VocalProviderArtifact(
                    kind="fixture_weights",
                    artifact_id="fake/vocal-fixture",
                    revision="sha256:" + "1" * 64,
                    license_id="Apache-2.0",
                )
            ],
        ),
        mode_evidence={
            mode: VocalModeEvidence(
                level="source_test",
                artifact_refs=[f"tests/test_vocal_provider_contract.py#{mode}"],
                claim_summary=(
                    "Source-contract evidence for a fake provider only; this is "
                    "not target audio evidence."
                ),
            )
            for mode in modes
        },
    )


def exact_satisfaction(goal_id: str) -> dict[str, object]:
    return {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": [goal_id],
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": "The exact qualified provider step covers this Goal.",
    }


def vocal_goal(mode: str = "singing") -> dict[str, object]:
    return {
        "goal_id": "goal-vocal",
        "description": "Perform the authored vocal content.",
        "source_text": "Sing a short greeting.",
        "metadata": {
            "responsibility_kind": "vocal_output",
            "execution_lane": "vocal",
            "output_mode": mode,
            "provider_required": True,
        },
    }


def vocal_model_output(
    *, mode: str = "singing", capability_id: str | None = None
) -> PlannerModelOutput:
    capability_id = capability_id or VOCAL_PERFORMANCE_CAPABILITY_ID
    return PlannerModelOutput.model_validate(
        {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 1.0,
            "goal_summary": "Perform the requested vocal content.",
            "response_text": "",
            "steps": [
                {
                    "step_id": "vocal-step",
                    "capability_id": capability_id,
                    "args": {"text": "Hello from Chromie.", "mode": mode},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-vocal"],
                    "reason_summary": "Use the exact qualified vocal mode.",
                }
            ],
            "goal_outcomes": {
                "goal-vocal": {
                    "disposition": "execute",
                    "coverage": "complete",
                    "response_text": "",
                    "unresolved": [],
                    "step_ids": ["vocal-step"],
                    "satisfaction": exact_satisfaction("goal-vocal"),
                    "rationale": "The exact vocal provider owns completion.",
                }
            },
            "goal_satisfaction": exact_satisfaction("goal-vocal"),
            "plan_relation": "exact",
            "user_confirmation_required": False,
        }
    )


def _request_ids(bindings):  # type: ignore[no-untyped-def]
    return tuple(item.request_id for item in bindings)


class ScriptedModel:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def generate(self, prompt: str, **kwargs: object) -> dict[str, object]:
        self.calls.append((prompt, dict(kwargs)))
        return self.response


class RuntimeDefinitionView:
    def __init__(self, definition) -> None:  # type: ignore[no-untyped-def]
        self.definition = definition

    async def ensure_capability_definitions(self, capability_ids: list[str]) -> None:
        if capability_ids != [VOCAL_PERFORMANCE_CAPABILITY_ID]:
            raise ValueError(capability_ids)

    def capability_definition(self, skill_id: str):  # type: ignore[no-untyped-def]
        if skill_id != VOCAL_PERFORMANCE_CAPABILITY_ID:
            raise ValueError(skill_id)
        return self.definition


class VocalDeclarationAndPlannerTests(unittest.TestCase):
    def test_advertised_modes_require_retained_mode_specific_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "mode_evidence must match"):
            VocalProviderDeclaration(
                **{
                    **declaration("recitation").model_dump(mode="python"),
                    "supported_modes": ["recitation", "singing"],
                }
            )

    def test_personal_voice_definitions_share_one_exclusive_resource(self) -> None:
        speech = local_speech_definition()
        vocal = vocal_performance_definition(declaration("singing"))

        self.assertEqual(speech.exclusive_group, "chromie.voice")
        self.assertEqual(vocal.exclusive_group, "chromie.voice")
        self.assertEqual(speech.metadata["resource_claims"], ["chromie.voice"])
        self.assertEqual(vocal.metadata["resource_claims"], ["chromie.voice"])
        self.assertEqual(speech.metadata["execution_lane"], "vocal")
        self.assertEqual(vocal.metadata["execution_lane"], "vocal")

    def test_default_catalog_retains_contract_without_advertising_a_mode(self) -> None:
        speech_manifest = next(
            item for item in chromie_manifests() if item.agent_id == "chromie.speech"
        )
        tool = next(
            item for item in speech_manifest.tools if item.name == VOCAL_PERFORMANCE_CAPABILITY_ID
        )

        self.assertFalse(tool.availability.available)
        self.assertEqual(tool.availability.modes, [])
        self.assertIn("no qualified vocal provider", tool.availability.reason or "")

    def test_qualified_catalog_exposes_exact_identity_without_backend_name(self) -> None:
        qualified = declaration("singing")
        registry = AgentCapabilityRegistry.from_bundles(
            [CapabilityBundle(agents=chromie_manifests(vocal_provider=qualified))]
        )
        catalog = CapabilityCatalog(registry)
        capability = asyncio.run(catalog.get_capability(VOCAL_PERFORMANCE_CAPABILITY_ID))

        self.assertIsNotNone(capability)
        assert capability is not None
        self.assertTrue(capability.available)
        self.assertTrue(capability.interaction_executable)
        self.assertEqual(
            capability.input_schema["properties"]["mode"]["enum"],
            ["singing"],
        )
        self.assertNotIn(
            qualified.provider_id,
            json.dumps(capability.model_dump(mode="json"), sort_keys=True),
        )

    def test_planner_accepts_only_exact_capability_and_goal_mode(self) -> None:
        validate_goal_responsibility_outcomes(
            vocal_model_output(),
            authoritative_goals=[vocal_goal()],
        )
        with self.assertRaisesRegex(ValueError, "exact capability_id"):
            validate_goal_responsibility_outcomes(
                vocal_model_output(capability_id="chromie.weather.lookup"),
                authoritative_goals=[vocal_goal()],
            )
        with self.assertRaisesRegex(ValueError, "exactly match"):
            validate_goal_responsibility_outcomes(
                vocal_model_output(mode="recitation"),
                authoritative_goals=[vocal_goal(mode="singing")],
            )

    def test_deep_planner_proposes_exact_qualified_vocal_step(self) -> None:
        qualified = declaration("singing")
        registry = AgentCapabilityRegistry.from_bundles(
            [CapabilityBundle(agents=chromie_manifests(vocal_provider=qualified))]
        )
        catalog = CapabilityCatalog(registry)
        raw = vocal_model_output().model_dump(mode="json")
        model = ScriptedModel(raw)
        request = cognitive_work_request(
            sid="vocal-planner-source-test",
            text="Sing a short greeting.",
            language="en-US",
            context={
                "active_goal_snapshots": [],
                "goal_association_resolution": {
                    "associations": [],
                    "new_goals": [vocal_goal()],
                },
            },
            history=[],
        )

        plan = asyncio.run(DeepPlannerResolver(model, catalog, max_contract_repairs=0).resolve(request))

        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(
            plan.steps[0].capability_id,
            VOCAL_PERFORMANCE_CAPABILITY_ID,
        )
        self.assertEqual(plan.steps[0].args["mode"], "singing")
        schema = model.calls[0][1]["response_format"]
        vocal_outcome = schema["properties"]["goal_outcomes"]["properties"]["goal-vocal"]
        self.assertIn(
            "execute",
            vocal_outcome["properties"]["disposition"]["enum"],
        )

    def test_deep_schema_keeps_execution_closed_without_qualified_capability(self) -> None:
        schema = canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=["goal-vocal"],
            allowed_capability_ids=[],
            provider_required_vocal_goal_ids=["goal-vocal"],
        )
        vocal_outcome = schema["properties"]["goal_outcomes"]["properties"]["goal-vocal"]
        self.assertEqual(
            vocal_outcome["properties"]["disposition"]["enum"],
            ["clarify", "unavailable", "refused"],
        )
        self.assertEqual(vocal_outcome["properties"]["step_ids"]["maxItems"], 0)

    def test_provider_vocal_goal_cannot_take_direct_chat_shortcut(self) -> None:
        provider_association = GoalAssociationResolution.model_validate(
            {"resolution_status": "resolved",
                "turn_id": "turn-provider-vocal",
                "new_goals": [vocal_goal(mode="recitation")],
                "confidence": 1.0,
                "metadata": {"status": "resolved"},
            }
        )
        ordinary_goal = {
            **vocal_goal(mode="speech"),
            "metadata": {
                **vocal_goal(mode="speech")["metadata"],
                "provider_required": False,
            },
        }
        ordinary_association = GoalAssociationResolution.model_validate(
            {"resolution_status": "resolved",
                "turn_id": "turn-ordinary-speech",
                "new_goals": [ordinary_goal],
                "confidence": 1.0,
                "metadata": {"status": "resolved"},
            }
        )

        self.assertFalse(
            GoalDrivenRuntimeCoordinator._is_direct_spoken_association(
                provider_association
            )
        )
        self.assertTrue(
            GoalDrivenRuntimeCoordinator._is_direct_spoken_association(
                ordinary_association
            )
        )


class VocalTrustedRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.declaration = declaration("recitation")
        self.calls: list[dict[str, object]] = []

        async def handler(args: dict[str, object]) -> VocalPerformanceDelivery:
            self.calls.append(args)
            return VocalPerformanceDelivery(
                delivered_mode="recitation",
                delivery_evidence_id="delivery-recitation-1",
                playback_started=True,
                playback_completed=True,
                audio_duration_ms=850.0,
                sample_format="pcm_s16le",
                sample_rate=24000,
                timing_marks_emitted=["word"],
            )

        self.provider = VocalPerformanceCapabilityProvider(
            self.declaration,
            handler,
        )
        self.definition = vocal_performance_definition(self.declaration)
        self.registry = RuntimeCapabilityRegistry()
        self.registry.register(local_speech_definition())
        self.registry.register(self.definition)
        self.runtime = CapabilityRuntime(self.registry)
        self.runtime.register_provider(
            LocalSpeechCapabilityProvider(
                lambda _args: {
                    "scheduled": True,
                    "playback_started": True,
                    "voice_released": True,
                    "spoken": True,
                }
            )
        )
        self.runtime.register_provider(self.provider)

    async def test_unreleased_speech_blocks_following_provider_vocal(self) -> None:
        registry = RuntimeCapabilityRegistry()
        speech_definition = local_speech_definition()
        registry.register(speech_definition)
        registry.register(self.definition)
        runtime = CapabilityRuntime(registry)
        runtime.register_provider(
            LocalSpeechCapabilityProvider(
                lambda _args: {
                    "scheduled": True,
                    "playback_started": True,
                    "voice_released": False,
                    "spoken": True,
                }
            )
        )
        runtime.register_provider(self.provider)
        response = InteractionResponse(
            interaction_id="speech-before-vocal-release-barrier",
            speech=[
                InteractionSpeech(
                    text="I will say this first.",
                    timing="sequential",
                )
            ],
            capabilities=[
                CapabilityRequest(
                    request_id="recite-after-speech",
                    capability_id=VOCAL_PERFORMANCE_CAPABILITY_ID,
                    args={"text": "Hello from Chromie.", "mode": "recitation"},
                    timing="sequential",
                )
            ],
        )

        result = await submit_and_wait_terminal(runtime, response)

        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0].reason_code, "personal_voice_not_released")
        self.assertEqual(self.calls, [])

    async def test_coordinator_registers_qualified_peer_without_replacing_speech(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda _args: {
                "scheduled": True,
                "playback_started": True,
                "voice_released": True,
                "spoken": True,
            },
            vocal_provider=self.provider,
        )

        self.assertEqual(
            coordinator.capability_definition(VOCAL_PERFORMANCE_CAPABILITY_ID).provider_id,
            self.declaration.provider_id,
        )
        self.assertEqual(
            coordinator.capability_definition("chromie.speak").provider_id,
            "chromie.local_speech",
        )
        self.assertEqual(
            coordinator.capability_definition("chromie.speak").metadata["execution_lane"],
            "vocal",
        )

    async def test_exact_identity_survives_authorization_execution_and_evidence(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-vocal-evidence",
            planner_tier="deep",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=["goal-vocal"],
            goal_summary="Recite the greeting.",
            steps=[
                {
                    "step_id": "vocal-step",
                    "capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
                    "args": {"text": "Hello from Chromie.", "mode": "recitation"},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-vocal"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-vocal",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["vocal-step"],
                }
            ],
        )
        composition = CoordinatedResponsePlan(
            composition_id="composition-vocal-evidence",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_plan=plan,
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="I can recite that.",
                    speech_act="inform",
                    commitment_state="evaluating",
                    must_not_claim_completion=True,
                    covers_goal_ids=["goal-vocal"],
                )
            ),
            confidence=1.0,
        )
        view = RuntimeDefinitionView(self.definition)
        response = await CanonicalPlanRuntimeAdapter(view).build_response(
            plan=plan,
            composition=composition,
            session_id="session-vocal-evidence",
            language="en-US",
        )

        self.assertEqual(response.capabilities[0].capability_id, VOCAL_PERFORMANCE_CAPABILITY_ID)
        self.assertEqual(response.capabilities[0].metadata["execution_lane"], "vocal")
        execution = await submit_and_wait_terminal(self.runtime, response)
        self.assertEqual(execution.status, "completed")
        vocal_result = next(
            item
            for item in execution.results
            if item.capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
        )
        self.assertEqual(vocal_result.capability_id, VOCAL_PERFORMANCE_CAPABILITY_ID)
        self.assertEqual(vocal_result.output["delivered_mode"], "recitation")

        bundle = CognitiveTurnClosure(view).build(
            response=response,
            execution=execution,
            session_id="session-vocal-evidence",
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertEqual(bundle.aggregate_status, "completed")
        self.assertEqual(bundle.evidence[0].capability_id, VOCAL_PERFORMANCE_CAPABILITY_ID)
        self.assertEqual(bundle.evidence[0].provider_id, self.declaration.provider_id)
        self.assertEqual(bundle.evidence[0].observation.status, "available")  # type: ignore[union-attr]
        self.assertEqual(
            bundle.evidence[0].observation.data["delivered_mode"],  # type: ignore[union-attr]
            "recitation",
        )

    async def test_unsupported_mode_returns_correlated_unavailable_result(self) -> None:
        execution = await submit_and_wait_terminal(self.runtime,
            InteractionResponse(
                interaction_id="unsupported-vocal-mode",
                capabilities=[
                    {
                        "request_id": "unsupported-singing",
                        "capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
                        "args": {"text": "Sing this.", "mode": "singing"},
                    }
                ],
            )
        )

        self.assertEqual(self.calls, [])
        self.assertEqual(execution.results[0].status, "refused")
        self.assertEqual(
            execution.results[0].reason_code,
            "vocal_mode_unavailable",
        )
        self.assertEqual(
            execution.results[0].capability_id,
            VOCAL_PERFORMANCE_CAPABILITY_ID,
        )
        self.assertIsNone(execution.results[0].output["delivered_mode"])

    async def test_provider_cannot_silently_downgrade_mode(self) -> None:
        async def downgrade(_args: dict[str, object]) -> VocalPerformanceDelivery:
            return VocalPerformanceDelivery(
                delivered_mode="speech",
                delivery_evidence_id="invalid-downgrade",
                playback_started=True,
                playback_completed=True,
                audio_duration_ms=500.0,
                sample_format="pcm_s16le",
                sample_rate=24000,
                timing_marks_emitted=[],
            )

        provider = VocalPerformanceCapabilityProvider(self.declaration, downgrade)
        runtime = CapabilityRuntime(self.registry)
        runtime.register_provider(provider)
        execution = await submit_and_wait_terminal(runtime,
            InteractionResponse(
                interaction_id="vocal-no-downgrade",
                capabilities=[
                    {
                        "request_id": "recitation-no-downgrade",
                        "capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
                        "args": {"text": "Recite this.", "mode": "recitation"},
                    }
                ],
            )
        )

        self.assertEqual(execution.results[0].status, "failed")
        self.assertEqual(
            execution.results[0].reason_code,
            "invalid_vocal_delivery_evidence",
        )
        self.assertEqual(execution.results[0].output["delivered_mode"], "speech")

    async def test_output_cancellation_preserves_exact_request_identity(self) -> None:
        started = asyncio.Event()
        cancelled: list[str] = []

        async def blocked(_args: dict[str, object]) -> VocalPerformanceDelivery:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("cancelled vocal provider resumed")

        async def cancel_handler(request, _state) -> None:  # type: ignore[no-untyped-def]
            cancelled.append(request.request_id)

        provider = VocalPerformanceCapabilityProvider(
            self.declaration,
            blocked,
            cancel_handler,
        )
        runtime = CapabilityRuntime(self.registry)
        runtime.register_provider(provider)
        interaction_id = "vocal-cancel"
        execution_task = asyncio.create_task(
            submit_and_wait_terminal(runtime,
                InteractionResponse(
                    interaction_id=interaction_id,
                    capabilities=[
                        {
                            "request_id": "vocal-cancel-request",
                            "capability_id": VOCAL_PERFORMANCE_CAPABILITY_ID,
                            "args": {
                                "text": "Recite until stopped.",
                                "mode": "recitation",
                            },
                        }
                    ],
                )
            )
        )
        await started.wait()

        receipt = await runtime.cancel_scope(
            CancellationDirective(
                source_turn_id="turn-stop-vocal",
                requested_scope="output_only",
                foreground_interaction_id=interaction_id,
            )
        )
        execution = await execution_task

        self.assertEqual(_request_ids(receipt.selected_request_bindings), ("vocal-cancel-request",))
        self.assertEqual(cancelled, ["vocal-cancel-request"])
        self.assertEqual(execution.results[0].capability_id, VOCAL_PERFORMANCE_CAPABILITY_ID)
        self.assertEqual(execution.results[0].status, "cancelled")
        self.assertEqual(execution.results[0].reason_code, "cancelled_output_only")


if __name__ == "__main__":
    unittest.main()
