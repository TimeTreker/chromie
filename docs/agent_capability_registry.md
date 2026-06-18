# Agent Capability Registry

## Status

Implemented and automatically tested. The current checked-in Soridormi
manifest is a static deployment snapshot; live compatibility and target
acceptance remain separate evidence.

The registry is used by Agent TaskGraph planning, validation, LLM context,
policy checks, MCP invocation, capability-aware routing, and the normal native
InteractionRuntime. It does not replace the host Orchestrator's runtime Skill
Registry.

## Source of truth

Chromie consumes externally generated manifests. For Soridormi, the authoritative
source is Soridormi's capability export. Chromie materializes transport metadata
and records the upstream commit rather than hand-maintaining tool schemas.

Current snapshot:

- six agent records;
- twenty-one tool records;
- task status schema includes single-skill dry-run and `skill_sequence`
  dry-run metadata, plus Soridormi-owned `plan_steps` and
  `blocked_subsystems`, and Chromie routing hints in
  `recommended_next_actions`;
- upstream Soridormi commit
  `2fa137ffd59ca7f5be347b09a1664ace0cbbf9c2`;
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
`GET /health` and `GET /capabilities` expose the static view. The shared catalog
also refreshes `soridormi.skill.list` through the trusted MCP transport and keeps
the last known-good named-skill snapshot. `GET /capabilities/catalog` exposes
that merged routing/execution view.

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

## Shared capability catalog and LLM visibility

The Agent owns one queryable catalog service. Static manifest tools are indexed
for routing and planning. Live Soridormi named skills are indexed separately as
`interaction_executable`, because those exact IDs are resolvable by the host
Skill Registry. Router calls `POST /capabilities/search`; native
InteractionRuntime performs the same search in-process before execution. This
second check prevents a Router timeout or stale route from silently turning a
robot request into generic chat.

`GET /capabilities/llm-context?language=en` returns the filtered context used for
planning and capability-aware conversation. Supplying `text=...` returns only
the most relevant candidates. The model receives descriptions and schemas, not
deployment secrets or unrestricted low-level controls. Restricted safety and
control capabilities remain policy-governed even when present in the registry.

Model output is never trusted as registry truth. Graph identity is replaced by
the service, capability references are resolved again, arguments are validated,
and execution is separately gated.

## Agent registry versus Skill Registry

The two registries solve different problems:

| Registry | Owner | Lifetime | Used for |
|---|---|---|---|
| Agent capability registry | Agent process | Loaded at startup | TaskGraph planning, validation, policy, MCP transport |
| Skill Registry | Host Orchestrator | Runtime/provider registration | `InteractionResponse` named-skill resolution and execution |

The native structured Agent path selects only live named skills marked
`interaction_executable`, then emits normal `SkillRequest` values. The host still
reloads and validates the provider catalog before execution. Static MCP tools
remain available for routing/planning but are not treated as directly executable
named skills. Raw motor-level fields remain forbidden.

## Inspection and verification

```bash
curl -s http://127.0.0.1:8092/capabilities | jq
curl -s 'http://127.0.0.1:8092/capabilities/catalog?refresh=true' | jq
curl -s http://127.0.0.1:8092/capabilities/search \
  -H 'Content-Type: application/json' \
  -d '{"text":"move forward slowly for one second","language":"en"}' | jq
curl -s 'http://127.0.0.1:8092/capabilities/llm-context?language=en&text=move%20forward' | jq -r .context
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
The probe verifies the full manifest unless an acceptance workflow explicitly
uses repeatable `--exclude-effect EFFECT` filters. Such filters define scope;
they do not relax schema validation for included tools.
