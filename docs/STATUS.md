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
| Vocal and media semantics | Goal Association separates `responsibility_kind`, `execution_lane`, `output_mode`, and `provider_required`; typed projections reach Planner. Mode-specific vocal Goals remain Speaking, reject vocal resource acquisition, and cannot be closed by generic response text or ordinary TTS. Media playback remains Activity. The dedicated closure runner binds the canonical gate to exact current-revision text-to-MuJoCo evidence. No validated singing provider exists. | Focused Goal Association and Fast/Deep Planner regressions cover compound resegmentation, schema requirements, generic-TTS rejection, honest unavailability, metadata projection, Planner ownership, and closure-evidence validation. `scripts/vocal_issue_closure.py` is the authoritative combined Level A/C gate. | Target validation remains open until one clean closure bundle proves real Soridormi walking/blinking dispatch, exact singing unavailability, matching source identity, and safe-idle recovery. | Source mechanism and closure tooling implemented; close the defect only from a passing retained closure bundle. |

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

- Run `python scripts/vocal_issue_closure.py --soridormi-repo ../soridormi`
  from clean paired checkouts and retain its passing closure bundle before
  closing the typed vocal Goal and Planner defect.
- Qualify an exact Chromie vocal capability contract and keep ordinary TTS
  evidence distinct from singing evidence.
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

- current-revision live Gateway/Core/Fast Planner smoke;
- current-revision voice-to-MuJoCo interaction and cancellation receipts;
- microphone intelligibility and first-audible TTS latency;
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
