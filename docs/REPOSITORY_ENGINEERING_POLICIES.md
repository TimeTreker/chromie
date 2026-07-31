# Repository Engineering Policies

Status: implemented and automatically verified
Scope: stable source, architecture, Agent Skill, contract, and local deployment
boundaries

## Purpose

Chromie keeps semantic intelligence in LLM-driven Agents while using deterministic
Host code for schema, authority, safety, provenance, and execution boundaries.
Stable mechanical rules must therefore be executable instead of relying only on
reviewer memory.

The canonical gate is:

```bash
python scripts/check_repository_policies.py
```

The maintained `scripts/run_tests.sh` entrypoint runs this command, and GitHub
Actions runs that same entrypoint. `scripts/benchmark_check.sh` also invokes the
canonical gate so benchmark work cannot bypass architecture policy.

The checker is dependency-light. It uses the Python AST, JSON, the maintained
Compose source checker, and the existing removed-Router guard. It does not call a
model, inspect prompt meaning, choose an Agent Skill, or evaluate benchmark
answers.

The removed-Router guard distinguishes ignored cache-only residue from
maintained content. A directory containing only `__pycache__` artifacts does
not recreate the removed service, while maintained source, imports, service
configuration, contracts, or current architecture claims still fail closed.

## Rule ownership

| Rule ID | Stable boundary |
|---|---|
| `python.production_assert` | Maintained runtime and generated-environment invariants must use explicit exceptions because `assert` disappears under `python -O`. |
| `python.silent_broad_exception` | A broad `Exception`, `BaseException`, or bare handler may not silently `pass`, `continue`, `break`, or return `None`. |
| `python.dynamic_execution` | Maintained Python may not call `eval` or `exec`. |
| `python.unsafe_shell` | Maintained Python may not use `os.system`, `os.popen`, shell subprocess helpers, or `subprocess(..., shell=True)`. |
| `contracts.low_level_actuation_field` | Chromie model-facing contracts may not expose raw motor, joint, torque, actuator, motor-target, or controller-array fields. |
| `compose.local_loopback` | The maintained local Compose profile may publish host ports only on loopback and may not use host networking. |
| `architecture.removed_authority` | The removed Router service, client, port, imports, metadata, and current-architecture claims may not return. |
| `agent_skills.execution_authority` | Agent Skill code remains passive and read-only: no plugin import path, Capability Runtime dependency, registration, authorization, dispatch, or execution method. |
| `agent_skills.model_authored_selection` | Candidate discovery may filter only declared IDs and role projections; it may not inspect semantic text, use phrase rules, or replace the configured model selection call. |
| `architecture.host_semantic_authority` | The Host may not own ordinary deep-thinking delegation, domain route repair, catalog phrase boosts, discourse classification, memory meaning, or route-specific user-facing wording. Compatibility fallbacks may report only bounded operational failure. |
| `architecture.legacy_phrase_agents` | Removed phrase/regex motion and pose agents cannot be restored or enabled through caller context. |
| `memory.model_authored_update` | Session-memory meaning must come from a typed model-authored proposal; `MemoryAgent` may not classify raw text. |
| `contracts.canonical_capability_identity` | Current model, Plan, API, trace, and evidence identities emit `capability_id`; bounded readers may still normalize retained `skill_id` input. |

The failure rules are intentionally narrower than a generic style linter. A broad
handler that re-raises, emits diagnostics/evidence, or returns an explicit typed
fallback is not classified as a trivially silent handler. More comprehensive
lint and type gates belong to their separately reviewed Issues.

## Exception registry

All exceptions live in:

```text
config/repository_policy_exceptions.json
```

The normal registry is empty. An exception must identify one exact rule, path,
and symbol and include both:

- a concrete reviewed reason;
- a concrete removal condition.

Example shape:

```json
{
  "schema_version": "1.0",
  "exceptions": [
    {
      "rule_id": "python.silent_broad_exception",
      "path": "orchestrator/example.py",
      "symbol": "Example.close",
      "reason": "A reviewed external cleanup API can throw after primary failure evidence is already retained.",
      "remove_when": "Remove when the external cleanup API exposes a narrow documented exception type."
    }
  ]
}
```

Wildcards, absolute paths, parent traversal, weak explanations, duplicate keys,
and unknown rule IDs fail closed. An exception that no longer matches a live
finding also fails as `policy.exception_stale`; contributors must remove it
rather than retain a permanent baseline.

Exceptions suppress only the matching structural finding. They cannot authorize
an Agent Skill, a Capability, a network exposure, a physical action, or a model
behavior.

## Machine-readable output

Automation may request JSON:

```bash
python scripts/check_repository_policies.py --json
```

The result reports `passed` or `failed`, the number of exact reviewed
suppressions, and bounded findings containing rule ID, path, line, symbol, and
message.

## Relationship to specialized checks

The following specialized tools remain useful at their owning boundaries:

- `scripts/check_local_runtime_exposure.py` also audits Docker Compose's fully
  resolved runtime JSON during service startup;
- `scripts/check_router_removed.py` retains the detailed historical Router
  removal inventory;
- `scripts/check_docs.py` validates documentation, API, configuration, and
  artifact authority.

The repository policy checker is the canonical aggregate gate. Specialized
checks do not create separate policy authority.

## Non-goals

This gate does not:

- perform semantic code review through regex;
- inspect prompts for preferred wording;
- map phrases or routes to Goals, Agent Skills, Capabilities, or actions;
- decide whether a model selected the best method;
- replace unit, integration, benchmark, live-service, simulator, or physical
  evidence;
- provide a general security scanner or remote-deployment trust design.

## Automatic evidence

Focused tests inject one violation for each of the thirteen rule families,
verify machine-readable output, verify exact exception matching, and require
stale exceptions to fail. On 2026-07-31 the fresh canonical gate passed the
policy checker together with unit, architecture, documentation, benchmark, and
legacy Agent tests.

Automatic policy success is implementation evidence. It does not prove live
provider behavior, LAN isolation on a deployed host, microphone/speaker quality,
MuJoCo execution, or physical-robot safety.
