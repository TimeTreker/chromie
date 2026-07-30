from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from pydantic import ValidationError

from agent.app.agent_skills import (
    AgentSkillLoadError,
    compute_agent_skill_content_digest,
    load_agent_skill_registry,
    parse_agent_skill_roots,
)
from agent.app.capabilities.local import build_chromie_registry
from shared.chromie_contracts import AgentSkillMetadata


class AgentSkillLoaderTests(unittest.TestCase):
    def _write_package(
        self,
        root: Path,
        name: str,
        *,
        agent_skill_id: str | None = None,
        owner_approved: bool = True,
        extends: list[str] | None = None,
        metadata_updates: dict[str, object] | None = None,
    ) -> Path:
        package = root / name
        (package / "projections").mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"# {name}\n\nReusable method content.\n",
            encoding="utf-8",
        )
        (package / "projections" / "fast_planner.md").write_text(
            "Use exact bindings and trusted evidence.\n",
            encoding="utf-8",
        )
        digest = compute_agent_skill_content_digest(package)
        metadata: dict[str, object] = {
            "schema_version": "1.0",
            "agent_skill_id": agent_skill_id or f"chromie.{name}",
            "version": "1.0.0",
            "title": name.replace("-", " ").title(),
            "description": "A bounded passive method package.",
            "authority": "agent_method_only",
            "execution_authority": "none",
            "owner_approved": owner_approved,
            "content_digest": digest,
            "extends": extends or [],
            "required_capabilities": ["chromie.weather.lookup"],
            "optional_capabilities": [
                "chromie.memory.retrieve_verified_tool_result"
            ],
            "projections": {
                "fast_planner": "projections/fast_planner.md",
            },
        }
        metadata.update(metadata_updates or {})
        (package / "skill.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        return package

    def test_metadata_rejects_execution_authority_and_executable_fields(self) -> None:
        valid = {
            "schema_version": "1.0",
            "agent_skill_id": "chromie.weather-information",
            "version": "1.0.0",
            "title": "Weather Information",
            "description": "Grounded weather methods.",
            "authority": "agent_method_only",
            "execution_authority": "none",
            "owner_approved": True,
            "content_digest": "sha256:" + "0" * 64,
            "projections": {"fast_planner": "projections/fast_planner.md"},
        }
        metadata = AgentSkillMetadata.model_validate(valid)
        self.assertEqual(metadata.execution_authority, "none")

        with self.assertRaises(ValidationError):
            AgentSkillMetadata.model_validate(
                {**valid, "execution_authority": "trusted_runtime"}
            )
        for required_field in ("authority", "execution_authority", "owner_approved"):
            with self.subTest(required_field=required_field):
                payload = dict(valid)
                payload.pop(required_field)
                with self.assertRaises(ValidationError):
                    AgentSkillMetadata.model_validate(payload)
        with self.assertRaises(ValidationError):
            AgentSkillMetadata.model_validate(
                {**valid, "scripts": ["run.py"]}
            )
        with self.assertRaises(ValidationError):
            AgentSkillMetadata.model_validate(
                {**valid, "providers": ["weather-provider"]}
            )

    def test_metadata_rejects_invalid_semver_identifier_and_paths(self) -> None:
        base = {
            "schema_version": "1.0",
            "agent_skill_id": "chromie.weather-information",
            "version": "1.0.0",
            "title": "Weather Information",
            "description": "Grounded weather methods.",
            "authority": "agent_method_only",
            "execution_authority": "none",
            "owner_approved": True,
            "content_digest": "sha256:" + "0" * 64,
            "projections": {"fast_planner": "projections/fast_planner.md"},
        }
        for field, value in (
            ("agent_skill_id", "Weather Information"),
            ("version", "v1"),
            ("content_digest", "abc"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    AgentSkillMetadata.model_validate({**base, field: value})
        with self.assertRaises(ValidationError):
            AgentSkillMetadata.model_validate(
                {**base, "projections": {"fast_planner": "../outside.md"}}
            )
        with self.assertRaises(ValidationError):
            AgentSkillMetadata.model_validate(
                {**base, "projections": {"planner": "projections/planner.md"}}
            )

    def test_parse_roots_is_explicit_and_bounded(self) -> None:
        self.assertEqual(parse_agent_skill_roots(None), [])
        self.assertEqual(
            parse_agent_skill_roots(" agent-skills , /opt/approved-skills "),
            ["agent-skills", "/opt/approved-skills"],
        )

    def test_valid_package_loads_summary_without_full_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root, "weather-information")

            configured = load_agent_skill_registry([root])
            summaries = configured.registry.list_summaries()

            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].agent_skill_id, "chromie.weather-information")
            self.assertEqual(summaries[0].execution_authority, "none")
            self.assertEqual(summaries[0].available_projections, ("fast_planner",))
            snapshot = configured.snapshot().model_dump(mode="json")
            self.assertNotIn("content", snapshot["summaries"][0])
            self.assertNotIn("source", snapshot["summaries"][0])
            self.assertEqual(configured.package_files, (str(package / "skill.yaml"),))

    def test_projection_and_document_load_lazily_with_digest_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            registry = load_agent_skill_registry([root]).registry

            projection = registry.load_projection(
                "chromie.weather-information",
                "fast_planner",
            )
            document = registry.load_document("chromie.weather-information")

            self.assertIn("trusted evidence", projection.content)
            self.assertTrue(projection.projection_digest.startswith("sha256:"))
            self.assertIn("Reusable method", document.content)
            self.assertEqual(projection.content_digest, document.content_digest)

    def test_content_change_after_load_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root, "weather-information")
            registry = load_agent_skill_registry([root]).registry
            (package / "projections" / "fast_planner.md").write_text(
                "Changed after approval.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                AgentSkillLoadError,
                "content_digest_mismatch",
            ):
                registry.load_projection(
                    "chromie.weather-information",
                    "fast_planner",
                )

    def test_digest_mismatch_and_missing_document_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(
                root,
                "weather-information",
                metadata_updates={"content_digest": "sha256:" + "f" * 64},
            )
            with self.assertRaisesRegex(
                AgentSkillLoadError,
                "content_digest_mismatch",
            ):
                load_agent_skill_registry([root])

            package.joinpath("skill.yaml").unlink()
            package.joinpath("SKILL.md").unlink()
            self._write_package(root, "other-information")
            other = root / "other-information"
            other.joinpath("SKILL.md").unlink()
            with self.assertRaisesRegex(AgentSkillLoadError, "content_missing"):
                load_agent_skill_registry([root])

    def test_unapproved_and_duplicate_ids_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(
                root,
                "unapproved",
                owner_approved=False,
            )
            with self.assertRaisesRegex(
                AgentSkillLoadError,
                "owner_approval_required",
            ):
                load_agent_skill_registry([root])

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(
                root,
                "one",
                agent_skill_id="chromie.duplicate-skill",
            )
            self._write_package(
                root,
                "two",
                agent_skill_id="chromie.duplicate-skill",
            )
            with self.assertRaisesRegex(
                AgentSkillLoadError,
                "duplicate_agent_skill_id",
            ):
                load_agent_skill_registry([root])

    def test_unknown_parent_and_inheritance_cycles_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(
                root,
                "child",
                extends=["chromie.missing-parent"],
            )
            with self.assertRaisesRegex(AgentSkillLoadError, "unknown_parent_skill"):
                load_agent_skill_registry([root])

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(
                root,
                "one",
                agent_skill_id="chromie.skill-one",
                extends=["chromie.skill-two"],
            )
            self._write_package(
                root,
                "two",
                agent_skill_id="chromie.skill-two",
                extends=["chromie.skill-one"],
            )
            with self.assertRaisesRegex(AgentSkillLoadError, "inheritance_cycle"):
                load_agent_skill_registry([root])

    def test_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "skills"
            root.mkdir()
            outside = Path(temp_dir) / "outside"
            outside.mkdir()
            package = self._write_package(root, "weather-information")
            target = package / "projections" / "fast_planner.md"
            target.unlink()
            try:
                target.symlink_to(outside / "projection.md")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable on this platform")

            with self.assertRaisesRegex(AgentSkillLoadError, "unsafe_path"):
                load_agent_skill_registry([root])

    def test_package_python_is_inert_and_cannot_register_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root, "weather-information")
            marker = Path(temp_dir) / "executed.txt"
            (package / "evil.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
                encoding="utf-8",
            )
            metadata_path = package / "skill.yaml"
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
            metadata["content_digest"] = compute_agent_skill_content_digest(package)
            metadata_path.write_text(
                yaml.safe_dump(metadata, sort_keys=False),
                encoding="utf-8",
            )

            capability_registry = build_chromie_registry([])
            capability_ids_before = [tool.name for tool in capability_registry.list_tools()]
            skill_registry = load_agent_skill_registry([root]).registry
            capability_ids_after = [tool.name for tool in capability_registry.list_tools()]

            self.assertFalse(marker.exists())
            self.assertEqual(capability_ids_before, capability_ids_after)
            self.assertFalse(hasattr(skill_registry, "register"))
            self.assertFalse(hasattr(skill_registry, "execute"))

    def test_safe_yaml_loader_rejects_python_object_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "unsafe"
            package.mkdir()
            (package / "skill.yaml").write_text(
                "!!python/object/apply:os.system ['touch should-not-run']\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AgentSkillLoadError, "metadata_invalid"):
                load_agent_skill_registry([root])
            self.assertFalse((Path.cwd() / "should-not-run").exists())

    def test_registry_and_contract_models_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            registry = load_agent_skill_registry([root]).registry
            metadata = registry.get_metadata("chromie.weather-information")

            with self.assertRaises(ValidationError):
                metadata.title = "mutated"  # type: ignore[misc]
            self.assertIsInstance(registry.list_summaries(), tuple)


if __name__ == "__main__":
    unittest.main()
