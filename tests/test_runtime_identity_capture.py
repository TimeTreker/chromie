from __future__ import annotations

import contextlib
import io
import json
import posixpath
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.capture_runtime_identity import (
    AGENT_CONTAINER_SOURCE_TREES,
    AGENT_SOURCE_TREES,
    DEFAULT_SERVICES,
    ROOT,
    _deployment_identity,
    _git_source_tree_identity,
    build_parser,
    agent_runtime_source_identity,
    main,
)


def _agent_dockerfile_copy_layout() -> dict[str, str]:
    """Map repository source paths to their absolute image paths in agent/Dockerfile."""
    workdir = "/"
    layout: dict[str, str] = {}
    for line in (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8").splitlines():
        words = line.split()
        if not words or words[0].upper() not in {"WORKDIR", "COPY"}:
            continue
        instruction = words[0].upper()
        if instruction == "WORKDIR":
            workdir = posixpath.join(workdir, words[1])
        elif instruction == "COPY":
            sources = [word for word in words[1:] if not word.startswith("--")]
            destination = posixpath.normpath(posixpath.join(workdir, sources.pop()))
            for source in sources:
                layout[posixpath.normpath(source)] = destination
    return layout


def _container_tree_for(label: str) -> str:
    host = dict((value, key) for key, value in AGENT_SOURCE_TREES)[label]
    return _agent_dockerfile_copy_layout()[host.relative_to(ROOT).as_posix()]


class RuntimeIdentityCaptureTests(unittest.TestCase):
    def test_container_source_trees_match_agent_dockerfile_layout(self) -> None:
        labels = [label for _, label in AGENT_SOURCE_TREES]
        self.assertEqual(sorted(labels), sorted(label for _, label in AGENT_CONTAINER_SOURCE_TREES))
        for path, label in AGENT_CONTAINER_SOURCE_TREES:
            with self.subTest(label=label):
                self.assertEqual(path, _container_tree_for(label))

    def test_packaged_agent_identity_detects_source_contract_and_skill_drift(self) -> None:
        real_run = subprocess.run
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            container_root = root / "container"
            host_trees = []
            container_trees = {}
            for label in ("app", "agent-skills", "chromie_contracts", "chromie_runtime"):
                # The fake image is laid out from agent/Dockerfile, not from the
                # script's own paths, so a stale image path fails here.
                container_trees[label] = container_root / _container_tree_for(label).lstrip("/")
                for tree in (root / "host" / label, container_trees[label]):
                    tree.mkdir(parents=True)
                    (tree / "source.py").write_text("original\n")
                host_trees.append((root / "host" / label, label))

            def container_run(command, **kwargs):
                self.assertEqual(command[:3], ["docker", "exec", "selected-agent"])
                script = command[-1].replace("Path('/", f"Path('{container_root}/")
                return real_run([sys.executable, "-c", script], **kwargs)

            with patch("scripts.capture_runtime_identity.AGENT_SOURCE_TREES", host_trees), patch(
                "scripts.capture_runtime_identity.subprocess.run", side_effect=container_run
            ):
                self.assertTrue(agent_runtime_source_identity("selected-agent")["matches"])
                cache = container_trees["app"] / "__pycache__"
                cache.mkdir()
                (cache / "source.pyc").write_bytes(b"generated")
                self.assertTrue(agent_runtime_source_identity("selected-agent")["matches"])
                for label in ("app", "agent-skills", "chromie_contracts", "chromie_runtime"):
                    with self.subTest(stale_tree=label):
                        source = container_trees[label] / "source.py"
                        source.write_text("old deployed source\n")
                        self.assertFalse(agent_runtime_source_identity("selected-agent")["matches"])
                        source.write_text("original\n")
                extra = container_trees["app"] / "removed_endpoint.py"
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
