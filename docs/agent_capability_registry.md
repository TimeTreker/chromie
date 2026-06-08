# Chromie Global Agent Capability Registry

Chromie owns the global capability registry because it hosts the LLM router,
DAG planner, MCP clients, TTS/ASR, user confirmation, and cross-agent task
orchestration.

Soridormi and other robot/body subsystems should not own this global registry.
Instead they export local MCP-ready capability manifests, and Chromie aggregates
those manifests with its own `chromie.*` tools.

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
```

A configured file or directory must exist and every discovered JSON manifest
must validate. The Agent fails at startup on missing, malformed, or duplicate
capabilities rather than silently running with a partial registry.

Inspect the active sources and mounted files through:

```text
GET /health
GET /capabilities
```

## Safety rule

Chromie may plan and route tasks, but it must not receive raw motor, joint, or
torque tools. Robot movement must remain behind Soridormi's safe MCP tools.
