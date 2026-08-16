from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.chromie_runtime import ResourceArbiter
from shared.chromie_contracts.execution_outcome import ClaimQualificationPolicy
from shared.chromie_contracts.interaction import (
    CapabilityIdentityModel,
    CapabilityRequest,
    CapabilityResult,
    CapabilityTrace,
    CapabilityTraceEvent,
    InteractionResponse,
    InteractionSpeech,
    MEDIA_CAPABILITY_IDS,
    MediaPlaybackEvidence,
    MediaProviderDeclaration,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    VOCAL_MODES,
    VocalPerformanceDelivery,
    VocalProviderDeclaration,
    reject_forbidden_low_level_fields,
    media_capability_input_schema,
    media_capability_output_schema,
    vocal_performance_input_schema,
    vocal_performance_output_schema,
)
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    CancellationProviderFailure,
    CancellationRequestBinding,
    CancellationScope,
)


def schema_valid_completion_evidence_policy(
    *,
    claim: str = "capability request completed",
) -> ClaimQualificationPolicy:
    """Host default for ordinary capabilities with a closed output schema.

    This is deliberately a Host policy, not a provider-authored declaration.
    It establishes only that the committed capability request returned one
    schema-valid correlated observation. More consequential providers may
    replace it with a stronger owner-reviewed policy.
    """

    return ClaimQualificationPolicy(
        claim=claim,
        requirement_groups=[
            {
                "requirements": [
                    {"source": "execution_observation"},
                ]
            }
        ],
    )


def embodied_completion_evidence_policy() -> ClaimQualificationPolicy:
    """Host-owned minimum evidence for Soridormi embodied completion.

    The execution result and post-execution provider status are separate
    observations, but this policy intentionally does not claim they are
    independent trust domains. A future provider may qualify stronger
    corroboration without changing Goal semantics.
    """

    return ClaimQualificationPolicy(
        claim="embodied capability request completed with safe closure",
        requirement_groups=[
            {
                "requirements": [
                    {
                        "source": "execution_observation",
                        "field_assertions": {"completed": True},
                    },
                    {
                        "source": "provider_postcondition",
                        "condition": "post_execution_robot_status",
                        "field_assertions": {
                            "safe_idle": True,
                            "active_task_present": False,
                        },
                    },
                ],
                "minimum_independent_trust_domains": 1,
            }
        ],
    )


logger = logging.getLogger(__name__)

CancellationDomain = Literal["output", "media_output", "embodied_motion"]

_RESULT_AUTHORITY_METADATA_KEYS = (
    "source_goal_ids",
    "covers_goal_ids",
    "canonical_plan_id",
    "canonical_plan_fingerprint",
    "step_id",
    "execution_lane",
    "coordination_id",
    "delivery_role",
    "lane_coordination_relation",
    "lane_start_policy",
    "lane_failure_policy",
    "parallel_with_activity",
)



class CapabilityDefinition(CapabilityIdentityModel):
    version: str = Field(default="0.1.0", min_length=1)
    provider_id: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    completion_evidence_policy: ClaimQualificationPolicy | None = None
    available: bool = True
    unavailable_reason: str | None = None
    requires_confirmation: bool = False
    interruptible: bool = True
    can_run_parallel: bool = True
    exclusive_group: str | None = None
    timeout_ms: int = Field(default=30000, ge=1, le=120000)
    idempotent: bool = False
    requires_safety_monitor: bool = False
    cancellation_domains: tuple[CancellationDomain, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_schema", "output_schema", "metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def default_owner_reviewed_completion_policy(self) -> "CapabilityDefinition":
        if self.completion_evidence_policy is None and self.output_schema:
            self.completion_evidence_policy = schema_valid_completion_evidence_policy()
        return self


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}

    def register(self, definition: CapabilityDefinition) -> None:
        if definition.capability_id in self._capabilities:
            raise ValueError(f"duplicate capability_id: {definition.capability_id}")
        self._capabilities[definition.capability_id] = definition

    def upsert(self, definition: CapabilityDefinition) -> None:
        self._capabilities[definition.capability_id] = definition

    def get(self, capability_id: str) -> CapabilityDefinition:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise ValueError(f"unknown capability {capability_id!r}") from exc

    def list(self) -> list[CapabilityDefinition]:
        return [self._capabilities[capability_id] for capability_id in sorted(self._capabilities)]

    def replace_provider_capabilities(
        self,
        definitions: list[CapabilityDefinition],
        *,
        provider_id: str,
        namespace_prefix: str | None = None,
        mark_absent_unavailable: bool = True,
    ) -> None:
        """Atomically refresh one provider-owned capability projection.

        Provider adapters own translation from their wire protocol into canonical
        :class:`CapabilityDefinition` objects. The registry only enforces canonical
        identity, provider ownership, duplicate rejection, and atomic replacement.
        """

        incoming: dict[str, CapabilityDefinition] = {}
        for definition in definitions:
            if definition.provider_id != provider_id:
                raise ValueError(
                    f"capability {definition.capability_id!r} belongs to provider "
                    f"{definition.provider_id!r}, expected {provider_id!r}"
                )
            if namespace_prefix and not definition.capability_id.startswith(namespace_prefix):
                raise ValueError(
                    f"capability {definition.capability_id!r} is outside provider namespace "
                    f"{namespace_prefix!r}"
                )
            if definition.capability_id in incoming:
                raise ValueError(
                    f"duplicate capability_id in provider refresh: {definition.capability_id}"
                )
            incoming[definition.capability_id] = definition

        updated = dict(self._capabilities)
        updated.update(incoming)
        if mark_absent_unavailable:
            for capability_id, definition in list(updated.items()):
                if definition.provider_id != provider_id:
                    continue
                if namespace_prefix and not capability_id.startswith(namespace_prefix):
                    continue
                if capability_id in incoming:
                    continue
                updated[capability_id] = definition.model_copy(
                    update={
                        "available": False,
                        "unavailable_reason": "not present in latest provider catalog",
                        "metadata": {**definition.metadata, "catalog_absent": True},
                    }
                )
        self._capabilities = updated



class CapabilityExecutionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    interaction_id: str
    confirmed: bool = False
    safety_monitor_active: bool = False
    provider_cancel_requested: bool = False
    provider_cancel_error: str | None = None
    provider_cancel_future: asyncio.Future[str | None] | None = None
    provider_cancel_source_turn_id: str | None = None
    provider_started: bool = False
    cancellation_scope: CancellationScope = "none"
    cancellation_reason_code: str = "cancelled"
    provider_state: dict[str, Any] = Field(default_factory=dict)
    progress_publisher: Callable[[dict[str, Any], str | None], Awaitable[None]] | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    trace: CapabilityTrace

    async def publish_progress(
        self,
        progress: dict[str, Any] | None = None,
        *,
        message: str | None = None,
    ) -> None:
        if self.progress_publisher is None:
            return
        await self.progress_publisher(dict(progress or {}), message)


