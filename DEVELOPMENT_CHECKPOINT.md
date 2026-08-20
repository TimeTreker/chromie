# Chromie Development Checkpoint

Status: current resume point; incomplete development snapshot
Updated: 2026-08-21
Patch baseline: user-supplied `chromie_20260821.zip`. The archive contains no
trusted `.git` history, so this checkpoint does not invent a commit SHA.

## Read first

Canonical owners remain [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), and
[Acceptance](docs/ACCEPTANCE.md). Source and executable evidence win over old
milestone prose.

Current focus: **Goal-driven single semantic authority** with event-driven,
readiness-driven continuation and one Planner authority.

## Current architecture

Four existing truth owners cooperate without adding another manager or store:

1. Runtime/Provider events report **what happened**.
2. Validated Evidence records **what is true**.
3. Responsibility/Goal state records **what remains owed**.
4. Planner decides **what to do now**, including no new Activity.

```text
person input -> Gateway -> Goal Interpretation -> Responsibility / WHAT
                                      |                   |
                                      |                   +-> Goal Association -> Goal continuity
                                      +-> Planner fast/deep passes -> Plan / Activities
                                                                  |
                                                                  v
                                                     Trusted Capability Runtime
                                                                  |
                                                               Provider
                                                                  |
                                                     async Runtime event
                                                                  |
                                       Host correlation -> trusted Evidence
                                                                  |
                    Responsibility + Goal + Situation + Work + Evidence
                                                                  |
                                                     CognitiveOpportunity
                                                                  |
                                                       Planner re-entry
                                                                  |
                                                 0..N Activity changes or none
```

`CognitiveOpportunity` is an ephemeral readiness signal, not a semantic owner.
Callbacks never choose speech or action. New person-authored meaning still uses
Gateway -> Goal Interpretation -> Goal Association when canonical continuity is
needed. Runtime/Evidence transitions already carry exact request/Activity/Goal
provenance and normally re-enter Planner directly.

Planner fast/deep are cognition depths of the same HOW authority. Comparing a
changed Goal with queued/running/completed Work is a Planner operation, not a
mandatory `Work Reconciliation` stage. The model-facing bounded Work projection is
`existing_work_activities`.

## Source closure in this patch

The uploaded archive already had asynchronous `CapabilityRuntimeEvent`, incremental
terminal `ExecutionEvidence`, detached result consumers, and `CognitiveOpportunity`.
The remaining defect was downstream: terminal Evidence re-entry hid executable
Capabilities in Planner and Host accepted only a response-only zero-step Plan.
Therefore weather/body/tool callbacks could produce a sentence but could not legally
make genuinely new Work ready.

Current source now:

- keeps the executable Capability catalog available on terminal Evidence re-entry;
- reconstructs bounded Situation/current Work plus original Responsibility/Goal
  provenance for Planner;
- lets Planner answer, author genuinely new follow-up Work, clarify/wait, or emit no
  new Activity;
- dispatches new Work through the same detached Trusted Capability Runtime so its
  later terminal transition can create another opportunity;
- rejects exact repetition of the Capability/arguments/Goal ownership that just
  completed;
- never treats an internal opportunity as confirmation for confirmation-requiring
  Work; and
- marks incrementally consumed Evidence so aggregate closure does not plan or speak
  from the same terminal transition again.

The runtime model lock is also resynchronized with the maintained hardware profiles;
the uploaded archive had a stale `agent_models` list that made the documentation gate
fail before this patch.

## Verification

Focused source verification passes:

- 189 Planner / async re-entry / Cognitive Runtime tests;
- 191 broader Runtime / outcome / cancellation / Conversation / Reflection tests,
  plus 20 subtests;
- repository engineering policy;
- semantic-authority audit.

`./scripts/run_tests.sh` starts successfully through repository policy and test
ownership but this sandbox does not contain the pinned Ruff executable, so the
canonical gate stops at the Ruff availability check. No live model, network weather
provider, microphone, audible speaker, MuJoCo, or physical-robot qualification is
claimed by this source patch.

## Resume order

1. Apply this patch to the exact uploaded archive baseline and run
   `./scripts/run_tests.sh` in the normal development environment with pinned test
   dependencies installed.
2. Run the retained async/general-ability cases with the current model profile.
3. Verify a real information lookup whose first terminal Evidence can either answer
   or schedule a second justified lookup without waiting for unrelated sibling Work.
4. Verify an embodied sequence where terminal body/provider Evidence can make the
   next Activity ready without fabricating a user turn.
5. Inspect delivered speech to ensure one Evidence transition creates at most one
   semantic response decision and never repeats the completed Activity.
6. Keep source/test/target/release evidence claims separate.
