from __future__ import annotations

import argparse
import asyncio

from .capabilities.loader import build_configured_registry
from .capabilities.probe import probe_mcp_capabilities


async def _run(manifests: list[str], timeout_s: float) -> int:
    configured = build_configured_registry(manifests)
    results = await probe_mcp_capabilities(
        configured.registry,
        timeout_s=timeout_s,
    )

    failed = False
    for result in results:
        print(f"Endpoint: {result.url}")
        print(
            f"  expected={len(result.expected_schemas)} "
            f"advertised={len(result.advertised_schemas)}"
        )
        if result.missing_tools:
            failed = True
            print(f"  missing: {', '.join(sorted(result.missing_tools))}")
        if result.schema_mismatches:
            failed = True
            print(f"  schema mismatch: {', '.join(sorted(result.schema_mismatches))}")
        if result.extra_tools:
            print(f"  extra: {', '.join(sorted(result.extra_tools))}")
        if result.ok:
            print("  status: ready")

    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify MCP endpoints advertise every tool declared by their manifests."
    )
    parser.add_argument(
        "--manifest",
        action="append",
        required=True,
        help="External capability bundle JSON. May be repeated.",
    )
    parser.add_argument("--timeout-s", type=float, default=10.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.manifest, args.timeout_s)))


if __name__ == "__main__":
    main()
