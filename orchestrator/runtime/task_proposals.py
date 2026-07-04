from __future__ import annotations

from typing import Any

from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.task_proposal import TaskProposal, TaskProposalLedger


LEDGER_SCHEMA_VERSION = 1
EFFECTFUL_TASK_TYPES = {
    "body.stop_motion",
    "task.cancel_current_action",
    "task.execute_robot_action",
    "task.execute_skill",
    "task.execute_task_graph",
    "task.use_tool",
}
EFFECTFUL_TASK_PREFIXES = (
    "body.",
    "task.execute",
)
COMMIT_GATE_STRATEGY = "interaction_response_commit_gate"
PROPOSAL_STATES = {
    "advisory",
    "committed",
    "running",
    "completed",
    "failed",
    "refused",
    "missing_ability",
    "timed_out",
    "cancelled",
    "not_committed",
    "rejected",
    "superseded",
}


def annotate_task_proposal_ledger(response: InteractionResponse) -> InteractionResponse:
    """Attach a host-side proposal/commit ledger without changing execution.

    Router and deep-thinking stages may propose tasks, but the host executes
    only concrete InteractionResponse skills/speech that pass later runtime
    gates. The ledger records that distinction so later smart merge work has a
    durable audit surface.
    """

    proposals = _route_task_proposals(response)
    has_deepthinking_task_proposals = _has_deepthinking_task_proposals(response)
    has_agent_task_proposals = _has_agent_task_proposals(response)
    proposals.extend(_deepthinking_task_proposals(response))
    proposals.extend(_agent_task_proposals(response))
    if not has_agent_task_proposals:
        proposals.extend(_committed_skill_proposals(response))
        proposals.extend(_committed_speech_proposals(response))
    proposals.extend(_revised_task_proposals(response))
    proposals.extend(_superseded_proposals(response))
    if not has_deepthinking_task_proposals:
        proposals.extend(_rejected_deepthinking_proposals(response))
    summary = _ledger_summary(proposals)
    ledger = TaskProposalLedger(
        schema_version=LEDGER_SCHEMA_VERSION,
        strategy=COMMIT_GATE_STRATEGY,
        summary=summary,
        proposals=proposals,
    )
    return response.model_copy(
        deep=True,
        update={
            "metadata": {
                **response.metadata,
                "task_proposal_ledger": ledger.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
            }
        },
    )


def _route_task_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    metadata = response.metadata or {}
    route_proposals = metadata.get("route_task_proposals")
    if route_proposals is None:
        route_proposals = metadata.get("task_proposals")
    if isinstance(route_proposals, list):
        return _route_shared_task_proposals(response, route_proposals)

    route_tasks = metadata.get("route_task_list")
    if route_tasks is None:
        route_tasks = metadata.get("task_list")
    if not isinstance(route_tasks, list):
        return []

    committed_skills = {_normalized_skill_id(request.skill_id) for request in response.skills}
    proposals: list[dict[str, Any]] = []
    for index, task in enumerate(route_tasks):
        if not isinstance(task, dict):
            continue
        task_type = str(task.get("task_type") or "").strip()
        capability_id = _normalized_skill_id(str(task.get("capability_id") or "").strip())
        source_stage = str(task.get("source_stage") or "router").strip() or "router"
        committed_by = ""
        state = "advisory"
        reason = "route proposal recorded for final commit review"
        if capability_id and capability_id in committed_skills:
            state = "committed"
            committed_by = "interaction_response.skill"
            reason = "matching InteractionResponse skill was committed"
        elif _is_effectful_task_type(task_type):
            state = "not_committed"
            reason = "effectful route proposal requires an InteractionResponse skill before execution"

        proposal = {
            "id": str(task.get("id") or f"{source_stage}:{index}:{task_type or 'task'}"),
            "source": source_stage,
            "proposal_kind": str(task.get("kind") or "task"),
            "task_type": task_type or "unknown",
            "state": state,
            "reason": reason,
            "effectful": _is_effectful_task_type(task_type),
            "priority": str(task.get("priority") or "normal"),
            "sequence": _safe_int(task.get("merged_sequence"), _safe_int(task.get("sequence"), index)),
        }
        if capability_id:
            proposal["skill_id"] = capability_id
        if committed_by:
            proposal["committed_by"] = committed_by
        proposals.append(proposal)
    return proposals


