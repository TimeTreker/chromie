from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from agent.app import main as agent_main


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
    def test_router_host_budget_exceeds_router_internal_budget(self) -> None:
        values = _common_env()
        self.assertGreater(
            int(values["ORCH_ROUTER_TIMEOUT_MS"]),
            int(values["ROUTER_LLM_TIMEOUT_MS"])
            + int(values["ROUTER_REVIEW_TIMEOUT_MS"])
            + int(values["ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS"]),
        )

    def test_router_uses_fast_llm_by_default(self) -> None:
        values = _common_env()
        self.assertEqual(values["ROUTER_USE_LLM"], "1")
        self.assertEqual(values["ROUTER_MODEL"], "qwen3:4b")
        self.assertEqual(values["ROUTER_LLM_KEEP_ALIVE"], "24h")
        self.assertEqual(values["ROUTER_WARM_LLM_ON_STARTUP"], "1")
        self.assertEqual(values["ROUTER_WARM_LLM_TIMEOUT_MS"], "60000")
        self.assertEqual(values["ROUTER_REVIEW_MODEL"], "gemma4:e2b")
        self.assertEqual(values["ROUTER_TIMEOUT_MS"], "5400")
        self.assertEqual(values["ROUTER_LLM_TIMEOUT_MS"], "5400")
        self.assertEqual(values["ROUTER_LLM_NUM_CTX"], "4096")
        self.assertEqual(values["ROUTER_LLM_NUM_PREDICT"], "96")
        self.assertEqual(values["ROUTER_REVIEW_TIMEOUT_MS"], "2500")
        self.assertEqual(values["ROUTER_CAPABILITY_CATALOG_CACHE_TTL_MS"], "5000")
        self.assertEqual(values["ROUTER_POST_INTERRUPT_REVIEW_ENABLED"], "0")
        self.assertEqual(values["ROUTER_SLOW_REVIEW_RECOVERY_ENABLED"], "1")
        self.assertEqual(values["ROUTER_GENERIC_CHAT_REVIEW_ENABLED"], "1")
        self.assertEqual(values["ROUTER_TOOL_FAST_SPEECH_REPAIR_ENABLED"], "0")

    def test_ollama_keeps_router_and_agent_models_loaded_without_extra_parallelism(self) -> None:
        values = _common_env()
        self.assertEqual(values["OLLAMA_MAX_LOADED_MODELS"], "2")
        self.assertEqual(values["OLLAMA_NUM_PARALLEL"], "1")
        self.assertEqual(values["OLLAMA_AUTO_RESTART_ON_CRASH"], "1")
        self.assertEqual(values["OLLAMA_WARM_NUM_PREDICT"], "1")

    def test_capability_planner_has_json_output_budget(self) -> None:
        values = _common_env()
        self.assertEqual(values["AGENT_RESPONSE_REVIEW_ENABLED"], "0")
        self.assertEqual(values["AGENT_CAPABILITY_NUM_CTX"], "24576")
        self.assertEqual(values["AGENT_CAPABILITY_NUM_PREDICT"], "512")
        self.assertEqual(values["AGENT_CAPABILITY_REVIEW_NUM_PREDICT"], "160")
        self.assertEqual(values["AGENT_REQUIRE_CAPABILITY_PLAN_REVIEW"], "0")
        self.assertEqual(values["AGENT_EXPRESSIVE_BODY_CUES"], "off")
        self.assertEqual(values["AGENT_CAPABILITY_MANIFESTS"], "")
        self.assertEqual(values["SORIDORMI_MCP_URL"], "")

    def test_agent_conversation_and_deepthinking_have_context_budgets(self) -> None:
        values = _common_env()
        self.assertEqual(values["AGENT_MAX_SPEAK_CHARS"], "140")
        self.assertEqual(values["AGENT_CONVERSATION_NUM_CTX"], "2048")
        self.assertEqual(values["AGENT_CONVERSATION_NUM_PREDICT"], "64")
        self.assertEqual(values["AGENT_DEEPTHINKING_NUM_CTX"], "8192")
        self.assertEqual(values["AGENT_DEEPTHINKING_NUM_PREDICT"], "384")

    def test_tool_fast_first_is_disabled_and_task_continuity_is_report_only_in_common_profile(self) -> None:
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
        self.assertEqual(values["ORCH_FAST_FIRST_TOOL_RESPONSE_ENABLED"], "0")
        self.assertEqual(values["ORCH_TASK_CONTINUITY_MODE"], "report_only")
        self.assertEqual(values["ORCH_TASK_CONTINUITY_TIMEOUT_MS"], "3500")
        self.assertEqual(values["AGENT_TASK_CONTINUITY_MODEL"], "qwen3:4b")
        self.assertEqual(values["AGENT_TASK_CONTINUITY_TIMEOUT_MS"], "3000")
        self.assertEqual(values["AGENT_TASK_CONTINUITY_NUM_CTX"], "4096")
        self.assertEqual(values["AGENT_TASK_CONTINUITY_NUM_PREDICT"], "256")

    def test_chinese_tts_uses_smaller_chunks_for_lower_first_audio_latency(self) -> None:
        values = _common_env()
        self.assertEqual(values["ORCH_TTS_CJK_CHUNK_CHARS"], "36")
        self.assertEqual(values["ORCH_TTS_CJK_MIN_CHUNK_CHARS"], "8")

    def test_tts_performance_diagnostics_and_cuda_graphs_are_enabled(self) -> None:
        values = _common_env()
        self.assertEqual(values["TTS_AUDIO_CODEC_DEVICE"], "auto")
        self.assertEqual(values["TTS_DETAILED_TIMING"], "1")
        self.assertEqual(values["TTS_METRICS_WINDOW"], "20")
        self.assertEqual(values["GGML_CUDA_DISABLE_GRAPHS"], "0")

        profile = (ROOT / "env" / "profiles" / "rtx4090_laptop.env").read_text(
            encoding="utf-8"
        )
        self.assertIn("TTS_CONTEXT_SIZE=4096", profile)
        self.assertIn("TTS_MAX_LENGTH=4096", profile)

    def test_episode_recording_is_enabled_by_default(self) -> None:
        values = _common_env()
        self.assertEqual(values["ORCH_ENABLE_EPISODE_RECORDING"], "1")
        self.assertEqual(values["ORCH_EPISODE_LOG_PATH"], ".chromie/experience/episodes.jsonl")
        self.assertEqual(values["ORCH_EPISODE_MAX_TURNS"], "12")

    def test_orchestrator_warms_router_and_agent_models_when_router_llm_enabled(self) -> None:
        source = (ROOT / "scripts" / "start_orchestrator.sh").read_text(
            encoding="utf-8"
        )
        values = _common_env()
        self.assertEqual(values["AGENT_RESPONSE_REVIEW_MODEL"], "gemma4:e2b")
        self.assertIn('[[ "${ROUTER_USE_LLM:-0}" =~ ^(1|true|yes|on)$ ]]', source)
        self.assertIn('WARM_MODELS=("${AGENT_MODEL:-gemma4:e2b}")', source)
        self.assertIn('AGENT_RESPONSE_REVIEW_MODEL:-gemma4:e2b', source)
        self.assertIn('WARM_MODELS=("${ROUTER_MODEL:-qwen3:4b}" "${WARM_MODELS[@]}")', source)
        self.assertIn('ROUTER_SLOW_REVIEW_RECOVERY_ENABLED:-1', source)
        self.assertIn('WARM_MODELS+=("${ROUTER_REVIEW_MODEL}")', source)
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
        self.assertIn("source .env.runtime", source)
        self.assertIn("COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)", source)
        self.assertIn('exec docker compose "${COMPOSE_ARGS[@]}" "$@"', source)

    def test_runtime_env_builder_writes_compose_compatibility_env(self) -> None:
        source = (ROOT / "scripts" / "build_runtime_env.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('COMPOSE_ENV=".env"', source)
        self.assertIn('cp "$RUNTIME_ENV" "$COMPOSE_ENV"', source)
        self.assertIn("Existing $COMPOSE_ENV is not generated by Chromie", source)

    def test_start_services_points_logs_to_compose_wrapper(self) -> None:
        source = (ROOT / "scripts" / "start_services.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("./scripts/compose.sh logs -f chromie-llm", source)
        self.assertNotIn("docker compose --env-file .env.runtime logs -f chromie-llm", source)

    def test_start_chromie_supports_service_only_attachment(self) -> None:
        source = (ROOT / "scripts" / "start_chromie.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--no-orchestrator", source)
        self.assertIn('START_ORCHESTRATOR=0', source)
        self.assertIn('Skipping host Orchestrator (--no-orchestrator)', source)
        self.assertIn('ORCH_RUNTIME_OVERRIDE_FILE="$ORCH_OVERRIDE"', source)

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
            "${CHROMIE_SOCIAL_ATTENTION_MODE:-${AGENT_SOCIAL_ATTENTION_MODE:-off}}",
            source,
        )
        self.assertIn("AGENT_SOCIAL_ATTENTION_MODE=sim_only", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_WAIT_AFTER_RESPONSE_MS=0", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_NUM_CTX=32768", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_NUM_PREDICT=4096", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_TIMEOUT_MS=120000", overlay)
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

        self.assertIn("AGENT_SOCIAL_ATTENTION_MODE=off", common)
        self.assertIn("AGENT_SOCIAL_ATTENTION_WAIT_AFTER_RESPONSE_MS=0", common)
        self.assertIn("AGENT_SOCIAL_ATTENTION_MODE=sim_only", overlay)
        self.assertIn("AGENT_SOCIAL_ATTENTION_WAIT_AFTER_RESPONSE_MS=0", overlay)
        self.assertIn('stub.get("social_attention_wait_after_response_ms", 0)', scenarios)
        self.assertNotIn('stub.get("social_attention_wait_after_response_ms", 150)', scenarios)
        self.assertIn("effective wait is always `0`", agent_readme)
        self.assertIn("runtime never awaits Social Attention", configuration)
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
        self.assertIn("--skill-timeout-s SECONDS", source)
        self.assertIn('--skill-timeout-s "$SKILL_TIMEOUT_S"', source)
        self.assertNotIn("--skill-timeout-s 15", source)

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
            'self.playback_chunk_ms = int(os.getenv("ORCH_PLAYBACK_CHUNK_MS", "80"))'
        )
        discard_diagnostic = source.index('"block_ms": self.playback_chunk_ms')
        self.assertLess(assignment, discard_diagnostic)
        self.assertNotIn('hasattr(self, "playback_chunk_ms")', source)

    def test_orchestrator_uses_configurable_asr_timeout(self) -> None:
        source = (ROOT / "orchestrator" / "orchestrator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('os.getenv("ORCH_ASR_TIMEOUT_MS", "30000")', source)
        self.assertIn("timeout=self.asr_timeout_s", source)
        self.assertNotIn("timeout=15.0", source)

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
