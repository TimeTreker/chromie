from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Iterable

from benchmarks.contracts import ContractError
from benchmarks.runners.core import load_normalized_cases, select_cases

from .executor import CommandE2EExecutor, ReplayE2EExecutor
from .first_party import FirstPartyAdapterManifest, FirstPartyE2EExecutor
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
    parser.add_argument(
        "--adapter-manifest",
        type=Path,
        default=Path("benchmarks/manifests/e2e_adapters.json"),
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--layer", action="append", default=[])
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--cohort", action="append", default=[])
    parser.add_argument("--style", action="append", default=[])
    parser.add_argument("--mode", action="append", default=[])
    parser.add_argument("--language", action="append", default=[])
    parser.add_argument("--invariant", action="append", default=[])
    parser.add_argument("--forbidden-behavior", action="append", default=[])
    parser.add_argument("--run-id", default="local-e2e")
    parser.add_argument("--replay-file", type=Path)
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--command")
    execution.add_argument(
        "--adapter",
        help=(
            "First-party adapter id from e2e_adapters.json. The adapter resolves "
            "one configured URL or Python callable and forwards the unchanged "
            "scenario contract."
        ),
    )
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("benchmarks/reports/e2e-artifacts"),
    )
    parser.add_argument("--model")
    parser.add_argument(
        "--effective-model",
        action="append",
        default=[],
        metavar="COMPONENT=MODEL",
        help="Resolved runtime model identity; repeat for each cognitive component.",
    )
    parser.add_argument("--prompt-revision")
    parser.add_argument("--code-revision")
    parser.add_argument("--provider-revision")
    parser.add_argument("--hardware-profile")
    parser.add_argument("--mind-profile")
    parser.add_argument("--social-style")
    parser.add_argument("--apply-lane", action="append", default=[])
    parser.add_argument("--semantic-authority-owner")
    parser.add_argument("--runtime-topology")
    parser.add_argument("--sample-count", type=int, default=1)
    parser.add_argument("--operator")
    parser.add_argument("--output", type=Path)
    return parser


def _parse_key_values(values: Iterable[str], *, name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key.strip() or not item.strip():
            raise EvidenceProfileError(f"{name} must use COMPONENT=MODEL syntax")
        key = key.strip()
        item = item.strip()
        if key in parsed and parsed[key] != item:
            raise EvidenceProfileError(f"{name} declares conflicting values for {key!r}")
        parsed[key] = item
    return parsed


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
        effective_models = _parse_key_values(
            args.effective_model, name="--effective-model"
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
            cohorts=set(args.cohort) or None,
            styles=set(args.style) or None,
            modes=set(args.mode) or None,
            languages=set(args.language) or None,
            invariants=set(args.invariant) or None,
            forbidden_behaviors=set(args.forbidden_behavior) or None,
        )
        if not selected:
            raise EvidenceProfileError("no scenarios matched the E2E cohort")
        artifact_dir = resolved(args.artifact_dir) / args.run_id
        if profile.transport == "replay":
            if args.replay_file is None or args.command or args.adapter:
                raise EvidenceProfileError(
                    "replay evidence profile requires --replay-file and forbids "
                    "--command/--adapter"
                )
            executor = ReplayE2EExecutor.from_file(resolved(args.replay_file))
        else:
            if args.replay_file is not None or not (args.command or args.adapter):
                raise EvidenceProfileError(
                    "live evidence profile requires exactly one of --command or "
                    "--adapter and forbids --replay-file"
                )
            if args.command:
                executor = CommandE2EExecutor(
                    shlex.split(args.command),
                    timeout_s=args.timeout_s,
                    artifact_root=artifact_dir,
                )
            else:
                adapter_manifest = FirstPartyAdapterManifest.from_file(
                    resolved(args.adapter_manifest)
                )
                adapter_profile = adapter_manifest.get(args.adapter)
                executor = FirstPartyE2EExecutor.from_environment(
                    adapter_profile,
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
                effective_model_topology=effective_models,
                mind_profile=args.mind_profile,
                social_interaction_style=args.social_style,
                apply_lanes=tuple(args.apply_lane),
                semantic_authority_owner=args.semantic_authority_owner,
                runtime_topology=args.runtime_topology,
                sample_count=args.sample_count,
                metadata={
                    "selection": {
                        "layers": list(args.layer),
                        "datasets": list(args.dataset),
                        "ids": list(args.id),
                        "cohorts": list(args.cohort),
                        "styles": list(args.style),
                        "modes": list(args.mode),
                        "languages": list(args.language),
                        "invariants": list(args.invariant),
                        "forbidden_behaviors": list(args.forbidden_behavior),
                        "selected_case_count": len(selected),
                    },
                    "adapter": args.adapter or "external_command",
                },
            ),
        ).run(selected)
    except (EvidenceProfileError, ContractError, ValueError) as exc:
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
