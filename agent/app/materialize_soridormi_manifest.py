from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .capabilities.models import CapabilityBundle


def materialize_soridormi_manifest(
    payload: dict[str, Any],
    *,
    endpoint: str = "${SORIDORMI_MCP_URL}",
    upstream_commit: str | None = None,
) -> CapabilityBundle:
    if payload.get("source") != "soridormi":
        raise ValueError("expected a Soridormi capability export")

    materialized = json.loads(json.dumps(payload))
    agents = materialized.get("agents")
    if not isinstance(agents, list) or not agents:
        raise ValueError("Soridormi capability export contains no agents")
    for agent in agents:
        agent["transport"] = {
            "kind": "mcp_streamable_http",
            "url": endpoint,
        }

    metadata = dict(materialized.get("metadata") or {})
    metadata.update(
        {
            "upstream_repository": "https://github.com/TimeTreker/soridormi.git",
            "transport_overlay": "mcp_streamable_http",
        }
    )
    if upstream_commit:
        metadata["upstream_commit"] = upstream_commit
    materialized["metadata"] = metadata
    return CapabilityBundle.model_validate(materialized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize a Chromie deployment manifest from Soridormi's export."
    )
    parser.add_argument("input", help="JSON produced by Soridormi export_capabilities.")
    parser.add_argument("output", help="Chromie deployment manifest to write.")
    parser.add_argument("--upstream-commit")
    args = parser.parse_args()

    source = Path(args.input)
    output = Path(args.output)
    payload = json.loads(source.read_text(encoding="utf-8"))
    bundle = materialize_soridormi_manifest(
        payload,
        upstream_commit=args.upstream_commit,
    )
    output.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
