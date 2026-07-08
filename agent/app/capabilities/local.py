from __future__ import annotations

import os

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


def _weather_tool_availability() -> ToolAvailability:
    enabled = os.getenv("AGENT_WEATHER_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    return ToolAvailability(
        available=enabled,
        modes=["runtime", "read_only"],
        requires=["network", "open_meteo"],
        reason=None if enabled else "AGENT_WEATHER_ENABLED is disabled",
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

    weather = AgentManifest(
        agent_id="chromie.weather",
        display_name="Chromie Weather Tool Agent",
        description=(
            "Chromie-side read-only weather lookup agent. It resolves a user-"
            "requested city/location and retrieves current or near-term forecast "
            "data through the configured weather provider."
        ),
        transport=TransportSpec(kind="local_python", module="app.agents.tool"),
        tags=["chromie", "tool", "weather", "external_read"],
        tools=[
            ToolCapability(
                name="chromie.weather.lookup",
                agent_id="chromie.weather",
                display_name="Lookup weather",
                description=(
                    "Retrieve current weather or a short forecast for a named city "
                    "or place. Use for user questions about today's weather, "
                    "tomorrow's weather, 天气/天气预报, temperature, rain, humidity, wind, or "
                    "forecast conditions. This is read-only and returns information; "
                    "it does not control the robot body."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "City or place name supplied by the user, such as "
                                "重庆, 北京, Chongqing, or Beijing."
                            ),
                        },
                        "date": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "default": "today",
                            "description": "Forecast date requested by the user.",
                        },
                        "units": {
                            "type": "string",
                            "enum": ["metric", "imperial", "auto"],
                            "default": "metric",
                            "description": "Preferred weather units.",
                        },
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "date": {"type": "string"},
                        "summary": {"type": "string"},
                        "temperature_c": {"type": "number"},
                        "high_c": {"type": "number"},
                        "low_c": {"type": "number"},
                    },
                },
                effects=["read_only", "external_read", "weather_lookup"],
                safety_class="safe_read",
                availability=_weather_tool_availability(),
                execution=ExecutionPolicy(
                    can_run_parallel=True,
                    timeout_s=8.0,
                    idempotent=True,
                    side_effect_free=True,
                ),
                default_failure_policy=FailurePolicy(strategy="stop_and_report"),
                llm_hints={
                    "prompt_tier": "common",
                    "prompt_tier_reason": (
                        "Weather/current forecast questions are common spoken "
                        "tool requests and must be visible to the fast router."
                    ),
                    "when_to_use": (
                        "Use when the user asks about current, today's, tomorrow's, "
                        "or upcoming weather or forecast for a city/location."
                    ),
                    "router_contract": "route=tool; intent=weather_query",
                    "router_intent": "weather_query",
                    "tool_name": "weather",
                    "semantic_type": "weather_lookup",
                    "fast_speech_guidance": (
                        "Acknowledge only that Chromie will check the requested "
                        "location/date. Do not state weather results before the tool returns."
                    ),
                },
            )
        ],
    )
    return [speech, task, weather]


def chromie_capability_bundle() -> CapabilityBundle:
    return CapabilityBundle(source="chromie", agents=chromie_manifests())


def build_chromie_registry(extra_bundles: list[CapabilityBundle] | None = None):
    from .models import CapabilityRegistry

    bundles = [chromie_capability_bundle()]
    bundles.extend(extra_bundles or [])
    return CapabilityRegistry.from_bundles(bundles)
