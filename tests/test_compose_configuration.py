from __future__ import annotations

import unittest
from pathlib import Path

import yaml


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
        self.assertIn(
            "OLLAMA_FLASH_ATTENTION: ${OLLAMA_FLASH_ATTENTION:-0}", llm_block
        )
        self.assertIn(
            "OLLAMA_KV_CACHE_TYPE: ${OLLAMA_KV_CACHE_TYPE:-f16}", llm_block
        )

    def test_agent_embeds_fast_user_meaning_interpreter_by_default(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split("\nnetworks:", 1)[0]

        self.assertIn("AGENT_USER_MEANING_INTERPRETER_MODEL: ${AGENT_USER_MEANING_INTERPRETER_MODEL:-qwen3.5:4b}", agent_block)
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
        self.assertIn("AGENT_USER_MEANING_INTERPRETER_LLM_KEEP_ALIVE: ${AGENT_USER_MEANING_INTERPRETER_LLM_KEEP_ALIVE:-24h}", agent_block)
        self.assertIn("AGENT_USER_MEANING_INTERPRETER_WARM_LLM_ON_STARTUP: ${AGENT_USER_MEANING_INTERPRETER_WARM_LLM_ON_STARTUP:-1}", agent_block)
        self.assertIn("AGENT_USER_MEANING_INTERPRETER_WARM_LLM_TIMEOUT_MS: ${AGENT_USER_MEANING_INTERPRETER_WARM_LLM_TIMEOUT_MS:-60000}", agent_block)
        self.assertIn("AGENT_USER_MEANING_INTERPRETER_TIMEOUT_MS: ${AGENT_USER_MEANING_INTERPRETER_TIMEOUT_MS:-5400}", agent_block)
        self.assertIn("AGENT_USER_MEANING_INTERPRETER_LLM_NUM_CTX: ${AGENT_USER_MEANING_INTERPRETER_LLM_NUM_CTX:-16384}", agent_block)
        self.assertIn("AGENT_USER_MEANING_INTERPRETER_LLM_NUM_PREDICT: ${AGENT_USER_MEANING_INTERPRETER_LLM_NUM_PREDICT:-512}", agent_block)
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
            "AGENT_USER_MEANING_INTERPRETER_MODE",
            "AGENT_USER_MEANING_INTERPRETER_USE_LLM",
            "AGENT_USER_MEANING_INTERPRETER_REVIEW_TIMEOUT_MS",
            "AGENT_USER_MEANING_INTERPRETER_CONFIDENCE_THRESHOLD",
        ):
            self.assertNotIn(stale, environment_keys)
        self.assertFalse(
            any(
                name.startswith("AGENT_USER_MEANING_INTERPRETER_CAPABILITY_CATALOG_")
                for name in environment_keys
            )
        )
        self.assertNotIn("AGENT_USER_MEANING_INTERPRETER_REVIEW_MODEL", agent_block)
        self.assertNotIn("AGENT_USER_MEANING_INTERPRETER_POST_INTERRUPT_REVIEW_ENABLED", agent_block)

    def test_agent_is_the_only_cognitive_service_and_owns_user_meaning_interpretation(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertEqual(compose.count("\n  chromie-agent:\n"), 1)
        self.assertNotIn("chromie-router", compose)
        self.assertNotIn("8091", compose)
        agent_block = compose.split("  chromie-agent:", 1)[1].split("\nnetworks:", 1)[0]
        self.assertIn("      context: .", agent_block)
        self.assertIn("      dockerfile: agent/Dockerfile", agent_block)
        self.assertIn("AGENT_USER_MEANING_INTERPRETER_MODEL", agent_block)

    def test_agent_service_passes_planner_catalog_configuration(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent_block = compose.split("  chromie-agent:", 1)[1].split(
            "\nnetworks:",
            1,
        )[0]

        self.assertNotIn("AGENT_SOCIAL_ATTENTION_", agent_block)
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


    def test_tts_services_share_one_runtime_contract(self) -> None:
        services = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))[
            "services"
        ]
        providers = {
            "chromie-tts": "${TTS_PROVIDER:-fun-cosyvoice3-0.5b}",
            "chromie-tts-oute": "oute",
            "chromie-tts-qwen3": "qwen3-tts-0.6b-base",
        }
        for name, provider in providers.items():
            with self.subTest(service=name):
                service = services[name]
                environment = service["environment"]
                build_args = service["build"]["args"]
                self.assertEqual(environment["TTS_PROVIDER"], provider)
                # One startup budget and one allocator key for every TTS service.
                self.assertEqual(
                    environment["TTS_WORKER_STARTUP_TIMEOUT_SEC"],
                    "${TTS_WORKER_STARTUP_TIMEOUT_SEC:-1200}",
                )
                self.assertEqual(
                    environment["PYTORCH_ALLOC_CONF"],
                    "${TTS_PYTORCH_ALLOC_CONF:-expandable_segments:True}",
                )
                self.assertNotIn("PYTORCH_CUDA_ALLOC_CONF", environment)
                for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy"):
                    self.assertIn(key, build_args)
                    self.assertIn(key, environment)
                self.assertEqual(
                    service["deploy"]["resources"]["reservations"]["devices"][0]["capabilities"],
                    ["gpu"],
                )
                self.assertEqual(service["extra_hosts"], ["host.docker.internal:host-gateway"])
                # The health probe compares against the configured identity, not a literal.
                probe = service["healthcheck"]["test"][1]
                self.assertIn('os.environ["TTS_PROVIDER"]', probe)
                self.assertNotIn("fun-cosyvoice3-0.5b", probe)
        for name in ("chromie-tts", "chromie-tts-qwen3"):
            self.assertEqual(
                services[name]["build"]["args"]["CUDA_IMAGE"],
                "${TTS_CANDIDATE_CUDA_IMAGE:?TTS_CANDIDATE_CUDA_IMAGE is set in .env.common}",
            )

    def test_agent_container_paths_are_not_overridden_by_host_relative_values(self) -> None:
        values = {}
        for line in (ROOT / ".env.common").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        # Empty values select the Compose container defaults (${KEY:-/app/...}).
        self.assertEqual(values["AGENT_SKILL_ROOTS"], "")
        self.assertEqual(values["AGENT_CAPABILITY_PROMPT_TIER_PRESET"], "")


if __name__ == "__main__":
    unittest.main()
