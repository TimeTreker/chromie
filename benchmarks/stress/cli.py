from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from benchmarks.contracts import ContractError
from benchmarks.e2e.executor import CommandE2EExecutor, ReplayE2EExecutor
from benchmarks.e2e.profiles import EvidenceProfileError, EvidenceProfileManifest
from benchmarks.runners.core import load_normalized_cases

from .profiles import StressProfileError, StressWorkloadManifest
from .runner import StressBenchmarkRunner, StressRunProfile
from .workloads import StressSample


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a versioned Chromie stress workload and report behavior distributions."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--normalized", type=Path)
    source.add_argument("--inventory", type=Path)
    parser.add_argument(
        "--workload-manifest",
        type=Path,
        default=Path("benchmarks/manifests/stress_workloads.json"),
    )
    parser.add_argument(
        "--e2e-profile-manifest",
        type=Path,
        default=Path("benchmarks/manifests/e2e_evidence_profiles.json"),
    )
    parser.add_argument("--workload", required=True)
    parser.add_argument("--run-id", default="local-stress")
    parser.add_argument("--replay-file", type=Path)
    parser.add_argument("--command")
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument(
        "--artifact-dir", type=Path, default=Path(".chromie/benchmark-artifacts/stress")
    )
    parser.add_argument("--model")
    parser.add_argument("--prompt-revision")
    parser.add_argument("--mind-profile")
    parser.add_argument("--code-revision")
    parser.add_argument("--provider-revision")
    parser.add_argument("--hardware-profile")
    parser.add_argument("--operator")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    def resolved(path: Path | None) -> Path | None:
        if path is None:
            return None
        return path if path.is_absolute() else repo_root / path

    try:
        workload_manifest = StressWorkloadManifest.from_file(
            resolved(args.workload_manifest)
        )
        workload = workload_manifest.get(args.workload)
        e2e_manifest = EvidenceProfileManifest.from_file(
            resolved(args.e2e_profile_manifest)
        )
        evidence_profile = e2e_manifest.get(workload.evidence_profile)
        if evidence_profile.supervision == "operator_required" and not args.operator:
            raise StressProfileError(
                f"workload {workload.id!r} requires --operator metadata"
            )
        cases = load_normalized_cases(
            repo_root,
            normalized_path=resolved(args.normalized),
            inventory_path=resolved(args.inventory),
        )
        if evidence_profile.transport == "replay":
            if args.replay_file is None or args.command:
                raise StressProfileError(
                    "replay stress workload requires --replay-file and forbids --command"
                )
            replay = ReplayE2EExecutor.from_file(resolved(args.replay_file))

            def executor_factory(sample: StressSample):
                return replay

        else:
            if not args.command or args.replay_file is not None:
                raise StressProfileError(
                    "command stress workload requires --command and forbids --replay-file"
                )
            command = shlex.split(args.command)
            artifact_root = resolved(args.artifact_dir) / args.run_id

            def executor_factory(sample: StressSample):
                return CommandE2EExecutor(
                    command,
                    timeout_s=args.timeout_s,
                    artifact_root=artifact_root / sample.sample_id,
                )

        report = StressBenchmarkRunner(
            executor_factory,
            StressRunProfile(
                run_id=args.run_id,
                model=args.model,
                prompt_revision=args.prompt_revision,
                mind_profile=args.mind_profile,
                code_revision=args.code_revision,
                provider_revision=args.provider_revision,
                hardware_profile=args.hardware_profile,
                operator=args.operator,
            ),
            workload,
            evidence_profile,
        ).run(cases)
    except (StressProfileError, EvidenceProfileError, ContractError) as exc:
        print(f"stress benchmark error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = resolved(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        try:
            print(output.relative_to(repo_root))
        except ValueError:
            print(output)
    else:
        sys.stdout.write(rendered)
    return 1 if report["summary"]["fail"] or report["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
