# Development Checkpoint

**Development identity:** `development`
**Status refresh date:** 2026-08-03
**Optional physical validation:** **Retain a Supervised Physical Voice Loop**
**Active evidence Issue:** **Close Current-Revision Target Evidence**

## Resume point

Chromie uses one Goal-driven semantic authority:

```text
Cognitive Gateway admission
    → Goal Association
    → model-authored Agent Skill selection/disclosure
    → Fast or terminal Deep Planner
    → Canonical Plan with content-free Skill provenance
    → Trusted Capability Runtime
    → evidence reconciliation and final response
```

The Host owns deterministic validation, authorization, scheduling, cancellation,
evidence, and lifecycle coordination. Soridormi owns backend selection, physical
feasibility, collision safety, stop, and recovery.

## Implemented foundations

- Cognitive Gateway/Core decomposition and fail-closed runtime boundaries.
- Canonical Capability terminology and passive Agent Skills.
- Grounded external-information and weather Skill packages.
- Loopback-only local service publication and repository policy gates.
- Ruff, Mypy, test-ownership ratchets, and revision-bound source qualification reporting.
- Typed Agent/ASR/TTS/Host/shared-runtime settings and extracted playback/input lifecycle collaborators.
- Ordered incremental Host playback from provider PCM with retained request,
  stream, first-PCM, stream-end, and audible-start milestones.
- Session-memory recall plus opt-in, consent-bound, expiring profile memory with
  atomic owner-local storage and explicit forget/clear operations.
- Deterministic, hybrid, and independent multi-model benchmark oracles; expanded
  bilingual closed-loop cognition; and a strict comprehensive evidence collector.
- Consolidated documentation authority with mechanically checked specialized-document ownership.
- Final core-principle audit closure: Host semantic delegation, phrase agents,
  catalog/action boosts, weather route repair, conversation phrase
  classification, ontology wording, and duplicate Provider execution paths are
  removed; memory is model-authored and current identities are canonical.

Implementation and evidence claims are owned by [Current Status](docs/STATUS.md).
Delivery and exit criteria are owned by [Roadmap](ROADMAP.md).

## Immediate resume point

The source implementation line is complete through the hybrid benchmark,
strict comprehensive collector, session and durable memory, provider-PCM
latency instrumentation, and ordered incremental Host playback. The next work is
qualification, not another architecture layer.

From a clean committed checkout with the pinned development dependencies:

```bash
python -m pip install -r requirements-test.txt
python scripts/run_source_qualification.py \
  --output .chromie/qualification/source/latest/report.json

./scripts/qualification/run_comprehensive_test.sh \
  --strict-exit \
  --capture auto \
  --languages zh,en
```

For important semantic changes, configure independent model families and rerun
the same clean cohort before and after the change:

```bash
./scripts/qualification/run_comprehensive_test.sh \
  --strict-exit \
  --semantic-reviewers .chromie/semantic-reviewers.json
```

The default comprehensive path never asks the operator to speak. It uses
Chromie-generated Chinese and English TTS, system-monitor or physical acoustic
capture, and Chromie's ASR. A human-voice run is optional and supports only a
separate real-user microphone claim. No source or automated report grants
release qualification.

## Active target-evidence resume point

Use the single resumable workflow in
[Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md). Initialize a new clean
`source_bound_development` evidence root for the current commit; never resume or
finalize an older failed/superseded root. Collect and review:

- Gateway/Core live-text plus paired MuJoCo execution, active cancellation, and
  safe idle;
- Agent Skill/weather continuity and evidence grounding;
- the homogeneous Social Attention baseline and selected MuJoCo evidence;
- local exposure and second-machine LAN reports;
- fingerprint-bound semantic review.

Physical voice and physical robot evidence are optional for this profile. Select
`supervised_physical_pilot` only when those stricter claims will also be attached.
Generated-speech acoustic capture may verify the physical audio path without the
operator speaking, but it does not establish real-user ASR robustness. Historical
failed and diagnostic roots remain provenance in Git and
[Project Handoff](docs/HANDOFF.md), not current qualification.

## Work after evidence closure

The former source-sustainability queue is complete. Continue only from retained
evidence:

- close the dependency-complete source report on the current revision;
- retain strict comprehensive before/after archives for large cognitive or audio
  changes and adjudicate only declared semantic dimensions with independent
  model families;
- close the default target-evidence profile, including Gateway/Core, weather,
  Social Attention, MuJoCo, local exposure, and second-machine LAN;
- measure warm/cold and shared-GPU latency, distinguishing Host transport
  streaming from provider-native generation behavior;
- qualify optional physical voice and physical robot profiles separately;
- extend durable family memory only with explicit consent, expiry, deletion,
  protected storage, and reviewed owner policy.

Detailed scope and exit criteria are in [Repository Engineering Sustainability Plan](docs/REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md).

## Required local gates

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/run_ruff.py
python scripts/run_mypy.py
python scripts/check_docs.py
./scripts/run_tests.sh
```

## Authority links

- [Documentation Authority](docs/DOCUMENTATION_AUTHORITY.md)
- [Final Core-Principle Audit](docs/FINAL_CORE_PRINCIPLE_AUDIT.md)
- [Project Charter](docs/PROJECT_CHARTER.md)
- [Current Status](docs/STATUS.md)
- [Roadmap](ROADMAP.md)
- [Operations Runbook](CHROMIE_RUNBOOK.md)
- [Cognitive Gateway/Core Qualification](docs/COGNITIVE_GATEWAY_CORE_QUALIFICATION.md)
