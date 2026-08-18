from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.app.settings import GoalInterpreterSettings, Settings

ROOT = Path(__file__).resolve().parents[1]


class AgentSettingsTests(unittest.TestCase):
    def test_service_settings_capture_typed_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_PORT": "9012",
                "AGENT_SOCIAL_ATTENTION_NUM_CTX": "4096",
                "AGENT_WEATHER_TIMEOUT_S": "12.5",
                "AGENT_WEATHER_ENABLED": "0",
            },
        ):
            settings = Settings()
        self.assertEqual(settings.port, 9012)
        self.assertEqual(settings.social_attention_num_ctx, 4096)
        self.assertEqual(settings.weather_timeout_s, 12.5)
        self.assertFalse(settings.weather_enabled)

    def test_goal_interpreter_settings_reuse_existing_deep_cognition_model(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_GOAL_INTERPRETER_TIMEOUT_MS": "7777",
                "AGENT_GOAL_INTERPRETER_MODEL": "fast-gi",
                "AGENT_DEEP_PLANNER_MODEL": "deep-cognition",
            },
            clear=False,
        ):
            settings = GoalInterpreterSettings()
        self.assertEqual(settings.timeout_ms, 7777)
        self.assertEqual(settings.model, "fast-gi")
        self.assertEqual(settings.deep_model, "deep-cognition")
        self.assertFalse(hasattr(settings, "mode"))
        self.assertFalse(hasattr(settings, "capability_catalog_url"))
        self.assertFalse(hasattr(settings, "review_timeout_ms"))

    def test_agent_runtime_environment_reads_are_owned_by_settings(self) -> None:
        owner = ROOT / "agent" / "app" / "settings.py"
        for path in (ROOT / "agent" / "app").rglob("*.py"):
            if path == owner or "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                is_getenv = (
                    node.func.attr == "getenv"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                )
                is_environ_read = (
                    node.func.attr in {"get", "__getitem__"}
                    and isinstance(node.func.value, ast.Attribute)
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "os"
                    and node.func.value.attr == "environ"
                )
                self.assertFalse(is_getenv or is_environ_read, f"{path}:{node.lineno}")


if __name__ == "__main__":
    unittest.main()
