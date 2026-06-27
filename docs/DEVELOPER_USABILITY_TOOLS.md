# Developer Usability Tools Plan

This plan turns the next Chromie implementation focus into a docs-first,
incremental tooling milestone. It does not change the project boundary:
Chromie remains the local-first interaction control plane, and Soridormi remains
the embodied planner and executor.

## Objective

Make a developer or operator able to answer, from one command surface:

- what deployment mode this checkout is configured for;
- which feature gates are enabled and whether risky gates are default-off;
- whether generated configuration files exist and are internally consistent;
- whether core services and optional Soridormi endpoints are reachable;
- whether the checked-in capability manifest is valid and safe to expose;
- what evidence can be collected without overstating simulator, audio, GPU, or
  hardware claims.

The milestone improves operability, traceability, and evidence packaging before
any new physical-robot capability work.

## Current Implementation State

PR0 through PR6 are implemented and automatically verified at Level A:

- the documentation plan is indexed and linked from the roadmap, checkpoint,
  and handoff;
- `python -m tools.chromie_cli --help` exposes the standard-library CLI
  skeleton;
- `status`, `config show`, and `config validate` inspect deployment mode,
  selected config sources, generated runtime state, risky feature gates, URLs,
  positive numeric budgets, and fail-closed gate combinations;
- `doctor` classifies environment, file, service reachability, optional
  Soridormi, and host audio checks as ok, warning, failure, or skipped;
- `capability check` verifies Soridormi manifest provenance, duplicate
  identities, tool/agent alignment, and forbidden low-level fields in
  model-facing schemas;
- `evidence bundle` assembles git/config/evidence metadata and labels evidence
  levels without turning local or automated output into release readiness;
- `trace view` reads retained local JSONL and JSON artifacts, filters by
  session, interaction, graph, or trace id, and summarizes session events,
  interaction responses, Skill Runtime executions, TaskGraph traces, and
  acceptance summaries according to [Trace Schema](TRACE_SCHEMA.md);
- plain text and JSON output are both supported.

`trace explain` remains future work.

## Non-goals

This milestone deliberately does not add:

- a web dashboard;
- Redis, SQLite, or distributed runtime-state migration;
- OpenTelemetry exporters;
- dynamic third-party provider plugin loading;
- long-term vector memory;
- hardware button or gesture confirmation;
- multi-GPU or MIG scheduling automation;
- new low-level robot controls or new physical-motion authorization.

## Command Surface

The stable command surface should eventually be:

```bash
chromie doctor
chromie status
chromie config show
chromie config validate
chromie capability check
chromie trace view
chromie evidence bundle
```

Until packaging is ready, the implementation may expose the same commands as:

```bash
python -m tools.chromie_cli ...
```

Use `argparse` and the Python standard library for the first implementation.
Avoid new presentation dependencies until the dependency-light automated suite
has a clear reason to accept them.

## Delivery Sequence

### PR 0 - Documentation Plan

Record this milestone in the roadmap, checkpoint, handoff, and documentation
index before implementation begins.

Exit criteria:

- roadmap names the milestone and its evidence level;
- checkpoint points the next developer to this plan;
- documentation checker passes.

### PR 1 - CLI Skeleton

Add the command package and shared output helpers without service probes yet.

Expected files:

```text
tools/chromie_cli/__init__.py
tools/chromie_cli/__main__.py
tools/chromie_cli/output.py
tests/test_chromie_cli_*.py
```

Exit criteria:

- `python -m tools.chromie_cli --help` exits successfully;
- unknown commands fail with a clear message;
- output helpers support plain text and machine-readable JSON;
- Level A tests cover argument parsing and stable exit codes.

### PR 2 - Status And Configuration Inspection

Implement:

```bash
python -m tools.chromie_cli status
python -m tools.chromie_cli config show
python -m tools.chromie_cli config validate
```

`status` should summarize the configured deployment mode, default-off risky
gates, physical-motion state, simulator state, and compatibility rollback
state. `config validate` should run without starting the full stack.

Validation should cover:

- parseable boolean feature gates;
- positive timeout and concurrency values;
- generated `.env.runtime` and ignored root `.env` presence when expected;
- illegal feature-gate combinations;
- empty or malformed service URLs;
- structured MuJoCo settings that require a Soridormi MCP URL and manifest;
- physical robot flags that must remain refused without commissioning evidence.

