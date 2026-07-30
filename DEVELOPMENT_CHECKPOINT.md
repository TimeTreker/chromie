# Development Checkpoint

**Development identity:** `development`
**Status refresh date:** 2026-07-30
**Current code Issue:** none; the accepted engineering-sustainability implementation backlog is complete.

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

- Cognitive Gateway/Core migration and fail-closed runtime boundaries.
- Canonical Capability terminology and passive Agent Skills.
- Grounded external-information and weather Skill packages.
- Loopback-only local service publication and repository policy gates.
- Ruff, Mypy, and test-ownership ratchets.
- Typed ASR service settings and the first `VoiceAssistant` collaborator extraction.
- Consolidated documentation authority.
- Final core-principle audit closure: Host semantic delegation, phrase agents,
  catalog/action boosts, weather route repair, conversation phrase
  classification, ontology wording, and duplicate Provider execution paths are
  removed; memory is model-authored and current identities are canonical.

Implementation and evidence claims are owned by [Current Status](docs/STATUS.md).
Delivery and exit criteria are owned by [Roadmap](ROADMAP.md).

## Open evidence work

1. Execute the source-bound Gateway/Core qualification workflow on a clean paired
   Chromie/Soridormi deployment and approve the exact artifacts.
2. Retain positive live Agent Skill selection and provider-backed weather evidence.
3. Resume Social Attention baseline qualification after the Gateway/Core evidence
   checkpoint closes.
4. Retain supervised physical audio and physical-robot evidence only under their
   dedicated safety procedures.
5. Confirm local loopback exposure from the deployed host and a second LAN machine.

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
- [Historical checkpoint narrative](DEVELOPMENT_CHECKPOINT_ARCHIVE_2026-07-30.md)
