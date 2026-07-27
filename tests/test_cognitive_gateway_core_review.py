from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.create_cognitive_gateway_core_review import create


class CognitiveGatewayCoreReviewTests(unittest.TestCase):
    def test_review_template_is_pending_and_fingerprint_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = root / "identity.json"
            identity.write_text(
                json.dumps({"identity_sha256": "a" * 64}),
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "qualification_id": "qualification-one",
                        "human_review_expectations": {
                            "required_checks": ["quality", "continuity"]
                        },
                    }
                ),
                encoding="utf-8",
            )
            live = root / "live.json"
            mujoco = root / "mujoco.json"
            cancellation = root / "cancellation.json"
            live.write_text('{"live":true}\n', encoding="utf-8")
            mujoco.write_text('{"sim":true}\n', encoding="utf-8")
            cancellation.write_text('{"cancel":true}\n', encoding="utf-8")
            output = root / "review.json"
            payload = create(
                argparse.Namespace(
                    manifest=manifest,
                    runtime_identity=identity,
                    live_summary=live,
                    mujoco_summary=mujoco,
                    cancellation_summary=cancellation,
                    reviewer="reviewer-one",
                    output=output,
                )
            )
            self.assertTrue(output.is_file())

        self.assertEqual(payload["decision"], "pending")
        self.assertEqual(
            payload["checks"],
            {"quality": "pending", "continuity": "pending"},
        )
        self.assertEqual(
            payload["artifact_sha256"]["live_summary"],
            hashlib.sha256(b'{"live":true}\n').hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
