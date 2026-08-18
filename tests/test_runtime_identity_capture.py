from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.capture_runtime_identity import (
    DEFAULT_SERVICES,
    _deployment_identity,
    _git_source_tree_identity,
    build_parser,
)


class RuntimeIdentityCaptureTests(unittest.TestCase):
    def test_source_tree_digest_tracks_evaluated_nonignored_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                check=True,
            )
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            source = root / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            (root / "ignored").mkdir()
            ignored = root / "ignored" / "private.log"
            ignored.write_text("first\n", encoding="utf-8")

            first = _git_source_tree_identity(root)
            ignored.write_text("second\n", encoding="utf-8")
            ignored_change = _git_source_tree_identity(root)
            source.write_text("value = 2\n", encoding="utf-8")
            source_change = _git_source_tree_identity(root)

        self.assertEqual(
            first["source_tree_sha256"],
            ignored_change["source_tree_sha256"],
        )
        self.assertNotEqual(
            first["source_tree_sha256"],
            source_change["source_tree_sha256"],
        )
        self.assertEqual(
            first["source_tree_scope"],
            "git_tracked_and_nonignored_untracked_files",
        )

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
