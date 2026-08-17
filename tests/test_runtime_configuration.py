from __future__ import annotations

import fcntl
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from agent.app import main as agent_main
from agent.app.cognitive_core.goal_interpreter.engine import Settings as GoalInterpreterSettings
from orchestrator.runtime.host_settings import HostSettingsSnapshot


ROOT = Path(__file__).resolve().parents[1]


def _common_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (ROOT / ".env.common").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    return values


class RuntimeConfigurationTests(unittest.TestCase):
    def test_goal_interpreter_has_no_rules_or_catalog_compatibility_settings(self) -> None:
        settings = GoalInterpreterSettings()
        self.assertFalse(hasattr(settings, "rules_first"))
        self.assertFalse(hasattr(settings, "capability_catalog_timeout_ms"))

    def test_standalone_service_fallbacks_match_documented_common_budgets(self) -> None:
        asr_settings_source = (ROOT / "asr" / "settings.py").read_text(encoding="utf-8")
        settings = HostSettingsSnapshot.from_env(project_root=ROOT, environ={})
        self.assertIn('"SHERPA_ONNX_NUM_THREADS",\n                2,', asr_settings_source)
        self.assertEqual(settings.cognition.agent_timeout_ms, 9000)
        self.assertEqual(settings.model_generation.keep_alive, "24h")

    def test_asr_image_includes_every_standalone_server_module(self) -> None:
        dockerfile = (ROOT / "asr" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn(
            "COPY backends.py server.py settings.py transcription.py ./",
            dockerfile,
        )

    def test_goal_interpreter_host_budget_exceeds_service_budget(self) -> None:
        values = _common_env()
        self.assertGreater(
            int(values["ORCH_AGENT_GOAL_INTERPRETER_TIMEOUT_MS"]),
            int(values["AGENT_GOAL_INTERPRETER_TIMEOUT_MS"]),
        )

    def test_goal_interpreter_uses_fast_llm_by_default(self) -> None:
        values = _common_env()
        self.assertEqual(values["AGENT_GOAL_INTERPRETER_MODEL"], "qwen3:4b")
        self.assertEqual(
            values["AGENT_COGNITIVE_GATEWAY_ATTENTION_ENABLED"],
            "1",
        )
        self.assertEqual(
            values["AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL"],
            "qwen3:4b",
        )
        self.assertEqual(values["AGENT_GOAL_INTERPRETER_LLM_KEEP_ALIVE"], "24h")
        self.assertEqual(values["AGENT_GOAL_INTERPRETER_WARM_LLM_ON_STARTUP"], "1")
        self.assertEqual(values["AGENT_GOAL_INTERPRETER_WARM_LLM_TIMEOUT_MS"], "60000")
        self.assertEqual(values["AGENT_GOAL_INTERPRETER_TIMEOUT_MS"], "5400")
        self.assertEqual(values["AGENT_GOAL_INTERPRETER_LLM_NUM_CTX"], "4096")
        self.assertEqual(values["AGENT_GOAL_INTERPRETER_LLM_NUM_PREDICT"], "512")

        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for name in (
            "AGENT_GOAL_INTERPRETER_LOG_LEVEL",
            "CHROMIE_AGENT_GOAL_INTERPRETER_DEBUG_RAW",
            "CHROMIE_AGENT_GOAL_INTERPRETER_DEBUG_PROMPT",
        ):
            self.assertIn(f"{name}:", compose)
        compose_keys = {
            line.strip().split(":", 1)[0]
            for line in compose.splitlines()
            if line.startswith("      AGENT_") or line.startswith("      CHROMIE_AGENT_")
        }
        for stale in (
            "AGENT_GOAL_INTERPRETER_MODE",
            "AGENT_GOAL_INTERPRETER_USE_LLM",
            "AGENT_GOAL_INTERPRETER_REVIEW_TIMEOUT_MS",
            "AGENT_GOAL_INTERPRETER_CONFIDENCE_THRESHOLD",
        ):
            self.assertNotIn(stale, compose_keys)
        self.assertFalse(
            any(
                name.startswith("AGENT_GOAL_INTERPRETER_CAPABILITY_CATALOG_")
                for name in compose_keys
            )
        )

    def test_documented_weather_controls_reach_agent_container(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for name in (
            "AGENT_WEATHER_ENABLED",
            "AGENT_WEATHER_TIMEOUT_S",
            "AGENT_WEATHER_GEOCODING_URL",
            "AGENT_WEATHER_FORECAST_URL",
        ):
            self.assertIn(f"{name}:", compose)

    def test_ollama_keeps_goal_interpreter_and_agent_models_loaded_without_extra_parallelism(self) -> None:
        values = _common_env()
        self.assertEqual(values["OLLAMA_MAX_LOADED_MODELS"], "2")
        self.assertEqual(values["OLLAMA_NUM_PARALLEL"], "1")
        self.assertEqual(values["OLLAMA_AUTO_RESTART_ON_CRASH"], "1")
        self.assertEqual(values["OLLAMA_WARM_NUM_PREDICT"], "1")
        self.assertEqual(values["AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE"], "2.0")
        self.assertEqual(values["AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS"], "512")

    def test_capability_planner_has_json_output_budget(self) -> None:
        values = _common_env()
        self.assertEqual(values["AGENT_SOCIAL_ATTENTION_MODE"], "on")
        self.assertFalse(
            any(name.startswith("AGENT_SOCIAL_ATTENTION_FALLBACK_") for name in values)
        )
        self.assertEqual(values["AGENT_CAPABILITY_MANIFESTS"], "")
        self.assertEqual(values["SORIDORMI_MCP_URL"], "")

    def test_common_profile_uses_one_coherent_cognitive_runtime(self) -> None:
        values = _common_env()
        self.assertEqual(values["ORCH_FAST_FIRST_RESPONSE_ENABLED"], "1")
        self.assertEqual(values["ORCH_FAST_FIRST_AUDIO_ENABLED"], "1")
        self.assertEqual(values["ORCH_FAST_FIRST_AUDIO_HEDGE_MS"], "750")
        self.assertEqual(
            values["ORCH_FAST_FIRST_AUDIO_CACHE_DIR"],
            ".chromie/cache/fast-first-audio",
        )
        self.assertEqual(values["ORCH_FAST_FIRST_AUDIO_PRIME_ON_STARTUP"], "1")
        self.assertEqual(values["ORCH_FAST_FIRST_AUDIO_PRIME_TIMEOUT_MS"], "120000")
        self.assertEqual(values["ORCH_FAST_FIRST_AUDIO_CONTENT_GATE_ENABLED"], "1")
        self.assertEqual(values["ORCH_FAST_FIRST_AUDIO_MAX_CUE_SECONDS"], "4")
        self.assertEqual(
            values["ORCH_FAST_FIRST_AUDIO_TRANSCRIPT_MIN_SIMILARITY"],
            "0.65",
        )
        self.assertEqual(values["ORCH_ADDRESSEDNESS_GATE_ENABLED"], "1")
        self.assertEqual(values["ORCH_ADDRESSEDNESS_ENGAGEMENT_TIMEOUT_SEC"], "45")
        self.assertEqual(
            values[
                "ORCH_AGENT_GOAL_INTERPRETER_GENERATED_FAST_SPEECH_ENABLED"
            ],
            "1",
        )
        self.assertEqual(values["ORCH_ENABLE_INTERACTION_RESPONSE"], "1")
        self.assertEqual(values["ORCH_ENABLE_SORIDORMI_CAPABILITIES"], "0")
        self.assertEqual(values["TTS_CANDIDATE_CANCEL_DRAIN_TIMEOUT_SEC"], "3")
        self.assertEqual(
            values["TTS_CANDIDATE_COLD_FIRST_AUDIO_TIMEOUT_SEC"], "180"
        )
        self.assertEqual(values["TTS_CANDIDATE_COLD_REQUEST_TIMEOUT_SEC"], "240")
        self.assertEqual(values["TTS_CANDIDATE_FIRST_AUDIO_TIMEOUT_SEC"], "20")
        self.assertEqual(values["TTS_CANDIDATE_REQUEST_TIMEOUT_SEC"], "60")
        self.assertEqual(values["TTS_PYTORCH_ALLOC_CONF"], "expandable_segments:True")
        self.assertEqual(values["ORCH_COGNITIVE_RUNTIME_MODE"], "apply")
        self.assertEqual(values["ORCH_COGNITIVE_APPLY_LANES"], "chat,memory,tool")
        self.assertEqual(values["ORCH_GOAL_ASSOCIATION_MODE"], "off")
        self.assertEqual(values["ORCH_FAST_PLANNER_MODE"], "off")
        self.assertEqual(values["ORCH_DEEP_PLANNER_MODE"], "off")
        self.assertEqual(values["ORCH_RESPONSE_COMPOSER_MODE"], "off")

    def test_runtime_ready_greeting_precedes_live_microphone_loop(self) -> None:
        source = (ROOT / "orchestrator" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            source.index("await self._announce_runtime_ready()"),
            source.index("await self.mic_stream()"),
        )

    def test_chinese_tts_uses_smaller_chunks_for_lower_first_audio_latency(self) -> None:
        values = _common_env()
        self.assertEqual(values["ORCH_TTS_CJK_CHUNK_CHARS"], "36")
        self.assertEqual(values["ORCH_TTS_CJK_MIN_CHUNK_CHARS"], "8")
        self.assertEqual(values["ORCH_RUNTIME_READY_GREETING_ENABLED"], "1")
        self.assertEqual(
            values["ORCH_RUNTIME_READY_GREETING_SPEECH_ENABLED"], "0"
        )
        self.assertEqual(values["ORCH_RUNTIME_READY_GREETING_TEXT"], "")
        self.assertEqual(
            values["ORCH_RUNTIME_READY_GREETING_FALLBACK_TEXT"],
            "",
        )
        self.assertEqual(values["ORCH_RUNTIME_READY_GREETING_LANGUAGE"], "zh-CN")
        self.assertEqual(values["ORCH_RUNTIME_READY_GREETING_MODEL"], "")
        self.assertEqual(values["ORCH_RUNTIME_READY_GREETING_NUM_PREDICT"], "32")
        self.assertEqual(
            values["ORCH_RUNTIME_READY_GREETING_GENERATION_TIMEOUT_MS"],
            "15000",
        )
        self.assertEqual(
            values["ORCH_RUNTIME_READY_GREETING_TIMEOUT_MS"],
            "45000",
        )

    def test_default_tts_is_cosyvoice_with_oute_diagnostics_retained_for_fallback(self) -> None:
        values = _common_env()
        self.assertEqual(values["CHROMIE_TTS_BACKEND"], "cosyvoice3")
        self.assertEqual(values["TTS_PROVIDER"], "fun-cosyvoice3-0.5b")
        self.assertEqual(values["TTS_VOICE_ROOT"], "assets/tts/voices")
        self.assertEqual(values["TTS_DEFAULT_SPEAKER"], "chromie_mixed")
        self.assertEqual(values["TTS_COSYVOICE_COMPACT_COGNITION"], "1")
        self.assertEqual(values["ORCH_TTS_CONCURRENCY"], "1")
        # Oute remains an explicit fallback, so its diagnostic controls stay valid.
        self.assertEqual(values["TTS_AUDIO_CODEC_DEVICE"], "auto")
        self.assertEqual(values["TTS_DETAILED_TIMING"], "1")
        self.assertEqual(values["TTS_METRICS_WINDOW"], "20")
        self.assertEqual(values["GGML_CUDA_DISABLE_GRAPHS"], "0")

        profile = (ROOT / "env" / "profiles" / "rtx4090_laptop.env").read_text(
            encoding="utf-8"
        )
        self.assertIn("TTS_CONTEXT_SIZE=4096", profile)
        self.assertIn("TTS_MAX_LENGTH=4096", profile)
        self.assertIn("AGENT_MODEL=gemma4:e4b", profile)
        self.assertIn("AGENT_GOAL_ASSOCIATION_MODEL=gemma4:e4b", profile)
        self.assertIn("AGENT_DEEP_PLANNER_MODEL=gemma4:e4b", profile)
        self.assertIn("AGENT_RESPONSE_COMPOSER_MODEL=gemma4:e4b", profile)
        self.assertIn("TTS_COSYVOICE_COMPACT_COGNITION=0", profile)
        self.assertIn("OLLAMA_MAX_LOADED_MODELS=1", profile)
        self.assertIn("AGENT_DEEP_PLANNER_NUM_PREDICT=4096", profile)

        rtx5090 = (ROOT / "env" / "profiles" / "rtx5090.env").read_text(
            encoding="utf-8"
        )
        self.assertIn("TTS_CONTEXT_SIZE=8192", rtx5090)
        self.assertIn("TTS_MAX_LENGTH=8192", rtx5090)
        self.assertIn("TTS_RESET_LLAMA_STATE=1", rtx5090)
        self.assertIn("AGENT_MODEL=gemma4:12b", rtx5090)
        self.assertIn("AGENT_GOAL_ASSOCIATION_MODEL=gemma4:12b", rtx5090)
        self.assertIn("AGENT_DEEP_PLANNER_MODEL=gemma4:12b", rtx5090)
        self.assertIn("AGENT_RESPONSE_COMPOSER_MODEL=gemma4:12b", rtx5090)
        self.assertIn("TTS_COSYVOICE_COMPACT_COGNITION=0", rtx5090)
        self.assertIn("TTS_COSYVOICE_OLLAMA_NUM_CTX=32768", rtx5090)
        self.assertIn("OLLAMA_MAX_LOADED_MODELS=2", rtx5090)
        self.assertIn("OLLAMA_NUM_CTX=32768", rtx5090)
        self.assertIn("AGENT_COGNITIVE_GATEWAY_ATTENTION_NUM_CTX=32768", rtx5090)
        self.assertIn("AGENT_GOAL_INTERPRETER_LLM_NUM_CTX=32768", rtx5090)
        self.assertIn("AGENT_GOAL_ASSOCIATION_NUM_CTX=32768", rtx5090)
        self.assertIn("AGENT_TOOL_RESULT_INTERPRETER_NUM_CTX=32768", rtx5090)
        self.assertIn("AGENT_DEEP_PLANNER_NUM_PREDICT=4096", rtx5090)
        self.assertIn("AGENT_RESPONSE_COMPOSER_NUM_PREDICT=4096", rtx5090)
        self.assertIn("AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS=2048", rtx5090)

    def test_episode_recording_is_enabled_by_default(self) -> None:
        values = _common_env()
        self.assertEqual(values["ORCH_ENABLE_EPISODE_RECORDING"], "1")
        self.assertEqual(values["ORCH_EPISODE_LOG_PATH"], ".chromie/experience/episodes.jsonl")
        self.assertEqual(values["ORCH_EPISODE_MAX_TURNS"], "12")

    def test_orchestrator_warms_goal_interpreter_and_agent_models_when_interpreter_llm_enabled(self) -> None:
        source = (ROOT / "scripts" / "start_orchestrator.sh").read_text(
            encoding="utf-8"
        )
        values = _common_env()
        self.assertIn('mapfile -t WARM_MODELS < <(./scripts/list_runtime_ollama_models.sh)', source)
        self.assertIn('Active profile models: ${WARM_MODELS[*]}', source)
        self.assertIn('./scripts/warm_ollama.sh "${WARM_MODELS[@]}"', source)

    def test_warm_ollama_reports_pull_command_for_missing_model(self) -> None:
        source = (ROOT / "scripts" / "warm_ollama.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('docker exec chromie-llm ollama pull $model', source)
        self.assertIn("Ollama model is not present locally", source)
        self.assertIn("OLLAMA_AUTO_RESTART_ON_CRASH", source)
        self.assertIn('docker compose restart "$OLLAMA_SERVICE_NAME"', source)
        self.assertIn("Ollama native runner crashed", source)

    def test_compose_wrapper_loads_generated_runtime_env(self) -> None:
        source = (ROOT / "scripts" / "compose.sh").read_text(encoding="utf-8")
        self.assertIn("./scripts/build_runtime_env.sh", source)
        self.assertIn("source .env.runtime", source)
        self.assertIn("COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)", source)
        self.assertIn('exec docker compose "${COMPOSE_ARGS[@]}" "$@"', source)

    def test_runtime_env_builder_delegates_to_automatic_generator(self) -> None:
        wrapper = (ROOT / "scripts" / "build_runtime_env.sh").read_text(encoding="utf-8")
        generator = (ROOT / "scripts" / "generate_runtime_env.py").read_text(encoding="utf-8")
        self.assertIn("generate_runtime_env.py", wrapper)
        self.assertIn("detect_profile", generator)
        self.assertIn("runtime_profile.json", generator)
        self.assertIn("atomic_write(compose_env_path, content)", generator)

    def test_start_services_points_logs_to_compose_wrapper(self) -> None:
        source = (ROOT / "scripts" / "start_services.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("./scripts/compose.sh logs -f chromie-llm", source)
        self.assertNotIn("docker compose --env-file .env.runtime logs -f chromie-llm", source)

    def test_start_services_recreates_owned_containers_after_build(self) -> None:
        source = (ROOT / "scripts" / "start_services.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('if [[ "${BUILD:-0}" == "1" ]]', source)
        self.assertIn("UP_ARGS+=(--force-recreate)", source)
        self.assertIn(
            'docker compose "${COMPOSE_ARGS[@]}" up "${UP_ARGS[@]}" "${SERVICES[@]}"',
            source,
        )

    def test_start_chromie_supports_service_only_attachment(self) -> None:
        source = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--no-orchestrator", source)
        self.assertIn('START_ORCHESTRATOR=0', source)
        self.assertIn('Skipping host Orchestrator (--no-orchestrator)', source)
        self.assertIn('ORCH_RUNTIME_OVERRIDE_FILE="$ORCH_OVERRIDE"', source)

    def test_start_chromie_refuses_to_mutate_services_under_active_orchestrator(self) -> None:
        launcher = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )
        guard = ROOT / "scripts" / "check_orchestrator_idle.sh"
        self.assertIn("./scripts/check_orchestrator_idle.sh", launcher)
        self.assertLess(
            launcher.index("\n./scripts/check_orchestrator_idle.sh\n"),
            launcher.index("\n./scripts/build_runtime_env.sh\n"),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "orchestrator.lock"
            with lock_path.open("w", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                blocked = subprocess.run(
                    [str(guard)],
                    cwd=ROOT,
                    env=dict(os.environ, ORCH_LOCK_FILE=str(lock_path)),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn("already running", blocked.stderr)
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

            idle = subprocess.run(
                [str(guard)],
                cwd=ROOT,
                env=dict(os.environ, ORCH_LOCK_FILE=str(lock_path)),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(idle.returncode, 0, idle.stderr)

    def test_start_chromie_uses_cosyvoice_by_default_with_explicit_fallbacks(self) -> None:
        launcher = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )
        services = (ROOT / "scripts" / "start_services.sh").read_text(
            encoding="utf-8"
        )
        orchestrator = (ROOT / "scripts" / "start_orchestrator.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--tts-backend NAME", launcher)
        self.assertIn('TTS_BACKEND="${CHROMIE_TTS_BACKEND:-cosyvoice3}"', launcher)
        self.assertIn("from scripts.tts_reference import validate_reference_dir", launcher)
        self.assertIn("TTS_URL=ws://127.0.0.1:5000", launcher)
        self.assertIn("TTS_SPEAKER_ID=default", launcher)
        self.assertIn("ORCH_FAST_FIRST_AUDIO_CACHE_REVISION=cosyvoice3-", launcher)
        self.assertIn("ORCH_FAST_FIRST_AUDIO_PRIME_ON_STARTUP=0", launcher)
        self.assertIn('echo "ORCH_TTS_CONCURRENCY=1"', launcher)
        self.assertIn("TTS_COSYVOICE_OLLAMA_MODEL:-qwen3:4b", launcher)
        self.assertIn("TTS_COSYVOICE_OLLAMA_NUM_CTX:-8192", launcher)
        self.assertIn("context=${COSYVOICE_BRAIN_NUM_CTX}", launcher)
        self.assertIn("TTS_COSYVOICE_OLLAMA_NUM_CTX:-8192", services)
        self.assertIn("context=$COSYVOICE_BRAIN_NUM_CTX", services)
        self.assertIn(
            'export AGENT_TOOL_RESULT_INTERPRETER_MODEL="$COSYVOICE_BRAIN_MODEL"',
            services,
        )
        self.assertIn("EFFECTIVE_OLLAMA_MAX_LOADED_MODELS=1", launcher)
        self.assertIn(
            'EFFECTIVE_TOOL_RESULT_INTERPRETER_MODEL="$COSYVOICE_BRAIN_MODEL"',
            launcher,
        )
        self.assertIn(
            'AGENT_TOOL_RESULT_INTERPRETER_MODEL=${EFFECTIVE_TOOL_RESULT_INTERPRETER_MODEL}',
            launcher,
        )
        verifier = (ROOT / "scripts" / "verify_runtime_profile.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("AGENT_TOOL_RESULT_INTERPRETER_MODEL", verifier)
        self.assertIn('voice_root = root / voice_root', launcher)
        self.assertIn('voice_root = root / voice_root', services)
        self.assertIn("CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE", launcher)
        self.assertIn("Chromie services are ready", launcher)
        self.assertNotIn("Chromie voice interaction is ready", launcher)
        self.assertIn("python_ws_health_check()", launcher)
        self.assertIn(
            'wait_for_ws_health 127.0.0.1 9001 asr 900 "ASR"',
            launcher,
        )
        self.assertIn(
            'wait_for_ws_health 127.0.0.1 "$TTS_READY_PORT" tts 1200 "$TTS_READY_LABEL"',
            launcher,
        )
        self.assertNotIn('wait_for_tcp 127.0.0.1 9001 900 "ASR"', launcher)
        self.assertIn("warm_tts_candidate", launcher)
        self.assertIn("reset_ollama_before_tts_warmup", launcher)

        self.assertIn(
            "Resetting Ollama runners before the shared-GPU TTS synthesis probe",
            launcher,
        )
        self.assertIn("show_shared_gpu_startup_diagnostics", launcher)
        self.assertLess(
            launcher.index('  reset_ollama_before_tts_warmup\nfi'),
            launcher.index('  COSYVOICE_WARMUP_TIMEOUT_SEC='),
        )
        self.assertIn("TTS_COSYVOICE_ZH_WARMUP_TEXT", launcher)
        self.assertIn("TTS_COSYVOICE_EN_WARMUP_TEXT", launcher)
        self.assertIn("TTS_COSYVOICE_MIXED_WARMUP_TEXT", launcher)
        self.assertIn('"$TTS_READY_LABEL" chromie_zh zh', launcher)
        self.assertIn('"$TTS_READY_LABEL" chromie_en en', launcher)
        self.assertIn('"$TTS_READY_LABEL" chromie_mixed mixed', launcher)
        self.assertIn('"speaker_id": speaker_id', launcher)
        self.assertIn('"language_hint": language_hint', launcher)
        self.assertIn("fun-cosyvoice3-0.5b", launcher)
        self.assertIn("TTS_SERVICE=chromie-tts", services)
        self.assertIn("TTS_SERVICE=chromie-tts-oute", services)
        self.assertIn("TTS_SERVICE=chromie-tts-qwen3", services)
        self.assertIn("--profile tts-evaluation", services)
        self.assertIn('TTS_URL="${TTS_URL:-ws://127.0.0.1:5000}"', orchestrator)
        self.assertEqual(_common_env()["TTS_COSYVOICE_OLLAMA_MODEL"], "qwen3:4b")
        self.assertEqual(_common_env()["TTS_COSYVOICE_WARMUP_TIMEOUT_SEC"], "300")
        candidate_server = (ROOT / "tts" / "candidate_server.py").read_text(encoding="utf-8")
        cosy_provider = (ROOT / "tts_candidates" / "cosyvoice" / "provider_impl.py").read_text(encoding="utf-8")
        self.assertIn('time.tzset()', candidate_server)
        self.assertIn('torch.OutOfMemoryError', cosy_provider)
        self.assertIn('os._exit(70)', cosy_provider)
        self.assertEqual(_common_env()["TTS_COSYVOICE_EN_WARMUP_TEXT"], "Hello.")
        self.assertEqual(_common_env()["ORCH_FAST_FIRST_AUDIO_GENERATION_ATTEMPTS"], "2")

        verifier = (ROOT / "scripts" / "verify_runtime_profile.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE", verifier)
        self.assertIn("AGENT_GOAL_INTERPRETER_MODEL", verifier)
        self.assertIn("AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL", verifier)
        self.assertIn("OLLAMA_CONTEXT_LENGTH", verifier)
        self.assertIn("AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS", verifier)
        self.assertIn("AGENT_DEEP_PLANNER_NUM_PREDICT", verifier)
        self.assertNotIn('check_value "$name"', verifier)

    def test_start_chromie_logs_effective_cognitive_model_roles(self) -> None:
        launcher = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("Effective cognitive model roles:", launcher)
        expected_roles = {
            "Cognitive Gateway attention": (
                "EFFECTIVE_COGNITIVE_GATEWAY_ATTENTION_MODEL"
            ),
            "Goal Interpretation": "EFFECTIVE_AGENT_GOAL_INTERPRETER_MODEL",
            "Goal Association": "EFFECTIVE_GOAL_ASSOCIATION_MODEL",
            "Fast Planner": "EFFECTIVE_FAST_PLANNER_MODEL",
            "Deep Planner": "EFFECTIVE_DEEP_PLANNER_MODEL",
            "Response Composer": "EFFECTIVE_RESPONSE_COMPOSER_MODEL",
            "Tool Result Interpreter": "EFFECTIVE_TOOL_RESULT_INTERPRETER_MODEL",
            "Social Attention": "EFFECTIVE_SOCIAL_ATTENTION_MODEL",
        }
        for role, variable in expected_roles.items():
            with self.subTest(role=role):
                self.assertRegex(
                    launcher,
                    rf"{re.escape(role)}\s+\| \$\{{{variable}\}}\s+\|",
                )
        self.assertIn(
            "Role                               | Model                            | Maintained runtime use",
            launcher,
        )
        self.assertIn("background social-decoration loop", launcher)
        self.assertNotIn("EFFECTIVE_RESPONSE_REVIEW_MODEL", launcher)
        self.assertNotIn("Response Review                    |", launcher)
        self.assertIn("skipped by pure ready reads", launcher)
        summary_index = launcher.index("Effective cognitive model roles:")
        self.assertLess(summary_index, launcher.index('cat > "$SERVICE_OVERRIDE"'))


    def test_runtime_shell_entrypoints_parse_with_bash(self) -> None:
        for relative in (
            "scripts/start_chromie.sh",
            "scripts/start_services.sh",
            "scripts/start_orchestrator.sh",
            "scripts/verify_runtime_profile.sh",
        ):
            with self.subTest(script=relative):
                completed = subprocess.run(
                    ["bash", "-n", str(ROOT / relative)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=completed.stderr or completed.stdout,
                )

    def test_runtime_verifier_checks_timezone_environment_and_mount(self) -> None:
        verifier = (ROOT / "scripts" / "verify_runtime_profile.sh").read_text(
            encoding="utf-8"
        )
        orchestrator = (ROOT / "scripts" / "start_orchestrator.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('export TZ="${CHROMIE_HOST_TIMEZONE:-UTC}"', verifier)
        self.assertIn('check_value "$service" TZ', verifier)
        self.assertIn('eq .Destination "/etc/localtime"', verifier)
        self.assertIn("Runtime timezone:", verifier)
        self.assertIn('export TZ="${CHROMIE_HOST_TIMEZONE:-UTC}"', orchestrator)

    def test_start_chromie_waits_for_application_health(self) -> None:
        source = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("python_http_check()", source)
        self.assertIn(
            'wait_for_http 127.0.0.1 8092 /health 300 "Agent"', source
        )
        self.assertNotIn('wait_for_tcp 127.0.0.1 8092 300 "Agent"', source)

    def test_architecture_validation_preserves_social_attention(self) -> None:
        source = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )
        overlay = (ROOT / "env" / "validation" / "architecture.env").read_text(
            encoding="utf-8"
        )
        self.assertIn("--architecture-validation", source)
        self.assertIn("Social Attention remains active", source)
        self.assertIn(
            "${AGENT_SOCIAL_ATTENTION_MODE:-on}",
            source,
        )
        self.assertIn("AGENT_SOCIAL_ATTENTION_MODE=on", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_NUM_CTX=32768", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_NUM_PREDICT=4096", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_TIMEOUT_MS=120000", overlay)
        self.assertIn("OLLAMA_NUM_CTX=32768", overlay)
        self.assertIn("OLLAMA_NUM_PREDICT=4096", overlay)
        self.assertIn("OLLAMA_NUM_PARALLEL=2", overlay)


    def test_social_attention_defaults_are_profile_specific_and_nonblocking(self) -> None:
        common = (ROOT / ".env.common").read_text(encoding="utf-8")
        overlay = (ROOT / "env" / "validation" / "architecture.env").read_text(
            encoding="utf-8"
        )
        scenarios = (ROOT / "scripts" / "behavior_scenarios.py").read_text(
            encoding="utf-8"
        )
        agent_readme = (ROOT / "agent" / "README.md").read_text(encoding="utf-8")
        configuration = (ROOT / "docs" / "CONFIGURATION.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("AGENT_SOCIAL_ATTENTION_MODE=on", common)
        self.assertIn("AGENT_SOCIAL_ATTENTION_MODE=on", overlay)
        self.assertIn("there is no compatibility wait-after-response setting", agent_readme)
        self.assertNotIn("AGENT_SOCIAL_ATTENTION_WAIT_AFTER_RESPONSE_MS", configuration)
        self.assertNotIn("default `150`", configuration)

    def test_start_chromie_diagnoses_soridormi_probe_failures(self) -> None:
        source = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("check_soridormi_from_agent_container", source)
        self.assertIn("chromie-agent cannot reach Soridormi MCP", source)
        self.assertIn("Soridormi capability probe failed", source)
        self.assertIn("host.docker.internal", source)
        self.assertIn("Bind Soridormi MCP to 0.0.0.0", source)

    def test_voice_mujoco_text_case_allows_long_sim_skills(self) -> None:
        source = (ROOT / "scripts" / "run_voice_mujoco_text_case.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'SKILL_TIMEOUT_S="${CHROMIE_VOICE_MUJOCO_SKILL_TIMEOUT_S:-120}"',
            source,
        )
        self.assertIn("--capability-timeout-s SECONDS", source)
        self.assertIn('--capability-timeout-s "$SKILL_TIMEOUT_S"', source)
        self.assertNotIn("--capability-timeout-s 15", source)

    def test_deprecated_voice_launcher_is_not_advertised(self) -> None:
        self.assertFalse((ROOT / "scripts" / "start_chromie_voice.sh").exists())

    def test_removed_dead_controls_are_not_deployed(self) -> None:
        common = (ROOT / ".env.common").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for name in (
            "AGENT_ENABLE_HARDWARE_CLIENT",
            "HARDWARE_DAEMON_URL",
            "ORCH_TTS_DEDUPE_WINDOW_SEC",
        ):
            self.assertNotIn(name, common)
            self.assertNotIn(name, compose)

    def test_playback_chunk_is_initialized_before_output_diagnostics(self) -> None:
        source = (ROOT / "orchestrator" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        assignment = source.index(
            "self.playback_chunk_ms = playback_settings.playback_chunk_ms"
        )
        discard_diagnostic = source.index('"block_ms": self.playback_chunk_ms')
        self.assertLess(assignment, discard_diagnostic)
        self.assertNotIn('hasattr(self, "playback_chunk_ms")', source)

    def test_orchestrator_uses_configurable_asr_timeout(self) -> None:
        host_source = (ROOT / "orchestrator" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        input_source = (
            ROOT / "orchestrator" / "runtime" / "input_session_runtime.py"
        ).read_text(encoding="utf-8")
        settings = HostSettingsSnapshot.from_env(
            project_root=ROOT,
            environ={"ORCH_ASR_TIMEOUT_MS": "4321"},
        )
        self.assertEqual(settings.audio_input.asr_timeout_ms, 4321)
        self.assertIn(
            "self.asr_timeout_s = max(0.001, audio_settings.asr_timeout_ms / 1000.0)",
            host_source,
        )
        self.assertIn("timeout=host.asr_timeout_s", input_source)
        self.assertNotIn("timeout=15.0", input_source)

    def test_task_graph_diagnostics_fail_closed_without_token(self) -> None:
        with patch.object(agent_main.settings, "task_graph_diagnostics_token", ""):
            with self.assertRaises(HTTPException) as raised:
                agent_main.require_task_graph_diagnostics_auth(None)
        self.assertEqual(raised.exception.status_code, 503)

    def test_task_graph_diagnostics_require_matching_bearer(self) -> None:
        with patch.object(agent_main.settings, "task_graph_diagnostics_token", "secret"):
            with self.assertRaises(HTTPException) as raised:
                agent_main.require_task_graph_diagnostics_auth("Bearer wrong")
            self.assertEqual(raised.exception.status_code, 401)
            agent_main.require_task_graph_diagnostics_auth("Bearer secret")

    def test_blank_diagnostics_token_falls_back_to_execution_token(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN": "",
                "AGENT_TASK_GRAPH_EXECUTION_TOKEN": "execution-secret",
            },
            clear=False,
        ):
            settings = agent_main.Settings()
        self.assertEqual(
            settings.task_graph_diagnostics_token,
            "execution-secret",
        )


if __name__ == "__main__":
    unittest.main()