def _route_shared_task_proposals(
    response: InteractionResponse,
    route_proposals: list[Any],
) -> list[dict[str, Any]]:
    committed_skills = {_normalized_skill_id(request.skill_id) for request in response.skills}
    proposals: list[dict[str, Any]] = []
    for index, raw in enumerate(route_proposals):
        if not isinstance(raw, dict):
            continue
        proposal = TaskProposal.model_validate(raw).model_dump(
            mode="json",
            exclude_none=True,
        )
        skill_id = _normalized_skill_id(str(proposal.get("skill_id") or "").strip())
        task_type = str(proposal.get("task_type") or "").strip()
        state = str(proposal.get("state") or "advisory")
        if state not in {"rejected", "superseded"}:
            if skill_id and skill_id in committed_skills:
                proposal["state"] = "committed"
                proposal["committed_by"] = "interaction_response.skill"
                proposal["reason"] = "matching InteractionResponse skill was committed"
            elif bool(proposal.get("effectful")) or _is_effectful_task_type(task_type):
                proposal["state"] = "not_committed"
                proposal["reason"] = "effectful route proposal requires an InteractionResponse skill before execution"
        proposal["sequence"] = _safe_int(proposal.get("sequence"), index)
        if skill_id:
            proposal["skill_id"] = skill_id
        proposals.append(proposal)
    return proposals


def _has_deepthinking_task_proposals(response: InteractionResponse) -> bool:
    raw = response.metadata.get("deepthinking_task_proposals")
    return isinstance(raw, list) and any(isinstance(item, dict) for item in raw)


def _has_agent_task_proposals(response: InteractionResponse) -> bool:
    raw = response.metadata.get("agent_task_proposals")
    return isinstance(raw, list) and any(isinstance(item, dict) for item in raw)


def _agent_task_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    raw = response.metadata.get("agent_task_proposals")
    if not isinstance(raw, list):
        return []
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        proposal = TaskProposal.model_validate(item).model_dump(
            mode="json",
            exclude_none=True,
        )
        proposal["sequence"] = _safe_int(proposal.get("sequence"), index)
        proposals.append(proposal)
    return proposals


def _deepthinking_task_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    raw = response.metadata.get("deepthinking_task_proposals")
    if not isinstance(raw, list):
        return []
    committed_skills = {_normalized_skill_id(request.skill_id) for request in response.skills}
    has_speech = bool(response.speech)
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        proposal = TaskProposal.model_validate(item).model_dump(
            mode="json",
            exclude_none=True,
        )
        skill_id = _normalized_skill_id(str(proposal.get("skill_id") or "").strip())
        task_type = str(proposal.get("task_type") or "").strip()
        state = str(proposal.get("state") or "advisory")
        if state not in {"rejected", "superseded", "committed"}:
            if skill_id and skill_id in committed_skills:
                proposal["state"] = "committed"
                proposal["committed_by"] = "interaction_response.skill"
                proposal["reason"] = "matching InteractionResponse skill was committed"
            elif task_type == "speech.speak" and has_speech:
                proposal["state"] = "committed"
                proposal["committed_by"] = "interaction_response.speech"
                proposal["reason"] = "InteractionResponse speech was committed"
            elif bool(proposal.get("effectful")) or _is_effectful_task_type(task_type):
                proposal["state"] = "not_committed"
                proposal["reason"] = "effectful deepthinking proposal requires an InteractionResponse skill before execution"
        proposal["sequence"] = _safe_int(proposal.get("sequence"), index)
        if skill_id:
            proposal["skill_id"] = skill_id
        proposals.append(proposal)
    return proposals


