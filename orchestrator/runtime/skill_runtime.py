from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

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
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    CancellationProviderFailure,
    CancellationRequestBinding,
    CancellationScope,
)

logger = logging.getLogger(__name__)

CancellationDomain = Literal["output", "embodied_motion"]


SORIDORMI_NAMED_SKILL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "completed": {"type": "boolean"},
        "skill_id": {"type": "string"},
        "mode": {"type": "string"},
        "no_motion": {"type": "boolean"},
        "recommendation_only": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": [
        "completed",
        "skill_id",
        "mode",
        "no_motion",
        "recommendation_only",
        "summary",
    ],
    "additionalProperties": False,
}


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
    cancellation_domains: tuple[CancellationDomain, ...] = ()
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
        """Atomically replace the live Soridormi named-skill view.

        Soridormi owns the body-side catalog, but Chromie owns the adapter
        result contract. Every imported named skill therefore exposes the same
        closed, model-safe execution-result schema while retaining the live
        input, availability, scheduling, and safety metadata. A malformed or
        duplicate entry rejects the whole refresh instead of partially
        mutating the trusted registry.
        """

        imported: dict[str, SkillDefinition] = {}
        for raw_item in skills:
            if not isinstance(raw_item, dict):
                raise ValueError("Soridormi skill catalog entries must be objects")
            item = dict(raw_item)
            upstream_id = str(item.get("skill_id", "")).strip()
            if not upstream_id:
                raise ValueError("Soridormi skill catalog entry has no skill_id")
            skill_id = f"soridormi.{upstream_id}"
            if skill_id in imported:
                raise ValueError(
                    f"duplicate Soridormi skill_id in one catalog: {upstream_id}"
                )

            execution = item.get("execution")
            execution_contract = execution if isinstance(execution, dict) else {}
            availability = item.get("availability")
            availability_contract = (
                availability if isinstance(availability, dict) else {}
            )
            confirmation = item.get("confirmation")
            confirmation_contract = (
                confirmation if isinstance(confirmation, dict) else {}
            )
            effects_raw = item.get("effects")
            if effects_raw is None:
                effects = ["physical_motion"]
            elif isinstance(effects_raw, list):
                effects = [
                    str(value)
                    for value in effects_raw
                    if str(value).strip()
                ]
            else:
                raise ValueError(
                    f"Soridormi skill {upstream_id!r} effects must be a list"
                )
            safety_class = str(item.get("safety_class") or "physical_motion")
            provider_requires_confirmation = bool(
                item.get(
                    "requires_confirmation",
                    confirmation_contract.get("required", False),
                )
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
            timeout_s = item.get(
                "timeout_s",
                execution_contract.get("timeout_s", 30.0),
            )
            can_run_parallel = item.get(
                "can_run_parallel",
                execution_contract.get("can_run_parallel", True),
            )
            exclusive_group = (
                str(
                    item.get("exclusive_group")
                    or execution_contract.get("exclusive_group")
                    or ""
                ).strip()
                or "soridormi.robot_motion"
            )
            input_schema = (
                item.get("parameters_schema")
                or item.get("input_schema")
                or {}
            )
            if not isinstance(input_schema, dict):
                raise ValueError(
                    f"Soridormi skill {upstream_id!r} input schema must be an object"
                )
            resource_claims = item.get(
                "resource_claims",
                execution_contract.get("resource_claims", []),
            )
            if not isinstance(resource_claims, list):
                raise ValueError(
                    f"Soridormi skill {upstream_id!r} resource_claims must be a list"
                )

            upstream_metadata = item.get("metadata")
            if not isinstance(upstream_metadata, dict):
                upstream_metadata = {}
            execution_constraints = item.get(
                "execution_constraints",
                execution_contract.get("execution_constraints", {}),
            )
            if not isinstance(execution_constraints, dict):
                raise ValueError(
                    f"Soridormi skill {upstream_id!r} execution_constraints must be an object"
                )

            imported[skill_id] = SkillDefinition(
                skill_id=skill_id,
                version=str(item.get("version") or version),
                provider_id=provider_id,
                description=str(item.get("description") or ""),
                input_schema=dict(input_schema),
                output_schema=SORIDORMI_NAMED_SKILL_OUTPUT_SCHEMA,
                available=bool(
                    item.get(
                        "available",
                        availability_contract.get("available", True),
                    )
                ),
                unavailable_reason=(
                    item.get("unavailable_reason")
                    or availability_contract.get("reason")
                ),
                requires_confirmation=effective_requires_confirmation,
                interruptible=bool(item.get("interruptible", False)),
                can_run_parallel=bool(can_run_parallel),
                exclusive_group=exclusive_group,
                timeout_ms=max(1, int(float(timeout_s or 30.0) * 1000)),
                idempotent=False,
                requires_safety_monitor=False,
                cancellation_domains=(
                    ("embodied_motion",)
                    if "physical_motion" in effects
                    else ()
                ),
                metadata={
                    "upstream_skill_id": upstream_id,
                    "effects": effects,
                    "safety_class": safety_class,
                    "cancellation_granularity": (
                        "global_domain"
                        if "physical_motion" in effects
                        else "request"
                    ),
                    "execution": execution,
                    "fallback": item.get("fallback"),
                    "hardware_enabled": item.get("hardware_enabled"),
                    "provider_managed_safety_monitor": True,
                    "resource_claims": [
                        str(value)
                        for value in resource_claims
                        if str(value).strip()
                    ],
                    "execution_constraints": dict(execution_constraints),
                    "output_contract": "chromie_soridormi_named_skill_v1",
                    "behavior_domains": [
                        str(value)
                        for value in upstream_metadata.get("behavior_domains", [])
                        if str(value).strip()
                    ],
                },
            )

        updated = dict(self._skills)
        updated.update(imported)
        if mark_absent_unavailable:
            for skill_id, definition in list(updated.items()):
                if (
                    definition.provider_id == provider_id
                    and skill_id.startswith("soridormi.")
                    and skill_id not in imported
                ):
                    updated[skill_id] = definition.model_copy(
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
        self._skills = updated



class SkillExecutionContext(BaseModel):
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


@dataclass(frozen=True)
class _CancellationRule:
    directive: CancellationDirective
    effective_scope: CancellationScope


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
        self._open_interactions: set[str] = set()
        self._executing_interactions: set[str] = set()
        self._scheduled: dict[
            str,
            dict[str, tuple[SkillRequest, SkillDefinition]],
        ] = {}
        self._cancellation_rules: dict[str, list[_CancellationRule]] = {}

    def register_provider(self, provider: SkillProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"duplicate skill provider: {provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def provider_ids(self) -> set[str]:
        return set(self._providers)

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

    async def execute(
        self,
        response: InteractionResponse,
        *,
        authorization: RuntimeAuthorization | None = None,
    ) -> SkillRuntimeResult:
        auto_managed = self.begin_interaction(response.interaction_id)
        try:
            authorization = authorization or RuntimeAuthorization()
            scheduled = self._scheduled_requests(response)
            validated = [
                self._validate_request(request, authorization)
                for request in scheduled
            ]
        except BaseException:
            if auto_managed:
                self.end_interaction(response.interaction_id)
            raise
        results: list[SkillResult] = []
        traces: list[SkillTrace] = []
        execution_registered = False

        try:
            async with self._active_lock:
                if response.interaction_id in self._executing_interactions:
                    raise ValueError(
                        "concurrent SkillRuntime.execute calls cannot reuse "
                        f"interaction_id={response.interaction_id!r}"
                    )
                self._executing_interactions.add(response.interaction_id)
                execution_registered = True
                interaction_scheduled = self._scheduled.setdefault(
                    response.interaction_id,
                    {},
                )
                interaction_scheduled.update(
                    {
                        request.request_id: (request, definition)
                        for request, definition in validated
                    }
                )
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
                            self._failure_blocks_following_requests(
                                response.interaction_id,
                                item,
                                definition,
                                result,
                            )
                            for (item, definition), result in zip(
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
                    if self._failure_blocks_following_requests(
                        response.interaction_id,
                        request,
                        definition,
                        result,
                    ):
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

            cancelled_results = [
                result for result in results if result.status == "cancelled"
            ]
            status = (
                "completed"
                if all(result.status == "completed" for result in results)
                else "cancelled"
                if cancelled_results
                and all(
                    result.status in {"completed", "cancelled"}
                    for result in results
                )
                and all(
                    str(result.reason_code or "").startswith("cancelled")
                    for result in cancelled_results
                )
                else "failed"
            )
            return SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status=status,
                results=results,
                traces=traces,
            )
        finally:
            if execution_registered:
                async with self._active_lock:
                    self._scheduled.pop(response.interaction_id, None)
                    self._executing_interactions.discard(
                        response.interaction_id
                    )
            if auto_managed:
                self.end_interaction(response.interaction_id)

    def _failure_blocks_following_requests(
        self,
        interaction_id: str,
        request: SkillRequest,
        definition: SkillDefinition,
        result: SkillResult,
    ) -> bool:
        """Honor explicit runtime barriers without making all skills fail-fast.

        Most independent skills should still report their own outcomes even if a
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
            cancellation_scope = reason_code.removeprefix(
                "cancellation_failed_"
            )
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
    def _is_runtime_cancellation(result: SkillResult) -> bool:
        return (
            result.status == "cancelled"
            and result.reason_code == "cancelled"
        )

    async def cancel_all(self) -> None:
        await self.cancel_scope(
            CancellationDirective(
                source_turn_id="skill_runtime_cancel_all",
                requested_scope="global_emergency",
            )
        )

    async def cancel_interaction(self, interaction_id: str) -> None:
        await self.cancel_scope(
            CancellationDirective(
                source_turn_id="skill_runtime_cancel_interaction",
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

            base_scheduled_items: list[
                tuple[str, SkillRequest, SkillDefinition]
            ] = []
            for interaction_id in base_interaction_ids:
                for request, definition in self._scheduled.get(
                    interaction_id,
                    {},
                ).values():
                    base_scheduled_items.append(
                        (interaction_id, request, definition)
                    )

            effective_scope = requested_scope
            widened = False
            widening_reason = ""
            stale_binding_request_ids: set[str] = set()
            shared_owner_conflict_request_ids: set[str] = set()
            base_selected: list[
                tuple[str, SkillRequest, SkillDefinition]
            ] = []
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
                        shared_owner_conflict_request_ids.add(
                            request.request_id
                        )
                        continue
                    if binding == "match":
                        base_selected.append(
                            (interaction_id, request, definition)
                        )
                    continue
                if self._scope_matches_definition(
                    requested_scope,
                    definition,
                ):
                    base_selected.append(
                        (interaction_id, request, definition)
                    )

            # Provider-global cancellation has collateral effect only when an
            # eligible provider request has actually started. Arbiter waiters
            # and not-yet-started requests are cancelled locally and must not
            # trigger a provider call or scope widening.
            global_domains_required: set[CancellationDomain] = set()
            for interaction_id, request, definition in base_selected:
                active_item = self._active.get(
                    (interaction_id, request.request_id)
                )
                if (
                    active_item is None
                    or (
                        active_item[0].done()
                        and active_item[3].provider_cancel_future is None
                    )
                    or not active_item[3].provider_started
                    or not request.cancellable
                    or not definition.interruptible
                    or not self._provider_cancellation_is_global(definition)
                ):
                    continue
                global_domains_required.update(
                    definition.cancellation_domains
                )

            domain_scope: dict[CancellationDomain, CancellationScope] = {
                "output": "output_only",
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
            ] = {
                key: requested_scope for key in selected_by_key
            }
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
                        "provider_supports_only_global_domain_cancel:"
                        + ",".join(ordered_domains)
                    )
                )
                global_scopes = {
                    domain_scope[item]
                    for item in global_domains_required
                }
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
                    requested_scope == "specific_goal"
                    and bool(base_interaction_ids)
                )
                should_install = bool(base_selected) or (
                    requested_scope
                    in {
                        "output_only",
                        "embodied_motion",
                        "current_interaction",
                        "global_emergency",
                    }
                ) or specific_goal_bound_to_open_interaction
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
                if (
                    item[0].done()
                    and item[3].provider_cancel_future is None
                )
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
                    and (
                        not item[0].done()
                        or item[3].provider_cancel_future is not None
                    )
                )
            ]

            locally_cancelled_items: list[
                tuple[
                    asyncio.Task[SkillResult],
                    SkillRequest,
                    SkillDefinition,
                    SkillExecutionContext,
                ]
            ] = []
            provider_cancel_items: list[
                tuple[
                    asyncio.Task[SkillResult],
                    SkillRequest,
                    SkillDefinition,
                    SkillExecutionContext,
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
                    context.cancellation_reason_code = (
                        f"cancelled_{context.cancellation_scope}"
                    )
                    provider_cancel_items.append(item)
                    continue
                if context.provider_started:
                    active_keys.add(key)
                if not context.provider_started:
                    context.cancellation_scope = self._dominant_scope(
                        context.cancellation_scope,
                        item_scope,
                    )
                    context.cancellation_reason_code = (
                        f"cancelled_{context.cancellation_scope}"
                    )
                    task.cancel()
                    locally_cancelled_items.append(item)
                elif request.cancellable and definition.interruptible:
                    context.cancellation_scope = self._dominant_scope(
                        context.cancellation_scope,
                        item_scope,
                    )
                    context.cancellation_reason_code = (
                        f"cancelled_{context.cancellation_scope}"
                    )
                    task.cancel()
                    locally_cancelled_items.append(item)
                    provider_cancel_items.append(item)
                else:
                    non_interruptible_keys.add(key)

            provider_groups: dict[
                tuple[str, ...],
                list[
                    tuple[
                        asyncio.Task[SkillResult],
                        SkillRequest,
                        SkillDefinition,
                        SkillExecutionContext,
                    ]
                ],
            ] = {}
            for item in provider_cancel_items:
                _, request, definition, context = item
                if self._provider_cancellation_is_global(definition):
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
                            asyncio.Task[SkillResult],
                            SkillRequest,
                            SkillDefinition,
                            SkillExecutionContext,
                        ]
                    ],
                    asyncio.Future[str | None],
                ]
            ] = []
            for group_items in provider_groups.values():
                first_future = group_items[0][
                    3
                ].provider_cancel_future
                same_future_for_all = (
                    first_future is not None
                    and all(
                        item[3].provider_cancel_future is first_future
                        for item in group_items
                    )
                )
                same_source_for_all = all(
                    item[3].provider_cancel_source_turn_id
                    == directive.source_turn_id
                    for item in group_items
                )
                prior_dispatch_succeeded = all(
                    item[3].provider_cancel_error is None
                    for item in group_items
                )
                same_dispatch = (
                    same_future_for_all
                    and (
                        not first_future.done()
                        or same_source_for_all
                        or prior_dispatch_succeeded
                    )
                )
                existing_future = (
                    first_future if same_dispatch else None
                )
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
                    item[3].provider_cancel_source_turn_id = (
                        directive.source_turn_id
                    )
                provider_group_futures.append(
                    (group_items, existing_future)
                )

            interaction_ids = sorted(
                {
                    *base_interaction_ids,
                    *rules_to_install,
                }
            )
            selected_binding_keys = set(selected_keys)
            queued_keys = selected_binding_keys - active_keys

        provider_results = await asyncio.gather(
            *(
                asyncio.shield(future)
                for _, future in provider_group_futures
            ),
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
                provider_failures[
                    (context.interaction_id, request.request_id)
                ] = error
        await asyncio.gather(
            *(item[0] for item in locally_cancelled_items),
            return_exceptions=True,
        )
        for _, request, _, context in provider_cancel_items:
            if context.provider_cancel_error:
                provider_failures[
                    (context.interaction_id, request.request_id)
                ] = context.provider_cancel_error

        affected_goal_ids = {
            goal_id
            for _, request, _ in selected
            for goal_id in self._request_goal_ids(request)
        }
        cancel_requested_keys = {
            (context.interaction_id, request.request_id)
            for _, request, _, context in provider_cancel_items
        }
        binding = lambda key: CancellationRequestBinding(
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
            expected_plan_fingerprint=(
                directive.expected_plan_fingerprint
            ),
            affected_goal_ids=tuple(sorted(affected_goal_ids)),
            selected_request_ids=tuple(
                sorted({key[1] for key in selected_binding_keys})
            ),
            selected_request_bindings=tuple(
                binding(key) for key in sorted(selected_binding_keys)
            ),
            active_request_ids=tuple(
                sorted({key[1] for key in active_keys})
            ),
            active_request_bindings=tuple(
                binding(key) for key in sorted(active_keys)
            ),
            queued_request_ids=tuple(
                sorted({key[1] for key in queued_keys})
            ),
            queued_request_bindings=tuple(
                binding(key) for key in sorted(queued_keys)
            ),
            cancel_requested_request_ids=tuple(
                sorted({key[1] for key in cancel_requested_keys})
            ),
            cancel_requested_request_bindings=tuple(
                binding(key) for key in sorted(cancel_requested_keys)
            ),
            non_interruptible_request_ids=tuple(
                sorted({key[1] for key in non_interruptible_keys})
            ),
            non_interruptible_request_bindings=tuple(
                binding(key) for key in sorted(non_interruptible_keys)
            ),
            shared_owner_conflict_request_ids=tuple(
                sorted(shared_owner_conflict_request_ids)
            ),
            stale_binding_request_ids=tuple(
                sorted(stale_binding_request_ids)
            ),
            provider_cancel_failures=tuple(
                (
                    f"{request_id}:"
                    f"{provider_failures[(interaction_id, request_id)]}"
                )
                for interaction_id, request_id in sorted(provider_failures)
            ),
            provider_cancel_failure_evidence=tuple(
                CancellationProviderFailure(
                    interaction_id=interaction_id,
                    request_id=request_id,
                    error=provider_failures[
                        (interaction_id, request_id)
                    ],
                )
                for interaction_id, request_id in sorted(provider_failures)
            ),
            widened=widened,
            widening_reason=widening_reason,
        )

    @staticmethod
    def _scope_matches_definition(
        scope: CancellationScope,
        definition: SkillDefinition,
    ) -> bool:
        if scope in {"current_interaction", "global_emergency"}:
            return True
        if scope == "output_only":
            return "output" in definition.cancellation_domains
        if scope == "embodied_motion":
            return "embodied_motion" in definition.cancellation_domains
        return False

    @staticmethod
    def _provider_cancellation_is_global(
        definition: SkillDefinition,
    ) -> bool:
        return (
            str(
                definition.metadata.get("cancellation_granularity")
                or "request"
            )
            == "global_domain"
        )

    @staticmethod
    def _scope_priority(scope: CancellationScope) -> int:
        return {
            "none": 0,
            "output_only": 10,
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
        return (
            second
            if cls._scope_priority(second) >= cls._scope_priority(first)
            else first
        )

    @staticmethod
    def _request_goal_ids(request: SkillRequest) -> set[str]:
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
                values.update(
                    str(item).strip()
                    for item in raw
                    if str(item).strip()
                )
        return values

    @classmethod
    def _specific_goal_binding(
        cls,
        directive: CancellationDirective,
        request: SkillRequest,
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
        if (
            str(metadata.get("canonical_plan_id") or "")
            != str(directive.expected_plan_id or "")
            or str(
                metadata.get("canonical_plan_fingerprint") or ""
            )
            != str(directive.expected_plan_fingerprint or "")
        ):
            return "stale"
        if not goal_ids.issubset(targets):
            return "shared_owner_conflict"
        return "match"

    def _matching_cancellation_rule(
        self,
        interaction_id: str,
        request: SkillRequest,
        definition: SkillDefinition,
    ) -> _CancellationRule | None:
        matching: list[tuple[int, _CancellationRule]] = []
        for index, rule in enumerate(
            self._cancellation_rules.get(interaction_id, ())
        ):
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
        scheduled = [*before, *response.skills, *after]
        request_ids = [request.request_id for request in scheduled]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError(
                "scheduled request IDs must be unique within one interaction"
            )
        return scheduled

    def _speech_request(self, speech: InteractionSpeech) -> SkillRequest:
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
            )
            if key in speech_metadata
        }
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
            metadata=authority_metadata,
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
                async with self._active_lock:
                    context.provider_started = True
                    trace.events.append(
                        SkillTraceEvent(type="started")
                    )
                return await provider.execute(request, definition, context)

        active_key = (interaction_id, request.request_id)
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
                result = SkillResult(
                    request_id=request.request_id,
                    skill_id=request.skill_id,
                    skill_version=definition.version,
                    status="cancelled",
                    provider_id=definition.provider_id,
                    reason_code="cancelled_before_start",
                    message=(
                        "skill execution was cancelled before provider start "
                        f"by scope={cancellation_rule.effective_scope}"
                    ),
                    trace_id=trace.trace_id,
                    started_at=trace.started_at,
                    finished_at=finished_at,
                )
                trace.status = "cancelled"
                trace.finished_at = finished_at
                trace.events.append(
                    SkillTraceEvent(
                        type="cancelled",
                        message=result.message,
                        data={
                            "reason_code": "cancelled_before_start",
                            "cancellation_scope": (
                                cancellation_rule.effective_scope
                            ),
                        },
                    )
                )
                return result, trace
            task = asyncio.create_task(invoke())
            self._active[active_key] = (task, request, definition, context)
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
                result = SkillResult(
                    request_id=request.request_id,
                    skill_id=request.skill_id,
                    skill_version=definition.version,
                    status=(
                        "failed" if scoped_cancel_failed else "cancelled"
                    ),
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
                            "; provider cancellation was not confirmed: "
                            f"{cancel_error}"
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
            cancelled_before_provider = not context.provider_started
            if (
                context.provider_started
                and request.cancellable
                and definition.interruptible
            ):
                cancel_error = await asyncio.shield(
                    self._cancel_provider(
                        provider,
                        request,
                        definition,
                        context,
                    )
                )
            scoped_cancel_failed = bool(
                cancel_error
                and context.cancellation_reason_code != "cancelled"
            )
            result = SkillResult(
                request_id=request.request_id,
                skill_id=request.skill_id,
                skill_version=definition.version,
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
                        else "skill execution was cancelled before provider start"
                        if cancelled_before_provider
                        else "skill execution was cancelled"
                    )
                    + (
                        f" by scope={context.cancellation_scope}"
                        if context.cancellation_scope != "none"
                        else ""
                    )
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
                interaction_scheduled = self._scheduled.get(interaction_id)
                if interaction_scheduled is not None:
                    interaction_scheduled.pop(request.request_id, None)

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
        provider: SkillProvider,
        request: SkillRequest,
        definition: SkillDefinition,
        contexts: tuple[SkillExecutionContext, ...],
    ) -> str | None:
        error: str | None = None
        try:
            await provider.cancel(request, definition, contexts[0])
        except asyncio.CancelledError:
            error = (
                "provider cancellation coroutine was cancelled"
            )
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            logger.warning(
                "Skill provider cancellation failed request_id=%s skill_id=%s "
                "provider_id=%s error=%s",
                request.request_id,
                request.skill_id,
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
    [SkillRequest, dict[str, Any]],
    None | Awaitable[None],
]


class LocalSpeechSkillProvider:
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
        if self._cancel_handler is None:
            return
        # The host speech handler may still be awaiting playback-start evidence
        # when its task is cancelled, so no completed scheduling receipt is
        # guaranteed here.  The host therefore treats missing receipt data as
        # requiring a conservative global output abort.
        raw = self._cancel_handler(request, {})
        if inspect.isawaitable(raw):
            await raw


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
        cancellation_domains=("output",),
        metadata={"cancellation_granularity": "global_domain"},
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
