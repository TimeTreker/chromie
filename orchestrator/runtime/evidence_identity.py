from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class RuntimeEvidenceIdentityError(ValueError):
    """Raised when a retained runtime identity cannot be trusted."""


def canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_runtime_evidence_identity(path: Path | None) -> dict[str, Any] | None:
    """Load and validate a source-bound runtime identity.

    Missing identity is allowed for ordinary development operation. Qualification
    tooling treats it as incomplete evidence rather than silently upgrading the
    run.
    """

    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeEvidenceIdentityError(
            f"failed to read runtime evidence identity {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeEvidenceIdentityError("runtime evidence identity must be an object")
    if payload.get("schema_version") != 1:
        raise RuntimeEvidenceIdentityError("unsupported runtime evidence identity schema")
    declared = str(payload.get("identity_sha256") or "").strip().lower()
    if len(declared) != 64 or any(ch not in "0123456789abcdef" for ch in declared):
        raise RuntimeEvidenceIdentityError("runtime identity has no valid identity_sha256")
    unsigned = dict(payload)
    unsigned.pop("identity_sha256", None)
    expected = canonical_json_sha256(unsigned)
    if declared != expected:
        raise RuntimeEvidenceIdentityError("runtime evidence identity digest mismatch")

    chromie = payload.get("chromie")
    runtime_profile = payload.get("runtime_profile")
    deployment = payload.get("deployment")
    manifests = payload.get("capability_manifests")
    if not isinstance(chromie, dict) or not str(chromie.get("revision") or "").strip():
        raise RuntimeEvidenceIdentityError("runtime identity has no Chromie revision")
    if not isinstance(runtime_profile, dict) or not str(
        runtime_profile.get("fingerprint") or ""
    ).strip():
        raise RuntimeEvidenceIdentityError("runtime identity has no runtime profile fingerprint")
    if not isinstance(deployment, dict):
        raise RuntimeEvidenceIdentityError("runtime identity has no deployment object")
    if not isinstance(manifests, list) or not manifests:
        raise RuntimeEvidenceIdentityError("runtime identity has no capability manifests")
    return payload


def runtime_identity_reference(
    identity: dict[str, Any] | None,
    *,
    path: Path | None,
) -> dict[str, Any]:
    if identity is None:
        return {
            "identity_sha256": None,
            "path": str(path) if path is not None else None,
            "complete": False,
        }
    return {
        "identity_sha256": identity["identity_sha256"],
        "path": str(path) if path is not None else None,
        "complete": True,
    }


__all__ = [
    "RuntimeEvidenceIdentityError",
    "canonical_json_sha256",
    "load_runtime_evidence_identity",
    "runtime_identity_reference",
]
