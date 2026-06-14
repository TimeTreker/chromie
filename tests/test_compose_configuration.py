from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ComposeConfigurationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
