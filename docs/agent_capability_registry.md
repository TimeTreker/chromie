# Chromie Global Agent Capability Registry

Chromie owns the global capability registry because it hosts the LLM router,
DAG planner, MCP clients, TTS/ASR, user confirmation, and cross-agent task
orchestration.

Soridormi and other robot/body subsystems should not own this global registry.
Soridormi is Chromie's robot cerebellum: it owns embodied planning, safety,
policy execution, and feedback. It exports an MCP-ready capability manifest,
and Chromie aggregates that contract with its own `chromie.*` tools.

## Boundary

- **Chromie**: global registry, LLM capability context, speech, listening,
  confirmation, reporting, DAG planning.
- **Soridormi**: local robot-body manifest and tools such as
  `soridormi.robot.get_status`, `soridormi.motion.create_plan`,
  `soridormi.motion.execute_plan`, and `soridormi.safety.emergency_stop`.

## CLI

List only Chromie's local tools:

```bash
PYTHONPATH=agent python -m app.list_capabilities
```

Merge an external Soridormi capability export:

```bash
PYTHONPATH=agent python -m app.list_capabilities \
  --manifest /path/to/soridormi_capabilities.json
```

Generate the LLM-facing capability context:

```bash
PYTHONPATH=agent python -m app.list_capabilities \
  --manifest /path/to/soridormi_capabilities.json \
  --llm-context --language zh
```

## Agent runtime configuration

The production Agent loads external manifests from the comma-separated
`AGENT_CAPABILITY_MANIFESTS` setting. Files placed in the repository's
`capabilities/` directory are mounted read-only at `/app/capabilities`.

```env
AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json
SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp
```

A configured file or directory must exist and every discovered JSON manifest
must validate. The Agent fails at startup on missing, malformed, or duplicate
capabilities rather than silently running with a partial registry. Manifest
strings support `${NAME}` references and fail startup when the referenced
environment variable is absent.

Inspect the active sources and mounted files through:

```text
GET /health
GET /capabilities
```

## Soridormi deployment probe

Chromie includes [the Soridormi deployment contract](../capabilities/soridormi.json).
It is materialized from the `TimeTreker/soridormi` export and records the
upstream commit in `metadata`. Its endpoint is supplied through
`SORIDORMI_MCP_URL`; the file intentionally does not contain a machine-specific
address.

Probe the live MCP server before enabling read-only or guarded execution:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=agent python -m app.probe_capabilities \
  --manifest capabilities/soridormi.json
```

The probe initializes an MCP Streamable HTTP session, calls `tools/list`, and
fails when the server omits a required tool or declares incompatible input
constraints. Extra advertised tools and schema annotations remain unavailable
because Chromie invokes only registry-approved names and validates against its
own manifest.

The checked-in manifest is the Chromie-side contract. Soridormi's dedicated
MCP container now advertises the same names and input contracts; target-host
deployment must still run the probe before execution is enabled.

Once the probe reports ready, run the read/planning acceptance graph:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json
```

This command probes first, reads robot status, then requests a bounded
zero-motion plan. It rejects a missing planning response contract and never
invokes `soridormi.motion.execute_plan`.

Add `--guarded-dry-run` to verify confirmed execution, monitor activation, and
normal stop fallback against Soridormi's network service. The current server
still wraps a dry-run tool service. Runtime-backed cancellation and supervised
hardware acceptance remain M5 target-host work.

## Safety rule

Chromie may plan and route tasks, but it must not receive raw motor, joint, or
torque tools. Robot movement must remain behind Soridormi's safe MCP tools.