Exit criteria:

- Level A tests cover common, missing, and malformed configuration cases;
- docs avoid claiming live service health from static configuration checks.

### PR 3 - Doctor

Implement:

```bash
python -m tools.chromie_cli doctor
```

The command should group checks into environment, files, services, optional
Soridormi, and host audio. Service checks may be skipped or reported as
unreachable without failing closed unless the selected mode requires them.

Initial checks:

- Python version;
- Docker and Docker Compose availability;
- generated runtime files;
- `capabilities/soridormi.json` presence and JSON parseability;
- Router, Agent, ASR, TTS, Ollama, and Soridormi reachability when configured;
- audio input and output configuration visibility.

Exit criteria:

- deterministic exit codes distinguish pass, warning, failure, and skipped;
- network/service failures include the failing URL and cause;
- no GPU, microphone, simulator, or hardware evidence is fabricated.

### PR 4 - Capability Manifest Check

Implemented at Level A.

Implement:

```bash
python -m tools.chromie_cli capability check
```

The command should inspect the checked-in manifest and fail closed on unsafe or
model-facing low-level controls.

Validation should cover:

- manifest parseability and expected top-level metadata;
- duplicate capability IDs;
- provenance fields for Soridormi snapshots;
- forbidden low-level motor, joint, actuator, torque, controller-array, or
  `action_14d` style fields;
- feature-gate consistency for executable interaction capabilities;
- clear reporting for unsupported task types that should remain refusals.

Exit criteria:

- Level A tests include safe, malformed, duplicate, and forbidden-field
  manifests;
- output is useful enough for release preflight and code review.

### PR 5 - Evidence Bundle Preflight

Implemented at Level A.

Implement:

```bash
python -m tools.chromie_cli evidence bundle
```

Start with preflight and manifest assembly, not a new evidence authority. The
command should gather existing evidence metadata, current git revision, relevant
configuration summaries, and pointers to retained bundles.

Exit criteria:

- bundle metadata records exact Chromie revision and selected evidence paths;
- automated, simulator, target GPU, physical audio, and hardware evidence are
  labeled separately;
- generated output does not convert automated or dry-run evidence into release
  readiness.

### PR 6 - Trace Schema And View

Implemented at Level A.

Document [Trace Schema](TRACE_SCHEMA.md) and implement:

```bash
python -m tools.chromie_cli trace view
```

The command reads retained local artifacts only. It supports filters for
Orchestrator sessions, InteractionResponse/Skill Runtime interactions,
TaskGraph graph ids, and Skill Runtime trace ids.

Exit criteria:

- the schema documents retained artifact families and stable correlation keys;
- the CLI summarizes JSONL session events and JSON route, interaction,
  execution, TaskGraph, and acceptance-summary artifacts;
- no live-service, simulator, audio, GPU, or hardware evidence claim is created.

## Trace Explainability Follow-up

`trace explain` should be a follow-up milestone after the initial retained
artifact viewer has enough real bundles to harden causal semantics. It needs
stable cross-links for session, interaction, TaskGraph, Skill Runtime,
Soridormi task events, TTS/playback, and fallback causes. Until then, avoid
explanations that imply more certainty than the artifacts retain.

Expected commands:

```bash
python -m tools.chromie_cli trace explain --interaction <interaction_id>
```

The follow-up should produce a human-readable account of what was heard,
routed, proposed, authorized, executed, refused, cancelled, timed out, or
recovered.

## Evidence Level

The developer-usability milestone is primarily Level A. It may run Level B
reachability checks when services are already deployed, but Level B failures
should be reported as environment findings unless the selected mode requires
the service. It must not create Level C or Level D claims without the retained
simulator, audio, GPU, or hardware evidence required by
[Acceptance and Evidence](ACCEPTANCE.md).

## Safety Rules

- Keep stop, cancel, emergency, silence, and unusable-audio paths deterministic.
- Keep physical execution default-off and Soridormi-owned.
- Do not expose low-level robot controls in any manifest or CLI output intended
  for model-facing contracts.
- Prefer clear warnings and skipped checks over hidden fallback behavior.
- Log causes for service and model-provider failures.
- Use generated `.env.runtime`; never instruct users to edit it directly.
