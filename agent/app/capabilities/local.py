from __future__ import annotations

from typing import Any

try:
    from chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        MEDIA_OPERATIONS,
        MediaProviderDeclaration,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
        VocalProviderDeclaration,
        media_capability_input_schema,
        media_capability_output_schema,
        vocal_performance_input_schema,
        vocal_performance_output_schema,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        MEDIA_OPERATIONS,
        MediaProviderDeclaration,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
        VocalProviderDeclaration,
        media_capability_input_schema,
        media_capability_output_schema,
        vocal_performance_input_schema,
        vocal_performance_output_schema,
    )

from ..settings import agent_service_settings

from .models import (
    AgentManifest,
    CapabilityBundle,
    ExecutionPolicy,
    FailurePolicy,
    ToolAvailability,
    ToolCapability,
    TransportSpec,
)


def _weather_tool_availability() -> ToolAvailability:
    enabled = agent_service_settings.weather_enabled
    return ToolAvailability(
        available=enabled,
        modes=["runtime", "read_only"],
        requires=["network", "open_meteo"],
        reason=None if enabled else "AGENT_WEATHER_ENABLED is disabled",
    )


def _external_information_availability() -> ToolAvailability:
    enabled = agent_service_settings.external_information_enabled and bool(
        agent_service_settings.external_information_url
    )
    reason = None
    if not agent_service_settings.external_information_enabled:
        reason = "AGENT_EXTERNAL_INFORMATION_ENABLED is disabled"
    elif not agent_service_settings.external_information_url:
        reason = "AGENT_EXTERNAL_INFORMATION_URL is not configured"
    return ToolAvailability(
        available=enabled,
        modes=["runtime", "read_only"],
        requires=["network", "external_information_provider"],
        reason=reason,
    )


def vocal_performance_tool(
    declaration: VocalProviderDeclaration | None = None,
) -> ToolCapability:
    """Build the exact public vocal Capability from a qualified declaration.

    The default static registry retains the public contract as unavailable. A
    deployment may expose it to planning only by supplying a declaration whose
    every advertised mode has retained evidence. Backend identity remains out
    of the model-facing semantic schema and hints.
    """

    supported_modes = list(declaration.supported_modes) if declaration else []
    evidence: dict[str, Any] = {}
    if declaration is not None:
        evidence = {
            mode: item.model_dump(mode="json") for mode, item in declaration.mode_evidence.items()
        }
    return ToolCapability(
        name=VOCAL_PERFORMANCE_CAPABILITY_ID,
        agent_id="chromie.speech",
        display_name="Perform qualified vocal output",
        description=(
            "Perform one provider-qualified vocal mode through Chromie's "
            "ordered playback and interruption boundary."
        ),
        version="1.0.0",
        input_schema=vocal_performance_input_schema(supported_modes or None),
        output_schema=vocal_performance_output_schema(),
        effects=["user_interaction", "audio_output", "vocal_performance"],
        safety_class="low_risk_action",
        availability=ToolAvailability(
            available=declaration is not None,
            modes=supported_modes,
            requires=["qualified_vocal_provider", "audio_output"],
            reason=(
                None
                if declaration is not None
                else "no qualified vocal provider declaration is configured"
            ),
        ),
        execution=ExecutionPolicy(
            can_run_parallel=True,
            exclusive_group="chromie.voice",
            timeout_s=120.0,
            idempotent=False,
            side_effect_free=False,
        ),
        default_failure_policy=FailurePolicy(strategy="skip"),
        llm_hints={
            "when_to_use": (
                "Use only when the requested typed vocal mode appears in "
                "supported_vocal_modes; never substitute ordinary speech, "
                "media playback, or a body gesture."
            ),
            "interaction_executable": True,
            "execution_lane": "vocal",
            "supported_vocal_modes": supported_modes,
            "mode_evidence": evidence,
            "can_run_parallel": True,
            "exclusive_group": "chromie.voice",
            "resource_claims": ["chromie.voice"],
            "execution_constraints": {
                "exact_mode_required": True,
                "silent_mode_downgrade_forbidden": True,
                "parallel_allowed_with_lanes": ["activity"],
            },
            "semantic_scope": {
                "responsibility_kind": "vocal_output",
                "execution_lane": "vocal",
                "output_modes": supported_modes,
                "provider_required": True,
            },
        },
    )


