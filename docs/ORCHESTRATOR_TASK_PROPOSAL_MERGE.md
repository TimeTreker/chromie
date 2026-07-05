# Orchestrator Task Proposal Merge

This document records the design direction for making Chromie's Orchestrator a
smart task arbiter rather than a passive executor. It is a plan plus the first
implemented slice. It does not widen physical execution authority.

## Problem

Chromie has several reasoning stages that can understand the same utterance:

- deterministic emergency and interruption filtering;
- quick intent routing;
- deeper reasoning through Agent and deepthinking paths.

The stages can disagree. For example, a user may say:

```text
Look out!
```

A fast semantic stage might misread this as a request to look out of a window.
A deeper stage should be able to notice that the phrase is probably a warning,
cancel or reject the mistaken proposal, hold motion, and explain the correction
to the user.

The unsafe version of the architecture is:

```text
router emits task -> task executes immediately -> deeper stage corrects later
```

That is not acceptable for embodied work. The safer architecture is:

```text
router emits proposal -> orchestrator merges and commits -> committed work executes
```

## Principle

Tasks emitted by routers are proposals. Tasks emitted by the Orchestrator after
merge are executable commitments.

The Orchestrator should behave like a careful adult:

- accept fast safe reflexes such as stop, cancel, or hold;
- allow low-risk provisional feedback such as a short thinking acknowledgement;
- keep physical motion, manipulation, task graphs, and external side effects
  behind a commit gate;
- correct earlier misunderstandings when later evidence is better;
- tell the user what changed without claiming work that did not happen.

## Proposal States

The merge path uses these conceptual states:

```text
proposed -> advisory
proposed -> committed -> running -> completed
proposed -> committed -> running -> failed/refused/timed_out/cancelled
proposed -> not_committed
proposed -> rejected
proposed -> superseded
understood desired ability -> missing_ability
```

Current implementation records `advisory`, `committed`, `not_committed`,
`missing_ability`, `rejected`, and `superseded`. Later-stage corrections can
now be represented through `revised_task_proposals`, which records a
replacement proposal and a schema-validated `superseded` marker for the earlier
proposal.

## Current Implementation Slice

Implemented in `orchestrator/runtime/task_proposals.py`.

The host now builds an internal proposal ledger from:

- route items copied from Router `RouteDecision.routes[]` and
  `RouteDecision.metadata.route_items[]`, which split one utterance into
  separately governed lanes such as immediate speech, memory, deepthought,
  tool, and Skill Runtime work;
- `route_task_proposals` copied from Router
  `RouteDecision.metadata.task_proposals`, when present;
- `route_task_list` copied from Router `RouteDecision.metadata.task_list`;
- non-executable desired ability proposals copied from Router
  `RouteDecision.metadata.desired_abilities` through the shared
  `task_proposals` surface;
- `deepthinking_task_proposals` emitted by the Agent deepthinking path;
- `agent_task_proposals` emitted for final Agent speech and skills;
- `revised_task_proposals` or `task_proposal_revisions` emitted by a merge or
  reconciler stage to replace an earlier proposal;
- final `InteractionResponse.skills`;
- final `InteractionResponse.speech`;
- static `preflight_validation` results for committed skills;
- deepthinking rejected task metadata, when present.

The ledger is attached to `InteractionResponse.metadata.task_proposal_ledger`
inside the Orchestrator runtime before execution. It is an audit surface; it
does not execute anything by itself.

Router now emits shared-schema `task_proposals` alongside the legacy
`task_list`, and mirrors the preferred multi-route split in
`metadata.route_items`. The Orchestrator prefers shared proposals and route-item
metadata, and keeps the legacy list as a fallback during migration. The Agent
deepthinking path also emits shared-schema `deepthinking_task_proposals` for
its speech, skill,
missing-ability, and rejected candidate tasks. The final Agent response now emits shared-schema
`agent_task_proposals` for committed speech and skills, including speech as the
local `chromie.speak` skill. The final ledger is validated through the shared
`shared/chromie_contracts/task_proposal.py` contract before being attached to
metadata. This keeps the wire shape JSON-compatible while making proposal
states, summaries, and preflight annotations common across services.
When low-confidence quick Router proposals are delegated, the Router includes
`quick_router_review_request` and deepthinking can record
`quick_review.decision=accept|revise|supersede`; replaced quick proposals are
represented through `superseded_task_proposals`.

