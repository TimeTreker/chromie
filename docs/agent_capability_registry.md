# Agent Capability Registry

## Status

Implemented and automatically tested. The current checked-in Soridormi
manifest is a static deployment snapshot; live compatibility and target
acceptance remain separate evidence.

The registry is used by Agent TaskGraph planning, validation, LLM context,
policy checks, and MCP invocation. It does not replace the host Orchestrator's
runtime Skill Registry.

## Source of truth

Chromie consumes externally generated manifests. For Soridormi, the authoritative
source is Soridormi's capability export. Chromie materializes transport metadata
and records the upstream commit rather than hand-maintaining tool schemas.

Current snapshot:

- four agent records;
- twelve tool records;
- upstream Soridormi commit
  `a092dc704f1ab797fb1d4f542696fe75026eb171`;
- MCP endpoint resolved from `${SORIDORMI_MCP_URL}`.

Refresh instructions are in
[`../capabilities/README.md`](../capabilities/README.md).

## Startup behavior

`AGENT_CAPABILITY_MANIFESTS` accepts a comma-separated list of files or
directories. Registry construction is fail-fast for:

- missing configured paths;
- malformed JSON or schema violations;
- unresolved required environment placeholders;
- duplicate agent identifiers;
- duplicate tool identifiers;
- invalid safety, fallback, or dependency references.

The Agent logs loaded sources, manifest files, and total tool count at startup.
`GET /health` and `GET /capabilities` expose the active view.

## Capability policy represented

Each tool can declare information such as:

- JSON input/output schemas;
- side-effect class (`safe_read`, `planning_only`, guarded effects, physical);
- confirmation requirement;
- safety monitor and emergency fallback relationships;
- whether parallel execution is permitted;
- an `exclusive_group` for resource serialization;
- transport-neutral invocation metadata.

The registry enables validation and policy decisions; it does not itself execute
a tool. Real calls cross a `ToolInvoker` boundary.

## LLM visibility

`GET /capabilities/llm-context?language=en` returns the filtered context used for
planning. The model receives only the descriptions intended for planning, not
deployment secrets or unrestricted low-level controls. Restricted safety and
control capabilities remain policy-governed even when they are present in the
registry.

Model output is never trusted as registry truth. Graph identity is replaced by
the service, capability references are resolved again, arguments are validated,
and execution is separately gated.

## Agent registry versus Skill Registry

The two registries solve different problems:

| Registry | Owner | Lifetime | Used for |
|---|---|---|---|
| Agent capability registry | Agent process | Loaded at startup | TaskGraph planning, validation, policy, MCP transport |
| Skill Registry | Host Orchestrator | Runtime/provider registration | `InteractionResponse` named-skill resolution and execution |

The native structured Agent path generates Skill Runtime requests directly,
while preserving the host's provider and execution boundary. It must not expose
raw MCP tool names or motor-level fields as a shortcut; runtime registry
resolution remains mandatory.

## Inspection and verification

```bash
curl -s http://127.0.0.1:8092/capabilities | jq
curl -s 'http://127.0.0.1:8092/capabilities/llm-context?language=en' | jq -r .context
```

Probe the live Soridormi server:

```bash
cd agent
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
PYTHONPATH=. python -m app.probe_capabilities \
  --manifest ../capabilities/soridormi.json
```

A successful probe demonstrates live surface compatibility. It is not evidence
that guarded or physical execution has been accepted on target hardware.
