# Runtime Failure Paths

Status: first failure-path audit implemented; complete broad-handler
classification queued
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

Deep Planner failure materializers always set `execution_allowed=False` on empty
rejected/unavailable Plans and retain the original error and validation feedback.
The existing Runtime adapter recognizes this as silent non-executable containment;
it must not invent response text or replace the original failure with a missing-text
exception. This does not permit silent unmarked or confirmation-gated execution.

## Failure classification

### expected cleanup

Best-effort release of an already-failing resource must not replace the primary
failure. Output-stream stop/close and ASR WebSocket close therefore retain
cleanup containment, but now emit debug diagnostics rather than silently using
`pass`.

Reversible playback ducking maps device abort and restart failures into explicit
`pause_error` and `resume_error` receipt fields. A pause failure keeps future
chunks blocked; a resume failure releases bounded waiters to avoid deadlock and
lets ordered playback retain the resulting transport failure. Neither path may
claim successful silence or resumed delivery.

### defined degradation

Malformed optional or historical context may be omitted only when the caller
still receives a complete typed result. Goal Association snapshots, discourse
referents, stale advisory-route archive items, and historical task-state fields catch
Pydantic validation failures narrowly and record debug or warning diagnostics.
They do not catch arbitrary model, provider, cancellation, or execution errors.

### operational failure

Invalid semantic task operations are state-changing inputs. Both atomic and
non-atomic application validate the complete batch before mutation and raise a
bounded `ValueError` on malformed input. Agent model paths now require their
configured Ollama client through an explicit `RuntimeError` instead of a
production `assert`.

Planner required Work inputs are serialized losslessly. Their accumulated Goal,
interaction, source, dialogue and terminal-evidence context shares the configured
whole-request model budget instead of fixed per-section character quotas. The
transport owns admission, including output reservation and safety margin; SGLang
verifies estimate overflow with its serving tokenizer. True overflow retains
`prompt_budget_exceeded` in `llm_budget` and fails before generation. Independently
bounded owners elsewhere still use `required_json` and retain
`required_context_over_budget` in `prompt_projection`; they never shorten a required
payload. Fast/Deep failures remain non-retryable and authorize no execution.
Canonical Fast uses `contract_failure` containment, so Host cannot invoke Deep to
repair a technical failure. Deep returns an empty rejected Plan, without invented
clarification speech. Streaming returns a typed `before_commit` failure.

Fast's native argument contract requires a source span for a required, unbound
string enum when none of its choices could be a literal copy from an owning
Responsibility outcome. This exposes the existing Host provenance requirement
before generation without choosing an enum value or translating user language.
Literal/case-only copies, typed bindings, declared realizations and trusted target
or verified-memory references retain their existing paths. Host still validates
the selected span against the immutable input and its owning Responsibility.

This includes rejected Fast Evidence re-entry DTOs, semantic-validation failures,
and authoritative-grounding mismatches: an exception is not a model-authored
request for depth. Keep the original failure and zero new Work; only a valid
semantic delegation can invoke Deep. Compact re-entry projects the existing
satisfaction bands from their shared contract into its primary prompt and full
Schema, and exposes actual escalation/no-escalation alternatives to the decoder.
Fractional score bounds stay in full Schema/DTO validation because the deployed
native float-range compiler rejects some valid interior values. Native acceptance
therefore remains insufficient evidence of score/status consistency.

Goal Association may retain a terminal Goal as related historical context, but
only open candidates may be superseded. Both the compact Schema (including its
per-item copies) and deterministic validation enforce that existing lifecycle
rule; related and superseded targets must remain disjoint.

Activation's bounded state retains acquisition step purpose and the Planner's
satisfaction/unmet requirements alongside provider completion. A completed lookup
is not proof of completed information delivery. Its native request uses the same
compact JSON formatting as Planner to avoid an unbounded whitespace loop.
Fast's verified-memory argument validator accepts an evidence/tool/material tuple
only from one exact trusted index entry and rejects conflicting current bindings;
opaque evidence IDs need no user-token citation. Runtime independently checks
freshness and material bindings when retrieving the result.
The corresponding Fast Activity Schema also excludes evidence_id, tool_id and
material_args from UserTurn argument_sources: it must not force a model to invent
user-token provenance for a tuple that the trusted memory index owns.
The memory provider declares acquisition purpose through the existing resource
contract, so retrieval completion cannot be mistaken for delivered information.
Activation inherits the active Fast model timeout unless explicitly overridden;
the former independent 10-second default could expire while concurrent SC used
the same serving model. Host and provider deadlines remain bounded; no retry or
additional model call is introduced.
Fast's bound-argument comparison uses the same material-value equivalence as
canonical Goal grounding. A capitalization difference cannot be accepted by one
boundary and rejected by the other; incompatible values remain rejected.

