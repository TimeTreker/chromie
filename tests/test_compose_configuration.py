from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ComposeConfigurationTests(unittest.TestCase):
    def test_asr_service_passes_backend_and_mode(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        asr_block = compose.split("  chromie-asr:", 1)[1].split(
            "  chromie-tts:",
            1,
        )[0]

        self.assertIn("ASR_BACKEND: ${ASR_BACKEND:-faster_whisper}", asr_block)
        self.assertIn("ASR_MODE: ${ASR_MODE:-final}", asr_block)

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
            "  chromie-agent:",
            1,
        )[0]

        self.assertIn("ROUTER_USE_LLM: ${ROUTER_USE_LLM:-1}", router_block)
        self.assertIn("ROUTER_MODEL: ${ROUTER_MODEL:-qwen3:0.6b}", router_block)
        self.assertIn("ROUTER_REVIEW_MODEL: ${ROUTER_REVIEW_MODEL:-gemma4:e2b}", router_block)
        self.assertIn("ROUTER_LLM_TIMEOUT_MS: ${ROUTER_LLM_TIMEOUT_MS:-2000}", router_block)
        self.assertIn("ROUTER_REVIEW_TIMEOUT_MS: ${ROUTER_REVIEW_TIMEOUT_MS:-3000}", router_block)

    def test_agent_service_uses_main_model_for_response_review_by_default(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertIn("AGENT_RESPONSE_REVIEW_ENABLED: ${AGENT_RESPONSE_REVIEW_ENABLED:-1}", agent_block)
        self.assertIn("AGENT_RESPONSE_REVIEW_MODEL: ${AGENT_RESPONSE_REVIEW_MODEL:-gemma4:e2b}", agent_block)
        self.assertIn(
            "AGENT_RESPONSE_REVIEW_TIMEOUT_MS: ${AGENT_RESPONSE_REVIEW_TIMEOUT_MS:-4000}",
            agent_block,
        )

    def test_agent_service_passes_capability_planner_budget(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertIn("AGENT_CAPABILITY_NUM_CTX: ${AGENT_CAPABILITY_NUM_CTX:-4096}", agent_block)
        self.assertIn(
            "AGENT_CAPABILITY_NUM_PREDICT: ${AGENT_CAPABILITY_NUM_PREDICT:-512}",
            agent_block,
        )

    def test_agent_service_passes_conversation_and_deepthinking_budgets(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertIn(
            "AGENT_CONVERSATION_NUM_CTX: ${AGENT_CONVERSATION_NUM_CTX:-4096}",
            agent_block,
        )
        self.assertIn(
            "AGENT_CONVERSATION_NUM_PREDICT: ${AGENT_CONVERSATION_NUM_PREDICT:-128}",
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