def _committed_skill_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    preflight = _preflight_items_by_request_id(response)
    for index, request in enumerate(response.skills):
        skill_id = _normalized_skill_id(request.skill_id)
        proposal = {
            "id": f"interaction_response:skill:{request.request_id}",
            "source": str(request.metadata.get("source") or "interaction_response"),
            "proposal_kind": "skill",
            "task_type": _task_type_for_skill(skill_id),
            "skill_id": skill_id,
            "request_id": request.request_id,
            "state": "committed",
            "reason": "InteractionResponse skill is eligible for Skill Runtime validation",
            "effectful": _is_effectful_skill(skill_id),
            "priority": "normal",
            "sequence": index,
            "timing": request.timing,
            "requires_confirmation": request.requires_confirmation,
        }
        preflight_item = preflight.get(request.request_id)
        if preflight_item:
            proposal["preflight"] = {
                "status": str(preflight_item.get("status") or "unknown"),
                "reason_code": str(preflight_item.get("reason_code") or "unknown"),
                "world_feasibility": str(
                    preflight_item.get("world_feasibility")
                    or "unknown_until_runtime"
                ),
            }
        proposals.append(proposal)
    return proposals


def _committed_speech_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for index, speech in enumerate(response.speech):
        proposals.append(
            {
                "id": f"interaction_response:speech:{speech.id}",
                "source": str(speech.metadata.get("source") or "interaction_response"),
                "proposal_kind": "speech",
                "task_type": "speech.speak",
                "speech_id": speech.id,
                "state": "committed",
                "reason": "InteractionResponse speech is eligible for local speech scheduling",
                "effectful": False,
                "priority": speech.priority,
                "sequence": index,
                "timing": speech.timing,
                "text_chars": len(speech.text),
            }
        )
    return proposals


def _rejected_deepthinking_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    rejected = response.metadata.get("deepthinking_rejected_tasks")
    if not isinstance(rejected, list):
        rejected = response.metadata.get("deepthinking_rejected_actions")
    if not isinstance(rejected, list):
        return []
    proposals: list[dict[str, Any]] = []
    for index, task in enumerate(rejected):
        if not isinstance(task, dict):
            continue
        task_type = str(task.get("task_type") or task.get("type") or "unknown").strip() or "unknown"
        skill_id = _normalized_skill_id(str(task.get("skill_id") or "").strip())
        proposal = {
            "id": f"deepthinking:rejected:{index}:{task_type}",
            "source": "deepthinking",
            "proposal_kind": "rejected_task",
            "task_type": task_type,
            "state": "rejected",
            "reason": str(task.get("reason") or "deepthinking task did not pass validation"),
            "effectful": _is_effectful_task_type(task_type) or _is_effectful_skill(skill_id),
            "priority": "normal",
            "sequence": index,
        }
        if skill_id:
            proposal["skill_id"] = skill_id
        proposals.append(proposal)
    return proposals


def _superseded_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    raw = response.metadata.get("superseded_task_proposals")
    if raw is None:
        raw = response.metadata.get("task_proposal_superseded")
    if not isinstance(raw, list):
        return []
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        task_type = str(item.get("task_type") or item.get("type") or "unknown").strip() or "unknown"
        skill_id = _normalized_skill_id(str(item.get("skill_id") or "").strip())
        proposal = {
            "id": str(item.get("id") or f"superseded:{index}:{task_type}"),
            "source": str(item.get("source") or "orchestrator_merge"),
            "proposal_kind": str(item.get("proposal_kind") or item.get("kind") or "task"),
            "task_type": task_type,
            "state": "superseded",
            "reason": str(item.get("reason") or "proposal was superseded by a later correction"),
            "effectful": bool(item.get("effectful")) or _is_effectful_task_type(task_type) or _is_effectful_skill(skill_id),
            "priority": str(item.get("priority") or "normal"),
            "sequence": _safe_int(item.get("sequence"), index),
        }
        superseded_by = str(item.get("superseded_by") or item.get("replacement_id") or "").strip()
        if superseded_by:
            proposal["superseded_by"] = superseded_by
        if skill_id:
            proposal["skill_id"] = skill_id
        proposals.append(proposal)
    return proposals


