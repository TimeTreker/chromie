# External Capability Manifests

This directory contains trusted capability snapshots consumed by
`chromie-agent`. Docker mounts it read-only at `/app/capabilities`.

The manifests are policy inputs, not informal tool descriptions. They define
agent identities, tool schemas, side-effect classes, confirmation requirements,
safety monitors, fallbacks, parallelism policy, and transport metadata used by
TaskGraph validation and execution.

## Soridormi snapshot

[`soridormi.json`](soridormi.json) is generated from Soridormi's authoritative
capability export and then materialized with Chromie's MCP Streamable HTTP
transport placeholder. The checked-in snapshot contains six agent records and
twenty-one tool records and identifies upstream Soridormi commit:

```text
2fa137ffd59ca7f5be347b09a1664ace0cbbf9c2
```

Do not hand-edit exported tools, schemas, or safety policy. Refresh the source
export and rematerialize the file instead.

The Soridormi task surface includes retry and monitoring contracts used by Chromie's
TaskGraph:

- `client_task_ref` lets Chromie retry `soridormi.task.submit` without creating
  duplicate Soridormi task records.
- `idempotent_replay` marks duplicate submits that return the original task.
- `soridormi.task.events` returns `soridormi.task_events.v1` with
  `latest_sequence`, `next_after_sequence`, `terminal`, `deadline_at`,
  `expired`, and `poll_recommendation`.

## Refresh from a Soridormi checkout

From the Chromie repository root, with Soridormi checked out at
`../soridormi`:

```bash
PYTHONPATH=../soridormi/src \
python -m soridormi_runtime.mcp.export_capabilities \
  --mode sim > /tmp/soridormi-export.json

PYTHONPATH=agent python -m app.materialize_soridormi_manifest \
  /tmp/soridormi-export.json \
  capabilities/soridormi.json \
  --upstream-commit "$(git -C ../soridormi rev-parse HEAD)"
```

Review the resulting diff, run the capability and contract tests, and record the
compatible Soridormi revision in release notes.

## Configure the Agent

```env
AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json
SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp
```

`${SORIDORMI_MCP_URL}` is resolved when the Agent loads the manifest. An unset
required variable fails startup rather than leaving a partially configured
registry.

Multiple manifest paths or directories may be separated by commas. Duplicate
agent or tool identifiers fail registry construction.

## Verify a live capability server

Prefer the deployed Agent container from the repository root:

```bash
./scripts/build_runtime_env.sh
docker compose --env-file .env.runtime up -d chromie-agent
docker compose --env-file .env.runtime exec -T \
  -e SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json
```

For host-only development, install `agent/requirements.txt` and run the module
with `PYTHONPATH=agent`.

The probe compares the declared manifest with the live MCP surface. Safe
acceptance commands are documented in
[`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md).

## Two registries with different purposes

Chromie currently has two related but distinct capability views:

1. The Agent capability registry is a startup-loaded, static manifest view used
   for TaskGraph planning, validation, policy, and MCP invocation.
2. The Orchestrator Skill Registry is a runtime catalog of trusted named skills
   used by `InteractionResponse` and the host Skill Runtime.

They share the principle that the model selects validated named capabilities,
not raw motor or joint commands, but they are not the same in-memory object.
The native structured Agent path now emits Skill Runtime requests directly,
while the host registry remains the final provider and execution authority.
Future catalog-alignment work must not bypass either policy layer.
