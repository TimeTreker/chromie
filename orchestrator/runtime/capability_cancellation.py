"""Scope-qualified cancellation for the Capability Runtime.

The functions take the ``CapabilityRuntime`` as ``runtime``. They resolve a
CancellationDirective to the exact active and scheduled requests it covers,
cancel them, retain cancellation rules for later submissions and return one
dispatch receipt.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
)
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    CancellationProviderFailure,
    CancellationRequestBinding,
    CancellationScope,
)

if TYPE_CHECKING:
    from orchestrator.runtime.capability_runtime import (
        CancellationDomain,
        CapabilityDefinition,
        CapabilityExecutionContext,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CancellationRule:
    directive: CancellationDirective
    effective_scope: CancellationScope


async def cancel_scope(
    runtime: Any,
    directive: CancellationDirective,
) -> CancellationDispatchReceipt:
    """Select active and queued work using trusted runtime bindings."""

    requested_scope = directive.requested_scope
    async with runtime._active_lock:
        known_interactions = {
            *runtime._open_interactions,
            *runtime._scheduled,
            *(key[0] for key in runtime._active),
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
            for request, definition in runtime._scheduled.get(
                interaction_id,
                {},
            ).values():
                base_scheduled_items.append((interaction_id, request, definition))

        effective_scope = requested_scope
        widened = False
        widening_reason = ""
        stale_binding_request_keys: set[tuple[str, str]] = set()
        shared_owner_conflict_request_keys: set[tuple[str, str]] = set()
        base_selected: list[tuple[str, CapabilityRequest, CapabilityDefinition]] = []
        for interaction_id, request, definition in base_scheduled_items:
            if requested_scope == "specific_goal":
                binding = specific_goal_binding(
                    directive,
                    request,
                )
                if binding == "stale":
                    stale_binding_request_keys.add((interaction_id, request.request_id))
                    continue
                if binding == "shared_owner_conflict":
                    shared_owner_conflict_request_keys.add((interaction_id, request.request_id))
                    continue
                if binding == "match":
                    base_selected.append((interaction_id, request, definition))
                continue
            if scope_matches_definition(
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
            active_item = runtime._active.get((interaction_id, request.request_id))
            if (
                active_item is None
                or (active_item[0].done() and active_item[3].provider_cancel_future is None)
                or not active_item[3].provider_started
                or not request.cancellable
                or not definition.interruptible
                or not provider_cancellation_is_global(definition)
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
            for request, definition in runtime._scheduled.get(
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
            list[CancellationRule],
        ] = {}

        if global_domains_required and requested_scope != "global_emergency":
            if directive.target_request_ids:
                selected_keys = {
                    (interaction_id, request.request_id)
                    for interaction_id, request, _definition in base_selected
                }
                collateral = any(
                    (interaction_id, request.request_id) not in selected_keys
                    and global_domains_required.intersection(definition.cancellation_domains)
                    for interaction_id, request, definition in all_scheduled_items
                )
                if collateral:
                    raise ValueError("scoped Planner cancellation cannot widen to other Work")
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
                    key=scope_priority,
                )
                selection_scope_by_key[key] = dominant_scope(
                    selection_scope_by_key.get(key, "none"),
                    item_scope,
                )
            for interaction_id in sorted(known_interactions):
                for item_scope in sorted(
                    global_scopes,
                    key=scope_priority,
                ):
                    rules_to_install.setdefault(
                        interaction_id,
                        [],
                    ).append(
                        CancellationRule(
                            directive=directive,
                            effective_scope=item_scope,
                        )
                    )
            for interaction_id in base_interaction_ids:
                rules_to_install.setdefault(
                    interaction_id,
                    [],
                ).append(
                    CancellationRule(
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
                        CancellationRule(
                            directive=directive,
                            effective_scope=requested_scope,
                        )
                    )

        for interaction_id, new_rules in rules_to_install.items():
            rules = runtime._cancellation_rules.setdefault(
                interaction_id,
                [],
            )
            for rule in new_rules:
                if rule not in rules:
                    rules.append(rule)

        completed_active_keys = {
            key
            for key, item in runtime._active.items()
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
            for key, item in runtime._active.items()
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
                context.cancellation_scope = dominant_scope(
                    context.cancellation_scope,
                    item_scope,
                )
                context.cancellation_reason_code = f"cancelled_{context.cancellation_scope}"
                provider_cancel_items.append(item)
                continue
            if context.provider_started:
                active_keys.add(key)
            if not context.provider_started:
                context.cancellation_scope = dominant_scope(
                    context.cancellation_scope,
                    item_scope,
                )
                context.cancellation_reason_code = f"cancelled_{context.cancellation_scope}"
                task.cancel()
                locally_cancelled_items.append(item)
            elif request.cancellable and definition.interruptible:
                context.cancellation_scope = dominant_scope(
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
            elif provider_cancellation_is_global(definition):
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
                    runtime._invoke_provider_cancel(
                        runtime._providers[definition.provider_id],
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
        goal_id for _, request, _ in selected for goal_id in request_goal_ids(request)
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
        selected_request_bindings=tuple(binding(key) for key in selected_binding_order),
        active_request_bindings=tuple(binding(key) for key in active_binding_order),
        queued_request_bindings=tuple(binding(key) for key in queued_binding_order),
        cancel_requested_request_bindings=tuple(
            binding(key) for key in sorted(cancel_requested_keys)
        ),
        non_interruptible_request_bindings=tuple(
            binding(key) for key in sorted(non_interruptible_keys)
        ),
        shared_owner_conflict_request_bindings=tuple(
            binding(key) for key in sorted(shared_owner_conflict_request_keys)
        ),
        stale_binding_request_bindings=tuple(
            binding(key) for key in sorted(stale_binding_request_keys)
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


def scope_matches_definition(
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


def provider_cancellation_is_global(
    definition: CapabilityDefinition,
) -> bool:
    return (
        str(definition.metadata.get("cancellation_granularity") or "request") == "global_domain"
    )


def scope_priority(scope: CancellationScope) -> int:
    return {
        "none": 0,
        "output_only": 10,
        "media_output": 15,
        "specific_goal": 20,
        "embodied_motion": 25,
        "current_interaction": 30,
        "global_emergency": 40,
    }[scope]


def dominant_scope(
    first: CancellationScope,
    second: CancellationScope,
) -> CancellationScope:
    return second if scope_priority(second) >= scope_priority(first) else first


def request_goal_ids(request: CapabilityRequest) -> set[str]:
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


def specific_goal_binding(
    directive: CancellationDirective,
    request: CapabilityRequest,
) -> Literal[
    "match",
    "no_match",
    "stale",
    "shared_owner_conflict",
]:
    if directive.target_request_ids and request.request_id not in directive.target_request_ids:
        return "no_match"
    goal_ids = request_goal_ids(request)
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


def matching_cancellation_rule(
    runtime: Any,
    interaction_id: str,
    request: CapabilityRequest,
    definition: CapabilityDefinition,
) -> CancellationRule | None:
    matching: list[tuple[int, CancellationRule]] = []
    for index, rule in enumerate(runtime._cancellation_rules.get(interaction_id, ())):
        if rule.effective_scope == "specific_goal":
            if (
                specific_goal_binding(
                    rule.directive,
                    request,
                )
                == "match"
            ):
                matching.append((index, rule))
        elif scope_matches_definition(
            rule.effective_scope,
            definition,
        ):
            matching.append((index, rule))
    if not matching:
        return None
    return max(
        matching,
        key=lambda item: (
            scope_priority(item[1].effective_scope),
            item[0],
        ),
    )[1]
