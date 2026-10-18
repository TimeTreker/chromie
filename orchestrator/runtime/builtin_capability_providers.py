"""Built-in Chromie-owned Capability providers and their definitions.

Vocal performance, media playback, local speech, session control and the mock
provider adapt Host-owned backends to the exact public Capability contracts
that ``CapabilityRuntime`` executes.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from orchestrator.runtime.scheduler import current_execution_start
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    MEDIA_CAPABILITY_IDS,
    MediaPlaybackEvidence,
    MediaProviderDeclaration,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    VOCAL_MODES,
    VocalPerformanceDelivery,
    VocalProviderDeclaration,
    media_capability_input_schema,
    media_capability_output_schema,
    vocal_performance_input_schema,
    vocal_performance_output_schema,
)
from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition,
    CapabilityExecutionContext,
)

logger = logging.getLogger(__name__)


SpeechHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
SpeechCancelHandler = Callable[
    [CapabilityRequest, dict[str, Any]],
    None | Awaitable[None],
]

VocalPerformanceHandler = Callable[
    [dict[str, Any]],
    VocalPerformanceDelivery
    | dict[str, Any]
    | Awaitable[VocalPerformanceDelivery | dict[str, Any]],
]
VocalPerformanceCancelHandler = Callable[
    [CapabilityRequest, dict[str, Any]],
    None | Awaitable[None],
]

MediaPlaybackHandler = Callable[
    [str, dict[str, Any]],
    MediaPlaybackEvidence | dict[str, Any] | Awaitable[MediaPlaybackEvidence | dict[str, Any]],
]
MediaPlaybackCancelHandler = Callable[
    [CapabilityRequest, dict[str, Any]],
    None | Awaitable[None],
]


class VocalPerformanceCapabilityProvider:
    """Adapt one qualified vocal backend to the exact public Capability.

    The backend may change, but its declaration and execution evidence are
    checked here before a completed result can cross the Trusted Capability
    Runtime boundary. Unsupported modes return a typed refusal rather than
    reaching the backend or being downgraded to ordinary speech.
    """

    def __init__(
        self,
        declaration: VocalProviderDeclaration,
        handler: VocalPerformanceHandler,
        cancel_handler: VocalPerformanceCancelHandler | None = None,
    ) -> None:
        self.declaration = declaration
        self.provider_id = declaration.provider_id
        self._handler = handler
        self._cancel_handler = cancel_handler
        self.cancelled_request_ids: set[str] = set()

    def _output(
        self,
        *,
        requested_mode: str,
        completed: bool,
        delivered_mode: str | None = None,
        delivery: VocalPerformanceDelivery | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        evidence = self.declaration.mode_evidence.get(requested_mode)  # type: ignore[arg-type]
        return {
            "completed": completed,
            "requested_mode": requested_mode,
            "delivered_mode": delivered_mode,
            "provider_id": self.provider_id,
            "provider_contract_version": self.declaration.contract_version,
            "evidence_level": evidence.level if evidence is not None else None,
            "provider_evidence_refs": (
                list(evidence.artifact_refs) if evidence is not None else []
            ),
            "delivery_evidence_id": (delivery.delivery_evidence_id if delivery is not None else ""),
            "playback_started": bool(delivery is not None and delivery.playback_started),
            "playback_completed": bool(delivery is not None and delivery.playback_completed),
            "audio_duration_ms": (delivery.audio_duration_ms if delivery is not None else 0.0),
            "sample_format": (delivery.sample_format if delivery is not None else ""),
            "sample_rate": delivery.sample_rate if delivery is not None else 0,
            "timing_marks_emitted": (
                list(delivery.timing_marks_emitted) if delivery is not None else []
            ),
            "reason": reason,
        }

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        requested_mode = str(request.args.get("mode") or "").strip()
        if requested_mode not in self.declaration.supported_modes:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="refused",
                provider_id=self.provider_id,
                output=self._output(
                    requested_mode=requested_mode,
                    completed=False,
                    reason=("requested vocal mode is not advertised by this qualified provider"),
                ),
                reason_code="vocal_mode_unavailable",
                message=(
                    f"vocal mode {requested_mode!r} is unavailable; supported "
                    f"modes are {self.declaration.supported_modes}"
                ),
            )

        try:
            raw = self._handler(dict(request.args))
            raw_delivery = await raw if inspect.isawaitable(raw) else raw
            delivery = (
                raw_delivery
                if isinstance(raw_delivery, VocalPerformanceDelivery)
                else VocalPerformanceDelivery.model_validate(raw_delivery)
            )
            invalid_reason = ""
            if delivery.delivered_mode != requested_mode:
                invalid_reason = "provider returned a different vocal mode"
            elif not delivery.playback_started or not delivery.playback_completed:
                invalid_reason = "audible playback did not complete"
            elif delivery.sample_format not in self.declaration.sample_formats:
                invalid_reason = "provider returned an undeclared sample format"
            elif delivery.sample_rate not in self.declaration.sample_rates:
                invalid_reason = "provider returned an undeclared sample rate"
            elif not set(delivery.timing_marks_emitted).issubset(
                self.declaration.timing_mark_types
            ):
                invalid_reason = "provider returned undeclared timing marks"
            if invalid_reason:
                return CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status="failed",
                    provider_id=self.provider_id,
                    output=self._output(
                        requested_mode=requested_mode,
                        completed=False,
                        delivered_mode=delivery.delivered_mode,
                        delivery=delivery,
                        reason=invalid_reason,
                    ),
                    reason_code="invalid_vocal_delivery_evidence",
                    message=invalid_reason,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=self._output(
                    requested_mode=requested_mode,
                    completed=False,
                    reason="provider did not return valid vocal delivery evidence",
                ),
                reason_code="invalid_vocal_delivery_evidence",
                message=str(exc) or type(exc).__name__,
            )

        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output=self._output(
                requested_mode=requested_mode,
                completed=True,
                delivered_mode=delivery.delivered_mode,
                delivery=delivery,
            ),
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        self.cancelled_request_ids.add(request.request_id)
        if self._cancel_handler is None:
            return
        raw = self._cancel_handler(request, dict(context.provider_state))
        if inspect.isawaitable(raw):
            await raw


class MediaPlaybackCapabilityProvider:
    """Adapt one qualified peer media backend to ``chromie.media.*``.

    Media is Activity work even though it shares a physical speaker with
    Vocal. Every result retains the exact operation, persistent playback
    identity, bounded progress, and the declared ducking policy.
    """

    _ALLOWED_STATES = {
        "play": {"playing", "completed"},
        "pause": {"paused"},
        "resume": {"playing", "completed"},
        "seek": {"playing", "paused", "completed"},
        "stop": {"stopped", "completed"},
        "volume": {"playing", "paused", "completed"},
        "status": {"starting", "playing", "paused", "completed", "stopped", "failed"},
    }

    def __init__(
        self,
        declaration: MediaProviderDeclaration,
        handler: MediaPlaybackHandler,
        cancel_handler: MediaPlaybackCancelHandler | None = None,
    ) -> None:
        self.declaration = declaration
        self.provider_id = declaration.provider_id
        self._handler = handler
        self._cancel_handler = cancel_handler
        self.cancelled_request_ids: set[str] = set()

    @staticmethod
    def _operation_for(capability_id: str) -> str:
        for operation, exact_id in MEDIA_CAPABILITY_IDS.items():
            if capability_id == exact_id:
                return operation
        return ""

    def _output(
        self,
        *,
        operation: str,
        capability_id: str,
        completed: bool,
        evidence: MediaPlaybackEvidence | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        qualification = self.declaration.operation_evidence.get(operation)  # type: ignore[arg-type]
        return {
            "completed": completed,
            "operation": operation,
            "capability_id": capability_id,
            "provider_id": self.provider_id,
            "provider_contract_version": self.declaration.contract_version,
            "evidence_level": qualification.level if qualification is not None else None,
            "provider_evidence_refs": (
                list(qualification.artifact_refs) if qualification is not None else []
            ),
            "playback_id": evidence.playback_id if evidence is not None else "",
            "state": evidence.state if evidence is not None else None,
            "media_kind": evidence.media_kind if evidence is not None else "",
            "media_ref": evidence.media_ref if evidence is not None else "",
            "position_ms": evidence.position_ms if evidence is not None else 0,
            "duration_ms": evidence.duration_ms if evidence is not None else None,
            "volume": evidence.volume if evidence is not None else 0.0,
            "delivery_evidence_id": (evidence.delivery_evidence_id if evidence is not None else ""),
            "mixer_policy": self.declaration.mixer_policy,
            "ducking_active": bool(evidence is not None and evidence.ducking_active),
            "reason": reason,
        }

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        operation = self._operation_for(request.capability_id)
        if operation not in self.declaration.supported_operations:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="refused",
                provider_id=self.provider_id,
                output=self._output(
                    operation=operation,
                    capability_id=request.capability_id,
                    completed=False,
                    reason="requested media operation is not advertised by this provider",
                ),
                reason_code="media_operation_unavailable",
                message=(
                    f"media operation {operation!r} is unavailable; supported operations "
                    f"are {self.declaration.supported_operations}"
                ),
            )

        try:
            raw = self._handler(operation, dict(request.args))
            raw_evidence = await raw if inspect.isawaitable(raw) else raw
            evidence = (
                raw_evidence
                if isinstance(raw_evidence, MediaPlaybackEvidence)
                else MediaPlaybackEvidence.model_validate(raw_evidence)
            )
            invalid_reason = ""
            if evidence.operation != operation:
                invalid_reason = "provider returned a different media operation"
            elif evidence.state not in self._ALLOWED_STATES[operation]:
                invalid_reason = (
                    f"provider returned state={evidence.state!r} incompatible with "
                    f"operation={operation!r}"
                )
            elif evidence.media_kind not in self.declaration.supported_media_kinds:
                invalid_reason = "provider returned an undeclared media kind"
            if invalid_reason:
                return CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status="failed",
                    provider_id=self.provider_id,
                    output=self._output(
                        operation=operation,
                        capability_id=request.capability_id,
                        completed=False,
                        evidence=evidence,
                        reason=invalid_reason,
                    ),
                    reason_code="invalid_media_lifecycle_evidence",
                    message=invalid_reason,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=self._output(
                    operation=operation,
                    capability_id=request.capability_id,
                    completed=False,
                    reason="provider did not return valid media lifecycle evidence",
                ),
                reason_code="invalid_media_lifecycle_evidence",
                message=str(exc) or type(exc).__name__,
            )

        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output=self._output(
                operation=operation,
                capability_id=request.capability_id,
                completed=True,
                evidence=evidence,
            ),
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        self.cancelled_request_ids.add(request.request_id)
        if self._cancel_handler is None:
            return
        raw = self._cancel_handler(request, dict(context.provider_state))
        if inspect.isawaitable(raw):
            await raw


class LocalSpeechCapabilityProvider:
    provider_id = "chromie.local_speech"
    supports_coordinated_start = True

    def __init__(
        self,
        handler: SpeechHandler,
        cancel_handler: SpeechCancelHandler | None = None,
    ) -> None:
        self._handler = handler
        self._cancel_handler = cancel_handler
        self.cancelled_request_ids: set[str] = set()

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        args = dict(request.args)
        if context.start_gate is not None:
            args["metadata"] = {**args.get("metadata", {}), "wait_for_voice_release": True}
        token = current_execution_start.set(context.start_gate)
        try:
            raw = self._handler(args)
            output = await raw if inspect.isawaitable(raw) else raw
        finally:
            current_execution_start.reset(token)
        metadata = args.get("metadata")
        playback_barrier = bool(
            isinstance(metadata, dict) and metadata.get("wait_for_playback_start") is True
        )
        playback_started = bool(isinstance(output, dict) and output.get("playback_started") is True)
        voice_release_required = bool(
            isinstance(metadata, dict) and metadata.get("wait_for_voice_release") is True
        )
        voice_released = bool(
            isinstance(output, dict) and output.get("voice_released") is True
        )
        if voice_release_required and not voice_released:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=output if isinstance(output, dict) else {},
                reason_code="personal_voice_not_released",
                message="personal Vocal resource was not released after speech",
            )
        if playback_barrier and not playback_started:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=output if isinstance(output, dict) else {},
                reason_code="playback_not_started",
                message=(
                    "required pre-action speech did not begin playback; "
                    "following requests were not authorized to start"
                ),
            )
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output=output,
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        self.cancelled_request_ids.add(request.request_id)
        if self._cancel_handler is None:
            return
        # The host speech handler may still be awaiting playback-start evidence
        # when its task is cancelled, so no completed scheduling receipt is
        # guaranteed here.  The host therefore treats missing receipt data as
        # requiring a conservative global output abort.
        raw = self._cancel_handler(request, {})
        if inspect.isawaitable(raw):
            await raw


class SessionControlCapabilityProvider:
    provider_id = "chromie.session_control"

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output={"control": "interrupt_acknowledged"},
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        return None


class MockCapabilityProvider:
    def __init__(
        self,
        provider_id: str = "mock",
        *,
        delay_s: float = 0.0,
    ) -> None:
        self.provider_id = provider_id
        self.delay_s = delay_s
        self.calls: list[CapabilityRequest] = []
        self.cancelled_request_ids: list[str] = []

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        self.calls.append(request)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output={"args": request.args},
        )

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None:
        self.cancelled_request_ids.append(request.request_id)


def local_speech_definition(*, timeout_ms: int | None = None) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="chromie.speak",
        version="1.0.0",
        provider_id=LocalSpeechCapabilityProvider.provider_id,
        description="Speak text through Chromie's TTS and playback path.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "style": {"type": "string"},
                "priority": {"type": "string"},
                "interruptible": {"type": "boolean"},
                "metadata": {"type": "object"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        timeout_ms=max(30000, int(timeout_ms or 30000)),
        interruptible=True,
        can_run_parallel=True,
        exclusive_group="chromie.voice",
        cancellation_domains=("output",),
        metadata={
            "cancellation_granularity": "global_domain",
            "effects": ["user_interaction", "audio_output"],
            "safety_class": "low_risk_action",
            "execution_lane": "vocal",
            "parallel_metadata_declared": True,
            "resource_claims": ["chromie.voice"],
        },
    )


def vocal_performance_definition(
    declaration: VocalProviderDeclaration,
) -> CapabilityDefinition:
    """Return the Host-owned definition for one qualified vocal provider."""

    return CapabilityDefinition(
        capability_id=VOCAL_PERFORMANCE_CAPABILITY_ID,
        version="1.0.0",
        provider_id=declaration.provider_id,
        description=(
            "Perform one exact provider-qualified vocal mode through Chromie's playback boundary."
        ),
        # The runtime accepts every typed public mode so a stale or malicious
        # request receives a correlated unavailable result from the provider
        # negotiation boundary instead of an uncaught schema exception.
        input_schema=vocal_performance_input_schema(list(VOCAL_MODES)),
        output_schema=vocal_performance_output_schema(),
        available=True,
        requires_confirmation=False,
        interruptible=declaration.request_cancellation,
        can_run_parallel=True,
        exclusive_group="chromie.voice",
        timeout_ms=120000,
        idempotent=False,
        cancellation_domains=("output",),
        metadata={
            "effects": ["user_interaction", "audio_output", "vocal_performance"],
            "safety_class": "low_risk_action",
            "execution_lane": "vocal",
            "parallel_metadata_declared": True,
            "resource_claims": ["chromie.voice"],
            "cancellation_granularity": "request",
            "supported_vocal_modes": list(declaration.supported_modes),
            "native_text_streaming": declaration.native_text_streaming,
            "native_audio_streaming": declaration.native_audio_streaming,
            "request_cancellation": declaration.request_cancellation,
            "timing_mark_types": list(declaration.timing_mark_types),
            "sample_formats": list(declaration.sample_formats),
            "sample_rates": list(declaration.sample_rates),
            "max_concurrency": declaration.max_concurrency,
            "provider_contract_version": declaration.contract_version,
            "provider_declaration": declaration.model_dump(mode="json"),
        },
    )


def media_playback_definitions(
    declaration: MediaProviderDeclaration,
) -> list[CapabilityDefinition]:
    """Return Host-owned definitions for one qualified peer media provider."""

    definitions: list[CapabilityDefinition] = []
    for operation in declaration.supported_operations:
        capability_id = MEDIA_CAPABILITY_IDS[operation]
        effectful = operation != "status"
        definitions.append(
            CapabilityDefinition(
                capability_id=capability_id,
                version="1.0.0",
                provider_id=declaration.provider_id,
                description=(
                    f"Apply exact media lifecycle operation {operation!r} through "
                    "Chromie's peer media provider."
                ),
                input_schema=media_capability_input_schema(
                    operation,
                    declaration.supported_media_kinds,
                ),
                output_schema=media_capability_output_schema(),
                available=True,
                requires_confirmation=False,
                interruptible=(declaration.request_cancellation and effectful),
                can_run_parallel=True,
                exclusive_group=(None if operation == "play" else "chromie.media.control"),
                timeout_ms=120000 if operation == "play" else 10000,
                idempotent=operation in {"pause", "resume", "stop", "volume", "status"},
                cancellation_domains=(("media_output",) if effectful else ()),
                metadata={
                    "effects": (
                        ["read_only", "media_playback", "playback_status"]
                        if operation == "status"
                        else ["audio_output", "media_playback", "playback_lifecycle"]
                    ),
                    "safety_class": "safe_read" if operation == "status" else "low_risk_action",
                    "execution_lane": "activity",
                    "parallel_metadata_declared": True,
                    "resource_claims": ["audio_output.media"],
                    "cancellation_granularity": "request",
                    "media_operation": operation,
                    "persistent_playback": declaration.persistent_playback,
                    "progress_reporting": declaration.progress_reporting,
                    "mixer_policy": declaration.mixer_policy,
                    "ducking_gain_db": declaration.ducking_gain_db,
                    "duck_attack_ms": declaration.duck_attack_ms,
                    "duck_release_ms": declaration.duck_release_ms,
                    "supported_media_kinds": list(declaration.supported_media_kinds),
                    "provider_contract_version": declaration.contract_version,
                    "provider_declaration": declaration.model_dump(mode="json"),
                },
            )
        )
    return definitions


def session_interrupt_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="session.interrupt",
        version="1.0.0",
        provider_id=SessionControlCapabilityProvider.provider_id,
        description="Acknowledge a host session interrupt already applied by the coordinator.",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        timeout_ms=300,
        interruptible=False,
        can_run_parallel=True,
        idempotent=True,
        metadata={"control": "session_interrupt"},
    )