The first commit rule is intentionally conservative:

- Router tasks are recorded as proposals.
- Safe `immediate_speech` chat route items may schedule host fast-first TTS
  when they contain short validated text and `direct_to_tts=true`; this is
  local speech feedback only and cannot claim memory writes, tool results,
  physical completion, or authorization.
- Memory, tool, deepthought, and skill route items remain separate policy lanes.
- Effectful router tasks without a matching `InteractionResponse.skill` become
  `not_committed`.
- A matching `InteractionResponse.skill` marks the router proposal as
  `committed`.
- `InteractionResponse.skills` are commitments that still must pass Skill
  Runtime validation, confirmation, provider availability, timeout, and
  cancellation policy.
- `InteractionResponse.speech` is a committed local speech task.
- Desired abilities with no executable skill are recorded as
  `state=missing_ability`, `proposal_kind=ability`, and optional `ability_id`.
  They are never forwarded to the Skill Runtime.
- Static preflight status is attached to committed skill proposals when the
  host can check registry, provider, schema, availability, confirmation, or
  safety-monitor requirements before execution.
- `revised_task_proposals` metadata records a replacement proposal and, when
  `supersedes_id`/`replaces_id` is present, an automatic `superseded` marker
  for the prior proposal.
- `superseded_task_proposals` metadata can mark a prior proposal as
  `superseded` and record the replacing proposal through `superseded_by`.

This means a quick router can be wrong without moving the robot. A later Agent
or deepthinking path must produce a valid committed skill before any embodied
work reaches the trusted Skill Runtime.

## Static Preflight

Implemented in `orchestrator/runtime/interaction_preflight.py`.

The Orchestrator now attaches `InteractionResponse.metadata.preflight_validation`
before execution. This is a narrow host-side contract audit. It can report:

- `passed`: static contract and provider checks passed;
- `needs_confirmation`: request-bound confirmation is still required;
- `needs_safety_monitor`: a required safety monitor is not active yet;
- `blocked`: the host already knows the skill is unknown, unavailable, has no
  provider, has a version mismatch, or has schema-invalid arguments;
- `deferred`: the host cannot check a Soridormi skill until the catalog is
  loaded.

Preflight deliberately does not decide whether the real world permits the task.
It does not know whether a cup is reachable, a path is clear, or a person is in
the way. Those facts remain the authority of Skill Runtime, Soridormi preview,
provider submit, monitor events, cancellation, and retained execution evidence.

## Target Architecture

The intended architecture is:

```text
ASR text
  -> emergency/reflex proposer
  -> quick intent proposer
  -> deep reconciler
  -> Orchestrator proposal merge
  -> commit gate
  -> Skill Runtime / Soridormi / local speech
  -> execution evidence
  -> conversation and experience state
```

The deep reconciler should receive:

- user ASR text;
- route stage outputs;
- quick intent proposals;
- current conversation and task context;
- capability catalog summaries;
- broad but non-executable desired ability proposals;
- recent execution evidence.

It should emit a corrected `InteractionResponse` or future shared
`TaskProposalSet` that can accept, revise, reject, or supersede earlier
proposals.

## "Look Out" Example

Safer behavior:

```text
Emergency/reflex: propose hold/freeze if supported.
Quick intent: may propose look_at_window, but it remains uncommitted.
Deep reconciler: rejects look_at_window, treats "look out!" as a warning.
Orchestrator: commits hold/no-motion plus speech.
Speech: "Sorry, I misunderstood that as a direction. Thanks for warning me. I will hold still."
```

The key property is that `look_at_window` never executes unless it survives the
commit gate.

## Expert Advice Triage

The outside architecture review is useful, but not every suggestion should be
applied literally. Chromie should keep the parts that strengthen contracts and
diagnostics while preserving the trusted execution boundary.

