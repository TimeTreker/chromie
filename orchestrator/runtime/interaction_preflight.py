from __future__ import annotations

from typing import Any

from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest

from .skill_runtime import SkillRegistry, _validate_json_schema


PREFLIGHT_SCHEMA_VERSION = 1
PREFLIGHT_STRATEGY = "static_skill_preflight_v1"


def annotate_preflight_validation(
    response: InteractionResponse,
    *,
    registry: SkillRegistry,
    provider_ids: set[str],
    confirmed_request_ids: set[str] | None = None,
    safety_monitor_active: bool = False,
    soridormi_catalog_loaded: bool = False,
) -> InteractionResponse:
    """Attach a static skill preflight summary without proving execution.

    This catches contract and provider issues the host can know before runtime.
    Dynamic world feasibility remains unknown until the trusted runtime and
    Soridormi preview/submit/monitor path produce evidence.
    """

    confirmed = set(confirmed_request_ids or ())
    items = [
        _preflight_skill_request(
            request,
            registry=registry,
            provider_ids=provider_ids,
            confirmed_request_ids=confirmed,
            safety_monitor_active=safety_monitor_active,
            soridormi_catalog_loaded=soridormi_catalog_loaded,
        )
        for request in response.skills
    ]
    return response.model_copy(
        deep=True,
        update={
            "metadata": {
                **response.metadata,
                "preflight_validation": {
                    "schema_version": PREFLIGHT_SCHEMA_VERSION,
                    "strategy": PREFLIGHT_STRATEGY,
                    "summary": _summary(items),
                    "items": items,
                    "limits": [
                        "static_contract_check_only",
                        "does_not_prove_world_feasibility",
                        "runtime_and_provider_evidence_remain_authoritative",
                    ],
                },
            }
        },
    )


def _preflight_skill_request(
    request: SkillRequest,
    *,
    registry: SkillRegistry,
    provider_ids: set[str],
    confirmed_request_ids: set[str],
    safety_monitor_active: bool,
    soridormi_catalog_loaded: bool,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "request_id": request.request_id,
        "skill_id": request.skill_id,
    }
    try:
        definition = registry.get(request.skill_id)
    except ValueError as exc:
        if request.skill_id.startswith("soridormi.") and not soridormi_catalog_loaded:
            return {
                **base,
                "status": "deferred",
                "reason_code": "soridormi_catalog_not_loaded",
                "message": "Soridormi catalog lookup remains a runtime authority.",
                "world_feasibility": "unknown_until_runtime",
            }
        return {
            **base,
            "status": "blocked",
            "reason_code": "unknown_skill",
            "message": str(exc),
            "world_feasibility": "unknown_until_runtime",
        }

    if definition.provider_id not in provider_ids:
        return {
            **base,
            "status": "blocked",
            "reason_code": "provider_unregistered",
            "message": f"no registered provider {definition.provider_id!r}",
            "world_feasibility": "unknown_until_runtime",
        }
    if request.skill_version and request.skill_version != definition.version:
        return {
            **base,
            "status": "blocked",
            "reason_code": "version_mismatch",
            "message": (
                f"requested version {request.skill_version!r} does not match "
                f"registered version {definition.version!r}"
            ),
            "world_feasibility": "unknown_until_runtime",
        }
    if not definition.available:
        return {
            **base,
            "status": "blocked",
            "reason_code": "skill_unavailable",
            "message": definition.unavailable_reason or "unavailable",
            "world_feasibility": "unknown_until_runtime",
        }
    try:
        _validate_json_schema(request.args, definition.input_schema, path="args")
    except ValueError as exc:
        return {
            **base,
            "status": "blocked",
            "reason_code": "schema_validation_failed",
            "message": str(exc),
            "world_feasibility": "unknown_until_runtime",
        }
    if (
        request.requires_confirmation or definition.requires_confirmation
    ) and request.request_id not in confirmed_request_ids:
        return {
            **base,
            "status": "needs_confirmation",
            "reason_code": "confirmation_required",
            "message": "request-bound confirmation is required before execution",
            "world_feasibility": "unknown_until_runtime",
        }
    if definition.requires_safety_monitor and not safety_monitor_active:
        return {
            **base,
            "status": "needs_safety_monitor",
            "reason_code": "safety_monitor_required",
            "message": "an active safety monitor is required before execution",
            "world_feasibility": "unknown_until_runtime",
        }
    return {
        **base,
        "status": "passed",
        "reason_code": "static_preflight_passed",
        "message": "static contract and provider checks passed",
        "world_feasibility": "unknown_until_runtime",
    }


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    reason_codes: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        reason_code = str(item.get("reason_code") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        reason_codes[reason_code] = reason_codes.get(reason_code, 0) + 1
    return {
        "checked_skill_count": len(items),
        "statuses": dict(sorted(statuses.items())),
        "reason_codes": dict(sorted(reason_codes.items())),
        "blocked_count": statuses.get("blocked", 0),
        "deferred_count": statuses.get("deferred", 0),
        "pending_count": statuses.get("needs_confirmation", 0)
        + statuses.get("needs_safety_monitor", 0),
        "passed_count": statuses.get("passed", 0),
    }