def _revised_task_proposals(response: InteractionResponse) -> list[dict[str, Any]]:
    raw = response.metadata.get("revised_task_proposals")
    if raw is None:
        raw = response.metadata.get("task_proposal_revisions")
    if not isinstance(raw, list):
        return []
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        replacement = _revision_replacement_proposal(item, index)
        proposals.append(replacement)
        superseded = _revision_superseded_marker(item, index, replacement)
        if superseded is not None:
            proposals.append(superseded)
    return proposals


def _revision_replacement_proposal(item: dict[str, Any], index: int) -> dict[str, Any]:
    task_type = str(item.get("task_type") or item.get("type") or "unknown").strip() or "unknown"
    skill_id = _normalized_skill_id(
        str(item.get("skill_id") or item.get("capability_id") or "").strip()
    )
    state = str(item.get("state") or "advisory").strip() or "advisory"
    if state not in PROPOSAL_STATES or state == "superseded":
        state = "advisory"
    default_effectful = _is_effectful_task_type(task_type) or _is_effectful_skill(skill_id)
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    metadata = dict(metadata)
    supersedes = _first_string(
        item,
        ("supersedes", "supersedes_id", "replaces", "replaces_id", "revision_of"),
    )
    if supersedes:
        metadata["supersedes"] = supersedes

    proposal: dict[str, Any] = {
        "id": str(item.get("id") or f"revision:{index}:{task_type}"),
        "source": str(item.get("source") or "orchestrator_merge"),
        "proposal_kind": str(item.get("proposal_kind") or item.get("kind") or "task"),
        "task_type": task_type,
        "state": state,
        "reason": str(item.get("reason") or "proposal was revised by later evidence"),
        "effectful": _safe_bool(item.get("effectful"), default_effectful),
        "priority": str(item.get("priority") or "normal"),
        "sequence": _safe_int(item.get("sequence"), index),
    }
    if skill_id:
        proposal["skill_id"] = skill_id
    for field in ("request_id", "speech_id", "committed_by", "timing"):
        value = str(item.get(field) or "").strip()
        if value:
            proposal[field] = value
    if isinstance(item.get("requires_confirmation"), bool):
        proposal["requires_confirmation"] = item["requires_confirmation"]
    if "text_chars" in item:
        proposal["text_chars"] = _safe_int(item.get("text_chars"), 0)
    if metadata:
        proposal["metadata"] = metadata
    return TaskProposal.model_validate(proposal).model_dump(mode="json", exclude_none=True)


def _revision_superseded_marker(
    item: dict[str, Any],
    index: int,
    replacement: dict[str, Any],
) -> dict[str, Any] | None:
    supersedes = _first_string(
        item,
        ("supersedes", "supersedes_id", "replaces", "replaces_id", "revision_of"),
    )
    if not supersedes:
        return None
    task_type = (
        str(
            item.get("superseded_task_type")
            or item.get("old_task_type")
            or item.get("previous_task_type")
            or "unknown"
        )
        .strip()
        or "unknown"
    )
    skill_id = _normalized_skill_id(
        str(
            item.get("superseded_skill_id")
            or item.get("old_skill_id")
            or item.get("previous_skill_id")
            or ""
        ).strip()
    )
    default_effectful = _is_effectful_task_type(task_type) or _is_effectful_skill(skill_id)
    proposal: dict[str, Any] = {
        "id": str(item.get("superseded_id") or f"{supersedes}:superseded"),
        "source": str(
            item.get("superseded_source")
            or item.get("old_source")
            or item.get("source")
            or "orchestrator_merge"
        ),
        "proposal_kind": str(
            item.get("superseded_proposal_kind")
            or item.get("old_proposal_kind")
            or item.get("proposal_kind")
            or "task"
        ),
        "task_type": task_type,
        "state": "superseded",
        "reason": str(
            item.get("superseded_reason")
            or item.get("reason")
            or "proposal was revised by later evidence"
        ),
        "effectful": _safe_bool(item.get("superseded_effectful"), default_effectful),
        "priority": str(item.get("superseded_priority") or item.get("priority") or "normal"),
        "sequence": _safe_int(
            item.get("superseded_sequence"),
            _safe_int(item.get("sequence"), index),
        ),
        "superseded_by": str(replacement.get("id") or ""),
    }
    if skill_id:
        proposal["skill_id"] = skill_id
    return TaskProposal.model_validate(proposal).model_dump(mode="json", exclude_none=True)


