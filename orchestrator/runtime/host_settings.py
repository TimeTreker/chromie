"""Immutable, typed Host startup settings.

This module owns environment parsing for the maintained VoiceAssistant startup
surface. Semantic identity and personality are intentionally excluded: they
remain owner-approved model context, not Python configuration policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class HostConfigurationError(ValueError):
    """One invalid operator/profile setting with its owning variable."""


def _raw(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name)
    return default if value is None else str(value)


def _text(values: Mapping[str, str], name: str, default: str = "") -> str:
    return _raw(values, name, default).strip()


def _bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    normalized = str(raw).strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise HostConfigurationError(
        f"{name} must be a boolean (0/1, false/true, no/yes, off/on); got {raw!r}"
    )


def _int(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = values.get(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except ValueError as exc:
            raise HostConfigurationError(
                f"{name} must be an integer; got {raw!r}"
            ) from exc
    if minimum is not None and value < minimum:
        raise HostConfigurationError(f"{name} must be >= {minimum}; got {value}")
    if maximum is not None and value > maximum:
        raise HostConfigurationError(f"{name} must be <= {maximum}; got {value}")
    return value


def _float(
    values: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = values.get(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(str(raw).strip())
        except ValueError as exc:
            raise HostConfigurationError(
                f"{name} must be a number; got {raw!r}"
            ) from exc
    if minimum is not None and value < minimum:
        raise HostConfigurationError(f"{name} must be >= {minimum}; got {value}")
    if maximum is not None and value > maximum:
        raise HostConfigurationError(f"{name} must be <= {maximum}; got {value}")
    return value


def _choice(
    values: Mapping[str, str],
    name: str,
    default: str,
    allowed: set[str],
) -> str:
    value = _text(values, name, default).casefold()
    if value not in allowed:
        raise HostConfigurationError(
            f"{name} must be one of {sorted(allowed)}; got {value!r}"
        )
    return value


def _path(
    values: Mapping[str, str],
    name: str,
    default: str,
    *,
    project_root: Path,
) -> Path:
    path = Path(_raw(values, name, default)).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


@dataclass(frozen=True)
class AudioInputSettings:
    asr_url: str
    asr_timeout_ms: int
    mode: str
    injected_rate: int
    injected_channels: int
    min_rms: float
    barge_in_min_rms: float
    min_audio_ms: int
    input_gain: float
    vad_mode: int
    vad_silence_ms: int
    vad_max_utterance_ms: int


@dataclass(frozen=True)
class CognitionSettings:
    llm_url: str
    ollama_model: str
    failure_response_model: str
    agent_url: str
    action_executor_url: str
    agent_timeout_ms: int
    action_timeout_ms: int
    action_dry_run: bool
    enable_agent: bool
    enable_interaction_response: bool
    enable_soridormi_skills: bool
    fast_first_response_enabled: bool
    fast_first_tool_response_enabled: bool
    core_generated_fast_speech_enabled: bool
    fast_planner_mode: str
    fast_planner_timeout_ms: int
    deep_planner_mode: str
    deep_planner_timeout_ms: int
    response_composer_mode: str
    response_composer_timeout_ms: int
    tool_result_interpreter_timeout_ms: int
    goal_association_mode: str
    goal_association_timeout_ms: int
    task_continuity_mode: str
    task_continuity_timeout_ms: int
    runtime_mode: str
    apply_lanes: frozenset[str]
    requested_fallback_policy: str
    legacy_semantic_fallback_enabled: bool
    runtime_timeout_ms: int
    host_replan_budget: int
    social_attention_mode: str
    capability_manifest_paths: str
    soridormi_manifest: Path


@dataclass(frozen=True)
class PlaybackSettings:
    tts_url: str
    output_mode: str
    discard_playback_realtime: bool
    output_rate: int
    flush_chars: int
    max_text_chars: int
    text_chunking_enabled: bool
    chunk_chars: int
    cjk_chunk_chars: int
    first_chunk_chars: int
    min_chunk_chars: int
    cjk_min_chunk_chars: int
    sample_rate: int
    speaker_id: str
    save_audio_enabled: bool
    voice_system_prompt: str
    ws_retries: int
    ws_retry_delay_ms: int
    playback_chunk_ms: int
    concurrency: int
    playback_start_timeout_ms: int
    fast_audio_enabled: bool
    fast_audio_hedge_ms: int
    fast_audio_prime_on_startup: bool
    fast_audio_prime_timeout_ms: int
    fast_audio_content_gate_enabled: bool
    fast_audio_max_cue_seconds: float
    fast_audio_transcript_min_similarity: float
    fast_audio_generation_attempts: int
    fast_audio_cache_dir: Path
    fast_audio_cache_revision: str
    ready_greeting_enabled: bool
    ready_greeting_text: str
    ready_greeting_fallback_text: str
    ready_greeting_language: str
    ready_greeting_model: str
    ready_greeting_num_predict: int
    ready_greeting_generation_timeout_ms: int
    ready_greeting_timeout_ms: int


@dataclass(frozen=True)
class SessionLifecycleSettings:
    timing_logs_enabled: bool
    addressedness_gate_enabled: bool
    addressedness_engagement_timeout_s: float
    confirmation_ttl_s: float
    body_recovery_max_attempts: int
    body_recovery_confirmation_ttl_s: float
    idle_sweep_s: float
    idle_timeout_ms: float


@dataclass(frozen=True)
class EvidenceSettings:
    cognitive_enabled: bool
    cognitive_include_text: bool
    cognitive_path: Path
    runtime_identity_path: Path
    recordings_dir: Path


@dataclass(frozen=True)
class HostSettingsSnapshot:
    audio_input: AudioInputSettings
    cognition: CognitionSettings
    playback: PlaybackSettings
    session: SessionLifecycleSettings
    evidence: EvidenceSettings

    @classmethod
    def from_env(
        cls,
        *,
        project_root: Path,
        environ: Mapping[str, str] | None = None,
    ) -> "HostSettingsSnapshot":
        values = os.environ if environ is None else environ
        ollama_model = _text(values, "OLLAMA_MODEL", "gemma4:e2b") or "gemma4:e2b"
        failure_model = (
            _text(values, "AGENT_RESPONSE_COMPOSER_MODEL", ollama_model)
            or ollama_model
        )
        max_text_chars = _int(values, "TTS_MAX_TEXT_CHARS", 220, minimum=20)
        runtime_lanes = frozenset(
            item.strip()
            for item in _raw(
                values,
                "ORCH_COGNITIVE_APPLY_LANES",
                "chat,robot_action,tool",
            ).split(",")
            if item.strip()
        )
        if not runtime_lanes:
            raise HostConfigurationError(
                "ORCH_COGNITIVE_APPLY_LANES must contain at least one lane"
            )
        social_mode = (
            _text(values, "CHROMIE_SOCIAL_ATTENTION_MODE")
            or _text(values, "AGENT_SOCIAL_ATTENTION_MODE")
            or "on"
        ).casefold()
        if social_mode not in {"off", "report_only", "on"}:
            raise HostConfigurationError(
                "CHROMIE_SOCIAL_ATTENTION_MODE/AGENT_SOCIAL_ATTENTION_MODE "
                f"must be off, report_only, or on; got {social_mode!r}"
            )
        playback = PlaybackSettings(
            tts_url=_text(values, "TTS_URL", "ws://localhost:5000"),
            output_mode=_choice(
                values,
                "ORCH_AUDIO_OUTPUT_MODE",
                "device",
                {"device", "discard"},
            ),
            discard_playback_realtime=_bool(
                values, "ORCH_DISCARD_PLAYBACK_REALTIME", True
            ),
            output_rate=_int(values, "ORCH_OUTPUT_RATE", 44100, minimum=1),
            flush_chars=_int(values, "TTS_FLUSH_CHARS", 160, minimum=1),
            max_text_chars=max_text_chars,
            text_chunking_enabled=_bool(values, "ORCH_TTS_TEXT_CHUNKING", True),
            chunk_chars=min(
                max_text_chars,
                _int(values, "ORCH_TTS_CHUNK_CHARS", 120, minimum=20),
            ),
            cjk_chunk_chars=min(
                max_text_chars,
                _int(values, "ORCH_TTS_CJK_CHUNK_CHARS", 36, minimum=12),
            ),
            first_chunk_chars=_int(
                values, "ORCH_TTS_FIRST_CHUNK_CHARS", 16, minimum=0
            ),
            min_chunk_chars=_int(
                values, "ORCH_TTS_MIN_CHUNK_CHARS", 20, minimum=1
            ),
            cjk_min_chunk_chars=_int(
                values, "ORCH_TTS_CJK_MIN_CHUNK_CHARS", 8, minimum=1
            ),
            sample_rate=_int(values, "TTS_SAMPLE_RATE", 44100, minimum=1),
            speaker_id=_text(values, "TTS_SPEAKER_ID", "default") or "default",
            save_audio_enabled=_bool(values, "ORCH_SAVE_AUDIO", False),
            voice_system_prompt=_raw(
                values,
                "ORCH_VOICE_SYSTEM_PROMPT",
                "You are a real-time voice assistant. Answer briefly in 1 to 3 short sentences. "
                "Do not use markdown. Do not use numbered lists unless the user explicitly asks for a list. "
                "Avoid long explanations unless the user asks for details.",
            ),
            ws_retries=_int(values, "ORCH_TTS_WS_RETRIES", 2, minimum=0),
            ws_retry_delay_ms=_int(
                values, "ORCH_TTS_WS_RETRY_DELAY_MS", 300, minimum=0
            ),
            playback_chunk_ms=_int(
                values, "ORCH_PLAYBACK_CHUNK_MS", 80, minimum=1
            ),
            concurrency=_int(values, "ORCH_TTS_CONCURRENCY", 1, minimum=1),
            playback_start_timeout_ms=_int(
                values,
                "ORCH_TTS_PLAYBACK_START_TIMEOUT_MS",
                20000,
                minimum=100,
            ),
            fast_audio_enabled=_bool(values, "ORCH_FAST_FIRST_AUDIO_ENABLED", True),
            fast_audio_hedge_ms=_int(
                values, "ORCH_FAST_FIRST_AUDIO_HEDGE_MS", 750, minimum=0
            ),
            fast_audio_prime_on_startup=_bool(
                values, "ORCH_FAST_FIRST_AUDIO_PRIME_ON_STARTUP", True
            ),
            fast_audio_prime_timeout_ms=_int(
                values,
                "ORCH_FAST_FIRST_AUDIO_PRIME_TIMEOUT_MS",
                120000,
                minimum=1000,
            ),
            fast_audio_content_gate_enabled=_bool(
                values, "ORCH_FAST_FIRST_AUDIO_CONTENT_GATE_ENABLED", True
            ),
            fast_audio_max_cue_seconds=_float(
                values,
                "ORCH_FAST_FIRST_AUDIO_MAX_CUE_SECONDS",
                4.0,
                minimum=0.25,
            ),
            fast_audio_transcript_min_similarity=_float(
                values,
                "ORCH_FAST_FIRST_AUDIO_TRANSCRIPT_MIN_SIMILARITY",
                0.65,
                minimum=0.0,
                maximum=1.0,
            ),
            fast_audio_generation_attempts=_int(
                values,
                "ORCH_FAST_FIRST_AUDIO_GENERATION_ATTEMPTS",
                2,
                minimum=1,
            ),
            fast_audio_cache_dir=_path(
                values,
                "ORCH_FAST_FIRST_AUDIO_CACHE_DIR",
                ".chromie/cache/fast-first-audio",
                project_root=project_root,
            ),
            fast_audio_cache_revision=_text(
                values, "ORCH_FAST_FIRST_AUDIO_CACHE_REVISION", ""
            ),
            ready_greeting_enabled=_bool(
                values, "ORCH_RUNTIME_READY_GREETING_ENABLED", True
            ),
            ready_greeting_text=_text(
                values, "ORCH_RUNTIME_READY_GREETING_TEXT", ""
            ),
            ready_greeting_fallback_text=_text(
                values,
                "ORCH_RUNTIME_READY_GREETING_FALLBACK_TEXT",
                "嗨，我醒啦！",
            ),
            ready_greeting_language=(
                _text(values, "ORCH_RUNTIME_READY_GREETING_LANGUAGE", "zh-CN")
                or "zh-CN"
            ),
            ready_greeting_model=_text(
                values, "ORCH_RUNTIME_READY_GREETING_MODEL", ""
            ),
            ready_greeting_num_predict=_int(
                values,
                "ORCH_RUNTIME_READY_GREETING_NUM_PREDICT",
                32,
                minimum=8,
            ),
            ready_greeting_generation_timeout_ms=_int(
                values,
                "ORCH_RUNTIME_READY_GREETING_GENERATION_TIMEOUT_MS",
                15000,
                minimum=1000,
            ),
            ready_greeting_timeout_ms=_int(
                values,
                "ORCH_RUNTIME_READY_GREETING_TIMEOUT_MS",
                45000,
                minimum=1000,
            ),
        )
        return cls(
            audio_input=AudioInputSettings(
                asr_url=_text(values, "ASR_URL", "ws://localhost:9001"),
                asr_timeout_ms=_int(
                    values, "ORCH_ASR_TIMEOUT_MS", 30000, minimum=1
                ),
                mode=_choice(
                    values,
                    "ORCH_AUDIO_INPUT_MODE",
                    "device",
                    {"device", "stdin"},
                ),
                injected_rate=_int(values, "ORCH_INPUT_RATE", 16000, minimum=1),
                injected_channels=_int(
                    values, "ORCH_INPUT_CHANNELS", 1, minimum=1
                ),
                min_rms=_float(values, "ORCH_MIN_RMS", 120.0, minimum=0.0),
                barge_in_min_rms=_float(
                    values, "ORCH_BARGE_IN_MIN_RMS", 350.0, minimum=0.0
                ),
                min_audio_ms=_int(
                    values, "ORCH_MIN_AUDIO_MS", 450, minimum=1
                ),
                input_gain=_float(
                    values, "ORCH_INPUT_GAIN", 1.0, minimum=0.0
                ),
                vad_mode=_int(values, "ORCH_VAD_MODE", 3, minimum=0, maximum=3),
                vad_silence_ms=_int(
                    values, "ORCH_VAD_SILENCE_MS", 650, minimum=1
                ),
                vad_max_utterance_ms=_int(
                    values,
                    "ORCH_VAD_MAX_UTTERANCE_MS",
                    20000,
                    minimum=1000,
                ),
            ),
            cognition=CognitionSettings(
                llm_url=_text(
                    values, "LLM_URL", "http://localhost:11434/api/generate"
                ),
                ollama_model=ollama_model,
                failure_response_model=failure_model,
                agent_url=_text(values, "AGENT_URL", "http://127.0.0.1:8092"),
                action_executor_url=_text(
                    values, "ACTION_EXECUTOR_URL", "http://127.0.0.1:8095"
                ),
                agent_timeout_ms=_int(
                    values, "ORCH_AGENT_TIMEOUT_MS", 9000, minimum=100
                ),
                action_timeout_ms=_int(
                    values, "ORCH_ACTION_TIMEOUT_MS", 5000, minimum=100
                ),
                action_dry_run=_bool(values, "ORCH_ACTION_DRY_RUN", True),
                enable_agent=_bool(values, "ORCH_ENABLE_AGENT", False),
                enable_interaction_response=_bool(
                    values, "ORCH_ENABLE_INTERACTION_RESPONSE", False
                ),
                enable_soridormi_skills=_bool(
                    values, "ORCH_ENABLE_SORIDORMI_SKILLS", False
                ),
                fast_first_response_enabled=_bool(
                    values, "ORCH_FAST_FIRST_RESPONSE_ENABLED", True
                ),
                fast_first_tool_response_enabled=_bool(
                    values, "ORCH_FAST_FIRST_TOOL_RESPONSE_ENABLED", True
                ),
                core_generated_fast_speech_enabled=_bool(
                    values,
                    "ORCH_AGENT_GOAL_INTERPRETER_GENERATED_FAST_SPEECH_ENABLED",
                    True,
                ),
                fast_planner_mode=_choice(
                    values,
                    "ORCH_FAST_PLANNER_MODE",
                    "off",
                    {"off", "report_only"},
                ),
                fast_planner_timeout_ms=_int(
                    values, "ORCH_FAST_PLANNER_TIMEOUT_MS", 3000, minimum=100
                ),
                deep_planner_mode=_choice(
                    values,
                    "ORCH_DEEP_PLANNER_MODE",
                    "off",
                    {"off", "report_only"},
                ),
                deep_planner_timeout_ms=_int(
                    values, "ORCH_DEEP_PLANNER_TIMEOUT_MS", 10000, minimum=100
                ),
                response_composer_mode=_choice(
                    values,
                    "ORCH_RESPONSE_COMPOSER_MODE",
                    "off",
                    {"off", "report_only"},
                ),
                response_composer_timeout_ms=_int(
                    values,
                    "ORCH_RESPONSE_COMPOSER_TIMEOUT_MS",
                    5000,
                    minimum=100,
                ),
                tool_result_interpreter_timeout_ms=_int(
                    values,
                    "ORCH_TOOL_RESULT_INTERPRETER_TIMEOUT_MS",
                    5500,
                    minimum=100,
                ),
                goal_association_mode=_choice(
                    values,
                    "ORCH_GOAL_ASSOCIATION_MODE",
                    "off",
                    {"off", "report_only"},
                ),
                goal_association_timeout_ms=_int(
                    values,
                    "ORCH_GOAL_ASSOCIATION_TIMEOUT_MS",
                    3500,
                    minimum=100,
                ),
                task_continuity_mode=_choice(
                    values,
                    "ORCH_TASK_CONTINUITY_MODE",
                    "off",
                    {"off", "report_only", "apply"},
                ),
                task_continuity_timeout_ms=_int(
                    values,
                    "ORCH_TASK_CONTINUITY_TIMEOUT_MS",
                    3500,
                    minimum=100,
                ),
                runtime_mode=_choice(
                    values,
                    "ORCH_COGNITIVE_RUNTIME_MODE",
                    "apply",
                    {"off", "report_only", "apply"},
                ),
                apply_lanes=runtime_lanes,
                requested_fallback_policy=_choice(
                    values,
                    "ORCH_COGNITIVE_FALLBACK_POLICY",
                    "fail_closed",
                    {"legacy", "fail_closed"},
                ),
                legacy_semantic_fallback_enabled=_bool(
                    values, "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED", False
                ),
                runtime_timeout_ms=_int(
                    values,
                    "ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS",
                    25000,
                    minimum=1000,
                ),
                host_replan_budget=_int(
                    values,
                    "ORCH_COGNITIVE_HOST_REPLAN_BUDGET",
                    1,
                    minimum=0,
                ),
                social_attention_mode=social_mode,
                capability_manifest_paths=_text(
                    values, "AGENT_CAPABILITY_MANIFESTS", ""
                ),
                soridormi_manifest=_path(
                    values,
                    "ORCH_SORIDORMI_MANIFEST",
                    "capabilities/soridormi.json",
                    project_root=project_root,
                ),
            ),
            playback=playback,
            session=SessionLifecycleSettings(
                timing_logs_enabled=_bool(
                    values, "ORCH_SESSION_TIMING_LOGS", True
                ),
                addressedness_gate_enabled=_bool(
                    values, "ORCH_ADDRESSEDNESS_GATE_ENABLED", True
                ),
                addressedness_engagement_timeout_s=_float(
                    values,
                    "ORCH_ADDRESSEDNESS_ENGAGEMENT_TIMEOUT_SEC",
                    45.0,
                    minimum=1.0,
                ),
                confirmation_ttl_s=_float(
                    values, "ORCH_CONFIRMATION_TTL_SEC", 20.0, minimum=0.1
                ),
                body_recovery_max_attempts=_int(
                    values, "ORCH_BODY_RECOVERY_MAX_ATTEMPTS", 1, minimum=0
                ),
                body_recovery_confirmation_ttl_s=_float(
                    values,
                    "ORCH_BODY_RECOVERY_CONFIRMATION_TTL_S",
                    10.0,
                    minimum=1.0,
                ),
                idle_sweep_s=_float(
                    values, "ORCH_SESSION_IDLE_SWEEP_S", 5.0, minimum=1.0
                ),
                idle_timeout_ms=_float(
                    values,
                    "ORCH_SESSION_IDLE_TIMEOUT_MS",
                    120000.0,
                    minimum=1000.0,
                ),
            ),
            evidence=EvidenceSettings(
                cognitive_enabled=_bool(
                    values, "ORCH_COGNITIVE_EVIDENCE_ENABLED", True
                ),
                cognitive_include_text=_bool(
                    values, "ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT", False
                ),
                cognitive_path=_path(
                    values,
                    "ORCH_COGNITIVE_EVIDENCE_PATH",
                    ".chromie/evidence/cognitive-runtime/events.jsonl",
                    project_root=project_root,
                ),
                runtime_identity_path=_path(
                    values,
                    "ORCH_COGNITIVE_RUN_IDENTITY_PATH",
                    ".chromie/evidence/runtime-identity.json",
                    project_root=project_root,
                ),
                recordings_dir=_path(
                    values,
                    "RECORDINGS_DIR",
                    "recordings",
                    project_root=project_root,
                ),
            ),
        )
