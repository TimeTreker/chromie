from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.capture_runtime_identity import (
    DEFAULT_SERVICES,
    _deployment_identity,
    _git_source_tree_identity,
    build_parser,
    agent_runtime_source_identity,
    main,
)


class RuntimeIdentityCaptureTests(unittest.TestCase):
    def test_packaged_agent_identity_detects_source_contract_and_skill_drift(self) -> None:
        real_run = subprocess.run
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host_trees = []
            for label in ("app", "agent-skills", "chromie_contracts", "chromie_runtime"):
                for side in ("host", "container"):
                    tree = root / side / label
                    tree.mkdir(parents=True)
                    (tree / "source.py").write_text("original\n")
                host_trees.append((root / "host" / label, label))

            def container_run(command, **kwargs):
                self.assertEqual(command[:3], ["docker", "exec", "selected-agent"])
                script = command[-1].replace("/app/", str(root / "container") + "/")
                return real_run([sys.executable, "-c", script], **kwargs)

            with patch("scripts.capture_runtime_identity.AGENT_SOURCE_TREES", host_trees), patch(
                "scripts.capture_runtime_identity.subprocess.run", side_effect=container_run
            ):
                self.assertTrue(agent_runtime_source_identity("selected-agent")["matches"])
                cache = root / "container" / "app" / "__pycache__"
                cache.mkdir()
                (cache / "source.pyc").write_bytes(b"generated")
                self.assertTrue(agent_runtime_source_identity("selected-agent")["matches"])
                for label in ("app", "agent-skills", "chromie_contracts", "chromie_runtime"):
                    with self.subTest(stale_tree=label):
                        source = root / "container" / label / "source.py"
                        source.write_text("old deployed source\n")
                        self.assertFalse(agent_runtime_source_identity("selected-agent")["matches"])
                        source.write_text("original\n")
                extra = root / "container" / "app" / "removed_endpoint.py"
                extra.write_text("retired\n")
                self.assertFalse(agent_runtime_source_identity("selected-agent")["matches"])

    def test_agent_verification_fails_closed_on_unavailable_or_malformed_probe(self) -> None:
        for outcome in (
            OSError("Docker unavailable"),
            subprocess.TimeoutExpired("docker", 120),
            subprocess.CompletedProcess([], 1, "", "container not running"),
            subprocess.CompletedProcess([], 0, "not JSON", ""),
            subprocess.CompletedProcess([], 0, json.dumps({}), ""),
        ):
            with self.subTest(outcome=outcome), patch(
                "scripts.capture_runtime_identity.subprocess.run"
            ) as run:
                if isinstance(outcome, Exception):
                    run.side_effect = outcome
                else:
                    run.return_value = outcome
                self.assertFalse(agent_runtime_source_identity()["matches"])

    def test_startup_verification_exit_status_blocks_mismatch(self) -> None:
        for container, matches in (("running-container", False), ("running-container", True), ("", False)):
            with self.subTest(container=container, matches=matches), patch(
                "scripts.capture_runtime_identity.agent_runtime_source_identity",
                return_value={"matches": matches},
            ) as probe, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
                code = main(["--verify-agent-source", container])
                probe.assert_called_once_with(container)
                self.assertEqual(code, 0 if matches else 1)
                if not matches:
                    self.assertIn("rebuild and recreate", error.getvalue())

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
                "AGENT_USER_MEANING_INTERPRETER_MODEL": "qwen3:4b",
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
            agent["effective_models"]["AGENT_USER_MEANING_INTERPRETER_MODEL"],
            "qwen3:4b",
        )
        self.assertEqual(DEFAULT_SERVICES[0], "chromie-agent")


if __name__ == "__main__":
    unittest.main()
