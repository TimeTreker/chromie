from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from benchmarks.contracts import ContractError
from benchmarks.runners.core import load_normalized_cases, select_cases

from .executor import CommandE2EExecutor, ReplayE2EExecutor
from .profiles import EvidenceProfileError, EvidenceProfileManifest
from .runner import E2EBenchmarkRunner, E2ERunProfile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Chromie semantic scenarios through an E2E evidence profile."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--normalized", type=Path)
    source.add_argument("--inventory", type=Path)
    parser.add_argument(
        "--profile-manifest",
        type=Path,
        default=Path("benchmarks/manifests/e2e_evidence_profiles.json"),
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--layer", action="append", default=[])
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--run-id", default="local-e2e")
    parser.add_argument("--replay-file", type=Path)
    parser.add_argument("--command")
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("benchmarks/reports/e2e-artifacts"),
    )
    parser.add_argument("--model")
    parser.add_argument("--prompt-revision")
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
        manifest = EvidenceProfileManifest.from_file(resolved(args.profile_manifest))
        profile = manifest.get(args.profile)
        if profile.supervision == "operator_required" and not args.operator:
            raise EvidenceProfileError(
                f"profile {profile.id!r} requires --operator metadata"
            )
        cases = load_normalized_cases(
            repo_root,
            normalized_path=resolved(args.normalized),
            inventory_path=resolved(args.inventory),
        )
        selected = select_cases(
            cases,
            layers=set(args.layer) or None,
            datasets=set(args.dataset) or None,
            ids=set(args.id) or None,
        )
        if not selected:
            raise EvidenceProfileError("no scenarios matched the E2E cohort")
        if profile.transport == "replay":
            if args.replay_file is None or args.command:
                raise EvidenceProfileError(
                    "replay evidence profile requires --replay-file and forbids --command"
                )
            executor = ReplayE2EExecutor.from_file(resolved(args.replay_file))
        else:
            if not args.command or args.replay_file is not None:
                raise EvidenceProfileError(
                    "command evidence profile requires --command and forbids --replay-file"
                )
            artifact_dir = resolved(args.artifact_dir) / args.run_id
            executor = CommandE2EExecutor(
                shlex.split(args.command),
                timeout_s=args.timeout_s,
                artifact_root=artifact_dir,
            )
        report = E2EBenchmarkRunner(
            executor,
            E2ERunProfile(
                run_id=args.run_id,
                evidence_profile=profile,
                model=args.model,
                prompt_revision=args.prompt_revision,
                code_revision=args.code_revision,
                provider_revision=args.provider_revision,
                hardware_profile=args.hardware_profile,
                operator=args.operator,
            ),
        ).run(selected)
    except (EvidenceProfileError, ContractError) as exc:
        print(f"E2E benchmark error: {exc}", file=sys.stderr)
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
