import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.release_provenance import (
    collect_provenance,
    exact_requirement_errors,
    mutable_image_errors,
    model_lock_errors,
    ollama_models,
)


class ReleaseProvenanceTests(unittest.TestCase):
    def test_repository_dependency_inputs_are_exactly_pinned(self) -> None:
        self.assertEqual(exact_requirement_errors(ROOT), [])

    def test_repository_model_lock_matches_profiles(self) -> None:
        self.assertEqual(model_lock_errors(ROOT), [])

    def test_maintained_asr_profiles_are_multilingual(self) -> None:
        for profile in sorted((ROOT / "env" / "profiles").glob("*.env")):
            with self.subTest(profile=profile.name):
                values = {}
                for line in profile.read_text(encoding="utf-8").splitlines():
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    values[key] = value
                model = values.get("ASR_MODEL", "")
                self.assertFalse(
                    model.endswith(".en"),
                    f"{profile.relative_to(ROOT)} uses English-only ASR model {model!r}",
                )
                self.assertTrue(values.get("ASR_MODEL_REVISION"))
                self.assertIn("sense-voice", model)

    def test_mutable_image_tags_are_rejected(self) -> None:
        self.assertEqual(mutable_image_errors(["python:3.12.10-slim"]), [])
        self.assertTrue(mutable_image_errors(["python:latest", "local/image"]))

    def test_preview_provenance_reports_runtime_and_mutable_image_blockers(self) -> None:
        with mock.patch("scripts.release_provenance.shutil.which", return_value=None), mock.patch(
            "scripts.release_provenance.ollama_models", side_effect=OSError("offline")
        ):
            result = collect_provenance(ROOT, require_runtime=False)
        self.assertFalse(result["complete"])
        self.assertTrue(result["source_errors"])
        self.assertTrue(
            all("mutable tag" in item for item in result["source_errors"]),
            result["source_errors"],
        )
        self.assertTrue(result["runtime_errors"])
        self.assertIn("model_lock", result)

    def test_ollama_digest_capture_requires_each_configured_model(self) -> None:
        payload = {
            "models": [
                {"name": "qwen3:4b", "digest": "sha256:abc", "size": 12}
            ]
        }
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch("scripts.release_provenance.urllib.request.urlopen", return_value=response), mock.patch(
            "scripts.release_provenance.json.load", return_value=payload
        ):
            result = ollama_models("http://localhost:11434", ["qwen3:4b"])
            self.assertEqual(result[0]["digest"], "sha256:abc")
            with self.assertRaisesRegex(RuntimeError, "not installed"):
                ollama_models("http://localhost:11434", ["missing:tag"])


if __name__ == "__main__":
    unittest.main()
