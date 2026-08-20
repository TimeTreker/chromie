# Capability Result Evidence Re-entry

## Purpose

A Capability result is trusted state input for an existing Responsibility, not a
new user request and not user-facing wording. Runtime first reports **what
happened**. The Host validates immutable request/Activity/Goal correlation and
schema/provenance, then materializes bounded terminal Evidence describing **what
is true**. If that transition is relevant to an open Responsibility, it creates
one ephemeral `CognitiveOpportunity` and reactivates Planner with the current
Responsibility, canonical Goal, Situation, actual Work, and Evidence.

A callback therefore never means “speak now.” Planner may answer, author genuinely
new follow-up Work, clarify, refuse, wait, or produce no new Activity. Newly planned
Work returns to the same asynchronous Trusted Capability Runtime and may create a
later independent opportunity when its own state materially changes.

The maintained flow is:

```text
Planner Capability Activity
  -> Trusted Capability Runtime submission
  -> Provider executes asynchronously
  -> correlated Runtime lifecycle event                 # what happened
  -> Host validates request / Activity / Goal / schema
  -> trusted terminal Evidence                          # what is true
  -> bounded current state:
       Responsibility + Goal + Situation + Work + Evidence
  -> CognitiveOpportunity                               # should cognition reconsider now?
  -> Planner fast pass / deep pass if HOW warrants it
       -> 0..N new Activity changes
       -> or no new Activity
  -> Runtime validates/applies any new Work asynchronously
```

There is no separate result-semantic or response-authoring stage between Planner and
Runtime. Result contents cannot infer their own Goal from provider fields, text
similarity, location, or recency. Missing immutable Goal provenance fails closed.
Goal Association is not rerun merely because a provider completed: the authorized
request already carries the exact Goal provenance. New person-authored meaning still
enters Gateway -> Goal Interpretation -> Goal Association through the ordinary turn path.

## Ownership

The Runtime/Host owns:

- correlated lifecycle events for accepted/running/progress/terminal state;
- complete result retention, schema/digest and provider-identity validation;
- exact request/Activity/Goal correlation;
- binding Evidence only to Goal IDs carried by the authorized request;
- bounded current Work/Situation projections supplied to Planner;
- duplicate-terminal-event, stale-version, cancellation and supersession rejection;
- mechanical validation and authorization of any Planner-authored Activity delta.

Planner owns:

- deciding what the new trusted state means for the still-open Responsibility;
- selecting relevant facts while preserving Evidence scope and uncertainty;
- deciding response, follow-up Work, reuse/cancellation/replacement, clarification,
  waiting, or no new Activity;
- exact natural wording of any Communicative Activity;
- carrying exact Goal and Evidence provenance into the next Plan.

Planner fast/deep are cognition depths of this same authority. The deep pass is
used only for genuinely complex HOW; ordinary terminal Evidence does not create a
second semantic owner or an automatic deep-thinking stage.

`CognitiveOpportunity` owns none of these decisions. It is only a bounded readiness
carrier for a meaningful trusted state transition. Heartbeats, routine progress ticks,
audio chunks, and queue-size churn do not justify Planner invocation merely because
they are events.

## Contract

`shared/chromie_contracts/tool_result.py` retains execution/result contracts and
`ToolResultEvidence`. `CapabilityRuntimeEvent` remains lifecycle observation rather
than Evidence. `ExecutionEvidence`/`ToolResultEvidence` is admitted only after the
Host validates the immutable execution join.

The Planner endpoint receives Host-bound terminal Evidence together with the existing
canonical Goal set and current bounded state. Re-entry may not widen the supplied Goal
set. A Planner step that exactly repeats the Capability/arguments/Goal ownership of the
terminal request that just completed is rejected; reactivation is not permission to
repeat history.

Post-evidence factual speech must use `truth_stage=post_evidence` and cite exact admitted
Evidence. Pre-evidence acknowledgements cite no terminal Evidence and cannot claim a
result. If Planner authors new Capability Work, ordinary Capability schemas,
authorization, confirmation, safety, privacy, resource and concurrency contracts still
apply. An internal opportunity is never user confirmation.

## Failure behavior

- Missing, stale, mismatched, provider-identity-invalid, or schema-invalid result data is
  not promoted to successful factual Evidence.
- Unknown Goal IDs or a Goal-set mismatch fail closed; result contents never guess
  ownership.
- Planner output that widens Goals or repeats the just-completed Activity is rejected.
- Confirmation-requiring new Work is not auto-confirmed by an asynchronous internal
  event.
- Once Planner has consumed one terminal Evidence item, aggregate closure must not run a
  second semantic response/planning pass over the same Evidence merely because sibling
  Work later completes. A later failure or new terminal result is a new transition with
  its own Evidence/opportunity.
- Re-entry failure produces no speculative incremental speech. Retained terminal truth
  remains available for diagnostics and a later authorized state transition.
