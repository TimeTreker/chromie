from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tts_provider_ab",
    ROOT / "scripts" / "tts_provider_ab.py",
)
assert SPEC is not None and SPEC.loader is not None
tts_provider_ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tts_provider_ab)


class TTSProviderABTests(unittest.TestCase):
    def test_committed_matrix_covers_every_required_kind(self) -> None:
        matrix = tts_provider_ab.load_matrix(
            ROOT / "scenarios" / "tts_provider_ab.json"
        )
        self.assertEqual(
            {case["kind"] for case in matrix["cases"]},
            tts_provider_ab.REQUIRED_KINDS,
        )

    def test_matrix_rejects_missing_or_shallow_required_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "matrix.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "cases": [
                            {"id": "zh", "kind": "chinese", "text": "你好"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing required kinds"):
                tts_provider_ab.load_matrix(path)

    def test_provider_specs_and_health_contract_fail_closed(self) -> None:
        self.assertEqual(
            tts_provider_ab.parse_provider_specs(
                ["oute=ws://127.0.0.1:5000", "qwen=ws://127.0.0.1:5001"]
            ),
            {
                "oute": "ws://127.0.0.1:5000",
                "qwen": "ws://127.0.0.1:5001",
            },
        )
        with self.assertRaisesRegex(ValueError, "NAME=ws"):
            tts_provider_ab.parse_provider_specs(["broken"])
        with self.assertRaisesRegex(RuntimeError, "contract version 1"):
            tts_provider_ab.validate_health("legacy", {"type": "pong"})
        valid_health = {
            "provider_contract_version": 1,
            "provider": {
                "provider_id": "fixture",
                "implementation": "fixture",
                "software_source": "https://example.invalid/fixture",
                "software_revision": "0123456789abcdef",
                "software_license_id": "Apache-2.0",
                "license_review_status": "declared_unreviewed",
                "model_artifacts": [
                    {
                        "kind": "weights",
                        "artifact_id": "fixture/model",
                        "revision": "0123456789abcdef",
                        "license_id": "Apache-2.0",
                    }
                ],
                "languages": ["zh", "en"],
                "sample_rates": [16000],
                "max_concurrency": 1,
                "native_text_streaming": False,
                "native_audio_streaming": True,
                "request_cancellation": True,
            },
        }
        self.assertEqual(
            tts_provider_ab.validate_health("fixture", valid_health)["provider_id"],
            "fixture",
        )
        valid_health["provider"]["software_revision"] = "main"
        with self.assertRaisesRegex(RuntimeError, "software revision is mutable"):
            tts_provider_ab.validate_health("fixture", valid_health)
        valid_health["provider"]["software_revision"] = "0.4.4"
        valid_health["provider"]["model_artifacts"][0]["revision"] = "main"
        with self.assertRaisesRegex(RuntimeError, "revision is mutable"):
            tts_provider_ab.validate_health("fixture", valid_health)

    def test_listening_review_prevents_automated_winner_selection(self) -> None:
        matrix = tts_provider_ab.load_matrix(
            ROOT / "scenarios" / "tts_provider_ab.json"
        )
        template = tts_provider_ab.listening_review_template(
            matrix,
            [{"label": "provider-a"}, {"label": "provider-b"}],
        )
        self.assertEqual(template["status"], "operator_review_required")
        self.assertGreater(len(template["reviews"]), len(matrix["cases"]))
        self.assertTrue(
            all(
                rating is None
                for review in template["reviews"]
                for rating in review["ratings"].values()
            )
        )

    def test_run_metadata_records_source_identity_and_dirty_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata = tts_provider_ab.run_metadata(Path(temp_dir) / "run-42")
        self.assertEqual(metadata["run_id"], "run-42")
        self.assertIn("generated_at", metadata)
        self.assertEqual(
            metadata["chromie_source"]["repository"], ROOT.resolve().name
        )
        self.assertRegex(metadata["chromie_source"]["revision"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(metadata["chromie_source"]["dirty"], bool)


if __name__ == "__main__":
    unittest.main()
