from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from benchmarks.evidence.sanitize import sanitize_evidence


class EvidenceSanitizationTests(unittest.TestCase):
    def test_sanitizes_without_modifying_raw_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw-run"
            (raw / "logs").mkdir(parents=True)
            (raw / "memory").mkdir()
            report = {
                "schema_version": 2,
                "revision": "abc",
                "checks": [],
                "api_key": "sk-ABCDEFGHIJKLMNOPQRSTUV",
                "path": "/home/alice/chromie",
            }
            (raw / "collection-report.json").write_text(json.dumps(report), encoding="utf-8")
            secret_log = "Authorization: Bearer secret-token\nOPENAI_API_KEY=sk-ABCDEFGHIJKLMNOPQRSTUV\n/home/alice/file\n"
            (raw / "logs" / "app.log").write_text(secret_log, encoding="utf-8")
            (raw / "memory" / "profile.json").write_text(
                json.dumps({"family": "private"}), encoding="utf-8"
            )
            (raw / "speech.wav").write_bytes(b"RIFF\x00\x00private-audio")
            binary_payload = bytes(range(1, 200))
            (raw / "opaque.bin").write_bytes(binary_payload)
            (raw / "events.jsonl").write_text(
                json.dumps({"access_token": "sk-ABCDEFGHIJKLMNOPQRSTUV", "event": "ok"}) + "\n",
                encoding="utf-8",
            )
            original = (raw / "logs" / "app.log").read_text()
            output = root / "sanitized.tar.gz"
            result = sanitize_evidence(
                raw,
                output_archive=output,
                redact_values=["alice"],
            )
            self.assertTrue(result["safe_to_upload"])
            self.assertEqual((raw / "logs" / "app.log").read_text(), original)
            self.assertTrue(output.is_file())
            self.assertTrue(Path(str(output) + ".sha256").is_file())
            extract = root / "extract"
            with tarfile.open(output, "r:gz") as archive:
                archive.extractall(extract, filter="data")
            sanitized_root = next(extract.iterdir())
            text = (sanitized_root / "logs" / "app.log").read_text()
            self.assertNotIn("secret-token", text)
            self.assertNotIn("sk-ABCDEFGHIJKLMNOPQRSTUV", text)
            self.assertNotIn("/home/alice", text)
            self.assertNotIn("alice", text)
            self.assertFalse((sanitized_root / "memory" / "profile.json").exists())
            self.assertTrue((sanitized_root / "speech.wav").is_file())
            self.assertEqual((sanitized_root / "opaque.bin").read_bytes(), binary_payload)
            event = json.loads((sanitized_root / "events.jsonl").read_text())
            self.assertEqual(event["access_token"], "<redacted>")
            sanitized_report = json.loads((sanitized_root / "sanitization-report.json").read_text())
            self.assertGreaterEqual(sanitized_report["summary"]["redaction_count"], 3)
            index = json.loads((sanitized_root / "artifact-index.json").read_text())
            indexed = {item["path"]: item for item in index["artifacts"]}
            self.assertIn("sanitization-report.json", indexed)
            for relative, item in indexed.items():
                self.assertEqual(
                    hashlib.sha256((sanitized_root / relative).read_bytes()).hexdigest(),
                    item["sha256"],
                )

    def test_can_exclude_audio_from_upload_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            (raw / "collection-report.json").write_text(
                json.dumps({"schema_version": 2, "checks": []}), encoding="utf-8"
            )
            (raw / "speech.wav").write_bytes(b"RIFF")
            output = root / "sanitized.tar.gz"
            report = sanitize_evidence(raw, output_archive=output, exclude_audio=True)
            self.assertFalse(report["policy"]["audio_included"])
            self.assertTrue(any(item["reason"] == "audio_excluded_by_policy" for item in report["excluded"]))


if __name__ == "__main__":
    unittest.main()
