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
exact affected canonical Goal subset and current bounded state. Re-entry may not widen
the supplied Goal set. Before invocation the Host mechanically removes excluded sibling
Responsibilities, Goal-Association rows, source-Plan steps/outcomes, and already-consumed
terminal Evidence from the prompt projection; the original user text remains context,
not authority to narrate an excluded sibling effect. Re-entry must reuse the originating
Goal-Interpretation `responsibilities[]` and the
Goal-Association `source_responsibility_refs` that bind those Responsibilities to the
affected Goals. If that immutable Responsibility provenance is missing, malformed, or
ambiguous, the Host retains the terminal Evidence but does not fabricate a callback
Responsibility and does not invoke Planner for that transition.

The mechanical policy for this boundary lives in
`orchestrator/runtime/planner_reentry.py`. It validates current Goal/Plan/request
correlation, selects only supplied Responsibility provenance, rejects exact repetition
of the terminal Activity, projects the current per-Goal execution status (including
unresolved sibling steps) from exact Plan/Evidence bindings, and suppresses
already-delivered exact speech deltas. These are pure Host checks over supplied truth;
the module does not interpret Goal meaning, author speech, invoke Planner, or mutate
Runtime. Both incremental and aggregate result re-entry supply this bounded
`trusted_execution_outcome`; the historical source Plan proves requested semantics and
arguments but never substitutes for current execution status.

A Planner step that exactly repeats the Capability/arguments/Goal ownership of the
terminal request that just completed is rejected; reactivation is not permission to
repeat history.

Post-evidence factual speech must use `truth_stage=post_evidence` and cite exact admitted
Evidence. Pre-evidence acknowledgements cite no terminal Evidence and cannot claim a
result. If Planner authors new Capability Work, ordinary Capability schemas,
authorization, confirmation, safety, privacy, resource and concurrency contracts still
apply. An internal opportunity is never user confirmation.

The re-entry tries Fast Planner first and may use the existing HOW escalation to Deep
Planner. The terminal response candidate from either tier is accepted only after the
same Planner-owned immutable truth qualification checks Evidence scope, epistemic
strength, and execution status. In particular, a probability strictly between 0% and
100% cannot support categorical “will” or “will not” wording. Qualification rejection
does not authorize Host rewriting and fails closed with no speculative speech. An exact
past-tense claim for the scoped source-Plan effect is execution-consistent only when the
trusted outcome marks that Goal complete and any required completion qualification is
established; source-Plan `execute` disposition alone is never current-status evidence.
The qualification DTO is internally closed: `accept` requires every violation flag to
be false, while `reject` requires at least one specific violation flag to be true. The
six required model-authored flags are the semantic judgments; trusted code mechanically
projects the required `decision` field from that complete vector when a provider emits
the opposite redundant enum. It never supplies a missing flag or makes a truth judgment.
This
prevents an ungrounded generic rejection from masquerading as a completed audit without
granting the Host authority to interpret or rewrite Planner language. Every flag and the
decision are required in model output; Python defaults may not silently complete a
partial certificate. The provider-facing decoder grammar is deliberately a flat object
with those seven required fields; the decision/flag consistency rule and redundant
aggregate projection are enforced by the authoritative typed DTO after decoding. This
avoids provider-specific composition-branch
decoding that can omit required sibling fields without weakening or locally repairing the
certificate. The auditor receives only the source step/argument/Goal projection,
not historical Plan disposition, selected skills, or other planning state. Execution
status means whether Chromie/provider performed that source step; tense inside an
Evidence-owned world proposition (for example whether forecast rain will happen) is
audited against Evidence and epistemic strength, not against lookup completion.

## Failure behavior

- Missing, stale, mismatched, provider-identity-invalid, or schema-invalid result data is
  not promoted to successful factual Evidence.
- Unknown Goal IDs or a Goal-set mismatch fail closed; result contents never guess
  ownership.
- Missing or ambiguous originating GI Responsibility provenance fails closed for this
  cognitive opportunity. The terminal Evidence remains historical truth, but the Host
  does not synthesize a replacement Responsibility merely to obtain a Planner response.
- Planner output that widens Goals or repeats the just-completed Activity is rejected.
- Confirmation-requiring new Work is not auto-confirmed by an asynchronous internal
  event.
- When one originating interaction owns multiple Capability requests, Runtime publishes
  and correlates every terminal event immediately. Each terminal sibling may create an
  exact scoped Planner re-entry, but that transaction receives only its bound GI
  Responsibilities, Goals, source-Plan steps, and Evidence; the retained originating
  UserTurnEnvelope is not replayed because it can contain excluded sibling semantics.
  This preserves incremental follow-up Work without granting authority to narrate a
  still-running sibling.
- Once Planner has consumed one terminal Evidence item, aggregate closure must not run a
  second semantic response/planning pass over the same Evidence merely because sibling
  Work later completes. If aggregate closure still has unconsumed Evidence, its Planner
  scope and execution-truth projection contain only those unconsumed items and their
  Goals. A later failure or new terminal result is a new transition with its own
  Evidence/opportunity.
- Re-entry failure produces no speculative incremental speech. Retained terminal truth
  remains available for diagnostics and a later authorized state transition.
