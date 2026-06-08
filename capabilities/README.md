# External Capability Manifests

Place trusted external capability bundle JSON files in this directory. Docker
mounts it read-only at `/app/capabilities` inside `chromie-agent`.

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
tools or server input schemas that omit manifest constraints fail the probe.

Do not expose raw motor, joint, or torque controls through these manifests.
