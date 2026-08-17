from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ComposeConfigurationTests(unittest.TestCase):
    def test_asr_service_passes_sensevoice_configuration(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        asr_block = compose.split("  chromie-asr:", 1)[1].split(
            "  chromie-tts:",
            1,
        )[0]

        self.assertNotIn("ASR_BACKEND:", asr_block)
        self.assertIn("ASR_MODE: ${ASR_MODE:-final}", asr_block)
        self.assertIn("SHERPA_ONNX_MODEL_TYPE: ${SHERPA_ONNX_MODEL_TYPE:-sense_voice}", asr_block)
        self.assertIn("SHERPA_ONNX_PROVIDER: ${SHERPA_ONNX_PROVIDER:-cuda}", asr_block)
        self.assertIn("SHERPA_ONNX_DEBUG: ${SHERPA_ONNX_DEBUG:-false}", asr_block)
        self.assertIn("ASR_STARTUP_WARMUP_ENABLED: ${ASR_STARTUP_WARMUP_ENABLED:-true}", asr_block)
        self.assertIn("ASR_STARTUP_WARMUP_AUDIO_SECONDS: ${ASR_STARTUP_WARMUP_AUDIO_SECONDS:-1.0}", asr_block)
        self.assertIn("start_period: 120s", asr_block)

    def test_ollama_healthcheck_uses_loopback_client_address(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        llm_block = compose.split("  chromie-llm:", 1)[1].split(
            "  chromie-agent:",
            1,
        )[0]

        self.assertIn(
            "OLLAMA_HOST=http://127.0.0.1:11434 ollama list >/dev/null",
            llm_block,
        )

    def test_ollama_cache_mount_is_configurable(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        llm_block = compose.split("  chromie-llm:", 1)[1].split(
            "  chromie-agent:",
            1,
        )[0]

        self.assertIn("${OLLAMA_DATA_DIR:-./ollama_data}:/root/.ollama", llm_block)

    def test_ollama_service_allows_two_loaded_models_without_extra_parallelism(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        llm_block = compose.split("  chromie-llm:", 1)[1].split(
            "  chromie-agent:",
            1,
        )[0]

        self.assertIn(
            "OLLAMA_MAX_LOADED_MODELS: ${OLLAMA_MAX_LOADED_MODELS:-2}",
            llm_block,
        )
        self.assertIn("OLLAMA_NUM_PARALLEL: ${OLLAMA_NUM_PARALLEL:-1}", llm_block)

    def test_agent_embeds_fast_goal_interpreter_by_default(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split("\nnetworks:", 1)[0]

        self.assertIn("AGENT_GOAL_INTERPRETER_MODEL: ${AGENT_GOAL_INTERPRETER_MODEL:-qwen3:4b}", agent_block)
        self.assertIn(
            "AGENT_COGNITIVE_GATEWAY_ATTENTION_ENABLED: "
            "${AGENT_COGNITIVE_GATEWAY_ATTENTION_ENABLED:-1}",
            agent_block,
        )
        self.assertIn(
            "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL: "
            "${AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL:-qwen3:4b}",
            agent_block,
        )
        self.assertIn("AGENT_GOAL_INTERPRETER_LLM_KEEP_ALIVE: ${AGENT_GOAL_INTERPRETER_LLM_KEEP_ALIVE:-24h}", agent_block)
        self.assertIn("AGENT_GOAL_INTERPRETER_WARM_LLM_ON_STARTUP: ${AGENT_GOAL_INTERPRETER_WARM_LLM_ON_STARTUP:-1}", agent_block)
        self.assertIn("AGENT_GOAL_INTERPRETER_WARM_LLM_TIMEOUT_MS: ${AGENT_GOAL_INTERPRETER_WARM_LLM_TIMEOUT_MS:-60000}", agent_block)
        self.assertIn("AGENT_GOAL_INTERPRETER_TIMEOUT_MS: ${AGENT_GOAL_INTERPRETER_TIMEOUT_MS:-5400}", agent_block)
        self.assertIn("AGENT_GOAL_INTERPRETER_LLM_NUM_CTX: ${AGENT_GOAL_INTERPRETER_LLM_NUM_CTX:-4096}", agent_block)
        self.assertIn("AGENT_GOAL_INTERPRETER_LLM_NUM_PREDICT: ${AGENT_GOAL_INTERPRETER_LLM_NUM_PREDICT:-512}", agent_block)
        self.assertIn("OLLAMA_CONTEXT_LENGTH: ${OLLAMA_CONTEXT_LENGTH:-2048}", agent_block)
        self.assertIn("OLLAMA_NUM_CTX: ${OLLAMA_NUM_CTX:-2048}", agent_block)
        self.assertIn("OLLAMA_NUM_PREDICT: ${OLLAMA_NUM_PREDICT:-64}", agent_block)
        self.assertIn(
            "AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE: ${AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE:-2.0}",
            agent_block,
        )
        self.assertIn(
            "AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS: ${AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS:-512}",
            agent_block,
        )
        environment_keys = {
            line.strip().split(":", 1)[0]
            for line in agent_block.splitlines()
            if line.startswith("      AGENT_") or line.startswith("      CHROMIE_AGENT_")
        }
        for stale in (
            "AGENT_GOAL_INTERPRETER_MODE",
            "AGENT_GOAL_INTERPRETER_USE_LLM",
            "AGENT_GOAL_INTERPRETER_REVIEW_TIMEOUT_MS",
            "AGENT_GOAL_INTERPRETER_CONFIDENCE_THRESHOLD",
        ):
            self.assertNotIn(stale, environment_keys)
        self.assertFalse(
            any(
                name.startswith("AGENT_GOAL_INTERPRETER_CAPABILITY_CATALOG_")
                for name in environment_keys
            )
        )
        self.assertNotIn("AGENT_GOAL_INTERPRETER_REVIEW_MODEL", agent_block)
        self.assertNotIn("AGENT_GOAL_INTERPRETER_POST_INTERRUPT_REVIEW_ENABLED", agent_block)

    def test_agent_is_the_only_cognitive_service_and_owns_goal_interpretation(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertEqual(compose.count("\n  chromie-agent:\n"), 1)
        self.assertNotIn("chromie-router", compose)
        self.assertNotIn("8091", compose)
        agent_block = compose.split("  chromie-agent:", 1)[1].split("\nnetworks:", 1)[0]
        self.assertIn("      context: .", agent_block)
        self.assertIn("      dockerfile: agent/Dockerfile", agent_block)
        self.assertIn("AGENT_GOAL_INTERPRETER_MODEL", agent_block)

    def test_agent_service_passes_capability_planner_budget(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertIn(
            "AGENT_SOCIAL_ATTENTION_MODE: ${AGENT_SOCIAL_ATTENTION_MODE:-on}",
            agent_block,
        )
        self.assertNotIn("AGENT_SOCIAL_ATTENTION_FALLBACK_", agent_block)
        self.assertIn("AGENT_CAPABILITY_NUM_CTX: ${AGENT_CAPABILITY_NUM_CTX:-24576}", agent_block)
        self.assertIn(
            "AGENT_CAPABILITY_NUM_PREDICT: ${AGENT_CAPABILITY_NUM_PREDICT:-512}",
            agent_block,
        )
        self.assertIn(
            "AGENT_CAPABILITY_REVIEW_NUM_PREDICT: ${AGENT_CAPABILITY_REVIEW_NUM_PREDICT:-160}",
            agent_block,
        )
        self.assertIn(
            "AGENT_CAPABILITY_MANIFESTS: ${AGENT_CAPABILITY_MANIFESTS:-/app/capabilities/soridormi.json}",
            agent_block,
        )
        self.assertIn(
            "AGENT_CAPABILITY_PROMPT_TIER_PRESET: ${AGENT_CAPABILITY_PROMPT_TIER_PRESET:-/app/capabilities/prompt_tiers.json}",
            agent_block,
        )
        self.assertIn(
            "AGENT_CAPABILITY_PROMPT_TIER_OVERRIDES: ${AGENT_CAPABILITY_PROMPT_TIER_OVERRIDES:-}",
            agent_block,
        )
        self.assertIn(
            "SORIDORMI_MCP_URL: ${SORIDORMI_MCP_URL:-http://host.docker.internal:8000/mcp}",
            agent_block,
        )

    def test_agent_service_passes_conversation_and_deepthinking_budgets(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertIn(
            "AGENT_CONVERSATION_NUM_CTX: ${AGENT_CONVERSATION_NUM_CTX:-2048}",
            agent_block,
        )
        self.assertIn(
            "AGENT_CONVERSATION_NUM_PREDICT: ${AGENT_CONVERSATION_NUM_PREDICT:-64}",
            agent_block,
        )
        self.assertIn(
            "AGENT_DEEPTHINKING_NUM_CTX: ${AGENT_DEEPTHINKING_NUM_CTX:-8192}",
            agent_block,
        )
        self.assertIn(
            "AGENT_DEEPTHINKING_NUM_PREDICT: ${AGENT_DEEPTHINKING_NUM_PREDICT:-384}",
            agent_block,
        )


if __name__ == "__main__":
    unittest.main()
