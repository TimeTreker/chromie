from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.capture_runtime_identity import (
    CaptureError,
    _validated_orchestrator_cognitive_budgets,
)
from scripts.generate_runtime_env import (
    COGNITIVE_BUDGET_KEYS,
    ConfigurationError,
    parse_env_file,
)
from scripts.sync_orchestrator_profile_env import sync_profile_budgets


class OrchestratorProfileEnvironmentTests(unittest.TestCase):
    @staticmethod
    def _budgets() -> dict[str, str]:
        return {
            key: str(1000 + index)
            for index, key in enumerate(COGNITIVE_BUDGET_KEYS)
        }

    @staticmethod
    def _write_env(path: Path, values: dict[str, str]) -> None:
        path.write_text(
            "".join(f"{key}={value}\n" for key, value in values.items()),
            encoding="utf-8",
        )

    def test_sync_copies_every_profile_owned_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / ".env.runtime"
            destination = root / "orchestrator.env"
            budgets = self._budgets()
            self._write_env(source, budgets)
            destination.write_text(
                "ORCH_COGNITIVE_RUNTIME_MODE=apply\n", encoding="utf-8"
            )

            sync_profile_budgets(source, destination)

            effective = parse_env_file(destination)
            self.assertEqual(effective["ORCH_COGNITIVE_RUNTIME_MODE"], "apply")
            self.assertEqual(
                {key: effective[key] for key in COGNITIVE_BUDGET_KEYS},
                budgets,
            )
            self.assertEqual(
                _validated_orchestrator_cognitive_budgets(
                    {"cognitive_budgets": budgets}, dict(effective)
                ),
                budgets,
            )

    def test_sync_rejects_conflicting_generated_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / ".env.runtime"
            destination = root / "orchestrator.env"
            budgets = self._budgets()
            self._write_env(source, budgets)
            destination.write_text(
                f"{COGNITIVE_BUDGET_KEYS[0]}=different\n",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                sync_profile_budgets(source, destination)

    def test_identity_rejects_missing_effective_budget(self) -> None:
        budgets = self._budgets()
        effective = dict(budgets)
        effective.pop(COGNITIVE_BUDGET_KEYS[-1])

        with self.assertRaises(CaptureError):
            _validated_orchestrator_cognitive_budgets(
                {"cognitive_budgets": budgets}, effective
            )


if __name__ == "__main__":
    unittest.main()
