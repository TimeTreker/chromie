from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.chromie_runtime import ResourceArbiter
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    SkillRequest,
    SkillResult,
    SkillTrace,
    SkillTraceEvent,
    reject_forbidden_low_level_fields,
)

logger = logging.getLogger(__name__)


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1)
    version: str = Field(default="0.1.0", min_length=1)
    provider_id: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    unavailable_reason: str | None = None
    requires_confirmation: bool = False
    interruptible: bool = True
    can_run_parallel: bool = True
    exclusive_group: str | None = None
    timeout_ms: int = Field(default=30000, ge=1, le=120000)
    idempotent: bool = False
    requires_safety_monitor: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_schema", "output_schema", "metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, definition: SkillDefinition) -> None:
        if definition.skill_id in self._skills:
            raise ValueError(f"duplicate skill_id: {definition.skill_id}")
        self._skills[definition.skill_id] = definition

    def upsert(self, definition: SkillDefinition) -> None:
        self._skills[definition.skill_id] = definition

    def get(self, skill_id: str) -> SkillDefinition:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise ValueError(f"unknown skill {skill_id!r}") from exc

    def list(self) -> list[SkillDefinition]:
        return [self._skills[skill_id] for skill_id in sorted(self._skills)]

    def import_soridormi_catalog(
        self,
        skills: list[dict[str, Any]],
        *,
        provider_id: str = "soridormi.mcp",
        version: str = "0.1.0",
        requires_confirmation: bool = True,
        mark_absent_unavailable: bool = True,
    ) -> None:
        seen_skill_ids: set[str] = set()
        for item in skills:
            upstream_id = str(item.get("skill_id", "")).strip()
            if not upstream_id:
                raise ValueError("Soridormi skill catalog entry has no skill_id")
            effects = list(item.get("effects") or ["physical_motion"])
            safety_class = str(item.get("safety_class") or "physical_motion")
            provider_requires_confirmation = bool(
                item.get("requires_confirmation", False)
            )
            effective_requires_confirmation = (
                provider_requires_confirmation
                or (
                    requires_confirmation
                    and (
                        safety_class in {"physical_motion", "safety_critical"}
                        or "physical_motion" in effects
                    )
                )
            )
            skill_id = f"soridormi.{upstream_id}"
            seen_skill_ids.add(skill_id)
            self.upsert(
                SkillDefinition(
                    skill_id=skill_id,
                    version=str(item.get("version") or version),
                    provider_id=provider_id,
                    description=str(item.get("description") or ""),
                    input_schema=dict(item.get("parameters_schema") or {}),
                    available=bool(item.get("available", False)),
                    unavailable_reason=item.get("unavailable_reason"),
                    requires_confirmation=effective_requires_confirmation,
                    interruptible=bool(item.get("interruptible", False)),
                    can_run_parallel=bool(item.get("can_run_parallel", True)),
                    exclusive_group=(
                        str(item.get("exclusive_group") or "").strip()
                        or "soridormi.robot_motion"
                    ),
                    timeout_ms=max(
                        1,
                        int(float(item.get("timeout_s") or 30.0) * 1000),
                    ),
                    idempotent=False,
                    requires_safety_monitor=False,
                    metadata={
                        "upstream_skill_id": upstream_id,
                        "execution": item.get("execution"),
                        "fallback": item.get("fallback"),
                        "hardware_enabled": item.get("hardware_enabled"),
                        "provider_managed_safety_monitor": True,
                        "resource_claims": [
                            str(value)
                            for value in (item.get("resource_claims") or [])
                            if str(value).strip()
                        ],
                        "execution_constraints": dict(
                            item.get("execution_constraints") or {}
                        ),
                    },
                )
            )
        if mark_absent_unavailable:
            for skill_id, definition in list(self._skills.items()):
                if (
                    definition.provider_id == provider_id
                    and skill_id.startswith("soridormi.")
                    and skill_id not in seen_skill_ids
                ):
                    self._skills[skill_id] = definition.model_copy(
                        update={
                            "available": False,
                            "unavailable_reason": (
                                "not present in latest Soridormi catalog"
                            ),
                            "metadata": {
                                **definition.metadata,
                                "catalog_absent": True,
                            },
                        }
                    )


class SkillExecutionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    interaction_id: str
    confirmed: bool = False
    safety_monitor_active: bool = False
    provider_cancel_requested: bool = False
    trace: SkillTrace