def media_playback_tools(
    declaration: MediaProviderDeclaration | None = None,
) -> list[ToolCapability]:
    """Build the stable media lifecycle family from one qualified declaration."""

    supported = set(declaration.supported_operations) if declaration else set()
    tools: list[ToolCapability] = []
    for operation in MEDIA_OPERATIONS:
        available = operation in supported
        evidence: dict[str, Any] = {}
        if declaration is not None and available:
            evidence = declaration.operation_evidence[operation].model_dump(mode="json")
        tools.append(
            ToolCapability(
                name=MEDIA_CAPABILITY_IDS[operation],
                agent_id="chromie.media",
                display_name=f"Media {operation}",
                description=(
                    f"Apply exact persistent media lifecycle operation {operation!r}; "
                    "this is Activity work, not authored vocal performance."
                ),
                version="1.0.0",
                input_schema=media_capability_input_schema(
                    operation,
                    (
                        declaration.supported_media_kinds
                        if declaration is not None and available
                        else None
                    ),
                ),
                output_schema=media_capability_output_schema(),
                effects=(
                    ["read_only", "media_playback", "playback_status"]
                    if operation == "status"
                    else ["audio_output", "media_playback", "playback_lifecycle"]
                ),
                safety_class="safe_read" if operation == "status" else "low_risk_action",
                availability=ToolAvailability(
                    available=available,
                    modes=[operation] if available else [],
                    requires=["qualified_media_provider", "audio_output"],
                    reason=(
                        None
                        if available
                        else (
                            "no qualified media provider declaration is configured"
                            if declaration is None
                            else f"qualified media provider does not advertise {operation}"
                        )
                    ),
                ),
                execution=ExecutionPolicy(
                    can_run_parallel=True,
                    exclusive_group=(None if operation == "play" else "chromie.media.control"),
                    timeout_s=120.0 if operation == "play" else 10.0,
                    idempotent=operation in {"pause", "resume", "stop", "volume", "status"},
                    side_effect_free=operation == "status",
                ),
                default_failure_policy=FailurePolicy(strategy="stop_and_report"),
                llm_hints={
                    "interaction_executable": True,
                    "prompt_tier": "common"
                    if operation in {"play", "pause", "resume", "stop"}
                    else "rare",
                    "when_to_use": (
                        f"Use only for exact media operation {operation!r}. Existing "
                        "audio playback is Activity; never use it as singing, humming, "
                        "recitation, or ordinary speech evidence."
                    ),
                    "execution_lane": "activity",
                    "media_operation": operation,
                    "persistent_playback": bool(
                        declaration is not None and declaration.persistent_playback
                    ),
                    "progress_reporting": bool(
                        declaration is not None and declaration.progress_reporting
                    ),
                    "mixer_policy": (declaration.mixer_policy if declaration is not None else None),
                    "ducking_gain_db": (
                        declaration.ducking_gain_db if declaration is not None else None
                    ),
                    "duck_attack_ms": (
                        declaration.duck_attack_ms if declaration is not None else None
                    ),
                    "duck_release_ms": (
                        declaration.duck_release_ms if declaration is not None else None
                    ),
                    "operation_evidence": evidence,
                    "can_run_parallel": True,
                    "exclusive_group": (None if operation == "play" else "chromie.media.control"),
                    "resource_claims": ["audio_output.media"],
                    "execution_constraints": {
                        "exact_operation_required": True,
                        "persistent_playback_identity_required": True,
                        "parallel_allowed_with_lanes": [
                            "vocal",
                            "activity",
                        ],
                    },
                    "semantic_scope": {
                        "responsibility_kind": "executable_action",
                        "execution_lane": "activity",
                        "output_mode": "media_playback",
                        "media_operation": operation,
                        "provider_required": True,
                    },
                },
            )
        )
    return tools


