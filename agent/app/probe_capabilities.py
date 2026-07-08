from __future__ import annotations

import argparse
import asyncio

from .capabilities.loader import build_configured_registry
from .capabilities.probe import probe_mcp_capabilities


async def _run(
    manifests: list[str],
    timeout_s: float,
    excluded_effects: frozenset[str],
) -> int:
    configured = build_configured_registry(manifests)
    try:
        results = await probe_mcp_capabilities(
            configured.registry,
            timeout_s=timeout_s,
            excluded_effects=excluded_effects,
        )
    except Exception as exc:
        print(
            "[probe][error] Could not verify MCP capabilities: "
            f"{type(exc).__name__}: {exc}"
        )
        print(
            "[probe][hint] Confirm SORIDORMI_MCP_URL is reachable from inside "
            "the chromie-agent container and that Soridormi advertises the "
            "manifest tools via MCP tools/list."
        )
        return 1

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
            for tool_name, details in result.schema_mismatch_details.items():
                for detail in details[:8]:
                    print(f"    - {tool_name}: {detail}")
                if len(details) > 8:
                    print(f"    - {tool_name}: ... {len(details) - 8} more differences")
        if result.schema_warnings:
            for tool_name, warnings in result.schema_warnings.items():
                for warning in warnings[:4]:
                    print(f"  schema warning: {tool_name}: {warning}")
                if len(warnings) > 4:
                    print(f"  schema warning: {tool_name}: ... {len(warnings) - 4} more warnings")
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
    parser.add_argument(
        "--exclude-effect",
        action="append",
        default=[],
        help=(
            "Do not require manifest tools with this effect. May be repeated; "
            "the default probe verifies the full manifest."
        ),
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            _run(
                args.manifest,
                args.timeout_s,
                frozenset(args.exclude_effect),
            )
        )
    )


if __name__ == "__main__":
    main()