class SkillProvider(Protocol):
    provider_id: str

    async def execute(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> SkillResult:
        ...

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        ...


class RuntimeAuthorization(BaseModel):
    confirmed_request_ids: set[str] = Field(default_factory=set)
    safety_monitor_active: bool = False


class SkillRuntimeResult(BaseModel):
    interaction_id: str
    status: str
    results: list[SkillResult] = Field(default_factory=list)
    traces: list[SkillTrace] = Field(default_factory=list)


class SkillRuntimeSchedulerStatus(BaseModel):
    max_concurrency: int
    active_count: int
    waiting_count: int
    serial_active: bool
    serial_waiters: int
    active_interaction_ids: list[str] = Field(default_factory=list)


class SkillRuntime:
    def __init__(
        self,
        registry: SkillRegistry,
        *,
        max_concurrency: int = 8,
        resource_arbiter: ResourceArbiter | None = None,
    ) -> None:
        self.registry = registry
        self._providers: dict[str, SkillProvider] = {}
        self._resource_arbiter = resource_arbiter or ResourceArbiter(max_concurrency)
        self._active: dict[
            tuple[str, str],
            tuple[
                asyncio.Task[SkillResult],
                SkillRequest,
                SkillDefinition,
                SkillExecutionContext,
            ],
        ] = {}
        self._active_lock = asyncio.Lock()

    def register_provider(self, provider: SkillProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"duplicate skill provider: {provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def provider_ids(self) -> set[str]:
        return set(self._providers)

    async def execute(
        self,
        response: InteractionResponse,
        *,
        authorization: RuntimeAuthorization | None = None,
    ) -> SkillRuntimeResult:
        authorization = authorization or RuntimeAuthorization()
        scheduled = self._scheduled_requests(response)
        validated = [self._validate_request(request, authorization) for request in scheduled]
        results: list[SkillResult] = []
        traces: list[SkillTrace] = []

        try:
            pending_parallel: list[tuple[SkillRequest, SkillDefinition]] = []
            for request, definition in validated:
                if request.timing == "parallel" and definition.can_run_parallel:
                    pending_parallel.append((request, definition))
                    continue
                if pending_parallel:
                    parallel_items = list(pending_parallel)
                    batch_results, batch_traces = await self._run_parallel(
                        response.interaction_id,
                        parallel_items,
                        authorization,
                    )
                    results.extend(batch_results)
                    traces.extend(batch_traces)
                    pending_parallel = []
                    if any(
                        self._is_runtime_cancellation(result)
                        for result in batch_results
                    ):
                        return SkillRuntimeResult(
                            interaction_id=response.interaction_id,
                            status="cancelled",
                            results=results,
                            traces=traces,
                        )
                    if any(
                        self._failure_blocks_following_requests(item, result)
                        for (item, _), result in zip(
                            parallel_items, batch_results, strict=True
                        )
                    ):
                        break
                result, trace = await self._run_one(
                    response.interaction_id,
                    request,
                    definition,
                    authorization,
                )
                results.append(result)
                traces.append(trace)
                if self._is_runtime_cancellation(result):
                    return SkillRuntimeResult(
                        interaction_id=response.interaction_id,
                        status="cancelled",
                        results=results,
                        traces=traces,
                    )
                if self._failure_blocks_following_requests(request, result):
                    break
            if pending_parallel:
                batch_results, batch_traces = await self._run_parallel(
                    response.interaction_id,
                    pending_parallel,
                    authorization,
                )
                results.extend(batch_results)
                traces.extend(batch_traces)
                if any(
                    self._is_runtime_cancellation(result)
                    for result in batch_results
                ):
                    return SkillRuntimeResult(
                        interaction_id=response.interaction_id,
                        status="cancelled",
                        results=results,
                        traces=traces,
                    )
        except asyncio.CancelledError:
            await asyncio.shield(
                self.cancel_interaction(response.interaction_id)
            )
            return SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="cancelled",
                results=results,
                traces=traces,
            )

        status = (
            "completed"
            if all(result.status == "completed" for result in results)
            else "failed"
        )
        return SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status=status,
            results=results,
            traces=traces,
        )

    @staticmethod
    def _failure_blocks_following_requests(
        request: SkillRequest,
        result: SkillResult,
    ) -> bool:
        """Honor explicit runtime barriers without making all skills fail-fast.

        Most independent skills should still report their own outcomes even if a
        sibling fails.  A pre-action speech cue is different: when it promises
        an audible acknowledgement before an effect, a failed playback-start
        barrier must prevent the later effect from beginning.
        """

        metadata = request.args.get("metadata")
        return bool(
            isinstance(metadata, dict)
            and metadata.get("abort_remaining_on_failure") is True
            and result.status != "completed"
        )

    @staticmethod
    def _is_runtime_cancellation(result: SkillResult) -> bool:
        return (
            result.status == "cancelled"
            and result.reason_code == "cancelled"
        )

    async def cancel_all(self) -> None:
        await self._cancel_matching(lambda _: True)

    async def cancel_interaction(self, interaction_id: str) -> None:
        await self._cancel_matching(
            lambda key: key[0] == interaction_id
        )

    async def _cancel_matching(
        self,
        predicate: Callable[[tuple[str, str]], bool],
    ) -> None:
        async with self._active_lock:
            active = [
                item
                for key, item in self._active.items()
                if predicate(key)
            ]
        for task, request, definition, context in active:
            if request.cancellable and definition.interruptible:
                task.cancel()
        await asyncio.gather(
            *(
                self._cancel_provider(
                    self._providers[definition.provider_id],
                    request,
                    definition,
                    context,
                )
                for _, request, definition, context in active
                if request.cancellable and definition.interruptible
            ),
            return_exceptions=True,
        )
        await asyncio.gather(*(item[0] for item in active), return_exceptions=True)

    def scheduler_status(self) -> SkillRuntimeSchedulerStatus:
        snapshot = self._resource_arbiter.snapshot()
        return SkillRuntimeSchedulerStatus(
            max_concurrency=snapshot.max_concurrency,
            active_count=snapshot.active_count,
            waiting_count=snapshot.waiting_count,
            serial_active=snapshot.serial_active,
            serial_waiters=snapshot.serial_waiters,
            active_interaction_ids=sorted(
                {interaction_id for interaction_id, _ in self._active}
            ),
        )

    def _scheduled_requests(self, response: InteractionResponse) -> list[SkillRequest]:
        before: list[SkillRequest] = []
        after: list[SkillRequest] = []
        for speech in response.speech:
            request = self._speech_request(speech)
            (after if speech.timing == "after_skills" else before).append(request)
        return [*before, *response.skills, *after]

    def _speech_request(self, speech: InteractionSpeech) -> SkillRequest:
        speech_metadata = dict(speech.metadata)
        playback_barrier = speech_metadata.get("wait_for_playback_start") is True
        if playback_barrier:
            speech_metadata["abort_remaining_on_failure"] = True
        return SkillRequest(
            request_id=speech.id,
            skill_id="chromie.speak",
            args={
                "text": speech.text,
                "style": speech.style,
                "priority": speech.priority,
                "interruptible": speech.interruptible,
                "metadata": speech_metadata,
            },
            timing=(
                "sequential"
                if playback_barrier
                or speech.timing in {"sequential", "after_skills"}
                else "parallel"
            ),
            timeout_ms=speech.timeout_ms,
            cancellable=speech.interruptible,
        )

    def _validate_request(
        self,
        request: SkillRequest,
        authorization: RuntimeAuthorization,
    ) -> tuple[SkillRequest, SkillDefinition]:
        definition = self.registry.get(request.skill_id)
        if definition.provider_id not in self._providers:
            raise ValueError(
                f"skill {request.skill_id!r} has no registered provider {definition.provider_id!r}"
            )
        if request.skill_version and request.skill_version != definition.version:
            raise ValueError(
                f"skill {request.skill_id!r} version {request.skill_version!r} "
                f"does not match registered version {definition.version!r}"
            )
        if not definition.available:
            reason = definition.unavailable_reason or "unavailable"
            raise ValueError(f"skill {request.skill_id!r} is unavailable: {reason}")
        _validate_json_schema(request.args, definition.input_schema, path="args")
        confirmed = request.request_id in authorization.confirmed_request_ids
        if (request.requires_confirmation or definition.requires_confirmation) and not confirmed:
            raise ValueError(f"skill {request.skill_id!r} requires confirmation")
        if definition.requires_safety_monitor and not authorization.safety_monitor_active:
            raise ValueError(f"skill {request.skill_id!r} requires an active safety monitor")
        return request, definition

    async def _run_parallel(
        self,
        interaction_id: str,
        items: list[tuple[SkillRequest, SkillDefinition]],
        authorization: RuntimeAuthorization,
    ) -> tuple[list[SkillResult], list[SkillTrace]]:
        tasks = [
            asyncio.create_task(
                self._run_one(
                    interaction_id,
                    request,
                    definition,
                    authorization,
                )
            )
            for request, definition in items
        ]
        try:
            completed = await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            completed_or_errors = await asyncio.shield(
                asyncio.gather(*tasks, return_exceptions=True)
            )
            completed = []
            for (
                request,
                definition,
            ), item in zip(items, completed_or_errors, strict=True):
                if isinstance(item, asyncio.CancelledError):
                    finished_at = datetime.now(timezone.utc)
                    trace = SkillTrace(
                        interaction_id=interaction_id,
                        request_id=request.request_id,
                        skill_id=request.skill_id,
                        provider_id=definition.provider_id,
                        status="cancelled",
                        events=[
                            SkillTraceEvent(type="validated"),
                            SkillTraceEvent(type="cancelled"),
                        ],
                        finished_at=finished_at,
                    )
                    result = SkillResult(
                        request_id=request.request_id,
                        skill_id=request.skill_id,
                        skill_version=definition.version,
                        status="cancelled",
                        provider_id=definition.provider_id,
                        reason_code="cancelled",
                        message="skill execution was cancelled",
                        trace_id=trace.trace_id,
                        started_at=trace.started_at,
                        finished_at=finished_at,
                    )
                    completed.append((result, trace))
                    continue
                if isinstance(item, BaseException):
                    raise item
                completed.append(item)
        return [item[0] for item in completed], [item[1] for item in completed]

    async def _run_one(
        self,
        interaction_id: str,
        request: SkillRequest,
        definition: SkillDefinition,
        authorization: RuntimeAuthorization,
    ) -> tuple[SkillResult, SkillTrace]:
        provider = self._providers[definition.provider_id]
        trace = SkillTrace(
            interaction_id=interaction_id,
            request_id=request.request_id,
            skill_id=request.skill_id,
            provider_id=definition.provider_id,
            events=[SkillTraceEvent(type="validated")],
        )
        context = SkillExecutionContext(
            interaction_id=interaction_id,
            confirmed=request.request_id in authorization.confirmed_request_ids,
            safety_monitor_active=authorization.safety_monitor_active,
            trace=trace,
        )
        timeout_s = (request.timeout_ms or definition.timeout_ms) / 1000.0

        async def invoke() -> SkillResult:
            async with self._resource_arbiter.claim(
                can_run_parallel=definition.can_run_parallel,
                exclusive_group=definition.exclusive_group,
            ):
                return await provider.execute(request, definition, context)

        task = asyncio.create_task(invoke())
        active_key = (interaction_id, request.request_id)
        async with self._active_lock:
            self._active[active_key] = (task, request, definition, context)
        trace.events.append(SkillTraceEvent(type="started"))
        try:
            result = await asyncio.wait_for(task, timeout=timeout_s)
        except TimeoutError:
            cancel_error = await self._cancel_provider(
                provider,
                request,
                definition,
                context,
            )
            result = SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="timed_out",
                provider_id=definition.provider_id,
                reason_code="timeout",
                message=(
                    f"skill exceeded {timeout_s:.3f}s timeout"
                    + (
                        f"; provider cancellation failed: {cancel_error}"
                        if cancel_error
                        else ""
                    )
                ),
            )
        except asyncio.CancelledError:
            cancel_error: str | None = None
            if request.cancellable and definition.interruptible:
                cancel_error = await asyncio.shield(
                    self._cancel_provider(
                        provider,
                        request,
                        definition,
                        context,
                    )
                )
            result = SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="cancelled",
                provider_id=definition.provider_id,
                reason_code="cancelled",
                message=(
                    "skill execution was cancelled"
                    + (
                        f"; provider cancellation failed: {cancel_error}"
                        if cancel_error
                        else ""
                    )
                ),
            )
        except Exception as exc:
            result = SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="failed",
                provider_id=definition.provider_id,
                reason_code="provider_error",
                message=str(exc) or exc.__class__.__name__,
            )
        finally:
            async with self._active_lock:
                self._active.pop(active_key, None)

        result.trace_id = trace.trace_id
        trace.status = result.status
        trace.finished_at = datetime.now(timezone.utc)
        if result.started_at is None:
            result.started_at = trace.started_at
        if result.finished_at is None:
            result.finished_at = trace.finished_at
        trace.events.append(
            SkillTraceEvent(
                type=result.status,
                message=result.message,
                data={"reason_code": result.reason_code},
            )
        )
        return result, trace

    async def _cancel_provider(
        self,
        provider: SkillProvider,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> str | None:
        if context.provider_cancel_requested:
            return None
        context.provider_cancel_requested = True
        try:
            await provider.cancel(request, definition, context)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            logger.warning(
                "Skill provider cancellation failed request_id=%s skill_id=%s "
                "provider_id=%s error=%s",
                request.request_id,
                request.skill_id,
                definition.provider_id,
                message,
            )
            return message
        return None


SpeechHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class LocalSpeechSkillProvider:
    provider_id = "chromie.local_speech"

    def __init__(self, handler: SpeechHandler) -> None:
        self._handler = handler
        self.cancelled_request_ids: set[str] = set()

    async def execute(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> SkillResult:
        raw = self._handler(request.args)
        output = await raw if inspect.isawaitable(raw) else raw
        metadata = request.args.get("metadata")
        playback_barrier = bool(
            isinstance(metadata, dict)
            and metadata.get("wait_for_playback_start") is True
        )
        playback_started = bool(
            isinstance(output, dict) and output.get("playback_started") is True
        )
        if playback_barrier and not playback_started:
            return SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
                status="failed",
                provider_id=self.provider_id,
                output=output if isinstance(output, dict) else {},
                reason_code="playback_not_started",
                message=(
                    "required pre-action speech did not begin playback; "
                    "following requests were not authorized to start"
                ),
            )
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output=output,
        )

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        self.cancelled_request_ids.add(request.request_id)