SC uses the existing Context Assembly projection before inference: current leaf
owners replace duplicate Conversation aggregate and retained Host task history.
Situation-specific disclosure-safe relational memory is selected after that
projection. The complete retained request still passes ordinary transport budget
admission; no required fact is shortened to fit a local section quota.

SC re-entry is still part of the admitted user turn. A supplied communication Need
that is already fulfilled by an exact same-turn act requires that act's unchanged
identity and text as an explicit coverage receipt; silence cannot stand in for
that receipt. Runtime reuses the existing delivery and qualifies completion from
playback evidence. Conversation history enriches the same delivered Activity
instead of appending a second utterance. Live text scenarios can require final
created-Goal satisfaction, independently of successful speech or HTTP responses.

An AFTER dependency on completed source Work may be discharged only by Planner
envelope materialization with matching source Plan identity/fingerprint, scoped
Goal/step ownership and retained terminal observation/hash. The authored relation
and completion proof remain in communication Need facts. Unknown references,
BEFORE dependencies and references to new Work are not discharged; ordinary
CanonicalPlan/Runtime ordering checks still reject invalid dependencies.

UMI's short-turn source-spelling constraints share one `SourceBackedBindingString`
definition for location, duration and speed. The original character-slice values,
40-character applicability bound and context-dependent fallback remain unchanged;
references reduce repeated wire data without selecting meaning or relaxing Host
provenance checks. Primary and source-based Deep use the same definition. Native
Schema bytes are not necessarily model input tokens or inference latency savings.

Canonical Fast uses the same request-local compact-JSON formatting as streaming
Fast and Deep to prevent unbounded syntactic whitespace. No string postprocessing
or shared model setting changes occur. Cross-field Work restrictions remain in
the authoritative Schema and DTO/Host validators: native decoder acceptance alone
is not proof of Schema, DTO, Host or semantic correctness. Bounds shared by every
valid Fast Work assignment are also exposed in native-visible fields; a
response-only re-entry cannot emit completed Work again. Advance branches preserve
UMI timing relations and provider compatibility before generation. Provider-required
vocal sources may bind only the qualified vocal provider with the exact UMI-authored
supported mode; unavailable/empty catalogs cannot substitute another provider.
Streaming decision-state alternatives also expose existing execution/delegation
invariants: execute/respond/mixed have complete accounting, normal outcomes have
no continuation, and escalation has one Deep continuation and no new Capability
commitment. Already-committed Work and later Evidence-triggered re-entry are
unchanged; this does not restrict Deep to execution failures. Full conditional
Schema and DTO/Host validation remain independent. Expanding whole
Fast Work assignments into native branches was rejected after production-schema
compiler/contrast failures; the retained projection does not select an assignment
or establish semantic qualification of general Work.

SC's existing decision states are also explicit native alternatives: communicate
contains acts, silence contains no acts and keeps needs pending, and deliberation
commits neither coverage nor Memory. Host independently requires every covered
Need to have an exact addressed verbal act. This mechanical Schema rule does not
select speech or reinterpret a pending Need as fulfilled. Native generation presents
Need accounting, disposition and Activities before the explanatory reason and uses compact
JSON; this preserves DTO meaning and multi-act outputs. Question-kind/phase branches
match existing Host requirements. Outside Situation ingress, both Memory proposal
arrays are constrained empty, matching Host authority. The complete raw JSON Schema
is checked before DTO/Host, including references and native union alternatives.

SC presents the unchanged delivery ledger before larger context without mutating
the retained request/digest. If prior act identities exist, native alternatives
offer fresh request-scoped IDs or reuse an existing ID only with its original
normalized words. Runtime still owns atomic playback reuse and immutable identity
validation. Fresh identity exclusions are also expressed as an equivalent finite-prefix
regular expression because the serving decoder ignores JSON Schema `not` and does
not support negative lookahead. New IDs use JSON-safe text without quotes,
backslashes or control characters: the native pattern compiler otherwise lets
wildcards cross encoded JSON string boundaries. Retained IDs remain reusable
through exact constants. Neither constraint limits expression cardinality.
Reusing the same existing ID and words is not new playback; an explicitly
distinct repeat is a separate act. Duplicate IDs within one result, changed words
under an old ID, or output truncation fail closed. None permits a partial act,
forced single act, semantic retry, or second model repair.

