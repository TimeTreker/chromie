from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from agent.app.interaction import AgentResultInteractionAdapter
from agent.app.schema import AgentResult
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
    build_soridormi_invoker,
)


async def run_acceptance(
    *,
    text: str,
    manifest: Path,
    cancel_after_s: float | None = None,
) -> dict[str, Any]:
    session_id = "text-acceptance"
    started = time.monotonic()
    legacy_result = AgentResult()
    legacy_result.add_speak_immediate("Okay.", style="brief")
    legacy_result.add_action(
        "robot_pose_controller",
        "head.nod",
        params={"times": 1},
        timeout_ms=1000,
    )
    response = AgentResultInteractionAdapter().convert(legacy_result)
    scheduled_speech: list[str] = []
    invoker = build_soridormi_invoker(manifest_path=manifest)
    coordinator = InteractionRuntimeCoordinator(
        lambda args: scheduled_speech.append(str(args["text"]))
        or {"scheduled": True},
        soridormi_invoker=invoker,
    )
    execution_task = asyncio.create_task(
        coordinator.execute(
            response,
            session_id=session_id,
        )
    )
    if cancel_after_s is not None:
        await asyncio.sleep(cancel_after_s)
        execution_task.cancel()
    execution = await execution_task
    status_outcome = await invoker.invoke("soridormi.robot.get_status", {})
    post_status = (
        status_outcome.output
        if status_outcome.status == "success"
        else {"error": status_outcome.error, "status": status_outcome.status}
    )
    elapsed_s = time.monotonic() - started

    expected_status = "cancelled" if cancel_after_s is not None else "completed"
    safe_idle = (
        post_status.get("active_task") is None
        and post_status.get("emergency_stop") is False
    )
    return {
        "ok": execution.status == expected_status and safe_idle,
        "text": text,
        "cancel_after_s": cancel_after_s,
        "route": {
            "source": "acceptance_fixture",
            "route": "robot_action",
            "intent": "capability:soridormi.nod_yes",
        },
        "interaction_response": response.model_dump(mode="json"),
        "scheduled_speech": scheduled_speech,
        "execution": execution.model_dump(mode="json"),
        "post_status": post_status,
        "elapsed_s": round(elapsed_s, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Chromie's text-to-speech-and-named-skill acceptance path."
    )
    parser.add_argument("text", nargs="?", default="nod")
    parser.add_argument(
        "--manifest",
        default="capabilities/soridormi.json",
    )
    parser.add_argument("--cancel-after-s", type=float)
    args = parser.parse_args()

    if not os.environ.get("SORIDORMI_MCP_URL"):
        raise SystemExit("SORIDORMI_MCP_URL is required")
    payload = asyncio.run(
        run_acceptance(
            text=args.text,
            manifest=Path(args.manifest),
            cancel_after_s=args.cancel_after_s,
        )
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["ok"] else 1)


if __name__ == "__main__":
    main()
