from __future__ import annotations

from typing import Any


def goal_list_change_by_task(
    applied_operations: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Map committed Goal-state operations to concise console change labels."""

    labels: dict[str, str] = {}
    priorities = {
        "unchanged": 0,
        "associated": 10,
        "updated": 20,
        "confirmed": 25,
        "resumed": 25,
        "paused": 30,
        "added": 40,
        "cancelled": 50,
        "rejected": 50,
    }
    for item in list(applied_operations or []):
        if not isinstance(item, dict) or item.get("applied") is not True:
            continue
        task_id = " ".join(str(item.get("task_id") or "").split())
        if not task_id:
            continue
        operation = str(item.get("operation") or "").strip().casefold()
        relationship = str(item.get("relationship") or "").strip().casefold()
        if operation == "create":
            label = "added"
        elif relationship in {"continue", "reference"}:
            label = "associated"
        elif operation in {"modify", "clarification_answer", "correct"}:
            label = "updated"
        elif operation == "confirm":
            label = "confirmed"
        elif operation == "resume":
            label = "resumed"
        elif operation == "pause":
            label = "paused"
        elif operation == "cancel":
            label = "cancelled"
        elif operation == "reject":
            label = "rejected"
        elif relationship:
            label = "associated"
        elif operation:
            label = "updated"
        else:
            continue
        previous = labels.get(task_id, "unchanged")
        if priorities.get(label, 1) >= priorities.get(previous, 0):
            labels[task_id] = label
    return labels


def goal_list_item_text(
    snapshot: dict[str, Any],
    *,
    bucket: str,
    index: int,
    total: int,
    change: str = "unchanged",
) -> str:
    """Format one Goal-list console row without owning Goal or Work truth."""

    goal = snapshot.get("goal") if isinstance(snapshot.get("goal"), dict) else {}
    metadata = (
        snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
    )
    description = " ".join(
        str(goal.get("description") or snapshot.get("last_user_update") or "").split()
    )
    if len(description) > 180:
        description = description[:179].rstrip() + "…"
    goal_id = " ".join(
        str(snapshot.get("goal_id") or goal.get("goal_id") or "unknown").split()
    )
    responsibility = " ".join(
        str(
            snapshot.get("responsibility_status")
            or goal.get("responsibility_status")
            or "unknown"
        ).split()
    )
    work = " ".join(str(snapshot.get("work_status") or "unknown").split())
    relation = " ".join(str(metadata.get("task_relation") or "unknown").split())
    version = snapshot.get("goal_version") or goal.get("version") or 0
    marker = {
        "added": "+",
        "associated": "~",
        "updated": "~",
        "confirmed": "✓",
        "resumed": ">",
        "paused": "||",
        "cancelled": "x",
        "rejected": "x",
    }.get(change, " ")
    return (
        "goal_list_item: "
        f"change={change} marker={marker} bucket={bucket} index={index}/{total} "
        f"goal_id={goal_id} responsibility={responsibility} work={work} "
        f"relation={relation} version={version} description={description!r}"
    )
