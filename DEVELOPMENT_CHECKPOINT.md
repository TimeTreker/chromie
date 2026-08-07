# Chromie Development Checkpoint

Status: current resume point

## Direction

Continue the **Goal-driven single semantic authority** architecture. The
Cognitive Gateway owns ingress, deterministic protective reflexes, and attention
admission. The Goal-driven Cognitive Core owns ordinary semantic interpretation,
goal association, planning, response composition, and outcome reconciliation.
Effects remain authorized only by trusted Host and provider boundaries.

## Current checkpoint

The semantic Issue stack was merged to `main` on 2026-08-07 as PRs #8 through
#11. The merge commits are `2bb7a14`, `832afa1`, `0514f3c`, and `e3d57ff`.
Issues #1, #5, #6, and #7 are closed. Retained evidence from their feature
revisions remains revision-bound rather than being relabelled as merge-revision
evidence.

The post-merge audit of `e3d57ff` established:

- the GPU, containers, Gateway/Core/Fast-Planner greeting round trip, TTS PCM,
  deterministic transport, and generated-speech barge-in path were live;
- the first strict comprehensive run retained 40 passing and 8 failing checks;
  missing host test dependencies caused the source/scenario portion of those
  failures, while log inspection and retained scenario replay exposed the
  implementation/orchestration defects and stale acceptance-event contract
  recorded in `docs/STATUS.md`;
- ordinary/final speech was played without entering the delivered-turn ledger;
  safe-read composition could duplicate or overclaim pre-evidence speech;
  Goal Association could anchor mechanical location defects and misclassify
  mixed stable-knowledge/reminder turns; session-memory contract retry repeated
  invalid output; typed pre-effect speech still made false tool/memory claims;
  valid tool results could fail only for sentence length; weather follow-ups
  replayed old evidence; service rebuilds could retain deleted image IDs; and
  the voice harness required retired events; the first mechanically clean
  comprehensive replay then exposed valid direct speech discarded by malformed
  optional Social Attention and a prompt-only decision-first contract that the
  deployed Fast Planner could ignore; the next mechanically clean replay then
  exposed an otherwise complete multi-Goal response inventing an unsupported
  user schedule as friendly reminder rationale;
- focused regressions now cover the repaired evidence ledger, current Core and
  Gateway event contracts, fresh model-owned Goal resegmentation, useful typed
  contract repair with authority-reducing session recovery, tool/memory
  pre-effect speech suppression, pure safe-read single ownership, and bounded
  evidence-preserving result repair, authority-reducing direct auxiliary
  validation, bounded model-owned retained-evidence communication review, and
  Response Composer grounding against invented user circumstances;
- the dependency-complete canonical gate passes 2,095 maintained tests, 20
  legacy Agent tests, and 102 benchmark tests, while Level A passes 66/66 across
  all ten general-ability classes;
- the comprehensive runner now builds once before nested voice acceptance;
  the first clean committed replay then exposed and removed an inapplicable
  full seven-case MuJoCo verifier call on its three-case diagnostic bundle; its
  next clean replay passed every mechanical check but remained blocked after
  manual delivered-text inspection found the two semantic defects above; and
- semantic documentation mismatches were corrected in the existing authority
  documents instead of creating another audit owner.

The final paired replay exposed three planner contract defects rather than a
Soridormi motion defect:

- Fast and Deep decoder schemas did not bind an exact capability to its provider
  argument schema, and only Fast described explicit numeric Goal provenance;
- Deep's unprojected catalog exceeded its prompt bound, so later capabilities
  such as exact velocity walking were absent from the deployed "full catalog";
- Deep's step and prose collections were not decoder-bounded, allowing one walk
  step to repeat until the model output limit before cancellation could reach a
  provider.

Exact capability schemas, shared numeric provenance validation, structured
bounded repair, a compact complete catalog, and bounded Deep collections close
those boundaries. Clean commit `90aa72a` passed the canonical source gate and a
rebuilt comprehensive profile with 46 passes, zero failures/timeouts, and one
explicit external-semantic-review skip. Manual inspection found no recurrence
of the audit's semantic blockers; strict status remains `incomplete`, not
release-qualified. `docs/STATUS.md` owns paths, limits, latency outliers, and the
paired audit. Clean merged-revision MuJoCo binding remains required.

The underlying maintained source still establishes:

- typed `interpretation_unavailable` instead of invented semantic fallback;
- strict catalog-backed action proposals in semantic repair;
- memory in maintained Goal-driven apply profiles;
- fail-closed excluded lanes without legacy semantic re-entry;
- a current Gateway-to-Core-to-Fast-Planner smoke contract;
- archive-portable deterministic source identity;
- benchmark validation in the canonical source gate;
- removal of duplicate audits, handoffs, implementation plans, and obsolete
  Route2/Route3 or named-skill planning documents.

`/interaction` and `/run` remain compatibility surfaces. Their semantic planner
is emergency-only and must not be used as ordinary fallback.

## Resume commands

From the repository root:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_runtime_structure.py
python scripts/check_docs.py
python scripts/semantic_authority_audit.py --check
./scripts/benchmark_check.sh
python -m unittest discover -s tests -p 'test_*.py'
```

In a dependency-complete environment, use the canonical gate instead:

```bash
./scripts/run_tests.sh
```

For a running Agent service:

```bash
python scripts/control_plane_smoke.py --base-url http://127.0.0.1:8092
```

For the maintained GPU profile and service lifecycle, use:

```bash
bash scripts/gpu_smoke_test.sh
```

Do not report GPU, microphone, speaker, MuJoCo, or physical-provider validation
unless the command actually ran against that target and retained its evidence.

## Next engineering work

The merged Issues retain clean, revision-bound source and highest-safe automated
evidence for the walk/sing/blink defect, reversible barge-in, the exact
`chromie.vocal.perform` contract, and peer media Activity. The evidence paths,
counts, limits, and remaining physical/provider gaps are owned by
[Current Status](docs/STATUS.md) and [Acceptance](docs/ACCEPTANCE.md). In
particular, generated speech and MuJoCo body results do not prove a physical
microphone, speaker, robot, real vocal provider, or real media provider.

The paired Soridormi reproducibility patch is merged as `fa8080d2`; Chromie's
capability manifest and compatibility authority are bound to that revision.
Merge the source-qualified Chromie candidate only after CI is green, then repeat
the exact compound execution and provider-start cancellation with clean merged
runtime identity. Keep backend names out of semantic Goals, do not introduce a
neutral media alias, and do not use source tests, generated/discarded TTS, or
simulator evidence as a claim for a real provider, physical audio, or hardware.
Real vocal and media modes remain unvalidated pending operation-specific proof.

## Canonical owners

- stable boundaries: [Project Charter](docs/PROJECT_CHARTER.md)
- delivery order: [Roadmap](ROADMAP.md)
- implementation and evidence: [Current Status](docs/STATUS.md)
- target workflow: [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md)
- interfaces: [API Reference](docs/API_REFERENCE.md)
- operation: [Runbook](CHROMIE_RUNBOOK.md)
- notable changes: [Changelog](CHANGELOG.md)