class CapabilityProvider(Protocol):
    provider_id: str

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult: ...

    async def cancel(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> None: ...


class RuntimeAuthorization(BaseModel):
    confirmed_request_ids: set[str] = Field(default_factory=set)
    safety_monitor_active: bool = False


CapabilityRuntimeEventType = Literal[
    "accepted",
    "running",
    "progress",
    "completed",
    "failed",
    "refused",
    "cancelled",
    "timed_out",
]


class CapabilityRuntimeEvent(CapabilityIdentityModel):
    sequence: int = Field(ge=1)
    event_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    dispatch_id: str = Field(min_length=1)
    interaction_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    type: CapabilityRuntimeEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str | None = None
    progress: dict[str, Any] = Field(default_factory=dict)
    result: CapabilityResult | None = None

    @property
    def terminal(self) -> bool:
        return self.type in {"completed", "failed", "refused", "cancelled", "timed_out"}


class CapabilityDispatchReceipt(BaseModel):
    dispatch_id: str
    interaction_id: str
    status: Literal["accepted"] = "accepted"
    request_ids: list[str] = Field(default_factory=list)
    event_cursor: int = Field(default=0, ge=0)
    accepted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CapabilityRuntimeResult(BaseModel):
    interaction_id: str
    status: str
    results: list[CapabilityResult] = Field(default_factory=list)
    traces: list[CapabilityTrace] = Field(default_factory=list)


class CapabilityRuntimeSchedulerStatus(BaseModel):
    max_concurrency: int
    active_count: int
    waiting_count: int
    serial_active: bool
    serial_waiters: int
    active_interaction_ids: list[str] = Field(default_factory=list)


class CapabilityRuntimeRequestObservation(CapabilityIdentityModel):
    interaction_id: str
    request_id: str
    provider_id: str
    source_goal_ids: list[str] = Field(default_factory=list)
    provider_started: bool
    task_done: bool


class CapabilityRuntimeExecutionObservation(BaseModel):
    captured_at: datetime
    open_interaction_ids: list[str] = Field(default_factory=list)
    executing_interaction_ids: list[str] = Field(default_factory=list)
    requests: list[CapabilityRuntimeRequestObservation] = Field(default_factory=list)


@dataclass(frozen=True)
class _CancellationRule:
    directive: CancellationDirective
    effective_scope: CancellationScope


class CapabilityRuntime:
    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        max_concurrency: int = 8,
        resource_arbiter: ResourceArbiter | None = None,
    ) -> None:
        self.registry = registry
        self._providers: dict[str, CapabilityProvider] = {}
        self._resource_arbiter = resource_arbiter or ResourceArbiter(max_concurrency)
        self._active: dict[
            tuple[str, str],
            tuple[
                asyncio.Task[Any],
                CapabilityRequest,
                CapabilityDefinition,
                CapabilityExecutionContext,
            ],
        ] = {}
        self._active_lock = asyncio.Lock()
        self._open_interactions: set[str] = set()
        self._executing_interactions: set[str] = set()
        self._submissions: dict[str, asyncio.Task[CapabilityRuntimeResult]] = {}
        self._dispatch_interactions: dict[str, str] = {}
        self._interaction_dispatch_ids: dict[str, str] = {}
        self._event_sequence = 0
        self._event_history: deque[CapabilityRuntimeEvent] = deque(maxlen=4096)
        self._event_condition = asyncio.Condition()
        self._scheduled: dict[
            str,
            dict[str, tuple[CapabilityRequest, CapabilityDefinition]],
        ] = {}
        self._cancellation_rules: dict[str, list[_CancellationRule]] = {}

    def register_provider(self, provider: CapabilityProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"duplicate capability provider: {provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def provider_ids(self) -> set[str]:
        return set(self._providers)

    async def execution_observation(self) -> CapabilityRuntimeExecutionObservation:
        """Return a bounded read-only view of scheduled/active execution.

        This is an observability boundary for qualification and operator tools.
        It intentionally excludes request arguments and provider payloads while
        exposing enough trusted state to prove that a cancellation was issued
        after an effectful provider request had actually started.
        """

        async with self._active_lock:
            requests: list[CapabilityRuntimeRequestObservation] = []
            for interaction_id in sorted(self._scheduled):
                for request_id in sorted(self._scheduled[interaction_id]):
                    request, definition = self._scheduled[interaction_id][request_id]
                    active = self._active.get((interaction_id, request_id))
                    context = active[3] if active is not None else None
                    metadata = request.metadata if isinstance(request.metadata, dict) else {}
                    source_goal_ids = metadata.get("source_goal_ids") or []
                    if not isinstance(source_goal_ids, list):
                        source_goal_ids = []
                    requests.append(
                        CapabilityRuntimeRequestObservation(
                            interaction_id=interaction_id,
                            request_id=request.request_id,
                            capability_id=request.capability_id,
                            provider_id=definition.provider_id,
                            source_goal_ids=[
                                str(value) for value in source_goal_ids if str(value).strip()
                            ],
                            provider_started=bool(context is not None and context.provider_started),
                            task_done=bool(active is not None and active[0].done()),
                        )
                    )
            return CapabilityRuntimeExecutionObservation(
                captured_at=datetime.now(timezone.utc),
                open_interaction_ids=sorted(self._open_interactions),
                executing_interaction_ids=sorted(self._executing_interactions),
                requests=requests,
            )

    def begin_interaction(self, interaction_id: str) -> bool:
        """Keep scoped directives alive across one coordinator-owned execution."""

        if interaction_id in self._open_interactions:
            return False
        self._open_interactions.add(interaction_id)
        self._cancellation_rules.pop(interaction_id, None)
        return True

    def end_interaction(self, interaction_id: str) -> None:
        self._open_interactions.discard(interaction_id)
        self._scheduled.pop(interaction_id, None)
        self._cancellation_rules.pop(interaction_id, None)

    async def runtime_events_after(
        self,
        after_sequence: int = 0,
        *,
        dispatch_id: str | None = None,
        limit: int = 256,
    ) -> list[CapabilityRuntimeEvent]:
        """Return retained lifecycle events after one consumer-owned cursor.

        Event history is observational Runtime state, not terminal Evidence. Multiple
        consumers may keep independent cursors without destructively consuming a queue.
        """

        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        async with self._event_condition:
            self._assert_event_cursor_available(after_sequence)
            events = [
                event
                for event in self._event_history
                if event.sequence > after_sequence
                and (dispatch_id is None or event.dispatch_id == dispatch_id)
            ]
            return events[:limit]

    async def wait_runtime_event(
        self,
        after_sequence: int = 0,
        *,
        dispatch_id: str | None = None,
    ) -> CapabilityRuntimeEvent:
        """Wait for the next lifecycle event after a consumer-owned cursor."""

        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        async with self._event_condition:
            while True:
                self._assert_event_cursor_available(after_sequence)
                for event in self._event_history:
                    if event.sequence <= after_sequence:
                        continue
                    if dispatch_id is None or event.dispatch_id == dispatch_id:
                        return event
                await self._event_condition.wait()

    def _assert_event_cursor_available(self, after_sequence: int) -> None:
        if not self._event_history:
            return
        oldest_sequence = self._event_history[0].sequence
        if after_sequence < oldest_sequence - 1:
            raise RuntimeError(
                "capability runtime event cursor expired: "
                f"cursor={after_sequence} oldest_retained={oldest_sequence}"
            )

    async def _publish_request_event(
        self,
        *,
        dispatch_id: str,
        interaction_id: str,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        event_type: CapabilityRuntimeEventType,
        message: str | None = None,
        progress: dict[str, Any] | None = None,
        result: CapabilityResult | None = None,
    ) -> CapabilityRuntimeEvent:
        async with self._event_condition:
            self._event_sequence += 1
            event = CapabilityRuntimeEvent(
                sequence=self._event_sequence,
                dispatch_id=dispatch_id,
                interaction_id=interaction_id,
                request_id=request.request_id,
                capability_id=request.capability_id,
                provider_id=definition.provider_id,
                type=event_type,
                message=message,
                progress=dict(progress or {}),
                result=result.model_copy(deep=True) if result is not None else None,
            )
            self._event_history.append(event)
            self._event_condition.notify_all()
            return event

    def _dispatch_id_for_interaction(self, interaction_id: str) -> str:
        try:
            return self._interaction_dispatch_ids[interaction_id]
        except KeyError as exc:
            raise RuntimeError(
                f"no active dispatch ownership for interaction_id={interaction_id!r}"
            ) from exc

    def _progress_publisher(
        self,
        interaction_id: str,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
    ) -> Callable[[dict[str, Any], str | None], Awaitable[None]]:
        async def publish(progress: dict[str, Any], message: str | None) -> None:
            await self._publish_request_event(
                dispatch_id=self._dispatch_id_for_interaction(interaction_id),
                interaction_id=interaction_id,
                request=request,
                definition=definition,
                event_type="progress",
                message=message,
                progress=progress,
            )

        return publish

    async def submit(
        self,
        response: InteractionResponse,
        *,
        authorization: RuntimeAuthorization | None = None,
    ) -> CapabilityDispatchReceipt:
        """Validate, register, and dispatch one capability scope without joining it.

        The returned receipt means Host validation and Runtime ownership
        registration succeeded and a Runtime-owned submission task exists. It
        does *not* mean any provider request has completed. Terminal completion
        is an explicit join through :meth:`wait_terminal`.
        """

        auto_managed = self.begin_interaction(response.interaction_id)
        try:
            authorization = authorization or RuntimeAuthorization()
            scheduled = self._scheduled_requests(response)
            validated = [self._validate_request(request, authorization) for request in scheduled]
        except BaseException:
            if auto_managed:
                self.end_interaction(response.interaction_id)
            raise

        dispatch_id = uuid4().hex
        event_cursor = self._event_sequence
        execution_registered = False
        start_gate = asyncio.Event()
        task: asyncio.Task[CapabilityRuntimeResult] | None = None
        try:
            async with self._active_lock:
                if response.interaction_id in self._executing_interactions:
                    raise ValueError(
                        "concurrent CapabilityRuntime.submit calls cannot reuse "
                        f"interaction_id={response.interaction_id!r}"
                    )
                self._executing_interactions.add(response.interaction_id)
                self._interaction_dispatch_ids[response.interaction_id] = dispatch_id
                execution_registered = True
                interaction_scheduled = self._scheduled.setdefault(
                    response.interaction_id,
                    {},
                )
                interaction_scheduled.update(
                    {request.request_id: (request, definition) for request, definition in validated}
                )
                task = asyncio.create_task(
                    self._run_submission(
                        response.interaction_id,
                        validated,
                        authorization,
                        auto_managed=auto_managed,
                        start_gate=start_gate,
                    ),
                    name=f"capability-dispatch:{response.interaction_id}:{dispatch_id}",
                )
                self._submissions[dispatch_id] = task
                self._dispatch_interactions[dispatch_id] = response.interaction_id

            for request, definition in validated:
                await self._publish_request_event(
                    dispatch_id=dispatch_id,
                    interaction_id=response.interaction_id,
                    request=request,
                    definition=definition,
                    event_type="accepted",
                )
            start_gate.set()
        except BaseException:
            if task is not None:
                task.cancel()
                start_gate.set()
            if execution_registered:
                async with self._active_lock:
                    self._scheduled.pop(response.interaction_id, None)
                    self._executing_interactions.discard(response.interaction_id)
                    if self._interaction_dispatch_ids.get(response.interaction_id) == dispatch_id:
                        self._interaction_dispatch_ids.pop(response.interaction_id, None)
                    self._submissions.pop(dispatch_id, None)
                    self._dispatch_interactions.pop(dispatch_id, None)
            if auto_managed:
                self.end_interaction(response.interaction_id)
            raise

        return CapabilityDispatchReceipt(
            dispatch_id=dispatch_id,
            interaction_id=response.interaction_id,
            request_ids=[request.request_id for request, _ in validated],
            event_cursor=event_cursor,
        )

    async def wait_terminal(
        self,
        receipt: CapabilityDispatchReceipt,
    ) -> CapabilityRuntimeResult:
        """Explicitly join one previously accepted Runtime submission."""

        async with self._active_lock:
            interaction_id = self._dispatch_interactions.get(receipt.dispatch_id)
            task = self._submissions.get(receipt.dispatch_id)
        if interaction_id is None or task is None:
            raise ValueError(f"unknown or already-consumed dispatch_id={receipt.dispatch_id!r}")
        if interaction_id != receipt.interaction_id:
            raise ValueError(
                "dispatch receipt interaction mismatch: "
                f"registered={interaction_id!r} receipt={receipt.interaction_id!r}"
            )
        try:
            return await task
        finally:
            if task.done():
                async with self._active_lock:
                    if self._submissions.get(receipt.dispatch_id) is task:
                        self._submissions.pop(receipt.dispatch_id, None)
                        self._dispatch_interactions.pop(receipt.dispatch_id, None)

    async def _run_submission(
        self,
        interaction_id: str,
        validated: list[tuple[CapabilityRequest, CapabilityDefinition]],
        authorization: RuntimeAuthorization,
        *,
        auto_managed: bool,
        start_gate: asyncio.Event,
    ) -> CapabilityRuntimeResult:
        results: list[CapabilityResult] = []
        traces: list[CapabilityTrace] = []
        try:
            await start_gate.wait()
            try:
                pending_parallel: list[tuple[CapabilityRequest, CapabilityDefinition]] = []
                for request, definition in validated:
                    if request.timing == "parallel" and definition.can_run_parallel:
                        pending_parallel.append((request, definition))
                        continue
                    if pending_parallel:
                        parallel_items = list(pending_parallel)
                        batch_results, batch_traces = await self._run_parallel(
                            interaction_id,
                            parallel_items,
                            authorization,
                        )
                        results.extend(batch_results)
                        traces.extend(batch_traces)
                        pending_parallel = []
                        if any(self._is_runtime_cancellation(result) for result in batch_results):
                            return CapabilityRuntimeResult(
                                interaction_id=interaction_id,
                                status="cancelled",
                                results=results,
                                traces=traces,
                            )
                        if any(
                            self._failure_blocks_following_requests(
                                interaction_id,
                                item,
                                item_definition,
                                result,
                            )
                            for (item, item_definition), result in zip(
                                parallel_items, batch_results, strict=True
                            )
                        ):
                            break
                    result, trace = await self._run_one(
                        interaction_id,
                        request,
                        definition,
                        authorization,
                    )
                    results.append(result)
                    traces.append(trace)
                    if self._is_runtime_cancellation(result):
                        return CapabilityRuntimeResult(
                            interaction_id=interaction_id,
                            status="cancelled",
                            results=results,
                            traces=traces,
                        )
                    if self._failure_blocks_following_requests(
                        interaction_id,
                        request,
                        definition,
                        result,
                    ):
                        break
                if pending_parallel:
                    batch_results, batch_traces = await self._run_parallel(
                        interaction_id,
                        pending_parallel,
                        authorization,
                    )
                    results.extend(batch_results)
                    traces.extend(batch_traces)
                    if any(self._is_runtime_cancellation(result) for result in batch_results):
                        return CapabilityRuntimeResult(
                            interaction_id=interaction_id,
                            status="cancelled",
                            results=results,
                            traces=traces,
                        )
            except asyncio.CancelledError:
                await asyncio.shield(self.cancel_interaction(interaction_id))
                return CapabilityRuntimeResult(
                    interaction_id=interaction_id,
                    status="cancelled",
                    results=results,
                    traces=traces,
                )

            cancelled_results = [result for result in results if result.status == "cancelled"]
            status = (
                "completed"
                if all(result.status == "completed" for result in results)
                else "cancelled"
                if cancelled_results
                and all(result.status in {"completed", "cancelled"} for result in results)
                and all(
                    str(result.reason_code or "").startswith("cancelled")
                    for result in cancelled_results
                )
                else "failed"
            )
            return CapabilityRuntimeResult(
                interaction_id=interaction_id,
                status=status,
                results=results,
                traces=traces,
            )
        finally:
            async with self._active_lock:
                self._scheduled.pop(interaction_id, None)
                self._executing_interactions.discard(interaction_id)
                self._interaction_dispatch_ids.pop(interaction_id, None)
            if auto_managed:
                self.end_interaction(interaction_id)

    def _failure_blocks_following_requests(
        self,
        interaction_id: str,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        result: CapabilityResult,
    ) -> bool:
        """Honor explicit runtime barriers without making all capabilities fail-fast.

        Most independent capabilities should still report their own outcomes even if a
        sibling fails.  A pre-action speech cue is different: when it promises
        an audible acknowledgement before an effect, a failed playback-start
        barrier must prevent the later effect from beginning.
        """

        metadata = request.args.get("metadata")
        reason_code = str(result.reason_code or "")
        cancellation_scope = ""
        if reason_code == "cancelled_before_start":
            rule = self._matching_cancellation_rule(
                interaction_id,
                request,
                definition,
            )
            if rule is not None:
                cancellation_scope = rule.effective_scope
        elif reason_code.startswith("cancelled_"):
            cancellation_scope = reason_code.removeprefix("cancelled_")
        elif reason_code.startswith("cancellation_failed_"):
            cancellation_scope = reason_code.removeprefix("cancellation_failed_")
        cancellation_closes_interaction = cancellation_scope in {
            "current_interaction",
            "global_emergency",
        }
        return bool(
            isinstance(metadata, dict)
            and metadata.get("abort_remaining_on_failure") is True
            and result.status != "completed"
            and not cancellation_closes_interaction
        )

    @staticmethod
    def _is_runtime_cancellation(result: CapabilityResult) -> bool:
        return result.status == "cancelled" and result.reason_code == "cancelled"

    async def cancel_all(self) -> None:
        await self.cancel_scope(
            CancellationDirective(
                source_turn_id="capability_runtime_cancel_all",
                requested_scope="global_emergency",
            )
        )

    async def cancel_interaction(self, interaction_id: str) -> None:
        await self.cancel_scope(
            CancellationDirective(
                source_turn_id="capability_runtime_cancel_interaction",
                requested_scope="current_interaction",
                foreground_interaction_id=interaction_id,
            )
        )

    async def cancel_scope(
        self,
        directive: CancellationDirective,
    ) -> CancellationDispatchReceipt:
        """Select active and queued work using trusted runtime bindings."""

        requested_scope = directive.requested_scope
        async with self._active_lock:
            known_interactions = {
                *self._open_interactions,
                *self._scheduled,
                *(key[0] for key in self._active),
            }
            if requested_scope in {
                "output_only",
                "current_interaction",
                "specific_goal",
            }:
                base_interaction_ids = (
                    [directive.foreground_interaction_id]
                    if directive.foreground_interaction_id in known_interactions
                    else []
                )
            else:
                base_interaction_ids = sorted(known_interactions)

            base_scheduled_items: list[tuple[str, CapabilityRequest, CapabilityDefinition]] = []
            for interaction_id in base_interaction_ids:
                for request, definition in self._scheduled.get(
                    interaction_id,
                    {},
                ).values():
                    base_scheduled_items.append((interaction_id, request, definition))

            effective_scope = requested_scope
            widened = False
            widening_reason = ""
            stale_binding_request_ids: set[str] = set()
            shared_owner_conflict_request_ids: set[str] = set()
            base_selected: list[tuple[str, CapabilityRequest, CapabilityDefinition]] = []
            for interaction_id, request, definition in base_scheduled_items:
                if requested_scope == "specific_goal":
                    binding = self._specific_goal_binding(
                        directive,
                        request,
                    )
                    if binding == "stale":
                        stale_binding_request_ids.add(request.request_id)
                        continue
                    if binding == "shared_owner_conflict":
                        shared_owner_conflict_request_ids.add(request.request_id)
                        continue
                    if binding == "match":
                        base_selected.append((interaction_id, request, definition))
                    continue
                if self._scope_matches_definition(
                    requested_scope,
                    definition,
                ):
                    base_selected.append((interaction_id, request, definition))

            # Provider-global cancellation has collateral effect only when an
            # eligible provider request has actually started. Arbiter waiters
            # and not-yet-started requests are cancelled locally and must not
            # trigger a provider call or scope widening.
            global_domains_required: set[CancellationDomain] = set()
            for interaction_id, request, definition in base_selected:
                active_item = self._active.get((interaction_id, request.request_id))
                if (
                    active_item is None
                    or (active_item[0].done() and active_item[3].provider_cancel_future is None)
                    or not active_item[3].provider_started
                    or not request.cancellable
                    or not definition.interruptible
                    or not self._provider_cancellation_is_global(definition)
                ):
                    continue
                global_domains_required.update(definition.cancellation_domains)

            domain_scope: dict[CancellationDomain, CancellationScope] = {
                "output": "output_only",
                "media_output": "media_output",
                "embodied_motion": "embodied_motion",
            }
            all_scheduled_items = [
                (interaction_id, request, definition)
                for interaction_id in sorted(known_interactions)
                for request, definition in self._scheduled.get(
                    interaction_id,
                    {},
                ).values()
            ]
            selected_by_key = {
                (interaction_id, request.request_id): (
                    interaction_id,
                    request,
                    definition,
                )
                for interaction_id, request, definition in base_selected
            }
            selection_scope_by_key: dict[
                tuple[str, str],
                CancellationScope,
            ] = {key: requested_scope for key in selected_by_key}
            rules_to_install: dict[
                str,
                list[_CancellationRule],
            ] = {}

            if global_domains_required and requested_scope != "global_emergency":
                widened = True
                ordered_domains = sorted(global_domains_required)
                widening_reason = (
                    "provider_supports_only_global_embodied_motion_cancel"
                    if ordered_domains == ["embodied_motion"]
                    else "provider_supports_only_global_output_cancel"
                    if ordered_domains == ["output"]
                    else (
                        "provider_supports_only_global_domain_cancel:" + ",".join(ordered_domains)
                    )
                )
                global_scopes = {domain_scope[item] for item in global_domains_required}
                if requested_scope == "specific_goal" and len(global_scopes) == 1:
                    effective_scope = next(iter(global_scopes))
                for interaction_id, request, definition in all_scheduled_items:
                    matching_domains = global_domains_required.intersection(
                        definition.cancellation_domains
                    )
                    if not matching_domains:
                        continue
                    key = (interaction_id, request.request_id)
                    selected_by_key[key] = (
                        interaction_id,
                        request,
                        definition,
                    )
                    item_scope = max(
                        (domain_scope[item] for item in matching_domains),
                        key=self._scope_priority,
                    )
                    selection_scope_by_key[key] = self._dominant_scope(
                        selection_scope_by_key.get(key, "none"),
                        item_scope,
                    )
                for interaction_id in sorted(known_interactions):
                    for item_scope in sorted(
                        global_scopes,
                        key=self._scope_priority,
                    ):
                        rules_to_install.setdefault(
                            interaction_id,
                            [],
                        ).append(
                            _CancellationRule(
                                directive=directive,
                                effective_scope=item_scope,
                            )
                        )
                for interaction_id in base_interaction_ids:
                    rules_to_install.setdefault(
                        interaction_id,
                        [],
                    ).append(
                        _CancellationRule(
                            directive=directive,
                            effective_scope=requested_scope,
                        )
                    )
            else:
                specific_goal_bound_to_open_interaction = (
                    requested_scope == "specific_goal" and bool(base_interaction_ids)
                )
                should_install = (
                    bool(base_selected)
                    or (
                        requested_scope
                        in {
                            "output_only",
                            "media_output",
                            "embodied_motion",
                            "current_interaction",
                            "global_emergency",
                        }
                    )
                    or specific_goal_bound_to_open_interaction
                )
                if should_install:
                    for interaction_id in base_interaction_ids:
                        rules_to_install.setdefault(
                            interaction_id,
                            [],
                        ).append(
                            _CancellationRule(
                                directive=directive,
                                effective_scope=requested_scope,
                            )
                        )

            for interaction_id, new_rules in rules_to_install.items():
                rules = self._cancellation_rules.setdefault(
                    interaction_id,
                    [],
                )
                for rule in new_rules:
                    if rule not in rules:
                        rules.append(rule)

            completed_active_keys = {
                key
                for key, item in self._active.items()
                if (item[0].done() and item[3].provider_cancel_future is None)
            }
            for key in completed_active_keys:
                selected_by_key.pop(key, None)
                selection_scope_by_key.pop(key, None)

            selected = list(selected_by_key.values())
            selected_keys = set(selected_by_key)
            active_selected = [
                (
                    key,
                    item,
                    selection_scope_by_key[key],
                )
                for key, item in self._active.items()
                if (
                    key in selected_keys
                    and (not item[0].done() or item[3].provider_cancel_future is not None)
                )
            ]

            locally_cancelled_items: list[
                tuple[
                    asyncio.Task[CapabilityResult],
                    CapabilityRequest,
                    CapabilityDefinition,
                    CapabilityExecutionContext,
                ]
            ] = []
            provider_cancel_items: list[
                tuple[
                    asyncio.Task[CapabilityResult],
                    CapabilityRequest,
                    CapabilityDefinition,
                    CapabilityExecutionContext,
                ]
            ] = []
            non_interruptible_keys: set[tuple[str, str]] = set()
            active_keys: set[tuple[str, str]] = set()
            for key, item, item_scope in active_selected:
                task, request, definition, context = item
                if task.done():
                    # The local provider coroutine may already have observed
                    # task cancellation while _run_one still awaits the
                    # provider-cancel dispatch assigned to this context.
                    # Keep that exact dispatch visible to concurrent callers.
                    active_keys.add(key)
                    context.cancellation_scope = self._dominant_scope(
                        context.cancellation_scope,
                        item_scope,
                    )
                    context.cancellation_reason_code = f"cancelled_{context.cancellation_scope}"
                    provider_cancel_items.append(item)
                    continue
                if context.provider_started:
                    active_keys.add(key)
                if not context.provider_started:
                    context.cancellation_scope = self._dominant_scope(
                        context.cancellation_scope,
                        item_scope,
                    )
                    context.cancellation_reason_code = f"cancelled_{context.cancellation_scope}"
                    task.cancel()
                    locally_cancelled_items.append(item)
                elif request.cancellable and definition.interruptible:
                    context.cancellation_scope = self._dominant_scope(
                        context.cancellation_scope,
                        item_scope,
                    )
                    context.cancellation_reason_code = f"cancelled_{context.cancellation_scope}"
                    task.cancel()
                    locally_cancelled_items.append(item)
                    provider_cancel_items.append(item)
                else:
                    non_interruptible_keys.add(key)

            provider_groups: dict[
                tuple[str, ...],
                list[
                    tuple[
                        asyncio.Task[CapabilityResult],
                        CapabilityRequest,
                        CapabilityDefinition,
                        CapabilityExecutionContext,
                    ]
                ],
            ] = {}
            for item in provider_cancel_items:
                _, request, definition, context = item
                provider_activity_id = str(
                    context.provider_state.get("provider_activity_id") or ""
                ).strip()
                if provider_activity_id:
                    group_key = (
                        "provider_activity",
                        definition.provider_id,
                        provider_activity_id,
                    )
                elif self._provider_cancellation_is_global(definition):
                    group_key = (
                        "global_domain",
                        definition.provider_id,
                        *sorted(definition.cancellation_domains),
                    )
                else:
                    group_key = (
                        "request",
                        context.interaction_id,
                        request.request_id,
                    )
                provider_groups.setdefault(group_key, []).append(item)

            provider_group_futures: list[
                tuple[
                    list[
                        tuple[
                            asyncio.Task[CapabilityResult],
                            CapabilityRequest,
                            CapabilityDefinition,
                            CapabilityExecutionContext,
                        ]
                    ],
                    asyncio.Future[str | None],
                ]
            ] = []
            for group_items in provider_groups.values():
                first_future = group_items[0][3].provider_cancel_future
                same_future_for_all = first_future is not None and all(
                    item[3].provider_cancel_future is first_future for item in group_items
                )
                same_source_for_all = all(
                    item[3].provider_cancel_source_turn_id == directive.source_turn_id
                    for item in group_items
                )
                prior_dispatch_succeeded = all(
                    item[3].provider_cancel_error is None for item in group_items
                )
                same_dispatch = same_future_for_all and (
                    not first_future.done() or same_source_for_all or prior_dispatch_succeeded
                )
                existing_future = first_future if same_dispatch else None
                if existing_future is None:
                    representative = group_items[0]
                    _, request, definition, context = representative
                    existing_future = asyncio.create_task(
                        self._invoke_provider_cancel(
                            self._providers[definition.provider_id],
                            request,
                            definition,
                            tuple(item[3] for item in group_items),
                        )
                    )
                for item in group_items:
                    item[3].provider_cancel_requested = True
                    item[3].provider_cancel_future = existing_future
                    item[3].provider_cancel_source_turn_id = directive.source_turn_id
                provider_group_futures.append((group_items, existing_future))

            interaction_ids = sorted(
                {
                    *base_interaction_ids,
                    *rules_to_install,
                }
            )
            # Preserve the trusted plan/scheduling order in cancellation
            # evidence. Request IDs are opaque digests and must never become a
            # semantic ordering key; changing a DTO field name may change those
            # digests without changing the Plan.
            selected_binding_order = tuple(selected_by_key)
            active_binding_order = tuple(
                key for key in selected_binding_order if key in active_keys
            )
            queued_binding_order = tuple(
                key for key in selected_binding_order if key not in active_keys
            )

        provider_results = await asyncio.gather(
            *(asyncio.shield(future) for _, future in provider_group_futures),
            return_exceptions=True,
        )
        provider_failures: dict[tuple[str, str], str] = {}
        for (group_items, _), result in zip(
            provider_group_futures,
            provider_results,
            strict=True,
        ):
            if isinstance(result, BaseException):
                error = f"{type(result).__name__}:{result}"
            else:
                error = str(result or "")
            if not error:
                continue
            for _, request, _, context in group_items:
                provider_failures[(context.interaction_id, request.request_id)] = error
        await asyncio.gather(
            *(item[0] for item in locally_cancelled_items),
            return_exceptions=True,
        )
        for _, request, _, context in provider_cancel_items:
            if context.provider_cancel_error:
                provider_failures[(context.interaction_id, request.request_id)] = (
                    context.provider_cancel_error
                )

        affected_goal_ids = {
            goal_id for _, request, _ in selected for goal_id in self._request_goal_ids(request)
        }
        cancel_requested_keys = {
            (context.interaction_id, request.request_id)
            for _, request, _, context in provider_cancel_items
        }

        def binding(key: tuple[str, str]) -> CancellationRequestBinding:
            return CancellationRequestBinding(
                interaction_id=key[0],
                request_id=key[1],
            )

        return CancellationDispatchReceipt(
            source_turn_id=directive.source_turn_id,
            requested_scope=requested_scope,
            effective_scope=effective_scope,
            interaction_ids=tuple(sorted(interaction_ids)),
            target_goal_ids=directive.target_goal_ids,
            expected_plan_id=directive.expected_plan_id,
            expected_plan_fingerprint=(directive.expected_plan_fingerprint),
            affected_goal_ids=tuple(sorted(affected_goal_ids)),
            selected_request_ids=tuple(key[1] for key in selected_binding_order),
            selected_request_bindings=tuple(binding(key) for key in selected_binding_order),
            active_request_ids=tuple(key[1] for key in active_binding_order),
            active_request_bindings=tuple(binding(key) for key in active_binding_order),
            queued_request_ids=tuple(key[1] for key in queued_binding_order),
            queued_request_bindings=tuple(binding(key) for key in queued_binding_order),
            cancel_requested_request_ids=tuple(sorted({key[1] for key in cancel_requested_keys})),
            cancel_requested_request_bindings=tuple(
                binding(key) for key in sorted(cancel_requested_keys)
            ),
            non_interruptible_request_ids=tuple(sorted({key[1] for key in non_interruptible_keys})),
            non_interruptible_request_bindings=tuple(
                binding(key) for key in sorted(non_interruptible_keys)
            ),
            shared_owner_conflict_request_ids=tuple(sorted(shared_owner_conflict_request_ids)),
            stale_binding_request_ids=tuple(sorted(stale_binding_request_ids)),
            provider_cancel_failures=tuple(
                (f"{request_id}:{provider_failures[(interaction_id, request_id)]}")
                for interaction_id, request_id in sorted(provider_failures)
            ),
            provider_cancel_failure_evidence=tuple(
                CancellationProviderFailure(
                    interaction_id=interaction_id,
                    request_id=request_id,
                    error=provider_failures[(interaction_id, request_id)],
                )
                for interaction_id, request_id in sorted(provider_failures)
            ),
            widened=widened,
            widening_reason=widening_reason,
        )

    @staticmethod
    def _scope_matches_definition(
        scope: CancellationScope,
        definition: CapabilityDefinition,
    ) -> bool:
        if scope in {"current_interaction", "global_emergency"}:
            return True
        if scope == "output_only":
            return "output" in definition.cancellation_domains
        if scope == "media_output":
            return "media_output" in definition.cancellation_domains
        if scope == "embodied_motion":
            return "embodied_motion" in definition.cancellation_domains
        return False

    @staticmethod
    def _provider_cancellation_is_global(
        definition: CapabilityDefinition,
    ) -> bool:
        return (
            str(definition.metadata.get("cancellation_granularity") or "request") == "global_domain"
        )

    @staticmethod
    def _scope_priority(scope: CancellationScope) -> int:
        return {
            "none": 0,
            "output_only": 10,
            "media_output": 15,
            "specific_goal": 20,
            "embodied_motion": 25,
            "current_interaction": 30,
            "global_emergency": 40,
        }[scope]

    @classmethod
    def _dominant_scope(
        cls,
        first: CancellationScope,
        second: CancellationScope,
    ) -> CancellationScope:
        return second if cls._scope_priority(second) >= cls._scope_priority(first) else first

    @staticmethod
    def _request_goal_ids(request: CapabilityRequest) -> set[str]:
        values: set[str] = set()
        for metadata in (
            request.metadata,
            request.args.get("metadata"),
        ):
            if not isinstance(metadata, dict):
                continue
            for key in ("source_goal_ids", "covers_goal_ids"):
                raw = metadata.get(key)
                if isinstance(raw, str):
                    raw = [raw]
                if not isinstance(raw, (list, tuple)):
                    continue
                values.update(str(item).strip() for item in raw if str(item).strip())
        return values

    @classmethod
    def _specific_goal_binding(
        cls,
        directive: CancellationDirective,
        request: CapabilityRequest,
    ) -> Literal[
        "match",
        "no_match",
        "stale",
        "shared_owner_conflict",
    ]:
        goal_ids = cls._request_goal_ids(request)
        targets = set(directive.target_goal_ids)
        if not goal_ids.intersection(targets):
            return "no_match"
        metadata = request.metadata
        if str(metadata.get("canonical_plan_id") or "") != str(
            directive.expected_plan_id or ""
        ) or str(metadata.get("canonical_plan_fingerprint") or "") != str(
            directive.expected_plan_fingerprint or ""
        ):
            return "stale"
        if not goal_ids.issubset(targets):
            return "shared_owner_conflict"
        return "match"

    def _matching_cancellation_rule(
        self,
        interaction_id: str,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
    ) -> _CancellationRule | None:
        matching: list[tuple[int, _CancellationRule]] = []
        for index, rule in enumerate(self._cancellation_rules.get(interaction_id, ())):
            if rule.effective_scope == "specific_goal":
                if (
                    self._specific_goal_binding(
                        rule.directive,
                        request,
                    )
                    == "match"
                ):
                    matching.append((index, rule))
            elif self._scope_matches_definition(
                rule.effective_scope,
                definition,
            ):
                matching.append((index, rule))
        if not matching:
            return None
        return max(
            matching,
            key=lambda item: (
                self._scope_priority(item[1].effective_scope),
                item[0],
            ),
        )[1]

    def scheduler_status(self) -> CapabilityRuntimeSchedulerStatus:
        snapshot = self._resource_arbiter.snapshot()
        return CapabilityRuntimeSchedulerStatus(
            max_concurrency=snapshot.max_concurrency,
            active_count=snapshot.active_count,
            waiting_count=snapshot.waiting_count,
            serial_active=snapshot.serial_active,
            serial_waiters=snapshot.serial_waiters,
            active_interaction_ids=sorted({interaction_id for interaction_id, _ in self._active}),
        )

    def _scheduled_requests(self, response: InteractionResponse) -> list[CapabilityRequest]:
        before: list[CapabilityRequest] = []
        after: list[CapabilityRequest] = []
        for speech in response.speech:
            request = self._speech_request(speech)
            (after if speech.timing == "after_capabilities" else before).append(request)
        scheduled = [*before, *response.capabilities, *after]
        vocal_positions = [
            index
            for index, request in enumerate(scheduled)
            if request.capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
        ]
        if vocal_positions:
            first_vocal_index = min(vocal_positions)
            for index, request in enumerate(list(scheduled)):
                if index >= first_vocal_index or request.capability_id != "chromie.speak":
                    continue
                args = dict(request.args)
                metadata = args.get("metadata")
                metadata = dict(metadata) if isinstance(metadata, dict) else {}
                metadata["wait_for_voice_release"] = True
                metadata["abort_remaining_on_failure"] = True
                args["metadata"] = metadata
                scheduled[index] = request.model_copy(update={"args": args})
        request_ids = [request.request_id for request in scheduled]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("scheduled request IDs must be unique within one interaction")
        return scheduled

    def _speech_request(self, speech: InteractionSpeech) -> CapabilityRequest:
        speech_metadata = dict(speech.metadata)
        playback_barrier = speech_metadata.get("wait_for_playback_start") is True
        if playback_barrier:
            speech_metadata["abort_remaining_on_failure"] = True
        authority_metadata = {
            key: speech_metadata[key]
            for key in (
                "source_goal_ids",
                "covers_goal_ids",
                "canonical_plan_id",
                "canonical_plan_fingerprint",
                "execution_lane",
                "coordination_id",
                "delivery_role",
                "lane_coordination_relation",
                "lane_start_policy",
                "lane_failure_policy",
                "parallel_with_activity",
            )
            if key in speech_metadata
        }
        return CapabilityRequest(
            request_id=speech.id,
            capability_id="chromie.speak",
            args={
                "text": speech.text,
                "style": speech.style,
                "priority": speech.priority,
                "interruptible": speech.interruptible,
                "metadata": speech_metadata,
            },
            timing=(
                "sequential"
                if playback_barrier or speech.timing in {"sequential", "after_capabilities"}
                else "parallel"
            ),
            timeout_ms=speech.timeout_ms,
            cancellable=speech.interruptible,
            metadata=authority_metadata,
        )

    def _validate_request(
        self,
        request: CapabilityRequest,
        authorization: RuntimeAuthorization,
    ) -> tuple[CapabilityRequest, CapabilityDefinition]:
        definition = self.registry.get(request.capability_id)
        if definition.provider_id not in self._providers:
            raise ValueError(
                f"capability {request.capability_id!r} has no registered provider {definition.provider_id!r}"
            )
        if request.capability_version and request.capability_version != definition.version:
            raise ValueError(
                f"capability {request.capability_id!r} version {request.capability_version!r} "
                f"does not match registered version {definition.version!r}"
            )
        if not definition.available:
            reason = definition.unavailable_reason or "unavailable"
            raise ValueError(f"capability {request.capability_id!r} is unavailable: {reason}")
        _validate_json_schema(request.args, definition.input_schema, path="args")
        confirmed = request.request_id in authorization.confirmed_request_ids
        if (request.requires_confirmation or definition.requires_confirmation) and not confirmed:
            raise ValueError(f"capability {request.capability_id!r} requires confirmation")
        if definition.requires_safety_monitor and not authorization.safety_monitor_active:
            raise ValueError(f"capability {request.capability_id!r} requires an active safety monitor")
        return request, definition

    @staticmethod
    def _provider_group_key(
        request: CapabilityRequest,
        definition: CapabilityDefinition,
    ) -> tuple[str, str] | None:
        if definition.metadata.get("provider_local_activity_compilation") is not True:
            return None
        # Provider-local embodied compilation follows the actual runtime parallel
        # batch, not Chromie's cross-lane coordination vocabulary. This lets
        # auxiliary Social Attention remain an Activity decoration while the body
        # provider still receives all simultaneous body members in one compile.
        return (definition.provider_id, "__parallel_body_batch__")

    async def _run_parallel(
        self,
        interaction_id: str,
        items: list[tuple[CapabilityRequest, CapabilityDefinition]],
        authorization: RuntimeAuthorization,
    ) -> tuple[list[CapabilityResult], list[CapabilityTrace]]:
        personal_voice_request_ids = [
            request.request_id
            for request, definition in items
            if definition.exclusive_group == "chromie.voice"
        ]
        if len(personal_voice_request_ids) > 1:
            raise ValueError(
                "parallel execution cannot contain multiple chromie.voice owners: "
                + ",".join(personal_voice_request_ids)
            )
        grouped_indices: dict[tuple[str, str], list[int]] = {}
        for index, (request, definition) in enumerate(items):
            provider = self._providers[definition.provider_id]
            group_key = self._provider_group_key(request, definition)
            if group_key is None or not callable(getattr(provider, "execute_group", None)):
                continue
            grouped_indices.setdefault(group_key, []).append(index)

        jobs: list[tuple[list[int], asyncio.Task[Any]]] = []
        consumed: set[int] = set()
        for indices in grouped_indices.values():
            if len(indices) < 2:
                continue
            consumed.update(indices)
            group_items = [items[index] for index in indices]
            jobs.append(
                (
                    indices,
                    asyncio.create_task(
                        self._run_provider_group(
                            interaction_id,
                            group_items,
                            authorization,
                        )
                    ),
                )
            )
        for index, (request, definition) in enumerate(items):
            if index in consumed:
                continue
            jobs.append(
                (
                    [index],
                    asyncio.create_task(
                        self._run_one(
                            interaction_id,
                            request,
                            definition,
                            authorization,
                        )
                    ),
                )
            )

        try:
            job_results = await asyncio.gather(*(task for _, task in jobs))
        except asyncio.CancelledError:
            for _, task in jobs:
                task.cancel()
            job_results = await asyncio.shield(
                asyncio.gather(
                    *(task for _, task in jobs),
                    return_exceptions=True,
                )
            )

        ordered: dict[int, tuple[CapabilityResult, CapabilityTrace]] = {}
        for (indices, _), outcome in zip(jobs, job_results, strict=True):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, asyncio.CancelledError):
                    raise outcome
                pairs = [
                    self._cancelled_pair(
                        interaction_id,
                        items[index][0],
                        items[index][1],
                        reason_code="cancelled",
                        message="capability execution was cancelled",
                    )
                    for index in indices
                ]
            elif len(indices) == 1:
                pairs = [outcome]
            else:
                pairs = list(outcome)
            if len(pairs) != len(indices):
                raise RuntimeError(
                    "provider-local group returned a different number of results "
                    "than scheduled requests"
                )
            for index, pair in zip(indices, pairs, strict=True):
                ordered[index] = pair

        completed = [ordered[index] for index in range(len(items))]
        return [item[0] for item in completed], [item[1] for item in completed]

    @staticmethod
    def _cancelled_pair(
        interaction_id: str,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        *,
        reason_code: str,
        message: str,
        scope: CancellationScope = "none",
    ) -> tuple[CapabilityResult, CapabilityTrace]:
        finished_at = datetime.now(timezone.utc)
        trace = CapabilityTrace(
            interaction_id=interaction_id,
            request_id=request.request_id,
            capability_id=request.capability_id,
            provider_id=definition.provider_id,
            status="cancelled",
            events=[
                CapabilityTraceEvent(type="validated"),
                CapabilityTraceEvent(
                    type="cancelled",
                    message=message,
                    data={
                        "reason_code": reason_code,
                        "cancellation_scope": scope,
                    },
                ),
            ],
            finished_at=finished_at,
        )
        result = CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            capability_version=definition.version,
            status="cancelled",
            provider_id=definition.provider_id,
            reason_code=reason_code,
            message=message,
            trace_id=trace.trace_id,
            started_at=trace.started_at,
            finished_at=finished_at,
        )
        return result, trace

    async def _run_provider_group(
        self,
        interaction_id: str,
        items: list[tuple[CapabilityRequest, CapabilityDefinition]],
        authorization: RuntimeAuthorization,
    ) -> list[tuple[CapabilityResult, CapabilityTrace]]:
        if len(items) < 2:
            raise ValueError("provider-local execution group requires at least two items")
        provider_ids = {definition.provider_id for _, definition in items}
        if len(provider_ids) != 1:
            raise ValueError("provider-local execution group spans multiple providers")
        provider_id = next(iter(provider_ids))
        provider = self._providers[provider_id]
        execute_group = getattr(provider, "execute_group", None)
        if not callable(execute_group):
            raise ValueError(f"provider {provider_id!r} does not implement execute_group")

        shared_state: dict[str, Any] = {
            "provider_group_request_ids": [request.request_id for request, _ in items]
        }
        traces: list[CapabilityTrace] = []
        contexts: list[CapabilityExecutionContext] = []
        for request, _definition in items:
            trace = CapabilityTrace(
                interaction_id=interaction_id,
                request_id=request.request_id,
                capability_id=request.capability_id,
                provider_id=provider_id,
                events=[CapabilityTraceEvent(type="validated")],
            )
            context = CapabilityExecutionContext(
                interaction_id=interaction_id,
                confirmed=request.request_id in authorization.confirmed_request_ids,
                safety_monitor_active=authorization.safety_monitor_active,
                provider_state=shared_state,
                progress_publisher=self._progress_publisher(
                    interaction_id, request, _definition
                ),
                trace=trace,
            )
            traces.append(trace)
            contexts.append(context)

        # Pydantic copies mutable inputs while validating each context.  Rebind
        # every group member to one actual provider-state object so the provider
        # activity identity written during compilation is visible to sibling
        # cancellation paths and the terminal correlated traces.
        shared_state = contexts[0].provider_state
        for context in contexts[1:]:
            context.provider_state = shared_state

        prestart_pairs: list[tuple[CapabilityResult, CapabilityTrace]] | None = None
        async with self._active_lock:
            cancellation_rules = [
                rule
                for (request, definition) in items
                if (
                    rule := self._matching_cancellation_rule(
                        interaction_id,
                        request,
                        definition,
                    )
                )
                is not None
            ]
            if cancellation_rules:
                scope = max(
                    (rule.effective_scope for rule in cancellation_rules),
                    key=self._scope_priority,
                )
                interaction_scheduled = self._scheduled.get(interaction_id)
                if interaction_scheduled is not None:
                    for request, _ in items:
                        interaction_scheduled.pop(request.request_id, None)
                prestart_pairs = [
                    self._cancelled_pair(
                        interaction_id,
                        request,
                        definition,
                        reason_code="cancelled_before_start",
                        message=(
                            "provider-local body activity was cancelled before start "
                            f"by scope={scope}"
                        ),
                        scope=scope,
                    )
                    for request, definition in items
                ]
        if prestart_pairs is not None:
            dispatch_id = self._dispatch_id_for_interaction(interaction_id)
            for (request, definition), (result, _trace) in zip(
                items, prestart_pairs, strict=True
            ):
                await self._publish_request_event(
                    dispatch_id=dispatch_id,
                    interaction_id=interaction_id,
                    request=request,
                    definition=definition,
                    event_type="cancelled",
                    message=result.message or None,
                    result=result,
                )
            return prestart_pairs

        async def invoke() -> list[CapabilityResult]:
            async with self._resource_arbiter.claim(
                can_run_parallel=True,
                exclusive_group=f"{provider_id}.compiled_body_activity",
            ):
                async with self._active_lock:
                    for trace, context in zip(traces, contexts, strict=True):
                        context.provider_started = True
                        trace.events.append(CapabilityTraceEvent(type="started"))
                dispatch_id = self._dispatch_id_for_interaction(interaction_id)
                for request, definition in items:
                    await self._publish_request_event(
                        dispatch_id=dispatch_id,
                        interaction_id=interaction_id,
                        request=request,
                        definition=definition,
                        event_type="running",
                    )
                return await execute_group(
                    [
                        (request, definition, context)
                        for (request, definition), context in zip(
                            items,
                            contexts,
                            strict=True,
                        )
                    ]
                )

        task = asyncio.create_task(invoke())
        active_keys = [(interaction_id, request.request_id) for request, _ in items]
        async with self._active_lock:
            for active_key, (request, definition), context in zip(
                active_keys,
                items,
                contexts,
                strict=True,
            ):
                self._active[active_key] = (
                    task,
                    request,
                    definition,
                    context,
                )

        timeout_s = max(
            (request.timeout_ms or definition.timeout_ms) / 1000.0 for request, definition in items
        )
        results: list[CapabilityResult]
        try:
            results = await asyncio.wait_for(task, timeout=timeout_s)
            active_scopes = [
                context.cancellation_scope
                for context in contexts
                if context.cancellation_scope != "none"
            ]
            if active_scopes:
                scope = max(active_scopes, key=self._scope_priority)
                cancel_error = await self._cancel_provider(
                    provider,
                    items[0][0],
                    items[0][1],
                    contexts[0],
                )
                results = self._group_terminal_results(
                    items,
                    status="failed" if cancel_error else "cancelled",
                    reason_code=(
                        f"cancellation_failed_{scope}" if cancel_error else f"cancelled_{scope}"
                    ),
                    message=(
                        "provider-local body activity returned after cancellation"
                        + (
                            f"; provider cancellation failed: {cancel_error}"
                            if cancel_error
                            else ""
                        )
                    ),
                )
        except TimeoutError:
            cancel_error = await self._cancel_provider(
                provider,
                items[0][0],
                items[0][1],
                contexts[0],
            )
            results = self._group_terminal_results(
                items,
                status="timed_out",
                reason_code="timeout",
                message=(
                    f"provider-local body activity exceeded {timeout_s:.3f}s timeout"
                    + (f"; provider cancellation failed: {cancel_error}" if cancel_error else "")
                ),
            )
        except asyncio.CancelledError:
            cancel_error = await asyncio.shield(
                self._cancel_provider(
                    provider,
                    items[0][0],
                    items[0][1],
                    contexts[0],
                )
            )
            results = self._group_terminal_results(
                items,
                status="failed" if cancel_error else "cancelled",
                reason_code=(
                    "cancellation_failed_current_interaction" if cancel_error else "cancelled"
                ),
                message=(
                    "provider-local body activity was cancelled"
                    + (f"; provider cancellation failed: {cancel_error}" if cancel_error else "")
                ),
            )
        except Exception as exc:
            results = self._group_terminal_results(
                items,
                status="failed",
                reason_code="provider_error",
                message=str(exc) or exc.__class__.__name__,
            )
        finally:
            async with self._active_lock:
                interaction_scheduled = self._scheduled.get(interaction_id)
                for active_key, (request, _) in zip(
                    active_keys,
                    items,
                    strict=True,
                ):
                    self._active.pop(active_key, None)
                    if interaction_scheduled is not None:
                        interaction_scheduled.pop(request.request_id, None)

        results = self._normalize_group_results(items, results)
        finished_at = datetime.now(timezone.utc)
        pairs: list[tuple[CapabilityResult, CapabilityTrace]] = []
        dispatch_id = self._dispatch_id_for_interaction(interaction_id)
        for result, trace, (request, definition) in zip(
            results,
            traces,
            items,
            strict=True,
        ):
            self._bind_result_authority(request, result)
            result.trace_id = trace.trace_id
            if result.started_at is None:
                result.started_at = trace.started_at
            if result.finished_at is None:
                result.finished_at = finished_at
            trace.status = result.status
            trace.finished_at = result.finished_at
            trace.events.append(
                CapabilityTraceEvent(
                    type=result.status,
                    message=result.message,
                    data={
                        "reason_code": result.reason_code,
                        "provider_local_group": True,
                        "provider_activity_id": contexts[0].provider_state.get(
                            "provider_activity_id"
                        ),
                    },
                )
            )
            await self._publish_request_event(
                dispatch_id=dispatch_id,
                interaction_id=interaction_id,
                request=request,
                definition=definition,
                event_type=result.status,
                message=result.message or None,
                result=result,
            )
            pairs.append((result, trace))
        return pairs

    @staticmethod
    def _group_terminal_results(
        items: list[tuple[CapabilityRequest, CapabilityDefinition]],
        *,
        status: str,
        reason_code: str,
        message: str,
    ) -> list[CapabilityResult]:
        return [
            CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status=status,
                provider_id=definition.provider_id,
                reason_code=reason_code,
                message=message,
            )
            for request, definition in items
        ]

    @classmethod
    def _normalize_group_results(
        cls,
        items: list[tuple[CapabilityRequest, CapabilityDefinition]],
        results: Any,
    ) -> list[CapabilityResult]:
        if not isinstance(results, list):
            return cls._group_terminal_results(
                items,
                status="failed",
                reason_code="invalid_group_result",
                message="provider-local execution group did not return a result list",
            )
        expected_request_ids = {request.request_id for request, _ in items}
        by_request_id: dict[str, CapabilityResult] = {}
        for result in results:
            if not isinstance(result, CapabilityResult):
                continue
            if result.request_id not in expected_request_ids:
                return cls._group_terminal_results(
                    items,
                    status="failed",
                    reason_code="provider_identity_mismatch",
                    message=(
                        "provider-local execution group returned an unknown request identity"
                    ),
                )
            if result.request_id in by_request_id:
                return cls._group_terminal_results(
                    items,
                    status="failed",
                    reason_code="invalid_group_result",
                    message="provider-local execution group returned duplicate request IDs",
                )
            by_request_id[result.request_id] = result
        normalized: list[CapabilityResult] = []
        for request, definition in items:
            result = by_request_id.get(request.request_id)
            if result is None:
                result = CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status="failed",
                    provider_id=definition.provider_id,
                    reason_code="member_result_missing",
                    message=("provider-local body activity omitted evidence for this member"),
                )
            normalized.append(cls._canonicalize_provider_result(request, definition, result))
        return normalized

    @staticmethod
    def _canonicalize_provider_result(
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        result: CapabilityResult,
    ) -> CapabilityResult:
        mismatches: dict[str, Any] = {}
        if result.request_id != request.request_id:
            mismatches["request_id"] = result.request_id
        if result.capability_id != request.capability_id:
            mismatches["capability_id"] = result.capability_id
        if result.provider_id not in {None, definition.provider_id}:
            mismatches["provider_id"] = result.provider_id
        if result.capability_version not in {None, definition.version}:
            mismatches["capability_version"] = result.capability_version
        if mismatches:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=definition.provider_id,
                reason_code="provider_identity_mismatch",
                message="provider result identity did not match Runtime-owned request identity",
                metadata={"provider_reported_identity": mismatches},
            )
        if result.status not in {"completed", "refused", "failed", "cancelled", "timed_out"}:
            return CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=definition.provider_id,
                reason_code="provider_non_terminal_result",
                message=(
                    "provider execute() returned a non-terminal status; terminal provider "
                    "completion must be represented by a terminal CapabilityResult"
                ),
                metadata={"provider_reported_status": result.status},
            )
        return result.model_copy(
            deep=True,
            update={
                "request_id": request.request_id,
                "capability_id": request.capability_id,
                "capability_version": definition.version,
                "provider_id": definition.provider_id,
            },
        )

    @staticmethod
    def _bind_result_authority(
        request: CapabilityRequest,
        result: CapabilityResult,
    ) -> CapabilityResult:
        """Retain Host-owned request provenance on terminal evidence.

        Providers own execution output and provider-local metadata, but they do
        not own canonical Goal or Plan identity. Copy the committed request's
        bounded authority fields onto the result after provider execution so a
        provider cannot omit or replace the ownership required for outcome
        reconciliation and retained evidence.
        """

        authority = {
            key: request.metadata[key]
            for key in _RESULT_AUTHORITY_METADATA_KEYS
            if key in request.metadata
        }
        if authority:
            result.metadata = {**result.metadata, **authority}
        return result

    async def _run_one(
        self,
        interaction_id: str,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        authorization: RuntimeAuthorization,
    ) -> tuple[CapabilityResult, CapabilityTrace]:
        provider = self._providers[definition.provider_id]
        trace = CapabilityTrace(
            interaction_id=interaction_id,
            request_id=request.request_id,
            capability_id=request.capability_id,
            provider_id=definition.provider_id,
            events=[CapabilityTraceEvent(type="validated")],
        )
        context = CapabilityExecutionContext(
            interaction_id=interaction_id,
            confirmed=request.request_id in authorization.confirmed_request_ids,
            safety_monitor_active=authorization.safety_monitor_active,
            progress_publisher=self._progress_publisher(
                interaction_id, request, definition
            ),
            trace=trace,
        )
        timeout_s = (request.timeout_ms or definition.timeout_ms) / 1000.0

        async def invoke() -> CapabilityResult:
            async with self._resource_arbiter.claim(
                can_run_parallel=definition.can_run_parallel,
                exclusive_group=definition.exclusive_group,
            ):
                async with self._active_lock:
                    context.provider_started = True
                    trace.events.append(CapabilityTraceEvent(type="started"))
                await self._publish_request_event(
                    dispatch_id=self._dispatch_id_for_interaction(interaction_id),
                    interaction_id=interaction_id,
                    request=request,
                    definition=definition,
                    event_type="running",
                )
                return await provider.execute(request, definition, context)

        active_key = (interaction_id, request.request_id)
        prestart_result: CapabilityResult | None = None
        async with self._active_lock:
            cancellation_rule = self._matching_cancellation_rule(
                interaction_id,
                request,
                definition,
            )
            if cancellation_rule is not None:
                interaction_scheduled = self._scheduled.get(interaction_id)
                if interaction_scheduled is not None:
                    interaction_scheduled.pop(request.request_id, None)
                finished_at = datetime.now(timezone.utc)
                prestart_result = CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status="cancelled",
                    provider_id=definition.provider_id,
                    reason_code="cancelled_before_start",
                    message=(
                        "capability execution was cancelled before provider start "
                        f"by scope={cancellation_rule.effective_scope}"
                    ),
                    trace_id=trace.trace_id,
                    started_at=trace.started_at,
                    finished_at=finished_at,
                )
                trace.status = "cancelled"
                trace.finished_at = finished_at
                trace.events.append(
                    CapabilityTraceEvent(
                        type="cancelled",
                        message=prestart_result.message,
                        data={
                            "reason_code": "cancelled_before_start",
                            "cancellation_scope": (cancellation_rule.effective_scope),
                        },
                    )
                )
            else:
                task = asyncio.create_task(invoke())
                self._active[active_key] = (task, request, definition, context)
        if prestart_result is not None:
            await self._publish_request_event(
                dispatch_id=self._dispatch_id_for_interaction(interaction_id),
                interaction_id=interaction_id,
                request=request,
                definition=definition,
                event_type="cancelled",
                message=prestart_result.message or None,
                result=prestart_result,
            )
            return prestart_result, trace
        try:
            result = await asyncio.wait_for(task, timeout=timeout_s)
            if context.cancellation_scope != "none":
                # A provider coroutine is not allowed to turn a selected
                # cancellation back into completion by swallowing task
                # cancellation. The trusted cancellation dispatch is the
                # terminal authority for this request.
                cancel_error = (
                    await self._cancel_provider(
                        provider,
                        request,
                        definition,
                        context,
                    )
                    if context.provider_started
                    else None
                )
                scoped_cancel_failed = bool(cancel_error)
                result = CapabilityResult(
                    request_id=request.request_id,
                    capability_id=request.capability_id,
                    capability_version=definition.version,
                    status=("failed" if scoped_cancel_failed else "cancelled"),
                    provider_id=definition.provider_id,
                    reason_code=(
                        f"cancellation_failed_{context.cancellation_scope}"
                        if scoped_cancel_failed
                        else context.cancellation_reason_code
                    ),
                    message=(
                        "provider execution returned after cancellation "
                        "was selected"
                        + (
                            f"; provider cancellation was not confirmed: {cancel_error}"
                            if cancel_error
                            else ""
                        )
                    ),
                )
        except TimeoutError:
            cancel_error = (
                await self._cancel_provider(
                    provider,
                    request,
                    definition,
                    context,
                )
                if context.provider_started
                else None
            )
            result = CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="timed_out",
                provider_id=definition.provider_id,
                reason_code="timeout",
                message=(
                    f"capability exceeded {timeout_s:.3f}s timeout"
                    + (f"; provider cancellation failed: {cancel_error}" if cancel_error else "")
                ),
            )
        except asyncio.CancelledError:
            cancel_error: str | None = None
            cancelled_before_provider = not context.provider_started
            if context.provider_started and request.cancellable and definition.interruptible:
                cancel_error = await asyncio.shield(
                    self._cancel_provider(
                        provider,
                        request,
                        definition,
                        context,
                    )
                )
            scoped_cancel_failed = bool(
                cancel_error and context.cancellation_reason_code != "cancelled"
            )
            result = CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed" if scoped_cancel_failed else "cancelled",
                provider_id=definition.provider_id,
                reason_code=(
                    f"cancellation_failed_{context.cancellation_scope}"
                    if scoped_cancel_failed
                    else "cancelled_before_start"
                    if cancelled_before_provider
                    else context.cancellation_reason_code
                ),
                message=(
                    (
                        "local execution was interrupted, but provider "
                        "cancellation was not confirmed"
                        if scoped_cancel_failed
                        else "capability execution was cancelled before provider start"
                        if cancelled_before_provider
                        else "capability execution was cancelled"
                    )
                    + (
                        f" by scope={context.cancellation_scope}"
                        if context.cancellation_scope != "none"
                        else ""
                    )
                    + (f"; provider cancellation failed: {cancel_error}" if cancel_error else "")
                ),
            )
        except Exception as exc:
            result = CapabilityResult(
                request_id=request.request_id,
                capability_id=request.capability_id,
                capability_version=definition.version,
                status="failed",
                provider_id=definition.provider_id,
                reason_code="provider_error",
                message=str(exc) or exc.__class__.__name__,
            )
        finally:
            async with self._active_lock:
                self._active.pop(active_key, None)
                interaction_scheduled = self._scheduled.get(interaction_id)
                if interaction_scheduled is not None:
                    interaction_scheduled.pop(request.request_id, None)

        result = self._canonicalize_provider_result(request, definition, result)
        self._bind_result_authority(request, result)
        result.trace_id = trace.trace_id
        trace.status = result.status
        trace.finished_at = datetime.now(timezone.utc)
        if result.started_at is None:
            result.started_at = trace.started_at
        if result.finished_at is None:
            result.finished_at = trace.finished_at
        trace.events.append(
            CapabilityTraceEvent(
                type=result.status,
                message=result.message,
                data={"reason_code": result.reason_code},
            )
        )
        await self._publish_request_event(
            dispatch_id=self._dispatch_id_for_interaction(interaction_id),
            interaction_id=interaction_id,
            request=request,
            definition=definition,
            event_type=result.status,
            message=result.message or None,
            result=result,
        )
        return result, trace

    async def _cancel_provider(
        self,
        provider: CapabilityProvider,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> str | None:
        in_flight = context.provider_cancel_future
        if in_flight is not None:
            return await asyncio.shield(in_flight)
        completion = asyncio.create_task(
            self._invoke_provider_cancel(
                provider,
                request,
                definition,
                (context,),
            )
        )
        context.provider_cancel_future = completion
        context.provider_cancel_requested = True
        return await asyncio.shield(completion)

    @staticmethod
    async def _invoke_provider_cancel(
        provider: CapabilityProvider,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        contexts: tuple[CapabilityExecutionContext, ...],
    ) -> str | None:
        error: str | None = None
        try:
            await provider.cancel(request, definition, contexts[0])
        except asyncio.CancelledError:
            error = "provider cancellation coroutine was cancelled"
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            logger.warning(
                "Capability provider cancellation failed request_id=%s capability_id=%s "
                "provider_id=%s error=%s",
                request.request_id,
                request.capability_id,
                definition.provider_id,
                error,
            )
        finally:
            for context in contexts:
                context.provider_cancel_requested = True
                context.provider_cancel_error = error
        return error


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
        raw = self._handler(request.args)
        output = await raw if inspect.isawaitable(raw) else raw
        metadata = request.args.get("metadata")
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


def local_speech_definition() -> CapabilityDefinition:
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
        timeout_ms=30000,
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


def _validate_json_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    if not schema:
        return
    schema_type = schema.get("type")
    allowed_types = (
        schema_type if isinstance(schema_type, list) else [schema_type] if schema_type else []
    )
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
