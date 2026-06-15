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
            int(values["ROUTER_TIMEOUT_MS"]),
        )

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
