from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.runtime.evidence_identity import (
    RuntimeEvidenceIdentityError,
    canonical_json_sha256,
    load_runtime_evidence_identity,
)


def identity_payload() -> dict:
    payload = {
        "schema_version": 1,
        "captured_at": "2026-07-27T00:00:00+00:00",
        "evidence_claim": "runtime_identity_only",
        "chromie": {"revision": "a" * 40, "dirty": False},
        "runtime_profile": {"fingerprint": "profile", "models": {}},
        "capability_manifests": [{"path": "capabilities/soridormi.json", "sha256": "b" * 64}],
        "deployment": {"complete": True, "service_images": {}},
        "qualification": {"release_qualified": False},
    }
    payload["identity_sha256"] = canonical_json_sha256(payload)
    return payload


class RuntimeEvidenceIdentityTests(unittest.TestCase):
    def test_loads_digest_bound_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            path.write_text(json.dumps(identity_payload()), encoding="utf-8")
            loaded = load_runtime_evidence_identity(path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["chromie"]["revision"], "a" * 40)

    def test_rejects_tampered_identity(self) -> None:
        payload = identity_payload()
        payload["chromie"]["revision"] = "c" * 40
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(RuntimeEvidenceIdentityError):
                load_runtime_evidence_identity(path)

    def test_missing_identity_is_diagnostic_not_implicit_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                load_runtime_evidence_identity(Path(tmp) / "missing.json")
            )


if __name__ == "__main__":
    unittest.main()
