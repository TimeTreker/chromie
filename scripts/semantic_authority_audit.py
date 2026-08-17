#!/usr/bin/env python3
"""Audit Chromie's single-semantic-authority boundary without live services.

This check is intentionally GPU-free. It verifies the machine-readable route
matrix, maintained profile defaults, emergency fallback gates, and source-level
fail-closed invariants. Live model and MuJoCo validation remain separate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from shared.chromie_contracts.semantic_authority import (
        semantic_authority_route_matrix,
    )
except ImportError:
    from chromie_contracts.semantic_authority import semantic_authority_route_matrix


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def audit() -> dict[str, Any]:
    errors: list[str] = []
    matrix = semantic_authority_route_matrix()

    expected_entrypoints = {
        "orchestrator.handle_routed_text/apply (mapped lane allowlisted)",
        "orchestrator.handle_routed_text/apply (mapped lane excluded)",
        "orchestrator.handle_routed_text/report_only",
        "agent./interaction with deprecated exact actions compatibility input",
        "agent./interaction or /run emergency compatibility",
    }
    actual_entrypoints = {str(row.get("entrypoint") or "") for row in matrix}
    if actual_entrypoints != expected_entrypoints:
        errors.append(
            "semantic authority route matrix does not cover the maintained entrypoints"
        )

    for row in matrix:
        role = str(row.get("role") or "")
        if role not in {"authoritative", "observer", "adapter"}:
            errors.append(f"invalid role in route matrix: {role!r}")
        if not row.get("planner_path"):
            errors.append(f"missing planner path for {row.get('entrypoint')!r}")

    apply_rows = [
        row
        for row in matrix
        if row.get("entrypoint")
        in {
            "orchestrator.handle_routed_text/apply (mapped lane allowlisted)",
            }
    ]
    for row in apply_rows:
        if row.get("owner") != "goal_driven_runtime":
            errors.append(
                f"apply entrypoint has non-goal authority: {row.get('entrypoint')}"
            )
        if row.get("fallback") != "fail_closed_after_authority_acquisition":
            errors.append(
                f"apply entrypoint can widen authority after acquisition: {row.get('entrypoint')}"
            )

    excluded_rows = [
        row
        for row in matrix
        if row.get("entrypoint")
        in {
            "orchestrator.handle_routed_text/apply (mapped lane excluded)",
            }
    ]
    for row in excluded_rows:
        if row.get("owner") != "goal_driven_runtime":
            errors.append(
                "excluded mapped lane can re-enter a second semantic authority: "
                f"{row.get('entrypoint')}"
            )
        if row.get("fallback") != "fail_closed_without_legacy_reentry":
            errors.append(
                "excluded mapped lane does not fail closed: "
                f"{row.get('entrypoint')}"
            )

    maintained_defaults = {
        "ORCH_COGNITIVE_RUNTIME_MODE": "apply",
        "AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED": "0",
    }
    for relative in (".env.common", ".env.example"):
        text = _read(relative)
        for key, value in maintained_defaults.items():
            if f"{key}={value}" not in text:
                errors.append(f"{relative} does not maintain {key}={value}")

    required_apply_lanes_by_profile = {
        ".env.common": {"chat", "memory", "tool"},
        "env/modes/speech.env": {"chat", "memory", "tool"},
        "env/modes/services.env": {"chat", "memory", "tool"},
        "env/modes/voice_mujoco.env": {"chat", "memory", "robot_action", "tool"},
        "env/modes/qualification.env": {"chat", "memory", "robot_action", "tool"},
    }
    for relative, required_apply_lanes in required_apply_lanes_by_profile.items():
        text = _read(relative)
        line = next(
            (
                item
                for item in text.splitlines()
                if item.startswith("ORCH_COGNITIVE_APPLY_LANES=")
            ),
            "",
        )
        lanes = {item.strip() for item in line.partition("=")[2].split(",") if item.strip()}
        missing = sorted(required_apply_lanes - lanes)
        if missing:
            errors.append(
                f"{relative} leaves maintained semantic lanes outside the Goal-driven runtime: "
                + ", ".join(missing)
            )

    launcher = _read("scripts/start_chromie.sh")
    for key, value in maintained_defaults.items():
        if f"{key}={value}" not in launcher:
            errors.append(f"scripts/start_chromie.sh does not force {key}={value}")

    capability = _read("agent/app/agents/capability.py")
    for required in (
        "if direct_actions:",
        'planning_result": "legacy_semantic_planner_disabled"',
        "legacy_capability_fallback_enabled",
        'authority.owner == "legacy_capability_fallback"',
        "authority.emergency_fallback",
    ):
        if required not in capability:
            errors.append(f"CapabilityAgent authority guard missing: {required}")

    for forbidden in (
        "_normalize_plan_for_routed_surface",
        "_look_direction_args_to_person_target_args",
        "_clamp_number_for_schema",
    ):
        if forbidden in capability:
            errors.append(
                "CapabilityAgent still rewrites model-selected skill semantics: "
                f"{forbidden}"
            )

    conversation = _read("agent/app/agents/conversation.py")
    for forbidden in (
        "_ensure_factual_subject_anchor",
        "The Sun is roughly spherical.",
        "The Sun is extremely hot.",
    ):
        if forbidden in conversation:
            errors.append(
                "ConversationAgent contains an entity-specific factual rewrite: "
                f"{forbidden}"
            )

    cognitive_runtime = _read("orchestrator/runtime/cognitive_runtime.py")
    if '"legacy_fallback"' in cognitive_runtime:
        errors.append("goal-driven runtime still declares a legacy_fallback status")
    if 'fallback_policy: str = "fail_closed"' not in cognitive_runtime:
        errors.append("goal-driven runtime code default is not fail_closed")

    orchestrator = _read("orchestrator/orchestrator.py")
    for required in (
        "_goal_driven_authority_context",
        "_legacy_agent_authority_context",
        '"status": "error"',
    ):
        if required not in orchestrator:
            errors.append(f"Orchestrator authority boundary missing: {required}")

    # The maintained compatibility surface has exactly two Agent semantic call
    # sites: /interaction and /run. Post-interrupt semantic re-entry was removed,
    # so every remaining compatibility call must carry the explicit authority claim.
    if orchestrator.count("context=agent_context") < 2:
        errors.append(
            "Orchestrator does not pass an explicit authority claim through every "
            "/interaction and /run compatibility call site"
        )

    legacy_host_cue_tokens = (
        "deep_thought_body" + "_cue",
        "host_deep" + "_thought_ack",
    )
    for forbidden in legacy_host_cue_tokens:
        if forbidden in orchestrator:
            errors.append(
                "Orchestrator still contains a Host-authored deep-thought body cue: "
                f"{forbidden}"
            )

    coordinator = _read("orchestrator/runtime/interaction_coordinator.py")
    legacy_optional_cue_key = "optional_body" + "_cue"
    if legacy_optional_cue_key in coordinator:
        errors.append(
            "Interaction coordinator still grants special semantics to legacy "
            "optional body-cue metadata"
        )

    social_runtime = _read("agent/app/runtime.py")
    social_prompt = _read("agent/app/social_attention.py")
    social_docs = "\n".join(
        _read(relative)
        for relative in (
            "docs/SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md",
            "docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md",
            "docs/HUMAN_LIKE_INTERACTION_CONTRACT.md",
            "agent/README.md",
        )
    )
    for forbidden in (
        "calibrated installation fallback",
        "use live target evidence before installation calibration",
        "Provider-supplied calibration is evidence",
    ):
        if forbidden in social_runtime or forbidden in social_prompt or forbidden in social_docs:
            errors.append(
                "Social Attention boundary still exposes provider calibration semantics: "
                f"{forbidden}"
            )

    health_schema = _read("agent/app/schema.py")
    if 'social_attention_mode: str = "on"' not in health_schema:
        errors.append("Agent health schema default is not Social Attention on")

    mind_contract = _read("shared/chromie_contracts/mind.py")
    if "active mind profile must be owner-approved" not in mind_contract:
        errors.append("MindProfile does not enforce owner approval")
    for required in (
        'preset: SocialInteractionPreset = "courteous"',
        'ORCH_SOCIAL_INTERACTION_STYLE_PRESET',
        'custom social interaction style requires reviewed guidance',
    ):
        if required not in mind_contract and required != 'ORCH_SOCIAL_INTERACTION_STYLE_PRESET':
            errors.append(f"Social Interaction Style contract missing: {required}")
    mind_runtime = _read("orchestrator/runtime/mind.py")
    if 'ORCH_SOCIAL_INTERACTION_STYLE_PRESET' not in mind_runtime:
        errors.append("Mind runtime does not expose the operator style preset")
    social_style_scenarios = list((ROOT / "scenarios" / "interaction").glob("social_attention_*"))
    required_style_cases = {
        "social_attention_courteous_greeting.json",
        "social_attention_neutral_information.json",
        "social_attention_reserved_greeting.json",
        "social_attention_cooldown_suppresses_repeat.json",
        "social_attention_user_requests_stillness.json",
    }
    present_style_cases = {path.name for path in social_style_scenarios}
    missing_style_cases = sorted(required_style_cases - present_style_cases)
    if missing_style_cases:
        errors.append(
            "Social Attention style regression matrix is incomplete: "
            + ", ".join(missing_style_cases)
        )

    abilities = _read("orchestrator/runtime/abilities.py")
    legacy_thinking_ability = "social.thinking" + "_pose"
    if legacy_thinking_ability in abilities:
        errors.append(
            "Static ability registry still defines a Host-selected thinking gesture"
        )

    # Bounded cognition guards protect semantic authority rather than historical
    # implementation sequences.  Rich diagnostics are allowed, but a deleted
    # second writer/reviewer/repair path must not silently regain model authority.
    attention_review = _read("agent/app/cognitive_gateway/attention_review.py")
    if attention_review.count("self.client.generate(") != 1:
        errors.append(
            "Cognitive Gateway Attention Review must have exactly one model judgment "
            f"call site; found {attention_review.count('self.client.generate(')}"
        )
    for forbidden in (
        "cognitive_gateway_attention_review.repair",
        "cognitive_gateway_attention_review.suppression_review",
        "_repair_prompt",
        "_suppression_review_prompt",
    ):
        if forbidden in attention_review:
            errors.append(
                "Cognitive Gateway Attention Review regained an online repair/reviewer path: "
                + forbidden
            )

    goal_interpreter = _read(
        "agent/app/cognitive_core/goal_interpreter/model_interpreter.py"
    )
    if '"logical_invocation_budget": 2' not in goal_interpreter:
        errors.append(
            "Goal Interpreter no longer declares the two-call primary/DTO budget"
        )
    if '"semantic_repair_attempted": False' not in goal_interpreter:
        errors.append(
            "Goal Interpreter no longer proves semantic repair is disabled"
        )
    for required in (
        "_reject_planner_shaped_fast_output",
        "Capability selection belongs to Planner after Goal Association",
        "downstream-owned contract field",
        'properties.pop("routes", None)',
        'schema["additionalProperties"] = False',
        "single-lane native_response is the immediate answer; ",
        "fast_speech must be null",
    ):
        if required not in goal_interpreter:
            errors.append(
                "Goal Interpreter lost Fast answer/work authority separation: "
                + required
            )

    goal_interpreter_prompt = _read(
        "agent/app/cognitive_core/goal_interpreter/prompts/goal_interpreter_system.txt"
    )
    for required in (
        "Responsibility evidence for downstream cognition",
        "Fast Planner is the first HOW owner when meaning is sufficient",
        "Fast and Deep Goal Interpretation share this boundary",
        "Never author Work, Primary Activities, response wording, Plan steps",
        "Do not output routes[]",
        "Activity/Work/Plan contracts",
        "Exact Work/Activity decomposition and Capability selection are Planner-owned",
    ):
        if required not in goal_interpreter_prompt:
            errors.append(
                "Goal Interpreter prompt regained Work/Activity/Plan authority: " + required
            )

    goal_association = _read("agent/app/goal_association.py")
    if '"logical_invocation_budget": 5' not in goal_association:
        errors.append(
            "Goal Association no longer declares its bounded five-invocation transaction"
        )

    fast_planner = _read("agent/app/fast_planner.py")
    for required in (
        "async def resolve_advance",
        "Fast Planner advance requires authoritative Responsibility evidence",
        "Goal Association owns canonical Goal continuity",
        "This phase never emits",
        "executable capability steps and never authorizes effects",
    ):
        if required not in fast_planner:
            errors.append("Fast Planner lost pre-Goal advancement boundary: " + required)
    deep_planner = _read("agent/app/deep_planner.py")
    for name, source in (("Fast Planner", fast_planner), ("Deep Planner", deep_planner)):
        if "self.max_contract_repairs = max(0, min(1, int(max_contract_repairs)))" not in source:
            errors.append(f"{name} no longer caps mechanical DTO regeneration at one")
    cognitive_runtime_source = _read("orchestrator/runtime/cognitive_runtime.py")
    for forbidden in ("host_replan_budget", "host_replan", "semantic_repair"):
        if forbidden in cognitive_runtime_source:
            errors.append(
                "Cognitive Host regained same-turn semantic replanning authority: "
                + forbidden
            )
    for required in (
        'if fast_planner_path == "contract_failure":',
        'raise CognitiveStageFailure("fast_planner", fast_failure)',
        'deep_reason = "semantic_escalation"',
        '"fast_plan_committed_without_deep"',
    ):
        if required not in cognitive_runtime_source:
            errors.append(
                "Fast/Deep commitment boundary guard missing: " + required
            )
    if 'deep_reason = "fast_contract_failure"' in cognitive_runtime_source:
        errors.append(
            "Deep Planner again treats a Fast contract failure as a semantic escalation"
        )

    response_composer = _read("agent/app/response_composer.py")
    response_contract = _read("shared/chromie_contracts/response_composition.py")
    for required in (
        "ResponseTruthAudit",
        'prompt_family="response_composer.truth_audit"',
        '"response_composer.dto_regeneration"',
        "_project_goal_coverage",
        'covers_goal_ids["maxItems"] = 0',
        "Do not author covers_goal_ids",
    ):
        if required not in response_composer:
            errors.append(f"Response bounded-authority guard missing: {required}")
    for forbidden in (
        "response_composer.semantic_review",
        "response_composer.effectful_semantic_review",
        "_repair_mixed_execution_coverage",
        "social_attention_plan",
    ):
        if forbidden in response_composer:
            errors.append(
                "Response Composer regained a deleted semantic-authority path: "
                f"{forbidden}"
            )
    if "social_attention_plan" in response_contract:
        errors.append(
            "Response composition contract again grants Social Attention authoring authority"
        )

    if social_prompt.count("client.generate(") != 1:
        errors.append(
            "Social Attention must have exactly one model-authoring call site; "
            f"found {social_prompt.count('client.generate(')}"
        )
    for forbidden in (
        "social_attention.contract_repair",
        "social_attention.none_semantic_review",
        "social_attention.semantic_review",
    ):
        if forbidden in social_prompt:
            errors.append(
                "Social Attention regained an online repair/reviewer path: " + forbidden
            )

    tool_result = _read("agent/app/tool_result_interpreter.py")
    for required in (
        "ToolResultTruthAudit",
        'prompt_family="tool_result_interpreter.truth_audit"',
        '"tool_result_interpreter.dto_regeneration"',
    ):
        if required not in tool_result:
            errors.append(f"Tool Result bounded-authority guard missing: {required}")
    for forbidden in (
        "tool_result_interpreter.contract_repair",
        "tool_result_interpreter.effectful_semantic_review",
        "tool_result_interpreter.semantic_repair",
    ):
        if forbidden in tool_result:
            errors.append(
                "Tool Result Interpreter regained a mutable reviewer/repair path: "
                + forbidden
            )

    reflection = _read("agent/app/reflection.py")
    if reflection.count("self.ollama.generate(") != 1:
        errors.append(
            "Reflection must have exactly one selective model-authoring call site; "
            f"found {reflection.count('self.ollama.generate(')}"
        )
    for forbidden in (
        "reflection.contract_repair",
        "reflection.semantic_review",
        "forward repair",
    ):
        if forbidden in reflection:
            errors.append(
                "Reflection regained current-turn repair/reviewer authority: " + forbidden
            )

    bounded_cognition_guards = {
        "gateway_attention_single_judgment": True,
        "goal_interpreter_two_call_budget": True,
        "fast_goal_outcome_separation": True,
        "goal_association_five_call_budget": True,
        "planner_one_mechanical_regeneration": True,
        "host_semantic_replan_forbidden": True,
        "fast_contract_failure_not_deep_repair": True,
        "response_single_writer": True,
        "response_goal_coverage_host_projection": True,
        "social_attention_single_writer": True,
        "tool_result_single_writer_with_truth_proof": True,
        "reflection_future_adaptation_only": True,
    }

    return {
        "schema_version": 1,
        "status": "pass" if not errors else "fail",
        "single_semantic_authority_enforced": not errors,
        "gpu_required": False,
        "live_model_or_robot_evidence_included": False,
        "entrypoints": matrix,
        "maintained_defaults": maintained_defaults,
        "bounded_cognition_guards": bounded_cognition_guards,
        "offline_equivalence_evidence": {
            "deprecated_exact_actions_compatibility": (
                "deterministic legacy adapter path only; current Fast Goal "
                "Interpretation does not author actions and semantic LLM re-entry is forbidden"
            ),
            "legacy_capability_planner": (
                "retained only behind host gate, Agent gate, and per-turn "
                "emergency authority claim"
            ),
            "goal_driven_failure": (
                "fail-closed after authority acquisition; no same-turn legacy re-entry"
            ),
        },
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit non-zero on failure")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = audit()
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 1 if args.check and report["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
