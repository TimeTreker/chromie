from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

try:
    from chromie_contracts.semantic_task import ResponsePlan, ResponseStage
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage


_PROCESS_COMMITMENTS = {"none", "heard", "evaluating"}
_STATUS_COMMITMENTS: dict[str, set[str]] = {
    "open": set(_PROCESS_COMMITMENTS),
    "planning": set(_PROCESS_COMMITMENTS),
    "needs_context": set(_PROCESS_COMMITMENTS),
    "waiting_for_user": {*_PROCESS_COMMITMENTS, "waiting_for_user"},
    "awaiting_confirmation": {*_PROCESS_COMMITMENTS, "waiting_for_user"},
    "committed": {*_PROCESS_COMMITMENTS, "accepted"},
    "scheduled": {*_PROCESS_COMMITMENTS, "accepted"},
    "running": {*_PROCESS_COMMITMENTS, "accepted", "executing"},
    "paused": {*_PROCESS_COMMITMENTS, "accepted"},
    "recoverable": {*_PROCESS_COMMITMENTS, "accepted"},
    "done": {*_PROCESS_COMMITMENTS, "accepted", "completed"},
    "failed": {*_PROCESS_COMMITMENTS, "failed"},
    "refused": {*_PROCESS_COMMITMENTS, "failed"},
    "timed_out": {*_PROCESS_COMMITMENTS, "failed"},
    "cancelled": {*_PROCESS_COMMITMENTS, "cancelled"},
    "canceled": {*_PROCESS_COMMITMENTS, "cancelled"},
    "superseded": set(_PROCESS_COMMITMENTS),
}
_KNOWN_PROCESS_CLAIMS = {"heard", "evaluating", "waiting_for_user"}
_TERMINAL_CLAIMS = {"completed", "failed", "cancelled"}
_EVIDENCE_CLAIMS = {
    "memory_committed": "memory_committed",
    "tool_result_available": "tool_result_available",
}


@dataclass(frozen=True)
class ResponseStageValidation:
    accepted: bool
    stage: ResponseStage | None
    errors: tuple[str, ...]
    checked_task_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "errors": list(self.errors),
            "checked_task_ids": list(self.checked_task_ids),
            "commitment_state": (
                self.stage.commitment_state if self.stage is not None else None
            ),
        }


def _snapshot_map(task_snapshots: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in task_snapshots:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "").strip()
        if task_id:
            out[task_id] = item
    return out


def _allowed_for_snapshot(snapshot: dict[str, Any]) -> set[str]:
    status = str(snapshot.get("status") or "open").strip().lower()
    return set(_STATUS_COMMITMENTS.get(status, _PROCESS_COMMITMENTS))


def _claim_supported(
    claim: str,
    *,
    covered: list[dict[str, Any]],
    commitment_state: str,
) -> bool:
    normalized = claim.strip().casefold()
    if not normalized:
        return True
    if normalized in _KNOWN_PROCESS_CLAIMS:
        return normalized == commitment_state or normalized in _PROCESS_COMMITMENTS
    if normalized in _TERMINAL_CLAIMS or normalized in {"accepted", "executing"}:
        return normalized == commitment_state
    evidence_key = _EVIDENCE_CLAIMS.get(normalized)
    if evidence_key:
        return bool(covered) and all(
            bool(
                (snapshot.get("evidence_summary") or {}).get(evidence_key)
                if isinstance(snapshot.get("evidence_summary"), dict)
                else False
            )
            for snapshot in covered
        )
    return False


def validate_response_stage(
    stage: ResponseStage,
    task_snapshots: Iterable[dict[str, Any]],
) -> ResponseStageValidation:
    snapshots = _snapshot_map(task_snapshots)
    errors: list[str] = []
    covered_ids = list(stage.covers_task_ids)
    unknown = [task_id for task_id in covered_ids if task_id not in snapshots]
    if unknown:
        errors.append("unknown_task_ids:" + ",".join(sorted(unknown)))

    covered = [snapshots[task_id] for task_id in covered_ids if task_id in snapshots]
    commitment = stage.commitment_state
    if not covered:
        if commitment not in _PROCESS_COMMITMENTS:
            errors.append("unscoped_stage_may_only_use_process_commitment")
    else:
        clarification_wait = (
            stage.speech_act.strip().casefold() in {"clarify", "ask_clarification"}
            and commitment == "waiting_for_user"
        )
        for snapshot in covered:
            if commitment not in _allowed_for_snapshot(snapshot) and not clarification_wait:
                errors.append(
                    "commitment_not_supported_by_task_state:"
                    f"{snapshot.get('task_id')}:{snapshot.get('status')}:{commitment}"
                )

    if stage.must_not_claim_completion and commitment in _TERMINAL_CLAIMS:
        errors.append("terminal_commitment_forbidden_by_stage_contract")

    for claim in stage.claims:
        if not _claim_supported(
            claim,
            covered=covered,
            commitment_state=commitment,
        ):
            errors.append(f"unsupported_claim:{claim}")

    return ResponseStageValidation(
        accepted=not errors,
        stage=stage if not errors else None,
        errors=tuple(errors),
        checked_task_ids=tuple(covered_ids),
    )


def validate_immediate_response_plan(
    value: ResponsePlan | dict[str, Any] | None,
    task_snapshots: Iterable[dict[str, Any]],
) -> ResponseStageValidation:
    if value is None:
        return ResponseStageValidation(
            accepted=False,
            stage=None,
            errors=("missing_response_plan",),
            checked_task_ids=(),
        )
    try:
        plan = value if isinstance(value, ResponsePlan) else ResponsePlan.model_validate(value)
    except Exception as exc:
        return ResponseStageValidation(
            accepted=False,
            stage=None,
            errors=(f"invalid_response_plan:{type(exc).__name__}",),
            checked_task_ids=(),
        )
    if plan.immediate is None:
        return ResponseStageValidation(
            accepted=False,
            stage=None,
            errors=("missing_immediate_stage",),
            checked_task_ids=(),
        )
    return validate_response_stage(plan.immediate, task_snapshots)
