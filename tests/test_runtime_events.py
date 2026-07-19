from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shared.chromie_runtime.runtime_events import persist_runtime_event


class RuntimeEventTests(unittest.TestCase):
    def test_persists_versioned_package_and_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = persist_runtime_event(
                event_type="chromie.test",
                event_subtype="example",
                severity="info",
                producer="chromie.tests",
                payloads={"sample.json": {"value": 1}},
                attributes={"category": "example"},
                correlations={"conversation_id": "conv-1"},
                derivation={"scenario_candidate_eligible": False},
                event_root=root / "events",
                trigger_root=root / "inbox",
            )

            self.assertEqual(result["capture_status"], "complete")
            self.assertEqual(result["trigger_status"], "accepted")
            ready = Path(result["payload_root"])
            manifest = json.loads((ready / "event.json").read_text())
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["event_type"], "chromie.test")
            self.assertEqual(manifest["correlations"]["conversation_id"], "conv-1")
            self.assertEqual(json.loads((ready / "sample.json").read_text())["value"], 1)
            trigger = json.loads(
                (root / "inbox" / f'{result["event_id"]}.json').read_text()
            )
            self.assertTrue(trigger["payload_complete"])
            self.assertEqual(trigger["manifest_path"], result["manifest_path"])

    def test_rejects_nested_payload_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = persist_runtime_event(
                event_type="chromie.test",
                event_subtype="bad_payload",
                severity="warning",
                producer="chromie.tests",
                payloads={"nested/value.json": {"value": 1}},
                event_root=Path(directory) / "events",
            )
            self.assertEqual(result["capture_status"], "failed")
            self.assertIn("payload name", result["error"])


if __name__ == "__main__":
    unittest.main()
