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
        self.assertEqual(values["ROUTER_MODEL"], "qwen3:0.6b")
        self.assertEqual(values["ROUTER_REVIEW_MODEL"], "gemma4:e2b")
        self.assertEqual(values["ROUTER_LLM_TIMEOUT_MS"], "1500")
        self.assertEqual(values["ROUTER_REVIEW_TIMEOUT_MS"], "8000")

    def test_ollama_keeps_router_and_agent_models_loaded_without_extra_parallelism(self) -> None:
        values = _common_env()
        self.assertEqual(values["OLLAMA_MAX_LOADED_MODELS"], "2")
        self.assertEqual(values["OLLAMA_NUM_PARALLEL"], "1")
        self.assertEqual(values["OLLAMA_AUTO_RESTART_ON_CRASH"], "1")

    def test_capability_planner_has_json_output_budget(self) -> None:
        values = _common_env()
        self.assertEqual(values["AGENT_CAPABILITY_NUM_CTX"], "4096")
        self.assertEqual(values["AGENT_CAPABILITY_NUM_PREDICT"], "256")
        self.assertEqual(values["AGENT_CAPABILITY_REVIEW_NUM_PREDICT"], "160")
        self.assertEqual(values["AGENT_REQUIRE_CAPABILITY_PLAN_REVIEW"], "1")
        self.assertEqual(values["AGENT_EXPRESSIVE_BODY_CUES"], "off")

    def test_agent_conversation_and_deepthinking_have_context_budgets(self) -> None:
        values = _common_env()
        self.assertEqual(values["AGENT_CONVERSATION_NUM_CTX"], "4096")
        self.assertEqual(values["AGENT_CONVERSATION_NUM_PREDICT"], "128")
        self.assertEqual(values["AGENT_DEEPTHINKING_NUM_CTX"], "8192")
        self.assertEqual(values["AGENT_DEEPTHINKING_NUM_PREDICT"], "384")

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
        self.assertIn('WARM_MODELS=("${ROUTER_MODEL:-qwen3:0.6b}" "${WARM_MODELS[@]}")', source)
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