SC's primary contract also distinguishes Need accounting from new playback. A
covered Need must cite a returned verbal act even when that exact act is already
pending or delivered in the current turn. Returning its unchanged identity and
words lets Runtime reuse playback and await its completion; a nonverbal gesture
or silence cannot stand in for this coverage witness. An acknowledgement alone
does not satisfy an answer Need. Silence retains pending Need accounting.
Playback-qualified dialogue history merges repeated receipts for the exact same
session, turn and communicative Activity identity. Final Need/Evidence metadata
updates the existing delivered record rather than adding another utterance; the
console therefore publishes it once. Different identities or turns can still
repeat identical words, and missing identity proof never triggers text deduplication.

Independent SC delivery joins both the Runtime terminal result and playback
completion. A failed expression/provider result or unplayed SC utterance is
retained as a session social-task failure, even when requested Work succeeded.
Conversely, GA/Planner failure stops uncommitted Work without cancelling the same
turn's admitted independent SC interaction. The coordinator joins that interaction's
delivery and retains the original Work failure; an SC failure is secondary diagnostic
evidence. Outer deadline or explicit interruption still cancels delivery. Host keeps
the exact delivered SC response without redispatch or an appended generic apology,
and final session reporting remains failed even when its speech succeeded.
The finalized workflow reports `failed`, not successful interaction completion.
`session_done` still denotes a terminal session and a complete Runtime Trace still
denotes a sealed trace; neither alone proves successful delivery. Optional failure
does not replay Work, rewrite speech, or invoke a model repair.

The same containment applies to result, provider, time and Situation re-entry:
returned technical failures and thrown call errors are retained as failed workflow
stages before adaptation or commitment. A Fast technical failure cannot invoke
Deep. Genuine semantic escalation still receives its one designated depth pass.
Acceptance inspects these retained failed stages even when the initial turn's
detached dispatch was already applied; it stops the cohort and marks coverage
incomplete. Redacted error prose is not interpreted as semantic evidence.
Streaming renders inside its guarded boundary and returns a typed `before_commit`
failure. These failures do not claim a truncated model response: no model was
called, and no partial Plan, Goal outcome or presentation is committed.

### evidence failure

`PlannerDTOContractError` preserves the existing `structured_output_validation` /
`model_contract` classification through Fast/Deep fallback materialization using
the runtime's typed exception metadata protocol. It remains non-retryable at that
boundary, with `architecture_attribution=not_evaluated`: locating a rejected DTO
does not identify whether its cause is Schema, context or model inference. Unknown
exceptions retain their unclassified failure rather than being relabeled by text.

A corrupt Runtime Trace checkpoint is archived under `corrupt/` and emits a
warning with the source, destination, error type, and bounded message. Episode
event persistence remains best-effort for realtime safety, but evidence loss is
now logged. Invalid stored recovery Plans are rejected with a warning rather
than disappearing silently.

### impossible invariant

Required invariants no longer depend on `assert`, which Python removes under
`-O`. Explicit exceptions now protect:

- WorkDAG invocation outcomes;
- confirmation replacement and approved-response binding;
- semantic create operations and pending-task metadata;
- provider output-schema object validation;
- Agent model-client availability;
- generated runtime-environment manifest structure.

## Audited boundaries

The maintained audit covers:

- `agent/app/` model, Goal Association, WorkDAG, and compatibility schema paths;
- `orchestrator/` interaction, conversation state, cancellation, recovery,
  episode, audio cleanup, and execution joins;
- `shared/chromie_runtime/` Runtime Trace evidence;
- `shared/chromie_contracts/` executable schema validation;
- `asr/` and maintained `tts/` optional protocol/telemetry parsing;
- `scripts/generate_runtime_env.py`, which is part of every supported launch.

Broad-handler counts are intentionally not copied into this document. Source
counts change with implementation and are not a reviewed classification. The
dependency-light repository checker rejects trivially silent broad handlers,
while each changed handler must demonstrate one explicit outcome:

- narrow and re-raise;
- map to a typed failure;
- fail closed at a trust boundary; or
- contain expected cleanup without replacing the primary failure, while
  recording a bounded diagnostic.

The active structural-simplification work in the
[Roadmap](../ROADMAP.md#structural-simplification) owns further narrowing. Stable
enforcement remains centralized in
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

The first audit established the classification above; it did not prove that
every broad catch is permanently optimal. Future changes to model, provider,
execution, cancellation, state, or evidence paths must narrow or type the
failure where possible. Expected cleanup may remain contained only when it
cannot replace the primary failure and remains diagnosable.