def chromie_manifests(
    *,
    vocal_provider: VocalProviderDeclaration | None = None,
    media_provider: MediaProviderDeclaration | None = None,
) -> list[AgentManifest]:
    speech = AgentManifest(
        agent_id="chromie.speech",
        display_name="Chromie Speech Agent",
        description="Chromie-side user speech, reporting, and confirmation tools. Owns TTS/ASR-facing user interaction.",
        transport=TransportSpec(kind="local_python", module="app.agents.speaker"),
        tags=["chromie", "speech", "user_interaction"],
        tools=[
            vocal_performance_tool(vocal_provider),
            ToolCapability(
                name="chromie.speak",
                agent_id="chromie.speech",
                display_name="Speak to user",
                description="Speak a short message to the user through Chromie's TTS/output layer.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "style": {
                            "type": "string",
                            "enum": ["brief", "normal", "confirm", "warning"],
                        },
                    },
                    "required": ["text"],
                },
                output_schema={"type": "object", "properties": {"spoken": {"type": "boolean"}}},
                effects=["user_interaction", "audio_output"],
                safety_class="low_risk_action",
                execution=ExecutionPolicy(
                    can_run_parallel=True,
                    exclusive_group="chromie.voice",
                    timeout_s=10.0,
                    idempotent=False,
                    side_effect_free=False,
                ),
                default_failure_policy=FailurePolicy(strategy="skip"),
                llm_hints={
                    "when_to_use": "Use to explain plans, progress, or results to the user.",
                    "execution_lane": "vocal",
                    "can_run_parallel": True,
                    "exclusive_group": "chromie.voice",
                    "resource_claims": ["chromie.voice"],
                    "execution_constraints": {
                        "parallel_allowed_with_lanes": ["activity"]
                    },
                },
            ),
            ToolCapability(
                name="chromie.ask_confirmation",
                agent_id="chromie.speech",
                display_name="Ask user confirmation",
                description="Ask the user to confirm a risky or physical action before it executes.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "minLength": 1},
                        "plan_summary": {"type": "string"},
                    },
                    "required": ["question"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "confirmed": {"type": "boolean"},
                        "user_text": {"type": "string"},
                    },
                    "required": ["confirmed"],
                },
                effects=["user_interaction"],
                safety_class="low_risk_action",
                execution=ExecutionPolicy(
                    can_run_parallel=False,
                    exclusive_group="user_dialog",
                    timeout_s=60.0,
                    idempotent=False,
                    side_effect_free=False,
                ),
                default_failure_policy=FailurePolicy(strategy="abort_task"),
                llm_hints={
                    "when_to_use": "Use before physical motion or memory writes that require explicit user approval."
                },
            ),
            ToolCapability(
                name="chromie.listen",
                agent_id="chromie.speech",
                display_name="Listen for user response",
                description="Listen for a short user response through Chromie's ASR/input layer.",
                input_schema={
                    "type": "object",
                    "properties": {"timeout_s": {"type": "number", "minimum": 0.1}},
                },
                output_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "language": {"type": "string"}},
                },
                effects=["read_only", "audio_input", "user_interaction"],
                safety_class="safe_read",
                execution=ExecutionPolicy(
                    can_run_parallel=False,
                    exclusive_group="chromie_audio",
                    timeout_s=60.0,
                    idempotent=False,
                    side_effect_free=False,
                ),
                default_failure_policy=FailurePolicy(strategy="ask_user"),
                llm_hints={
                    "when_to_use": "Use when a task requires a spoken clarification or confirmation."
                },
            ),
            ToolCapability(
                name="chromie.report",
                agent_id="chromie.speech",
                display_name="Report result",
                description="Report task progress, failure, or completion to the user.",
                input_schema={
                    "type": "object",
                    "properties": {"message": {"type": "string", "minLength": 1}},
                    "required": ["message"],
                },
                output_schema={"type": "object", "properties": {"reported": {"type": "boolean"}}},
                effects=["user_interaction", "audio_output"],
                safety_class="low_risk_action",
                execution=ExecutionPolicy(
                    can_run_parallel=False,
                    exclusive_group="chromie_audio",
                    timeout_s=10.0,
                    idempotent=False,
                    side_effect_free=False,
                ),
                default_failure_policy=FailurePolicy(strategy="skip"),
                llm_hints={
                    "when_to_use": "Use at the end of a DAG or after fallback to explain the outcome."
                },
            ),
        ],
    )

    media = AgentManifest(
        agent_id="chromie.media",
        display_name="Chromie Peer Media Provider",
        description=(
            "Persistent playback of existing media through exact Activity-lane "
            "capabilities. It shares the output mixer with Vocal without "
            "becoming speech or vocal-performance evidence."
        ),
        transport=TransportSpec(
            kind="host_runtime",
            module="orchestrator.runtime.skill_runtime",
        ),
        tags=["chromie", "media", "playback", "activity"],
        tools=media_playback_tools(media_provider),
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
                execution=ExecutionPolicy(
                    can_run_parallel=True, timeout_s=2.0, idempotent=True, side_effect_free=True
                ),
                default_failure_policy=FailurePolicy(strategy="skip"),
            )
        ],
    )

    memory = AgentManifest(
        agent_id="chromie.memory",
        display_name="Chromie Verified Tool Memory",
        description=(
            "Host-owned read-only retrieval of one previously verified tool result. "
            "It never resolves pronouns or chooses a location; Goal Association must "
            "already provide exact semantic bindings."
        ),
        transport=TransportSpec(
            kind="host_runtime",
            module="orchestrator.runtime.conversation_memory_provider",
        ),
        tags=["chromie", "memory", "safe_read", "verified_result"],
        tools=[
            ToolCapability(
                name="chromie.memory.retrieve_verified_tool_result",
                agent_id="chromie.memory",
                display_name="Retrieve verified tool result",
                description=(
                    "Retrieve one recent verified tool result by exact evidence ID, "
                    "original tool ID, and already-resolved material arguments. Use "
                    "only when the verified memory index advertises an exact fresh "
                    "match. This capability does not search loosely, resolve references, "
                    "or return another task's result."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "evidence_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Exact evidence_id copied from the verified memory index.",
                        },
                        "tool_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Original capability ID that produced the verified result.",
                        },
                        "material_args": {
                            "type": "object",
                            "minProperties": 1,
                            "description": (
                                "Exact already-resolved material Goal bindings, such as "
                                "location and date. Values must match the memory index."
                            ),
                            "additionalProperties": True,
                        },
                        "max_age_s": {
                            "type": "number",
                            "minimum": 1,
                            "maximum": 86400,
                            "default": 900,
                        },
                    },
                    "required": ["evidence_id", "tool_id", "material_args"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "found": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "evidence_id": {"type": "string"},
                        "tool_id": {"type": "string"},
                        "request_args_json": {"type": "string"},
                        "recorded_ms": {"type": ["number", "null"]},
                        "age_ms": {"type": ["number", "null"]},
                        "max_age_s": {"type": ["number", "null"]},
                        "result_json": {"type": "string"},
                        "source": {"type": "string"},
                    },
                    "required": [
                        "found",
                        "reason",
                        "evidence_id",
                        "tool_id",
                        "request_args_json",
                        "recorded_ms",
                        "age_ms",
                        "max_age_s",
                        "result_json",
                        "source",
                    ],
                    "additionalProperties": False,
                },
                effects=["read_only", "memory_read", "verified_tool_result"],
                safety_class="safe_read",
                execution=ExecutionPolicy(
                    can_run_parallel=True,
                    timeout_s=2.0,
                    idempotent=True,
                    side_effect_free=True,
                ),
                default_failure_policy=FailurePolicy(strategy="stop_and_report"),
                llm_hints={
                    "interaction_executable": True,
                    "prompt_tier": "common",
                    "prompt_tier_reason": (
                        "Recent verified lookup reuse is common in multi-turn spoken interaction."
                    ),
                    "when_to_use": (
                        "Use only after Goal Association resolved all references and the "
                        "verified tool-memory index contains one exact fresh match for "
                        "the same tool_id and material arguments."
                    ),
                    "semantic_type": "verified_tool_memory_retrieval",
                    "reference_resolution_authority": False,
                    "pre_execution_speech_guidance": (
                        "Say naturally that Chromie recently checked the exact subject "
                        "and is retrieving that result. Do not state the result before retrieval."
                    ),
                },
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
                    "or place. Use for user questions about current, tonight's, or "
                    "another supported short-range forecast, including today's or "
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
                                "Canonical city or place binding resolved from the "
                                "user turn, such as 重庆, 河南省内乡县, Chongqing, "
                                "or Neixiang County. Preserve this value exactly; "
                                "provider retries must not replace the Goal target."
                            ),
                        },
                        "location_context": {
                            "type": "object",
                            "description": (
                                "Optional model-authored structure for the same "
                                "resolved place. Include only components stated or "
                                "unambiguously resolved from discourse; this helps "
                                "the provider geocoder recognize hierarchical names."
                            ),
                            "properties": {
                                "locality": {"type": "string", "minLength": 1},
                                "admin1": {"type": "string", "minLength": 1},
                                "country": {"type": "string", "minLength": 1},
                                "aliases": {
                                    "type": "array",
                                    "items": {"type": "string", "minLength": 1},
                                    "maxItems": 6,
                                },
                            },
                            "additionalProperties": False,
                        },
                        "date": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "default": "today",
                            "description": "Forecast date requested by the user.",
                        },
                        "period": {
                            "type": "string",
                            "enum": [
                                "day",
                                "morning",
                                "afternoon",
                                "evening",
                                "tonight",
                            ],
                            "default": "day",
                            "description": (
                                "Local-day evidence scope. Use the exact canonical day-part "
                                "binding when the Goal asks for morning, afternoon, evening, "
                                "or tonight; a whole-day date is not equivalent evidence."
                            ),
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
                        "location": {"type": "string", "minLength": 1},
                        "country": {"type": ["string", "null"]},
                        "timezone": {"type": ["string", "null"]},
                        "date": {"type": ["string", "null"]},
                        "condition": {"type": "string", "minLength": 1},
                        "weather_code": {"type": ["integer", "null"]},
                        "current_temperature_c": {"type": ["number", "null"]},
                        "apparent_temperature_c": {"type": ["number", "null"]},
                        "high_c": {"type": ["number", "null"]},
                        "low_c": {"type": ["number", "null"]},
                        "precipitation_probability_max": {"type": ["number", "null"]},
                        "precipitation_sum_mm": {"type": ["number", "null"]},
                        "wind_speed_kmh": {"type": ["number", "null"]},
                        "forecast_period": {
                            "type": ["object", "null"],
                            "properties": {
                                        "scope": {
                                            "type": "string",
                                            "enum": [
                                                "morning",
                                                "afternoon",
                                                "evening",
                                                "tonight",
                                            ],
                                        },
                                        "start_local": {"type": "string", "minLength": 1},
                                        "end_local": {"type": "string", "minLength": 1},
                                        "condition": {"type": "string", "minLength": 1},
                                        "weather_code": {"type": ["integer", "null"]},
                                        "temperature_min_c": {"type": ["number", "null"]},
                                        "temperature_max_c": {"type": ["number", "null"]},
                                        "apparent_temperature_min_c": {
                                            "type": ["number", "null"]
                                        },
                                        "apparent_temperature_max_c": {
                                            "type": ["number", "null"]
                                        },
                                        "precipitation_probability_max": {
                                            "type": ["number", "null"]
                                        },
                            },
                            "required": [
                                "scope",
                                "start_local",
                                "end_local",
                                "condition",
                                "weather_code",
                                "temperature_min_c",
                                "temperature_max_c",
                                "apparent_temperature_min_c",
                                "apparent_temperature_max_c",
                                "precipitation_probability_max",
                            ],
                            "additionalProperties": False,
                        },
                        "summary": {"type": "string", "minLength": 1},
                        "source": {"type": "string", "minLength": 1},
                    },
                    "required": [
                        "location",
                        "country",
                        "timezone",
                        "date",
                        "condition",
                        "weather_code",
                        "current_temperature_c",
                        "apparent_temperature_c",
                        "high_c",
                        "low_c",
                        "precipitation_probability_max",
                        "precipitation_sum_mm",
                        "wind_speed_kmh",
                        "forecast_period",
                        "summary",
                        "source",
                    ],
                    "additionalProperties": False,
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
                    "interaction_executable": True,
                    "prompt_tier": "common",
                    "prompt_tier_reason": (
                        "Weather/current forecast questions are common spoken "
                        "tool requests and should be visible in the common capability context."
                    ),
                    "when_to_use": (
                        "Use when the user asks about current, today's, morning, afternoon, "
                        "evening, tonight, tomorrow, or upcoming weather or forecast for a "
                        "city/location."
                    ),
                    "tool_name": "weather",
                    "semantic_type": "weather_lookup",
                    "fast_speech_guidance": (
                        "Use one short, ordinary acknowledgement that says what Chromie is "
                        "looking at, such as the weather forecast for the requested place/date. "
                        "Do not use generic workflow language and do not state weather results "
                        "before the tool returns."
                    ),
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                        "delivery_modes": ["spoken_explanation", "structured_result"],
                        "acquisition": "structured_weather_retrieval",
                        "provider_result": "evidence_material",
                        "domain": "weather_forecast",
                        "supported_temporal_scopes": [
                            "current",
                            "today",
                            "morning",
                            "afternoon",
                            "evening",
                            "tonight",
                            "tomorrow",
                            "near_term_forecast",
                        ],
                        "unsupported_temporal_scopes": [
                            "annual",
                            "seasonal",
                            "historical",
                            "climate_normals",
                        ],
                        "scope_mismatch_policy": "clarify_or_unavailable_never_narrow",
                    },
                    "resource_contract": {
                        "provider_role": "acquire_information",
                        "plan_requires": [],
                        "plan_provides": ["resource_acquired"],
                        "completion_evidence": "trusted_tool_result",
                        "final_delivery_owner": "chromie_response_layer",
                    },
                    "pre_execution_speech_guidance": (
                        "Generate natural model-owned wording for the specific lookup. "
                        "The Host validates truth and timing but does not provide a fixed sentence."
                    ),
                },
            )
        ],
    )
    external_information = AgentManifest(
        agent_id="chromie.external_information",
        display_name="Chromie External Information Provider Adapter",
        description=(
            "Read-only adapter for a configured external-information provider. "
            "It retrieves grounded evidence for current facts, place or restaurant "
            "recommendations, how-to research, and other web-backed information; "
            "Chromie's Tool Result Interpreter and Response Composer own the final answer."
        ),
        transport=TransportSpec(
            kind="local_python",
            module="app.clients.external_information_client",
        ),
        tags=["chromie", "tool", "external_information", "external_read"],
        tools=[
            ToolCapability(
                name="chromie.external_information.retrieve",
                agent_id="chromie.external_information",
                display_name="Retrieve grounded external information",
                description=(
                    "Retrieve grounded, read-only external information for a fully "
                    "specified question. Use for restaurant or place recommendations, "
                    "current web facts, news, and how-to research when no more exact "
                    "registered Capability covers the Goal. The provider returns "
                    "evidence material; it does not author Chromie's final speech."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1200,
                        },
                        "request_kind": {
                            "type": "string",
                            "enum": [
                                "general_research",
                                "fact_lookup",
                                "recommendation",
                                "place_search",
                                "restaurant_search",
                                "how_to",
                                "news",
                            ],
                            "default": "general_research",
                        },
                        "location": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 300,
                        },
                        "time_scope": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 160,
                        },
                        "freshness": {
                            "type": "string",
                            "enum": ["current", "recent", "any"],
                            "default": "current",
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 8,
                        },
                        "constraints": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["question"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "object"},
                        "summary": {"type": "string", "minLength": 1},
                        "items": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "sources": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "url": {"type": "string"},
                                    "published_at": {"type": ["string", "null"]},
                                    "retrieved_at": {"type": ["string", "null"]},
                                },
                                "additionalProperties": False,
                            },
                        },
                        "retrieved_at": {"type": "string", "minLength": 1},
                        "provider": {"type": "string", "minLength": 1},
                    },
                    "required": [
                        "query",
                        "summary",
                        "items",
                        "sources",
                        "retrieved_at",
                        "provider",
                    ],
                    "additionalProperties": False,
                },
                effects=["read_only", "external_read", "information_retrieval"],
                safety_class="safe_read",
                availability=_external_information_availability(),
                execution=ExecutionPolicy(
                    can_run_parallel=True,
                    timeout_s=max(
                        0.1,
                        agent_service_settings.external_information_timeout_ms / 1000.0,
                    ),
                    idempotent=True,
                    side_effect_free=True,
                ),
                default_failure_policy=FailurePolicy(strategy="stop_and_report"),
                llm_hints={
                    "interaction_executable": True,
                    "prompt_tier": "common",
                    "prompt_tier_reason": (
                        "Externally grounded facts and recommendations are common user needs."
                    ),
                    "when_to_use": (
                        "Use for a provider-neutral information resource Goal after "
                        "Goal Association has fixed all material bindings and no more "
                        "specific exact read Capability covers the request."
                    ),
                    "when_not_to_use": (
                        "Do not use as a topical substitute for physical objects, "
                        "effectful actions, or a more exact registered Capability."
                    ),
                    "semantic_type": "external_information_retrieval",
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                        "acquisition": "external_grounded_retrieval",
                        "provider_result": "evidence_material",
                        "delivery_modes": ["spoken_explanation", "structured_result"],
                        "supported_request_kinds": [
                            "general_research",
                            "fact_lookup",
                            "recommendation",
                            "place_search",
                            "restaurant_search",
                            "how_to",
                            "news",
                        ],
                    },
                    "resource_contract": {
                        "provider_role": "acquire_information",
                        "plan_requires": [],
                        "plan_provides": ["resource_acquired"],
                        "completion_evidence": "grounded_retrieval_evidence",
                        "final_delivery_owner": "chromie_response_layer",
                    },
                    "pre_execution_speech_guidance": (
                        "Acknowledge the specific information being checked without "
                        "claiming a result before provider evidence returns."
                    ),
                },
            )
        ],
    )

    return [speech, media, task, memory, weather, external_information]


def chromie_capability_bundle() -> CapabilityBundle:
    return CapabilityBundle(source="chromie", agents=chromie_manifests())


def build_chromie_registry(extra_bundles: list[CapabilityBundle] | None = None):
    from .models import CapabilityRegistry

    bundles = [chromie_capability_bundle()]
    bundles.extend(extra_bundles or [])
    return CapabilityRegistry.from_bundles(bundles)
