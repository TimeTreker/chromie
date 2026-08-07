# Chromie Current Status

Status: current implementation and evidence authority

Chromie remains a development project. The maintained direction is a
**Goal-driven single semantic authority**: the Cognitive Gateway owns ingress,
protective reflexes, and attention admission; the Goal-driven Cognitive Core
owns ordinary meaning, goals, planning, response composition, and outcome
reconciliation. Trusted Host and provider boundaries authorize effects.

## Current source state

| Area | Implementation | Automatic verification | Target validation | Release readiness |
|---|---|---|---|---|
| Core interpretation | Non-empty turns that cannot be interpreted now return a typed `interpretation_unavailable` outcome. They are not reassigned to chat or deep thought. | Contract, endpoint, fallback, behavior-scenario, and capability-routing tests cover unavailable and empty-input paths. | A live deployed Core still needs current model/GPU evidence. | Development only. |
| Capability repair | Semantic repair can return strict ordered action proposals only for `robot_action`; every capability and argument remains subject to catalog and policy validation. | Schema, prompt, scenario, and end-to-end routing tests cover compound nod/blink repair and rejection outside the action lane. | Live-model distribution and physical execution remain target evidence. | Development only. |
| Semantic authority | Maintained profiles include memory in Goal-driven apply lanes. A disabled or unsupported mapped lane fails closed and cannot re-enter the legacy planner. | Semantic-authority audit, profile configuration, Orchestrator, and behavior tests cover allowlisted and excluded lanes. | Retained live service and simulator evidence must be refreshed for the patched source. | Development only. |
| Control-plane smoke | The smoke test builds an immutable Gateway/Core request and validates the current Core and Fast Planner contracts. It no longer uses the retired flat interpretation payload or ordinary `/run` planning. | Builder tests and shell syntax checks are source-verifiable. | Requires a running Agent service and configured model. | Development only. |
| Source identity | Evidence metadata uses the Git commit in a checkout or a deterministic SHA-256 source-tree identity in an archive. | Archive and checkout forms are covered by unit tests. | Runtime provenance still requires resolved image and model digests. | Development only. |
| Canonical verification | Repository, ownership, static-analysis, configuration, structure, documentation, benchmark, unit, and retained legacy checks are wired through `scripts/run_tests.sh`. GitHub Actions are pinned by immutable SHA. | The local audit environment verifies all dependency-available gates; unavailable pinned analyzers must remain reported as unavailable rather than passed. | CI and target profiles must be rerun from the final source revision. | Development only. |
| Documentation surface | Historical audits, handoffs, proposal plans, implementation plans, and duplicate registries identified by the audit have been removed. Durable rules now live in the Charter, architecture, policies, status, roadmap, API, and component guides. | Local-link, index, ownership, terminology, and surface-ratchet checks enforce the reduced tree. | Not applicable. | Maintained development documentation. |
| Reversible barge-in | VAD speech start now ducks the exact playback generation without cognitive cancellation. Likely echo/noise resumes the next unplayed chunk; confirmed external speech closes the ducked stream before output-only invalidation, then routes a new session for semantic scope. Echo comparison is order-aware so a short replay is not diluted by the rest of a long response. | Focused duck/echo/device/timeout regressions, the `deterministic_safety_controls` general-ability class, runtime exception classifications, and the canonical gate cover source behavior. The focused voice runner replays retained output PCM and enforces 250 ms duck/silence budgets, clean resume completion, distinct Gateway receipts, and no stale or duplicate output. | **Target validated for generated-speech synthetic input** on clean Chromie `94718ab` in `.chromie/acceptance/voice/issue-5-94718ab-clean`: `barge-in-echo` passed 6/6 and `barge-in` passed 7/7; VAD-start-to-duck was 0.0 ms, confirmed-speech-to-silence was 8.3 ms, the resumed echo session completed 11/11 scheduled chunks, and Gateway dispatch/provider failures were zero. Physical microphone/speaker, arbitrary human pronunciation, audible device latency, and acoustic echo-path review remain open. | Development only; automated generated speech is not physical audio or release evidence. |
| Vocal and media semantics | Goal Association separates `responsibility_kind`, `execution_lane`, `output_mode`, and `provider_required`; typed projections reach Planner. `chromie.vocal.perform` is the exact public source contract for qualified provider work. Declarations bind supported modes to retained evidence plus streaming, timing, sample, concurrency, cancellation, and immutable provenance properties. Provider vocal Goals pass through canonical planning, remain Speaking during coordination, and keep one identity through Host authorization, execution, cancellation, and evidence. Unsupported modes and silent downgrades fail closed. The default catalog advertises no qualified mode, ordinary TTS remains separate, media playback remains Activity, and no validated singing provider exists. | Fake-provider declaration/runtime/closure tests, Planner and Response Composer regressions, the exact recitation cognitive-runtime scenario, the 8/8 `stable_capability_grounding` Level A class, ordinary TTS regressions, and the canonical gate cover source behavior. The final pre-commit canonical run passed 2,041 maintained tests, 20 legacy Agent tests, and 102 benchmark tests. `scripts/vocal_issue_closure.py` remains the authoritative combined Level A/C default-provider gate. | **Target validated** for the earlier exact text-to-MuJoCo walk/sing/blink profile in `.chromie/acceptance/vocal-issue-1/20260807T032038Z`: clean Chromie `6809a84`, clean Soridormi `1c15371`, walking and blinking completed with typed body Goal ownership, singing remained `unavailable` with zero steps, and safe idle held before and after. A current-revision clean replay is still required before Issue #6 delivery. Physical microphone, speaker, singing-provider, and robot behavior remain excluded. | Exact vocal-provider source acceptance is complete; delivery remains development-only pending the clean current-revision default-provider replay. This does not qualify a singing provider or a release. |

