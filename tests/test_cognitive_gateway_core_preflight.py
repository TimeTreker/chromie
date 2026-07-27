from __future__ import annotations

import unittest

from scripts.preflight_cognitive_gateway_core_qualification import (
    _endpoint_source_revision,
    _evaluate_preflight,
)


class CognitiveGatewayCorePreflightTests(unittest.TestCase):
    @staticmethod
    def _valid_inputs() -> dict[str, object]:
        revision = "a" * 40
        return {
            "chromie": {"dirty": False, "revision": "b" * 40},
            "soridormi": {"dirty": False, "revision": revision},
            "manifest_revision": revision,
            "agent_health": {"ok": True, "capability_sources": ["soridormi"]},
            "provider_status": {
                "mode": "sim",
                "safe_idle": True,
                "active_task": None,
                "emergency_stop": False,
                "fallen": False,
                "source_revision": revision,
            },
        }

    def test_matching_clean_deployment_is_ready(self) -> None:
        checks, errors = _evaluate_preflight(**self._valid_inputs())
        self.assertEqual(errors, [])
        self.assertTrue(checks)
        self.assertTrue(all(item["passed"] for item in checks))

    def test_missing_endpoint_revision_fails_closed(self) -> None:
        values = self._valid_inputs()
        status = dict(values["provider_status"])
        status.pop("source_revision")
        values["provider_status"] = status
        _, errors = _evaluate_preflight(**values)
        self.assertTrue(any("must report source_revision" in item for item in errors))

    def test_endpoint_revision_must_match_checkout_and_manifest(self) -> None:
        values = self._valid_inputs()
        status = dict(values["provider_status"])
        status["provider_revision"] = "c" * 40
        status.pop("source_revision")
        values["provider_status"] = status
        _, errors = _evaluate_preflight(**values)
        self.assertTrue(any("paired checkout" in item for item in errors))
        self.assertTrue(any("capability manifest" in item for item in errors))

    def test_nested_revision_alias_is_supported(self) -> None:
        revision = "d" * 40
        self.assertEqual(
            _endpoint_source_revision({"provider": {"git_revision": revision}}),
            revision,
        )


if __name__ == "__main__":
    unittest.main()
