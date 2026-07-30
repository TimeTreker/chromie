from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from agent.app.agent_skills import (
    AgentSkillLoadError,
    compute_agent_skill_content_digest,
    load_agent_skill_registry,
)
from agent.app.schema import HealthResponse


ROOT = Path(__file__).resolve().parents[1]


class AgentSkillRuntimeSurfaceTests(unittest.TestCase):
    def test_empty_repository_owned_root_is_valid_and_model_selection_is_off(self) -> None:
        configured = load_agent_skill_registry([ROOT / "agent-skills"])
        snapshot = configured.snapshot()
        health = HealthResponse(
            agent_skill_roots=list(configured.roots),
            agent_skill_package_files=list(configured.package_files),
            agent_skill_count=len(configured.registry),
            agent_skill_model_selection_enabled=False,
        )

        self.assertEqual(snapshot.summaries, ())
        self.assertEqual(health.agent_skill_count, 0)
        self.assertFalse(health.agent_skill_model_selection_enabled)

    def test_compose_mounts_agent_skill_root_read_only(self) -> None:
        compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        service = compose["services"]["chromie-agent"]

        self.assertEqual(
            service["environment"]["AGENT_SKILL_ROOTS"],
            "${AGENT_SKILL_ROOTS:-/app/agent-skills}",
        )
        self.assertIn("./agent-skills:/app/agent-skills:ro", service["volumes"])

    def test_agent_image_contains_repository_owned_empty_root(self) -> None:
        dockerfile = (ROOT / "agent" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY agent-skills ./agent-skills", dockerfile)

    def test_digest_cli_matches_loader_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = Path(temp_dir) / "sample"
            package.mkdir()
            (package / "SKILL.md").write_text("# Sample\n", encoding="utf-8")
            expected = compute_agent_skill_content_digest(package)

            completed = subprocess.run(
                [
                    "python",
                    str(ROOT / "scripts" / "agent_skill_digest.py"),
                    str(package),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.stdout.strip(), expected)

    def test_duplicate_yaml_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "duplicate-keys"
            package.mkdir()
            (package / "SKILL.md").write_text("# Duplicate keys\n", encoding="utf-8")
            digest = compute_agent_skill_content_digest(package)
            (package / "skill.yaml").write_text(
                "\n".join(
                    [
                        'schema_version: "1.0"',
                        "agent_skill_id: chromie.duplicate-keys",
                        "agent_skill_id: chromie.other-id",
                        "version: 1.0.0",
                        "title: Duplicate Keys",
                        "description: Must fail closed.",
                        "authority: agent_method_only",
                        "execution_authority: none",
                        "owner_approved: true",
                        f"content_digest: {digest}",
                        "projections:",
                        "  fast_planner: SKILL.md",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(AgentSkillLoadError, "metadata_invalid"):
                load_agent_skill_registry([root])


if __name__ == "__main__":
    unittest.main()