class SessionControlSkillProvider:
    provider_id = "chromie.session_control"

    async def execute(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> SkillResult:
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output={"control": "interrupt_acknowledged"},
        )

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        return None


class MockSkillProvider:
    def __init__(
        self,
        provider_id: str = "mock",
        *,
        delay_s: float = 0.0,
    ) -> None:
        self.provider_id = provider_id
        self.delay_s = delay_s
        self.calls: list[SkillRequest] = []
        self.cancelled_request_ids: list[str] = []

    async def execute(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> SkillResult:
        self.calls.append(request)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return SkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_version=definition.version,
            status="completed",
            provider_id=self.provider_id,
            output={"args": request.args},
        )

    async def cancel(
        self,
        request: SkillRequest,
        definition: SkillDefinition,
        context: SkillExecutionContext,
    ) -> None:
        self.cancelled_request_ids.append(request.request_id)


def local_speech_definition() -> SkillDefinition:
    return SkillDefinition(
        skill_id="chromie.speak",
        version="1.0.0",
        provider_id=LocalSpeechSkillProvider.provider_id,
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
        timeout_ms=30000,
        interruptible=True,
        can_run_parallel=True,
        exclusive_group="chromie.audio",
    )


def session_interrupt_definition() -> SkillDefinition:
    return SkillDefinition(
        skill_id="session.interrupt",
        version="1.0.0",
        provider_id=SessionControlSkillProvider.provider_id,
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


def _validate_json_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    if not schema:
        return
    schema_type = schema.get("type")
    allowed_types = schema_type if isinstance(schema_type, list) else [schema_type] if schema_type else []
    if allowed_types and not any(_matches_type(value, item) for item in allowed_types):
        raise ValueError(f"{path} expected {allowed_types}, got {type(value).__name__}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} exceeds maximum {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"{path} is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path} is longer than {schema['maxLength']}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                raise ValueError(f"{path} is missing required field {required!r}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ValueError(f"{path} has unknown fields: {unknown}")
        for key, item in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                _validate_json_schema(item, child_schema, path=f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValueError(f"{path} has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path} has more than {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_json_schema(item, item_schema, path=f"{path}[{index}]")


def _matches_type(value: Any, schema_type: str) -> bool:
    if schema_type == "null":
        return value is None
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True
