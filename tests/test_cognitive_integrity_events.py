from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from shared.chromie_runtime.cognitive_integrity_events import (
    capture_cognitive_integrity_event,
    cognitive_integrity_metadata,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer


class _Failure(RuntimeError):
    def metadata(self):
        return {
            "failure_class": "output_truncated",
            "failure_domain": "llm_budget",
            "model": "test-model",
            "done_reason": "length",
        }

    def incident_evidence(self):
        return {"request": {"prompt": "p"}, "response": {"response": "partial"}}


class CognitiveIntegrityEventTests(unittest.TestCase):
    def test_atomic_bundle_and_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = capture_cognitive_integrity_event(
                stage="fast_planner",
                failure=_Failure().metadata(),
                session_id="sid-1",
                user_text="walk forward",
                language="en",
                route_decision={"route": "robot_action"},
                runtime_context={"experience_context": {"conversation_id": "conv-1"}},
                model_exchange={},
                event_root=root / "events",
                trigger_root=root / "inbox",
            )
            self.assertEqual(result["capture_status"], "complete")
            self.assertEqual(result["trigger_status"], "accepted")
            manifest = json.loads(Path(result["manifest_path"]).read_text())
            self.assertEqual(manifest["attributes"]["stage"], "fast_planner")
            self.assertEqual(manifest["correlations"]["conversation_id"], "conv-1")
            self.assertTrue(manifest["derivation"]["scenario_candidate_eligible"])
            failure = json.loads(
                (Path(result["payload_root"]) / "failure.json").read_text()
            )
            self.assertFalse(failure["automatic_retry_allowed"])
            self.assertTrue((root / "inbox" / f'{result["event_id"]}.json').is_file())


    def test_active_runtime_trace_is_attached_to_incident_package(self) -> None:
        module = TraceModule(
            name="tests.cognitive_stage",
            component_type="test",
            implementation="CognitiveIntegrityEventTests",
        )
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            root = Path(directory)
            scope = runtime_tracer.start_trace(
                correlations={"session_id": "sid-trace"}
            )
            with scope:
                with runtime_tracer.span(module=module, operation="resolve"):
                    result = capture_cognitive_integrity_event(
                        stage="fast_planner",
                        failure=_Failure().metadata(),
                        session_id="sid-trace",
                        user_text="walk forward",
                        language="en",
                        route_decision={"route": "robot_action"},
                        runtime_context={},
                        model_exchange={},
                        event_root=root / "events",
                        trigger_root=root / "inbox",
                    )
            scope.finish()

            payload_root = Path(result["payload_root"])
            self.assertTrue((payload_root / "trace.json").is_file())
            self.assertTrue((payload_root / "trace-summary.json").is_file())
            manifest = json.loads((payload_root / "event.json").read_text())
            self.assertTrue(manifest["attributes"]["trace_attached"])
            self.assertTrue(manifest["correlations"]["trace_id"].startswith("trace_"))

    def test_common_metadata_for_any_cognitive_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = SimpleNamespace(
                sid="sid-2",
                text="hello",
                language="en",
                route_decision={},
                context={},
            )
            old = os.environ.get("CHROMIE_EVENT_ROOT")
            os.environ["CHROMIE_EVENT_ROOT"] = str(Path(directory) / "events")
            try:
                metadata = cognitive_integrity_metadata(
                    stage="goal_association",
                    exc=_Failure(),
                    request=request,
                )
            finally:
                if old is None:
                    os.environ.pop("CHROMIE_EVENT_ROOT", None)
                else:
                    os.environ["CHROMIE_EVENT_ROOT"] = old
            self.assertTrue(metadata["user_notification_required"])
            self.assertTrue(metadata["execution_prevented"])
            self.assertEqual(metadata["incident"]["capture_status"], "complete")


if __name__ == "__main__":
    unittest.main()