def _ledger_summary(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    states: dict[str, int] = {}
    sources: dict[str, int] = {}
    preflight_statuses: dict[str, int] = {}
    effectful_total = 0
    committed_effectful = 0
    not_committed_effectful = 0
    superseded_count = 0
    for proposal in proposals:
        state = str(proposal.get("state") or "unknown")
        source = str(proposal.get("source") or "unknown")
        states[state] = states.get(state, 0) + 1
        sources[source] = sources.get(source, 0) + 1
        if state == "superseded":
            superseded_count += 1
        if bool(proposal.get("effectful")):
            effectful_total += 1
            if state == "committed":
                committed_effectful += 1
            if state in {"not_committed", "rejected", "superseded"}:
                not_committed_effectful += 1
        preflight = proposal.get("preflight")
        if isinstance(preflight, dict):
            status = str(preflight.get("status") or "unknown")
            preflight_statuses[status] = preflight_statuses.get(status, 0) + 1
    return {
        "proposal_count": len(proposals),
        "states": dict(sorted(states.items())),
        "sources": dict(sorted(sources.items())),
        "preflight_statuses": dict(sorted(preflight_statuses.items())),
        "effectful_proposal_count": effectful_total,
        "committed_effectful_count": committed_effectful,
        "not_committed_effectful_count": not_committed_effectful,
        "superseded_count": superseded_count,
    }


def _preflight_items_by_request_id(
    response: InteractionResponse,
) -> dict[str, dict[str, Any]]:
    validation = response.metadata.get("preflight_validation")
    if not isinstance(validation, dict):
        return {}
    items = validation.get("items")
    if not isinstance(items, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        request_id = str(item.get("request_id") or "").strip()
        if request_id:
            out[request_id] = item
    return out


def _safe_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _first_string(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalized_skill_id(value: str) -> str:
    skill_id = (value or "").strip()
    if not skill_id:
        return ""
    if skill_id.startswith("soridormi.") or skill_id.startswith("chromie.") or skill_id.startswith("session."):
        return skill_id
    return f"soridormi.{skill_id}"


def _task_type_for_skill(skill_id: str) -> str:
    if skill_id == "chromie.speak":
        return "speech.speak"
    if skill_id == "session.interrupt":
        return "task.cancel_current_action"
    if skill_id == "chromie.task_graph.execute":
        return "task.execute_task_graph"
    if skill_id.startswith("soridormi."):
        return "task.execute_skill"
    return "task.execute_skill"


def _is_effectful_skill(skill_id: str) -> bool:
    return (
        skill_id.startswith("soridormi.")
        or skill_id == "session.interrupt"
        or skill_id == "chromie.task_graph.execute"
        or (
            skill_id.startswith("chromie.")
            and skill_id != "chromie.speak"
        )
    )


def _is_effectful_task_type(task_type: str) -> bool:
    normalized = (task_type or "").strip()
    return normalized in EFFECTFUL_TASK_TYPES or any(
        normalized.startswith(prefix) for prefix in EFFECTFUL_TASK_PREFIXES
    )