## Compatibility state

`POST /interaction` and `POST /run` remain compatibility interfaces. Their old
CapabilityAgent semantic planner is emergency-only and requires explicit service
and per-turn authority gates. Normal Goal-driven apply failures and excluded
lanes do not enter it. Exact Core action proposals may cross a deterministic
compatibility adapter, but the adapter cannot reinterpret meaning or authorize
execution.

The compatibility planner should be removed after current replay, live-service,
and operator rollback evidence shows that no maintained profile depends on it.

## Open source issues

- Retain the clean current-revision default-provider walk/sing/blink replay
  before starting peer media-provider work.
- Define peer media playback as an exact Activity capability with a bounded
  lifecycle; do not use it as evidence for authored vocal performance.
- Keep the vocal-hosting decision deferred until a measured synchronization,
  cancellation-latency, platform-adaptation, or resource-contention blocker is
  retained.
- Reduce the Orchestrator composition root while preserving current structural
  ratchets and exception boundaries.
- Remove remaining compatibility planner code after equivalent retained
  evidence exists.
- Keep dependency-complete Ruff and Mypy execution available in the maintained
  CI environment.
- Continue replacing development-only mutable runtime aliases with resolved
  digests in publishable provenance rather than pretending local aliases are
  immutable.

## Open target evidence

- current-revision live Gateway/Core/Fast Planner smoke beyond the retained
  walk/sing/blink closure profile;
- current-revision voice-to-MuJoCo cancellation receipts beyond that exact
  completed interaction;
- microphone intelligibility and first-audible TTS latency;
- physical microphone/speaker barge-in, echo rejection, and resume latency;
- shared-GPU warm/cold latency and contention behavior;
- physical-provider commissioning, stop, recovery, and rollback;
- resolved container and model artifact digests for any future publication.

## Verification commands

```bash
./scripts/run_tests.sh
python scripts/semantic_authority_audit.py --check
./scripts/benchmark_check.sh
bash scripts/gpu_smoke_test.sh
```

The first three commands are source gates. The GPU smoke requires running
services. Physical audio and robot claims require retained target evidence under
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md).

## Status vocabulary

- **Implemented:** source and contracts exist.
- **Automatically verified:** maintained automated checks pass for the source.
- **Target validated:** retained evidence exists from the required runtime,
  simulator, GPU, audio device, or robot.
- **Release ready:** publication inputs, compatibility, provenance, support, and
  rollback are closed for a declared release target.

Do not collapse these states into “done.”
