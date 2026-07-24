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
            "  chromie-router:",
            1,
        )[0]

        self.assertIn(
            "OLLAMA_HOST=http://127.0.0.1:11434 ollama list >/dev/null",
            llm_block,
        )

    def test_ollama_cache_mount_is_configurable(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        llm_block = compose.split("  chromie-llm:", 1)[1].split(
            "  chromie-router:",
            1,
        )[0]

        self.assertIn("${OLLAMA_DATA_DIR:-./ollama_data}:/root/.ollama", llm_block)

    def test_ollama_service_allows_two_loaded_models_without_extra_parallelism(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        llm_block = compose.split("  chromie-llm:", 1)[1].split(
            "  chromie-router:",
            1,
        )[0]

        self.assertIn(
            "OLLAMA_MAX_LOADED_MODELS: ${OLLAMA_MAX_LOADED_MODELS:-2}",
            llm_block,
        )
        self.assertIn("OLLAMA_NUM_PARALLEL: ${OLLAMA_NUM_PARALLEL:-1}", llm_block)

    def test_router_service_uses_fast_llm_by_default(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        router_block = compose.split("  chromie-router:", 1)[1].split(
            "\n  chromie-agent:",
            1,
        )[0]

        self.assertIn("ROUTER_USE_LLM: ${ROUTER_USE_LLM:-1}", router_block)
        self.assertIn("ROUTER_MODEL: ${ROUTER_MODEL:-qwen3:4b}", router_block)
        self.assertIn("ROUTER_LLM_KEEP_ALIVE: ${ROUTER_LLM_KEEP_ALIVE:-24h}", router_block)
        self.assertIn("ROUTER_WARM_LLM_ON_STARTUP: ${ROUTER_WARM_LLM_ON_STARTUP:-1}", router_block)
        self.assertIn("ROUTER_WARM_LLM_TIMEOUT_MS: ${ROUTER_WARM_LLM_TIMEOUT_MS:-60000}", router_block)
        self.assertIn("ROUTER_REVIEW_MODEL: ${ROUTER_REVIEW_MODEL:-gemma4:e2b}", router_block)
        self.assertIn("ROUTER_TIMEOUT_MS: ${ROUTER_TIMEOUT_MS:-5400}", router_block)
        self.assertIn("ROUTER_LLM_TIMEOUT_MS: ${ROUTER_LLM_TIMEOUT_MS:-5400}", router_block)
        self.assertIn("ROUTER_LLM_NUM_CTX: ${ROUTER_LLM_NUM_CTX:-4096}", router_block)
        self.assertIn("ROUTER_LLM_NUM_PREDICT: ${ROUTER_LLM_NUM_PREDICT:-512}", router_block)
        self.assertIn("ROUTER_REVIEW_TIMEOUT_MS: ${ROUTER_REVIEW_TIMEOUT_MS:-2500}", router_block)
        self.assertIn(
            "ROUTER_CAPABILITY_CATALOG_CACHE_TTL_MS: ${ROUTER_CAPABILITY_CATALOG_CACHE_TTL_MS:-5000}",
            router_block,
        )
        self.assertIn(
            "ROUTER_POST_INTERRUPT_REVIEW_ENABLED: ${ROUTER_POST_INTERRUPT_REVIEW_ENABLED:-0}",
            router_block,
        )
        self.assertIn(
            "ROUTER_SLOW_REVIEW_RECOVERY_ENABLED: ${ROUTER_SLOW_REVIEW_RECOVERY_ENABLED:-1}",
            router_block,
        )
        self.assertIn(
            "ROUTER_GENERIC_CHAT_REVIEW_ENABLED: ${ROUTER_GENERIC_CHAT_REVIEW_ENABLED:-1}",
            router_block,
        )
        self.assertIn(
            "ROUTER_TOOL_FAST_SPEECH_REPAIR_ENABLED: ${ROUTER_TOOL_FAST_SPEECH_REPAIR_ENABLED:-0}",
            router_block,
        )

    def test_router_waits_for_agent_catalog_service_before_starting(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        router_block = compose.split("  chromie-router:", 1)[1].split(
            "\n  chromie-agent:",
            1,
        )[0]

        self.assertIn("chromie-agent:", router_block)
        self.assertIn("condition: service_healthy", router_block)

    def test_router_build_context_includes_shared_contracts(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        router_block = compose.split("  chromie-router:", 1)[1].split(
            "\n  chromie-agent:",
            1,
        )[0]

        self.assertIn("      context: .", router_block)
        self.assertIn("      dockerfile: router/Dockerfile", router_block)

    def test_agent_service_uses_main_model_for_response_review_by_default(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertIn("AGENT_RESPONSE_REVIEW_ENABLED: ${AGENT_RESPONSE_REVIEW_ENABLED:-0}", agent_block)
        self.assertIn("AGENT_RESPONSE_REVIEW_MODEL: ${AGENT_RESPONSE_REVIEW_MODEL:-gemma4:e2b}", agent_block)
        self.assertIn(
            "AGENT_RESPONSE_REVIEW_TIMEOUT_MS: ${AGENT_RESPONSE_REVIEW_TIMEOUT_MS:-4000}",
            agent_block,
        )
        self.assertIn("AGENT_RESPONSE_REVIEW_MODE: ${AGENT_RESPONSE_REVIEW_MODE:-auto}", agent_block)

    def test_agent_service_passes_capability_planner_budget(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertIn("AGENT_EXPRESSIVE_BODY_CUES: ${AGENT_EXPRESSIVE_BODY_CUES:-off}", agent_block)
        self.assertIn(
            "AGENT_SOCIAL_ATTENTION_MODE: ${AGENT_SOCIAL_ATTENTION_MODE:-on}",
            agent_block,
        )
        self.assertNotIn("AGENT_SOCIAL_ATTENTION_FALLBACK_", agent_block)
        self.assertIn(
            "AGENT_REQUIRE_CAPABILITY_PLAN_REVIEW: ${AGENT_REQUIRE_CAPABILITY_PLAN_REVIEW:-0}",
            agent_block,
        )
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
