#!/usr/bin/env python3
"""Validate the deployed Gateway -> Core -> Fast Planner control-plane contract."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.runtime.cognitive_gateway import CognitiveGateway
from shared.chromie_contracts.core_interpretation import (
    CognitiveWorkRequest,
    CoreInterpretationResult,
    CoreInterpretationUnavailable,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.user_turn import AttentionReviewResult, CoreTurnRequest

DEFAULT_TEXT = "Hello, Chromie."
DEFAULT_SESSION_ID = "gpu-smoke-control"
DEFAULT_CONVERSATION_ID = "gpu-smoke-control"
DEFAULT_GOAL_ID = "goal-gpu-smoke-greeting"


def build_core_request(
    *,
    text: str = DEFAULT_TEXT,
    session_id: str = DEFAULT_SESSION_ID,
    conversation_id: str = DEFAULT_CONVERSATION_ID,
    language: str = "en-US",
) -> CoreTurnRequest:
    """Build one admitted immutable Core request through the real Gateway facade."""

    gateway = CognitiveGateway()
    capture = gateway.capture(
        text,
        session_id=session_id,
        conversation_id=conversation_id,
        channel="text",
        language=language,
    )
    snapshot = gateway.assemble_context(
        capture,
        {
            "history": [],
            "active_goal_snapshots": [],
            "robot_state": {"emergency_stop": False},
            "smoke_test": True,
        },
    )
    review = AttentionReviewResult(
        turn_id=capture.turn_id,
        session_id=capture.session_id,
        context_digest=snapshot.digest,
        disposition="admit",
        speech_act="greeting",
        confidence=1.0,
        source="scripts.control_plane_smoke",
        reason="explicit smoke-test direct address",
    )
    envelope = gateway.admit_attention(capture, snapshot, review)
    return gateway.core_request(envelope, snapshot)


def build_fast_plan_request(
    interpretation: CoreInterpretationResult,
    *,
    text: str = DEFAULT_TEXT,
    goal_id: str = DEFAULT_GOAL_ID,
) -> CognitiveWorkRequest:
    """Build the maintained Responsibility→Planner work request."""

    return CognitiveWorkRequest(
        sid=interpretation.session_id,
        text=text,
        language=interpretation.language,
        responsibilities=interpretation.responsibilities,
        interpretation_confidence=interpretation.confidence,
        interpretation_unresolved=interpretation.unresolved,
        context={
            "active_goal_snapshots": [],
            "goal_association_resolution": {
                "associations": [],
                "new_goals": [
                    {
                        "goal_id": goal_id,
                        "description": "Respond to the user's greeting.",
                        "source_text": text,
                        "constraints": {},
                        "success_criteria": ["Reply without physical action."],
                    }
                ],
            },
            "robot_state": {"emergency_stop": False},
            "smoke_test": True,
        },
        history=[],
    )


def _post_json(url: str, payload: dict[str, Any], *, timeout_s: float) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return int(response.status), json.load(response)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return int(exc.code), payload


def run(base_url: str, *, timeout_s: float) -> dict[str, Any]:
    core_request = build_core_request()
    status, core_payload = _post_json(
        f"{base_url.rstrip('/')}/cognitive-core/interpret",
        core_request.model_dump(mode="json"),
        timeout_s=timeout_s,
    )
    if status == 503:
        unavailable = CoreInterpretationUnavailable.model_validate(core_payload)
        raise RuntimeError(
            "Core interpretation unavailable during greeting smoke test: "
            f"{unavailable.failure_class}: {unavailable.reason}"
        )
    if status != 200:
        raise RuntimeError(f"Core endpoint returned HTTP {status}: {core_payload!r}")

    interpretation = CoreInterpretationResult.model_validate(core_payload)
    if len(interpretation.responsibilities) != 1:
        raise AssertionError(
            "smoke greeting must produce exactly one Responsibility, got "
            f"{len(interpretation.responsibilities)}"
        )
    responsibility = interpretation.responsibilities[0]
    if responsibility.output_mode != "speech":
        raise AssertionError(
            "greeting Responsibility must remain immediate ordinary speech"
        )
    if responsibility.completion_requires_work:
        raise AssertionError(
            "greeting Responsibility must not claim downstream completion work"
        )
    if responsibility.completion_requires_fresh_evidence:
        raise AssertionError("greeting Responsibility must not claim fresh evidence")

    planner_request = build_fast_plan_request(interpretation)
    status, plan_payload = _post_json(
        f"{base_url.rstrip('/')}/fast-plan",
        planner_request.model_dump(mode="json", exclude_none=True),
        timeout_s=timeout_s,
    )
    if status != 200:
        raise RuntimeError(f"Fast Planner returned HTTP {status}: {plan_payload!r}")
    plan = CanonicalPlan.model_validate(plan_payload)
    if plan.planner_tier != "fast":
        raise AssertionError(f"unexpected planner tier: {plan.planner_tier!r}")
    if plan.goal_ids != [DEFAULT_GOAL_ID]:
        raise AssertionError(f"planner lost authoritative goal identity: {plan.goal_ids!r}")
    if plan.steps:
        raise AssertionError(f"chat smoke plan produced executable steps: {plan.steps!r}")
    if plan.disposition != "respond":
        raise AssertionError(f"chat smoke plan did not respond: {plan.disposition!r}")

    return {
        "core": {
            "turn_id": interpretation.turn_id,
            "responsibility_count": len(interpretation.responsibilities),
            "confidence": interpretation.confidence,
            "unresolved": list(interpretation.unresolved),
        },
        "fast_plan": {
            "plan_id": plan.plan_id,
            "planner_tier": plan.planner_tier,
            "disposition": plan.disposition,
            "goal_ids": plan.goal_ids,
            "step_count": len(plan.steps),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8092")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    result = run(args.base_url, timeout_s=max(1.0, args.timeout_seconds))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
