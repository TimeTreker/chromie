from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from benchmarks.e2e.profiles import EvidenceProfileError, EvidenceProfileManifest

from .profiles import StressProfileError, StressWorkloadManifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Chromie stress workloads")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/manifests/stress_workloads.json"),
    )
    parser.add_argument(
        "--e2e-profile-manifest",
        type=Path,
        default=Path("benchmarks/manifests/e2e_evidence_profiles.json"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()

    def resolved(path: Path) -> Path:
        return path if path.is_absolute() else repo_root / path

    try:
        manifest = StressWorkloadManifest.from_file(resolved(args.manifest))
        evidence_manifest = EvidenceProfileManifest.from_file(
            resolved(args.e2e_profile_manifest)
        )
        for workload in manifest.workloads:
            evidence_manifest.get(workload.evidence_profile)
    except (StressProfileError, EvidenceProfileError) as exc:
        print(f"stress workload validation error: {exc}", file=sys.stderr)
        return 2
    summary = {
        "schema_version": 1,
        "workload_count": len(manifest.workloads),
        "runtime_policy_authority": manifest.runtime_policy_authority,
        "metrics_are_observational": manifest.metrics_are_observational,
        "comparison_dimensions": list(manifest.comparison_dimensions),
        "workloads": [item.to_dict() for item in manifest.workloads],
    }
    if args.check:
        print(f"Stress workloads valid: {len(manifest.workloads)}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
