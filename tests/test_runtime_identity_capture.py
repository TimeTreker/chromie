from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.capture_runtime_identity import (
    DEFAULT_SERVICES,
    _deployment_identity,
    build_parser,
)


class RuntimeIdentityCaptureTests(unittest.TestCase):
    def test_parser_uses_canonical_defaults_without_append_duplicates(self) -> None:
        args = build_parser().parse_args([])
        self.assertIsNone(args.service)
        self.assertIsNone(args.capability_manifest)
        self.assertEqual(
            build_parser().parse_args(["--service", "chromie-agent"]).service,
            ["chromie-agent"],
        )

    def test_deployment_identity_retains_image_runtime_and_model_identity(self) -> None:
        def run(command, *, cwd=Path(".")):
            if "ps" in command:
                return "container-agent"
            if "{{.Image}}" in command:
                return "sha256:agent-image"
            if "{{.Config.Image}}" in command:
                return "chromie-agent:development"
            raise AssertionError(command)

        with patch("scripts.capture_runtime_identity._run", side_effect=run), patch(
            "scripts.capture_runtime_identity._container_environment",
            return_value={
                "CHROMIE_RUNTIME_ENV_FINGERPRINT": "fingerprint",
                "CHROMIE_ACTIVE_PROFILE": "rtx5090",
                "AGENT_GOAL_INTERPRETER_MODEL": "qwen3:4b",
            },
        ):
            identity = _deployment_identity(
                root=Path("/tmp/chromie"),
                services=["chromie-agent"],
                overrides=[],
                allow_missing_images=False,
            )

        agent = identity["service_images"]["chromie-agent"]
        self.assertEqual(agent["image_id"], "sha256:agent-image")
        self.assertEqual(
            agent["effective_runtime"]["CHROMIE_RUNTIME_ENV_FINGERPRINT"],
            "fingerprint",
        )
        self.assertEqual(
            agent["effective_models"]["AGENT_GOAL_INTERPRETER_MODEL"],
            "qwen3:4b",
        )
        self.assertEqual(DEFAULT_SERVICES[0], "chromie-agent")


if __name__ == "__main__":
    unittest.main()
