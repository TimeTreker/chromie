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

## Safety rule

Chromie may plan and route tasks, but it must not receive raw motor, joint, or
torque tools. Robot movement must remain behind Soridormi's safe MCP tools.
