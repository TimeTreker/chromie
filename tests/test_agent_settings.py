from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.app.settings import UserMeaningInterpreterSettings, Settings
from shared.chromie_runtime.env_values import InvalidBooleanSetting, parse_bool

ROOT = Path(__file__).resolve().parents[1]


class AgentSettingsTests(unittest.TestCase):
    def test_activation_inherits_active_model_budget_unless_explicitly_overridden(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings().cognitive_activation_timeout_ms, 60000)
        with patch.dict(os.environ, {"AGENT_FAST_PLANNER_TIMEOUT_MS": "45000"}, clear=True):
            self.assertEqual(Settings().cognitive_activation_timeout_ms, 45000)
            os.environ["AGENT_COGNITIVE_ACTIVATION_TIMEOUT_MS"] = "18000"
            self.assertEqual(Settings().cognitive_activation_timeout_ms, 18000)

    def test_service_settings_capture_typed_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_PORT": "9012",
                "AGENT_WEATHER_TIMEOUT_S": "12.5",
                "AGENT_WEATHER_ENABLED": "0",
            },
        ):
            settings = Settings()
        self.assertEqual(settings.port, 9012)
        self.assertEqual(settings.weather_timeout_s, 12.5)
        self.assertFalse(hasattr(settings, "social_attention_model"))
        self.assertFalse(settings.weather_enabled)

    def test_boolean_flags_fail_closed_on_unrecognized_values(self) -> None:
        for name in (
            "AGENT_ENABLE_GUARDED_DAG_EXECUTION",
            "AGENT_ENABLE_PARALLEL_DAG_EXECUTION",
            "AGENT_ENABLE_PHYSICAL_DAG_EXECUTION",
            "AGENT_USE_LLM",
            "CHROMIE_AGENT_USER_MEANING_INTERPRETER_DEBUG_RAW",
        ):
            for value in ("disabled", "maybe", "2", "enable"):
                with self.subTest(name=name, value=value):
                    with patch.dict(os.environ, {name: value}, clear=True):
                        with self.assertRaisesRegex(InvalidBooleanSetting, name):
                            Settings()

    def test_boolean_flags_accept_strict_vocabulary_and_empty_means_default(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_ENABLE_GUARDED_DAG_EXECUTION": "",
                "AGENT_ENABLE_PARALLEL_DAG_EXECUTION": "  ",
                "AGENT_ENABLE_READ_ONLY_DAG_EXECUTION": "YES",
                "AGENT_WEATHER_ENABLED": "Off",
            },
            clear=True,
        ):
            settings = Settings()
        self.assertFalse(settings.enable_guarded_dag_execution)
        self.assertFalse(settings.enable_parallel_dag_execution)
        self.assertTrue(settings.enable_read_only_dag_execution)
        self.assertFalse(settings.weather_enabled)

    def test_shared_boolean_parser_vocabulary(self) -> None:
        for raw in ("1", "true", "TRUE", " yes ", "On"):
            self.assertTrue(parse_bool(raw, name="X", default=False))
        for raw in ("0", "false", "No", " OFF "):
            self.assertFalse(parse_bool(raw, name="X", default=True))
        self.assertTrue(parse_bool(None, name="X", default=True))
        self.assertFalse(parse_bool("", name="X", default=False))
        with self.assertRaisesRegex(InvalidBooleanSetting, "X must be a boolean"):
            parse_bool("disabled", name="X", default=False)

    def test_fast_planner_stream_has_one_model_and_timeout_authority(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_FAST_PLANNER_MODEL": "streaming-planner",
                "AGENT_FAST_PLANNER_TIMEOUT_MS": "8000",
                "AGENT_FAST_FIRST_RESPONSE_MODEL": "obsolete-model",
                "AGENT_FAST_FIRST_RESPONSE_TIMEOUT_MS": "2500",
            },
            clear=False,
        ):
            settings = Settings()
        self.assertEqual(settings.fast_planner_model, "streaming-planner")
        self.assertEqual(settings.fast_planner_timeout_ms, 8000)
        self.assertFalse(hasattr(settings, "fast_first_response_model"))
        self.assertFalse(hasattr(settings, "fast_first_response_timeout_ms"))

    def test_user_meaning_interpreter_deep_pass_retains_its_own_model_authority(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENT_USER_MEANING_INTERPRETER_TIMEOUT_MS": "7777",
                "AGENT_USER_MEANING_INTERPRETER_MODEL": "fast-umi",
                "AGENT_DELIBERATIVE_MODEL": "deep-cognition",
            },
            clear=False,
        ):
            settings = UserMeaningInterpreterSettings()
        self.assertEqual(settings.timeout_ms, 7777)
        self.assertEqual(settings.model, "fast-umi")
        self.assertEqual(settings.deep_model, "fast-umi")
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
