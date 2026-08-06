# Chromie Current Status

Status: current implementation and evidence authority

Chromie remains a development project. The maintained direction is a
**Goal-driven single semantic authority**: the Cognitive Gateway owns ingress,
protective reflexes, and attention admission; the Goal-driven Cognitive Core
owns ordinary meaning, goals, planning, response composition, and outcome
reconciliation. Trusted Host and provider boundaries authorize effects. The
approved target keeps interaction orchestration in Chromie while moving
platform-facing body, vocal, media, sensor, and device execution behind a
Soridormi Execution Runtime plus private Platform Provider.

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
| Chromie-Soridormi execution boundary | The target two-container Soridormi boundary and retained Chromie Interaction Orchestrator are documented. The current runtime has not migrated: Chromie still owns TTS/playback and Soridormi primarily owns body execution. | Documentation and existing contract tests can verify only current source consistency; they do not prove the target boundary. | No target validation exists for Soridormi-owned vocal/media execution, platform audio adaptation, or unified multimodal start/cancel. | Design approved; implementation not started. |
| Vocal and singing semantics | Source prompts and tests attempt to keep vocal performance in Speaking, but the retained live compound episode remains open. The current Goal DTO still overloads completion modality, lane, and provider need, and no validated singing provider exists. | Focused tests exist, but they did not reproduce the final live failure and therefore are insufficient closure evidence. | No retained successful walk/blink/sing execution or singing-mode provider evidence. | Defect open; development only. |

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

The ordered implementation queue is owned by
[Roadmap: Chromie-Soridormi execution-boundary migration](../ROADMAP.md#chromie-soridormi-execution-boundary-migration):

1. repair vocal-mode Goal and Planner semantics, including the retained
   walk/sing/blink failure;
2. define the immutable Chromie-to-Soridormi execution and evidence envelope;
3. introduce the Soridormi Execution Runtime facade for existing body work;
4. migrate vocal/TTS execution;
5. migrate media playback as Activity capabilities;
6. move platform audio and sensor adaptation into Soridormi Platform Provider;
7. add provider-local multimodal prepare/start/cancel coordination;
8. slim the Chromie Interaction Orchestrator and remove direct execution; and
9. close target evidence before deleting compatibility paths.

Additional open work:

- retain the deferred speech-start barge-in Issue without implementing it before
  the audio ownership boundary is settled;
- remove remaining compatibility planner code after equivalent retained
  evidence exists;
- keep dependency-complete Ruff and Mypy execution available in the maintained
  CI environment; and
- continue replacing development-only mutable runtime aliases with resolved
  digests in publishable provenance rather than pretending local aliases are
  immutable.

## Open target evidence

- current-revision live Gateway/Core/Fast Planner smoke;
- current-revision voice-to-MuJoCo interaction and cancellation receipts;
- microphone intelligibility and first-audible TTS latency on the current path;
- Soridormi-owned vocal streaming, media playback, interruption, delivery
  receipts, and mode-specific singing evidence after migration;
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
