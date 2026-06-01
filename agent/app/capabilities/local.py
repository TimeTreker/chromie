from __future__ import annotations

from .models import (
    AgentManifest,
    AgentStatus,
    CapabilityBundle,
    ConfirmationPolicy,
    ExecutionPolicy,
    FailurePolicy,
    MonitoringPolicy,
    ToolAvailability,
    ToolCapability,
    TransportSpec,
)


def chromie_manifests() -> list[AgentManifest]:
    speech = AgentManifest(
        agent_id="chromie.speech",
        display_name="Chromie Speech Agent",
        description="Chromie-side user speech, reporting, and confirmation tools. Owns TTS/ASR-facing user interaction.",
        transport=TransportSpec(kind="local_python", module="app.agents.speaker"),
        tags=["chromie", "speech", "user_interaction"],
        tools=[
            ToolCapability(
                name="chromie.speak",
                agent_id="chromie.speech",
                display_name="Speak to user",
                description="Speak a short message to the user through Chromie's TTS/output layer.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "style": {"type": "string", "enum": ["brief", "normal", "confirm", "warning"]},
                    },
                    "required": ["text"],
                },
                output_schema={"type": "object", "properties": {"spoken": {"type": "boolean"}}},
                effects=["user_interaction", "audio_output"],
                safety_class="low_risk_action",
                execution=ExecutionPolicy(can_run_parallel=False, exclusive_group="chromie_audio", timeout_s=10.0, idempotent=False, side_effect_free=False),
                default_failure_policy=FailurePolicy(strategy="skip"),
                llm_hints={"when_to_use": "Use to explain plans, progress, or results to the user."},
            ),
            ToolCapability(
                name="chromie.ask_confirmation",
                agent_id="chromie.speech",
                display_name="Ask user confirmation",
                description="Ask the user to confirm a risky or physical action before it executes.",
                input_schema={
                    "type": "object",
                    "properties": {"question": {"type": "string", "minLength": 1}, "plan_summary": {"type": "string"}},
                    "required": ["question"],
                },
                output_schema={
                    "type": "object",
                    "properties": {"confirmed": {"type": "boolean"}, "user_text": {"type": "string"}},
                    "required": ["confirmed"],
                },
                effects=["user_interaction"],
                safety_class="low_risk_action",
                execution=ExecutionPolicy(can_run_parallel=False, exclusive_group="user_dialog", timeout_s=60.0, idempotent=False, side_effect_free=False),
                default_failure_policy=FailurePolicy(strategy="abort_task"),
                llm_hints={"when_to_use": "Use before physical motion or memory writes that require explicit user approval."},
            ),
            ToolCapability(
                name="chromie.listen",
                agent_id="chromie.speech",
                display_name="Listen for user response",
                description="Listen for a short user response through Chromie's ASR/input layer.",
                input_schema={"type": "object", "properties": {"timeout_s": {"type": "number", "minimum": 0.1}}},
                output_schema={"type": "object", "properties": {"text": {"type": "string"}, "language": {"type": "string"}}},
                effects=["read_only", "audio_input", "user_interaction"],
                safety_class="safe_read",
                execution=ExecutionPolicy(can_run_parallel=False, exclusive_group="chromie_audio", timeout_s=60.0, idempotent=False, side_effect_free=False),
                default_failure_policy=FailurePolicy(strategy="ask_user"),
                llm_hints={"when_to_use": "Use when a task requires a spoken clarification or confirmation."},
            ),
            ToolCapability(
                name="chromie.report",
                agent_id="chromie.speech",
                display_name="Report result",
                description="Report task progress, failure, or completion to the user.",
                input_schema={"type": "object", "properties": {"message": {"type": "string", "minLength": 1}}, "required": ["message"]},
                output_schema={"type": "object", "properties": {"reported": {"type": "boolean"}}},
                effects=["user_interaction", "audio_output"],
                safety_class="low_risk_action",
                execution=ExecutionPolicy(can_run_parallel=False, exclusive_group="chromie_audio", timeout_s=10.0, idempotent=False, side_effect_free=False),
                default_failure_policy=FailurePolicy(strategy="skip"),
                llm_hints={"when_to_use": "Use at the end of a DAG or after fallback to explain the outcome."},
            ),
        ],
    )

    task = AgentManifest(
        agent_id="chromie.task",
        display_name="Chromie Task Agent",
        description="Chromie-side task trace and planning scaffolding. It does not execute robot motion directly.",
        transport=TransportSpec(kind="local_python", module="app.runtime"),
        tags=["chromie", "task", "dag"],
        tools=[
            ToolCapability(
                name="chromie.task.get_trace",
                agent_id="chromie.task",
                display_name="Get task trace",
                description="Read the current or most recent task execution trace.",
                input_schema={"type": "object", "properties": {"task_id": {"type": "string"}}},
                output_schema={"type": "object", "properties": {"events": {"type": "array"}}},
                effects=["read_only"],
                safety_class="safe_read",
                execution=ExecutionPolicy(can_run_parallel=True, timeout_s=2.0, idempotent=True, side_effect_free=True),
                default_failure_policy=FailurePolicy(strategy="skip"),
            )
        ],
    )
    return [speech, task]


def chromie_capability_bundle() -> CapabilityBundle:
    return CapabilityBundle(source="chromie", agents=chromie_manifests())


def build_chromie_registry(extra_bundles: list[CapabilityBundle] | None = None):
    from .models import CapabilityRegistry

    bundles = [chromie_capability_bundle()]
    bundles.extend(extra_bundles or [])
    return CapabilityRegistry.from_bundles(bundles)