| Advice | Decision | Rationale |
| --- | --- | --- |
| Use a clearer prompt/context structure. | Adopt. | The deep reconciler should receive layered context: stable identity and policy, session summary, current request, proposal inputs, capability summaries, execution evidence, and output contract. Raw conversation history should not be injected as the normal path. |
| Give the LLM an explicit output contract. | Adopt. | Deep reasoning needs a machine-parseable proposal contract. Speech is a skill/proposal alongside motion, memory, and tool work; it is not a separate privileged lane. |
| Make deepthinking emit both speech and task lists. | Modify. | The model should emit whatever proposals are justified by the request. Sometimes that is only speech, sometimes only a hold/cancel, sometimes a multi-step task set with concise user-facing repair speech. |
| Add capability contract validation before LLM selection. | Modify. | The Orchestrator can validate schemas, policy, provider availability, obvious missing arguments, and known preconditions. It cannot prove real-world feasibility before execution. Embodied feasibility remains a Skill Runtime and Soridormi preview, submit, monitor, and evidence problem. |
| Turn task graph gates on by default for development. | Reject as a default. | Risky execution gates must fail closed. Development profiles may enable simulator-only guarded paths explicitly, but repository defaults should not silently widen physical authority. |
| Disable or simplify LLM response review for latency. | Defer with guardrails. | Review should be measured and used only where it adds safety or truthfulness. Latency-critical paths should prefer deterministic checks, but this is separate from proposal merge semantics. |
| Close the experience journal loop. | Adopt carefully. | Experience should feed future prompts through reviewed summaries or owner-approved rules, not raw logs. The proposal ledger gives a better substrate for summarizing mistakes, corrections, and outcomes. |

This triage turns the review into implementation direction without making the
Orchestrator pretend it can know the real world before the trusted runtime has
looked.

## Implementation Plan

1. Internal proposal ledger. Implemented and automatically verified.
2. Route metadata bridge. Implemented for the structured `/interaction` path:
   the Orchestrator copies Router stage outputs and task list into response
   metadata before runtime execution.
3. Proposal-aware diagnostics. Implemented for experience summaries:
   task-proposal and preflight summaries are retained without leaking raw
   proposal payloads or prompt history. Session-log and trace surfacing remains
   open.
4. Deep reconciler contract. Define a structured output contract that can
   accept, revise, reject, or supersede earlier proposals while producing
   concise speech.
5. Commit gate policy. Promote the current ledger rule into an explicit policy
   module with tests for physical, tool, speech, memory, and interrupt tasks.
6. Correction UX. First narrow slice implemented for warning misreads:
   if a later stage rejects a risky earlier proposal such as a mistaken
   window-gaze interpretation of "Look out!", host truth reconciliation emits
   specific repair speech and keeps the physical proposal uncommitted.
   The ledger also supports `revised_task_proposals` for explicit
   accept/revise/supersede audits. Broader commit policy remains open.
7. Shared contract. Implemented for the ledger schema in
   `shared/chromie_contracts/task_proposal.py`. Router now emits
   shared-schema `task_proposals` alongside legacy `task_list`, and the Agent
   deepthinking path emits shared-schema `deepthinking_task_proposals`.
   Final Agent speech and skills also emit shared-schema
   `agent_task_proposals`, so the ledger no longer needs fallback
   `interaction_response:*` entries when native Agent metadata is present.
8. Context summarization. Partially implemented for deepthinking and its
   spoken-response reviewer: the slow path uses extracted task/session context
   instead of raw transcript turns. The target extractor and prompt-builder
   contract is documented in `docs/MEMORY_EXTRACTION.md`. Quick Router,
   conversation, capability, direct fallback, and deepthinking prompts now have
   the first deterministic extracted-memory path; durable and LLM-assisted
   memory remain open.
9. Preflight validation. Implemented as a non-authoritative validation layer for
   schemas, provider registration, versions, availability, confirmation, and
   safety-monitor requirements. Dynamic world feasibility remains unknown until
   Skill Runtime and Soridormi provide evidence.
10. Experience loop. Implemented for proposal/preflight summaries: mismatches,
    blocked preflights, rejected proposals, and truth reconciliation can create
    owner-reviewable experience updates. They never auto-apply.

## Non-Goals

- Do not let any model authorize its own side effects.
- Do not execute physical tasks merely because a router proposed them.
- Do not prove real-world feasibility in the Orchestrator. Soridormi preview,
  submit, monitor, cancellation, and provider evidence remain the authority for
  embodied execution.
- Do not turn experience logs or raw conversation history into prompt payloads.
  Use reviewed summaries only.

## Verification

The first slice is covered by `tests/test_task_proposals.py`.

Required checks:

```bash
python -m unittest tests.test_task_proposals tests.test_interaction_coordinator
python scripts/check_docs.py
./scripts/run_tests.sh
```
