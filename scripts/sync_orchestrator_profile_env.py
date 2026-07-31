#!/usr/bin/env python3
"""Copy profile-owned cognitive budgets into a generated Orchestrator env file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_runtime_env import (  # noqa: E402
    COGNITIVE_BUDGET_KEYS,
    ConfigurationError,
    atomic_write,
    parse_env_file,
    shell_quote,
)


def sync_profile_budgets(source: Path, destination: Path) -> None:
    source_values = parse_env_file(source)
    destination_values = parse_env_file(destination)
    missing = [key for key in COGNITIVE_BUDGET_KEYS if key not in source_values]
    if missing:
        raise ConfigurationError(
            f"{source}: missing profile-owned cognitive budgets: {', '.join(missing)}"
        )

    conflicts = [
        key
        for key in COGNITIVE_BUDGET_KEYS
        if key in destination_values and destination_values[key] != source_values[key]
    ]
    if conflicts:
        raise ConfigurationError(
            f"{destination}: conflicts with generated runtime profile: "
            + ", ".join(conflicts)
        )

    retained = destination.read_text(encoding="utf-8").rstrip("\n")
    additions = [
        f"{key}={shell_quote(source_values[key])}"
        for key in COGNITIVE_BUDGET_KEYS
        if key not in destination_values
    ]
    content = retained + "\n"
    if additions:
        content += "\n# Profile-owned cognitive budgets from .env.runtime\n"
        content += "\n".join(additions) + "\n"
    atomic_write(destination, content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".env.runtime")
    parser.add_argument(
        "--destination",
        type=Path,
        default=ROOT / ".chromie" / "voice-runtime" / "orchestrator.env",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sync_profile_budgets(
            args.source.expanduser().resolve(),
            args.destination.expanduser().resolve(),
        )
    except ConfigurationError as exc:
        print(f"[orchestrator-env][error] {exc}", file=sys.stderr)
        return 1
    print(
        "[orchestrator-env] Synchronized profile-owned cognitive budgets: "
        f"{args.destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
