# Capability Result Evidence Re-entry

## Purpose

A Capability result is trusted evidence for an existing responsibility, not a
new user request and not user-facing wording. The Host retains the complete
schema-validated result, binds it to the immutable execution request and exact
canonical Goal set, then reactivates Fast Planner with a bounded Goal/Evidence
snapshot. Fast Planner decides whether to answer, follow up, retry through a
new authorized Plan, or remain silent.

The maintained flow is:

```text
Planner Capability Activity
  -> Trusted Capability Runtime terminal event
  -> Host validates request/result correlation and schema
  -> Host binds Evidence to the request's exact Goal IDs
  -> Host updates Goal/task state
  -> Fast Planner Evidence re-entry
  -> Planner-owned post-evidence Communicative Activity or no activity
  -> Host truth/provenance validation
  -> ordered TTS realization
```

There is no separate Tool Result Interpreter and no Response Composer. The
result cannot infer its Goal from provider fields, text similarity, location,
or recency. Missing immutable Goal provenance fails closed.

## Ownership

The Host owns:

- complete result retention, schema and digest validation;
- exact request/result correlation;
- binding Evidence only to Goal IDs carried by the authorized request;
- Goal/task-state transitions and a bounded, versioned re-entry snapshot;
- mechanical validation that post-evidence speech cites admitted Evidence;
- cancellation, timeout, duplicate-terminal-event, and stale-version handling.

Fast Planner owns:

- interpreting what admitted Evidence means for the existing Goal;
- selecting relevant facts and calibrated uncertainty;
- deciding answer, follow-up, new Plan, or silence;
- exact natural wording of any Communicative Activity;
- carrying the exact Goal and Evidence references used by that activity.

Deep Planner is used only when the re-entry creates genuinely complex HOW work;
ordinary result understanding does not add another model stage.

## Contract

`shared/chromie_contracts/tool_result.py` retains execution/result contracts and
`ToolResultEvidence`, the bounded immutable observation containing execution,
Capability, Goal provenance, status, payload, and digest. The existing
`POST /fast-plan` endpoint accepts Host-bound terminal Evidence in its bounded
context. A valid re-entry may not widen the supplied Goal set or schedule a
duplicate execution step.

The Planner's post-evidence Communicative Activity must use
`truth_stage=post_evidence` and cite at least one exact `evidence_ref`.
Pre-evidence acknowledgements cite no Evidence and cannot claim a result.

## Failure behavior

- Missing, stale, mismatched, or schema-invalid results never enter Planner
  re-entry as available Evidence.
- Unknown Goal IDs or a Goal-set mismatch fail closed; result contents are never
  used to guess ownership.
- Planner output that widens Goals, re-executes the completed request, omits
  Evidence references, or claims unsupported facts is rejected.
- Re-entry failure produces no speculative incremental speech. The retained
  terminal result remains available for diagnostics and a later authorized
  retry.

