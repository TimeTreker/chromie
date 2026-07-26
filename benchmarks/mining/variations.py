from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .models import MiningError, candidate_fingerprint


def build_variation_briefs(
    candidate: Mapping[str, Any],
    requested: list[tuple[str, str]],
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    axes = manifest.get("variation_axes")
    if not isinstance(axes, Mapping):
        raise MiningError("variation axes are not configured")
    briefs: list[dict[str, Any]] = []
    fingerprint = candidate_fingerprint(candidate)
    for axis, value in requested:
        allowed = axes.get(axis)
        if not isinstance(allowed, list) or value not in allowed:
            raise MiningError(f"unsupported variation {axis}={value}")
        digest = hashlib.sha256(f"{candidate['id']}|{axis}|{value}".encode("utf-8")).hexdigest()[:12]
        briefs.append(
            {
                "schema_version": 1,
                "variation_id": f"variation_{digest}",
                "source_candidate_id": candidate["id"],
                "source_candidate_fingerprint": fingerprint,
                "axis": axis,
                "requested_value": value,
                "authoring_instruction": (
                    "Author one natural candidate that preserves the source responsibility and "
                    "expected safety boundary while varying only the requested axis. Do not map a "
                    "phrase to a fixed action, and do not change Runtime policy."
                ),
                "generated_scenario": None,
                "requires_human_review": True,
                "auto_promotion_allowed": False,
                "runtime_policy_authority": False,
            }
        )
    return briefs
