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
person -> Gateway -> GI -> Responsibility / WHAT
                           |-> GA -> canonical Goal continuity
                           `-> Planner fast/deep -> Plan / Activities
                                                 -> Runtime -> Provider
                                                 -> async event -> Evidence
Responsibility + Goal + Situation + Work + Evidence
                           -> CognitiveOpportunity -> Planner
                           -> 0..N Activity changes or none
```

`CognitiveOpportunity` is an ephemeral readiness signal, not a semantic owner.
Callbacks never choose speech or action. New person-authored meaning still uses
Gateway -> Goal Interpretation -> Goal Association when canonical continuity is
needed. Runtime/Evidence transitions already carry exact request/Activity/Goal
provenance and normally re-enter Planner directly.

Goal Association implementation is now internally split without changing that authority: `agent/app/goal_association_contract.py` contains only model-facing DTO/schema/normalization rules, while `GoalAssociationResolver` in `agent/app/goal_association.py` retains inference, continuity decisions, and canonical Goal materialization. The stale `human-child kind` segmentation wording is removed; GA now preserves the owner-approved six-year-old-girl social identity without converting it into a biological-human claim.

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

## Audit convergence after the async backbone

The 2026-08-20 full audit remains useful as an issue inventory, but several findings
were already closed by later source before this checkpoint. This convergence slice keeps
the event/readiness architecture above and removes only still-current contradictions:

- identity truth now distinguishes Chromie's owner-approved six-year-old-girl / family-
  secretary social identity from biological-human claims while preserving truthful robotic
  embodiment when relevant;
- a disabled Attention Review fails open as explicitly unreviewed evidence with zero
  confidence rather than fabricating certainty;
- standalone admitted greeting continuity is one rule: Planner speech may start before GA,
  GA still commits the canonical conversational Goal, and binding does not create a second
  utterance;
- production prompt JSON uses structure-preserving bounded serialization instead of slicing
  serialized JSON mid-object/string;
- remaining phrase/case examples in the Planner first-response truth contract were reduced
  to general grammatical truth-stage, actor, continuation, and provenance rules;
- Conversation State uses only typed `ORCH_CONVERSATION_*` Host settings; retired
  `ORCH_CONTEXT_*` aliases and the second production `from_env()` authority are removed;
- `docs/STATUS.md` is current facts rather than an append-only architecture history; and
- named Charter requirements give the documentation gate mechanical anchors for identity,
  Attention, greeting continuity, speech ownership, one Planner authority, asynchronous
  cognition, and latency.

The audit's proposed Response-Composer/`fast_speech`, structural-benchmark-false-pass,
and speech semantic-ID fixes are not reimplemented here because the uploaded archive had
already removed or corrected those current-path defects. Broad god-object decomposition is
kept as separate structural work, and the 2s/3s latency target remains a live qualification
question rather than a static-source checkbox.

## First Host structural slice

Terminal Evidence re-entry previously kept several distinct mechanical concerns inside the
`VoiceAssistant` composition root and contained one semantic escape hatch: when the original
GI `responsibilities[]` could not be recovered, the callback fabricated a generic
"continue the existing canonical Responsibility" object so Planner would still run. That
made Host callback code an accidental Responsibility author.

Current source extracts pure policy to `orchestrator/runtime/planner_reentry.py`.
It validates current Goal/Plan/request bindings, selects only originating GI
Responsibilities through GA `source_responsibility_refs`, rejects completed-Activity
repetition, and removes exact already-delivered speech deltas. Missing or ambiguous
Responsibility provenance retains Evidence but suppresses this opportunity before model
invocation; the Host no longer fabricates callback meaning.

The module owns no Goal meaning, speech, Planner call, Runtime mutation, or state. Nine
private methods first leave `VoiceAssistant` (`159 -> 150`). The next mechanical slice
moves TTS text segmentation and Goal-list console projection out of the composition root,
lowering it to 142 methods. Observability recording containment lives in `orchestrator/runtime/observability_recording.py` as stateless Host policy and lowers the root to 139 methods; it records existing runtime facts and never changes Goal, Planner, speech, or execution semantics. Fixed-reflex confirmation-token revoke/audit bookkeeping lives in the existing `orchestrator/runtime/confirmation.py` owner, lowering `VoiceAssistant` again to 136 methods. Confirmation meaning remains GA-owned and confirmation wording remains Planner-owned. OS-default audio-device lifecycle lives in `orchestrator/runtime/audio_device_lifecycle.py`, lowering the root to 129 methods while `AudioDeviceManager` still discovers devices and `PlaybackTransport` still owns output I/O. Top-level process teardown now lives in stateless `orchestrator/runtime/shutdown_lifecycle.py`: it reuses `InputTurnLifecycle.shutdown_tasks()`, resolves Playback wait/duck state, closes the actual PlaybackTransport output owner, finalizes Session traces, and closes ASR/HTTP/audio resources. `VoiceAssistant.cleanup()` and its cleanup-only output-close wrapper are removed, lowering the root to 127 methods. Accelerator telemetry scheduling, detached-task tracking, and Session-trace attachment now live with the existing stateless observability policy, lowering the root again to 124 methods. Playback/TTS transport facades are now removed as well: `PlaybackTransport` directly owns stream open/abort, PCM playback, skip queueing, ordered playback, provider synthesis, and the associated session trace spans. Host integration calls the cached transport directly, lowering `VoiceAssistant` to 117 methods without moving speech or interruption semantics. Input/session transport facades are now removed as well: `InputSessionRuntime` owns microphone callback, VAD/ASR queue progression, routed-turn launch/completion, injected/device audio streams, and idle sweeping directly; `VoiceAssistant.run()` and interruption paths obtain that existing runtime explicitly. `InputTurnLifecycle` still owns ASR/turn/reflex task state. This lowers the root to 105 methods without moving Gateway, turn, reflex, or conversation semantics. These are narrow ownership-seam extractions, not new managers or completed Host decomposition.

## Verification

Focused source verification passes before final patch packaging:

- 261 Planner re-entry / detached Evidence / Cognitive Runtime / Situation / interaction
  tests after the structural extraction;
- pure-policy and Host integration coverage for missing Responsibility provenance;
- 205 focused async/runtime/reflex/TTS/observability tests plus 36 subtests after the observability extraction;
- runtime-structure ratchet, repository engineering policy, and test ownership checks.

The final delivery reruns documentation, semantic-authority, configuration, and broader
focused tests on a fresh patch chain; quote those exact results from the patch handoff.

`./scripts/run_tests.sh` starts successfully through repository policy and test
ownership but this sandbox does not contain the pinned Ruff executable, so the
canonical gate stops at the Ruff availability check. No live model, network weather
provider, microphone, audible speaker, MuJoCo, or physical-robot qualification is
claimed by this source patch.

## Resume order

1. Apply patches 1, 2, 3, 4, and 5 in order to the uploaded archive, then run
   `./scripts/run_tests.sh` with pinned test dependencies.
2. Run retained async/general-ability cases on the current model profile.
3. Retain provider-backed information and embodied episodes that exercise follow-up Work,
   sibling concurrency, no fabricated user turn, and no duplicate speech/execution.
4. Keep source/test/target/release evidence claims separate.
