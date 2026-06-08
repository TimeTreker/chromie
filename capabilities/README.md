# External Capability Manifests

Place trusted external capability bundle JSON files in this directory. Docker
mounts it read-only at `/app/capabilities` inside `chromie-agent`.

`soridormi.json` is generated from Soridormi's authoritative capability export,
then overlaid with Chromie's MCP Streamable HTTP endpoint placeholder. Do not
hand-edit its tools or schemas.

Refresh it from a local Soridormi checkout:

```bash
PYTHONPATH=../soridormi/src \
  python -m soridormi_runtime.mcp.export_capabilities \
  --mode sim > /tmp/soridormi-export.json

PYTHONPATH=agent python -m app.materialize_soridormi_manifest \
  /tmp/soridormi-export.json capabilities/soridormi.json \
  --upstream-commit "$(git -C ../soridormi rev-parse HEAD)"
```

Enable one file:

```env
AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json
SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp
```

Enable every JSON file in the directory:

```env
AGENT_CAPABILITY_MANIFESTS=/app/capabilities
```

Multiple files or directories are comma-separated. Configured paths are
required to exist and parse successfully; otherwise the Agent fails at startup.
Manifest strings may reference required environment variables as `${NAME}`.
Chromie fails startup when a referenced variable is missing.

Before enabling execution, verify that the configured MCP server advertises
every tool declared by the manifest:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=agent python -m app.probe_capabilities \
  --manifest capabilities/soridormi.json
```

Extra server tools are reported but do not become available to Chromie. Missing
tools or incompatible declared input constraints fail the probe.

After a successful probe, run safe read/planning acceptance:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json
```

The default request creates a zero-motion plan and does not execute hardware.

Soridormi `main` provides a dedicated `soridormi-mcp` container around its
current dry-run tool core. Chromie remains in its own containers and connects
through `SORIDORMI_MCP_URL`.

Verify the guarded dry-run boundary with:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --guarded-dry-run
```

This is network integration evidence, not supervised robot hardware evidence.

Do not expose raw motor, joint, or torque controls through these manifests.
