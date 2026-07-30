# Runtime Failure Paths

Status: implemented and automatically verified
Scope: maintained Agent, Orchestrator, shared Runtime/contract, audio-service,
and generated-runtime-environment boundaries

## Purpose

This document records the failure-path audit completed under
`Issue: Make Runtime Failure Paths Explicit`.

The governing rule is:

> Expected cleanup may degrade quietly at debug level. Model, provider,
> execution, cancellation, state, and evidence failures must return typed
> failure evidence, fail closed, or remain operationally visible.

This Issue does not convert every broad catch into an error log. It classifies
why a boundary catches broadly and changes only handlers that were silent,
ambiguous, or dependent on `assert` for a required invariant.

## Failure classification

### expected cleanup

Best-effort release of an already-failing resource must not replace the primary
failure. Output-stream stop/close and ASR WebSocket close therefore retain
cleanup containment, but now emit debug diagnostics rather than silently using
`pass`.

### defined degradation

Malformed optional or historical context may be omitted only when the caller
still receives a complete typed result. Goal Association snapshots, discourse
referents, compatibility route items, and legacy task-state fields now catch
Pydantic validation failures narrowly and record debug or warning diagnostics.
They do not catch arbitrary model, provider, cancellation, or execution errors.

### operational failure

Invalid semantic task operations are state-changing inputs. Both atomic and
non-atomic application validate the complete batch before mutation and raise a
bounded `ValueError` on malformed input. Agent model paths now require their
configured Ollama client through an explicit `RuntimeError` instead of a
production `assert`.

### evidence failure

A corrupt Runtime Trace checkpoint is archived under `corrupt/` and emits a
warning with the source, destination, error type, and bounded message. Episode
event persistence remains best-effort for realtime safety, but evidence loss is
now logged. Invalid stored recovery Plans are rejected with a warning rather
than disappearing silently.

### impossible invariant

Required invariants no longer depend on `assert`, which Python removes under
`-O`. Explicit exceptions now protect:

- TaskGraph invocation outcomes;
- confirmation replacement and approved-response binding;
- semantic create operations and pending-task metadata;
- provider output-schema object validation;
- Agent model-client availability;
- generated runtime-environment manifest structure.

## Audited boundaries

The audit covered:

- `agent/app/` model, Goal Association, TaskGraph, and compatibility schema paths;
- `orchestrator/` interaction, conversation state, cancellation, recovery,
  episode, audio cleanup, and execution joins;
- `shared/chromie_runtime/` Runtime Trace evidence;
- `shared/chromie_contracts/` executable schema validation;
- `asr/` and maintained `tts/` optional protocol/telemetry parsing;
- `scripts/generate_runtime_env.py`, which is part of every supported launch.

Remaining broad handlers are intentional boundaries that already re-raise,
return typed failure results, or log a defined degradation. Stable enforcement is
now centralized in the dependency-light checker documented by
[Repository Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md).

## Automatic evidence

Focused tests verify:

- no `assert` statements remain in maintained runtime Python or generated-env
  startup code;
- missing Agent model clients fail through an explicit exception;
- malformed non-atomic semantic-operation batches fail before state mutation;
- corrupt Runtime Trace checkpoints are archived and warned;
- this classification document remains linked from documentation governance.

Automatic verification does not prove live provider, microphone, speaker,
Soridormi, or physical-robot behavior. Those remain separate target-evidence
tracks.

## Post-evidence narrowing audit

The classification above records the completed first audit, not proof that every
remaining broad catch is permanently optimal. The current archive contains 142
`except Exception` handlers across `orchestrator/`, `agent/`, and `shared/`. After
the source-bound runtime baseline closes, each handler must retain an explicit
reviewed classification and regression boundary. Model, provider, execution,
cancellation, state, and evidence paths take priority; expected cleanup may stay
contained when it cannot replace the primary failure.
