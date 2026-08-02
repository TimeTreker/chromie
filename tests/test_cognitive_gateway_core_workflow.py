from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.run_cognitive_gateway_core_qualification import (
    StageSpec,
    _collect_stages,
    _finalize_stage,
    _initial_state,
    _paths,
    _run_stage,
    _stage_is_resumable,
)


class CognitiveGatewayCoreWorkflowTests(unittest.TestCase):
    def _args(self, root: Path, manifest: Path) -> argparse.Namespace:
        return argparse.Namespace(
            python="python",
            manifest=manifest,
            evidence_root=root,
            reviewer="reviewer-one",
            soridormi_repo=root / "soridormi",
            compose_override=root / "compose.yaml",
            orchestrator_env=root / "orchestrator.env",
            runtime_profile=None,
            capability_manifest=root / "soridormi.json",
            agent_url="http://agent:8092",
            soridormi_mcp_url="http://soridormi:8000/mcp",
            preflight_timeout_s=4.0,
            timeout_s=123.0,
            interrupt_start_timeout_s=17.0,
            speaker=False,
        )

    def test_collect_plan_uses_manifest_owned_cancellation_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            manifest = {
                "qualification_id": "qualification-one",
                "simulator_expectations": {
                    "required_terminal_skills": ["soridormi.walk_velocity"]
                },
                "cancellation_expectations": {
                    "command_text": "Manifest-owned walking request.",
                    "interrupt_text": "Manifest-owned stop.",
                    "required_skill": "soridormi.walk_velocity",
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            paths = _paths(root / "evidence")
            stages = _collect_stages(self._args(root, manifest_path), paths, manifest)

        by_name = {stage.name: stage for stage in stages}
        cancellation = by_name["active-cancellation"].command
        self.assertIn("Manifest-owned walking request.", cancellation)
        self.assertIn("Manifest-owned stop.", cancellation)
        self.assertIn("soridormi.walk_velocity", cancellation)
        self.assertNotIn("approve", " ".join(by_name["human-review-template"].command))
        for name in (
            "preflight",
            "runtime-identity",
            "live-text",
            "mujoco",
            "active-cancellation",
        ):
            self.assertEqual(
                by_name[name].env_files,
                (root / "orchestrator.env",),
            )


    def test_collect_plan_runs_fail_fast_preflight_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            manifest = {
                "qualification_id": "qualification-one",
                "simulator_expectations": {"required_terminal_skills": []},
                "cancellation_expectations": {
                    "command_text": "Walk.",
                    "interrupt_text": "Stop.",
                    "required_skill": "soridormi.walk_velocity",
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            paths = _paths(root / "evidence")
            stages = _collect_stages(self._args(root, manifest_path), paths, manifest)

        self.assertEqual(stages[0].name, "preflight")
        command = list(stages[0].command)
        self.assertIn("scripts/preflight_cognitive_gateway_core_qualification.py", command)
        self.assertIn(str(paths.preflight), command)
        self.assertIn("http://agent:8092", command)
        self.assertIn("http://soridormi:8000/mcp", command)
        self.assertEqual(stages[0].env_files, (root / "orchestrator.env",))

    def test_resume_requires_matching_artifact_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.json"
            artifact.write_text('{"ok":true}\n', encoding="utf-8")
            stage = StageSpec("one", ("true",), (artifact,))
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            state = {
                "stages": {
                    "one": {
                        "status": "completed",
                        "artifacts": [
                            {
                                "path": str(artifact.resolve()),
                                "sha256": digest,
                                "size_bytes": artifact.stat().st_size,
                            }
                        ],
                        "environment_files": [],
                    }
                }
            }
            self.assertTrue(_stage_is_resumable(state, stage))
            artifact.write_text('{"ok":false}\n', encoding="utf-8")
            self.assertFalse(_stage_is_resumable(state, stage))

    def test_stage_loads_and_binds_generated_orchestrator_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root / "evidence")
            artifact = root / "effective.txt"
            env_file = root / "orchestrator.env"
            env_file.write_text(
                "BOUND_RUNTIME_VALUE=from-generated-env\n", encoding="utf-8"
            )
            stage = StageSpec(
                "bound-stage",
                (
                    sys.executable,
                    "-c",
                    (
                        "import os,pathlib,sys; "
                        "pathlib.Path(sys.argv[1]).write_text("
                        "os.environ['BOUND_RUNTIME_VALUE'], encoding='utf-8')"
                    ),
                    str(artifact),
                ),
                (artifact,),
                (env_file,),
            )
            state = _initial_state(paths, {"qualification_id": "qualification-one"})
            _run_stage(paths, state, stage, resume=False)

            self.assertEqual(artifact.read_text(encoding="utf-8"), "from-generated-env")
            self.assertTrue(_stage_is_resumable(state, stage))
            env_file.write_text("BOUND_RUNTIME_VALUE=changed\n", encoding="utf-8")
            self.assertFalse(_stage_is_resumable(state, stage))
            with self.assertRaisesRegex(RuntimeError, "start a new evidence root"):
                _run_stage(paths, state, stage, resume=False)

    def test_finalize_command_uses_all_bound_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp) / "evidence")
            args = argparse.Namespace(
                python="python",
                manifest=Path(tmp) / "manifest.json",
            )
            stage = _finalize_stage(args, paths)
        command = list(stage.command)
        for path in (
            paths.runtime_identity,
            paths.live_summary,
            paths.mujoco_summary,
            paths.cancellation_summary,
            paths.human_review,
            paths.qualification,
        ):
            self.assertIn(str(path), command)

    def test_initial_state_never_claims_release_or_issue_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp) / "evidence")
            state = _initial_state(paths, {"qualification_id": "qualification-one"})
        self.assertFalse(state["qualification"]["issue_closure_eligible"])
        self.assertFalse(state["qualification"]["release_qualified"])
        self.assertTrue(state["qualification"]["human_review_required"])


if __name__ == "__main__":
    unittest.main()
