# Development Checkpoint

**Development identity:** `development`
**Status refresh date:** 2026-07-31
**Deferred physical validation:** **Retain a Current-Revision Live Voice Loop**
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

## Immediate resume point

The canonical local gate is restored. On 2026-07-31,
`INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh` passed repository policy,
test-ownership, Ruff, the unchanged four-file Mypy ratchet, documentation,
1,673 primary tests, and 20 legacy Agent tests.

The `current-revision-live-voice` verifier profile is implemented and preserves
the default full seven-case verifier. Focused coverage rejects synthetic input,
partial events, dirty or mismatched source, missing or incomplete runtime
identity, executable skills, timeout/truncation/fallback, stale playback,
artifact tampering, and absent operator review. Python 3.11+ is now checked by
both the supervised preflight and the Orchestrator launcher before dependency
installation or model warm-up. The latest 2026-07-31 attention-contract run
passes 1,673 primary tests plus 20 legacy Agent tests.

The managed `Chromie` environment is now Python 3.11.15 and passes the runtime
gate. Clean supervised attempt `20260731T110834Z` at revision `e931af3` then
confirmed that this PC has no usable microphone input: the Orchestrator and ASR
service were ready, but both guided utterances produced no audio or `asr_final`.
The operator confirmed that no microphone is installed and directed that this
physical test be skipped. This is not live-loop evidence; target validation is
deferred to a host with input hardware. When such a host is available, use:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"

python scripts/voice_acceptance.py \
  --mode supervised \
  --cases speech-only \
  --start-services \
  --acceptance-id "$RUN_ID"

python scripts/verify_voice_evidence.py \
  ".chromie/acceptance/voice/$RUN_ID" \
  --profile current-revision-live-voice \
  --require-clean
```

Do not replace physical input with synthetic input for this claim.

The retained run must contain:

- clean Chromie source and captured running runtime identity;
- physical microphone input and `asr_final`;
- admitted Gateway/Core processing and applied `chat`;
- zero executable skills;
- correlated TTS schedule, playback start/end, and clean session completion;
- an operator audible-output verdict;
- `release_qualified=false` and no simulator/robot claim.

The full seven-case supervised verifier retains its current requirements. The
default `source_bound_development` closure is now active because physical voice
is optional for that profile; the deferred narrow claim remains ineligible.

Detailed Issue scope is in
[Repository Engineering Sustainability Plan](docs/REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md).

## Active target-evidence resume point

This is the active delivery line. Freeze new architecture layers, ordinary behavior flags,
standalone design documents, and project terminology unless a change is
required to remove a reproduced evidence blocker. Prefer deletion, merging, or
simplification over adding another compatibility surface.

Use the single resumable workflow in
[Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md). Initialize one clean
source-bound evidence root, collect/finalize Gateway/Core and Agent Skill/weather,
collect or attach the homogeneous Social Attention qualification, attach local and
second-machine LAN exposure reports, then finalize the default development
profile. Select `supervised_physical_pilot` only when supervised physical voice
and robot evidence will also be attached. Human review remains explicit and
fingerprint-bound.

Diagnostic root `20260731T121727Z` validates paired-source MuJoCo and active cancellation after correcting canonical `capability_id` reads.
Its ambient failure was reproduced independently; Attention Review now uses general speech-act contrasts, rejects `addressed=false` directed/unclear pairs, and permits one fail-open schema repair.
Focused tests and `robust_intent_understanding` 8/8 pass; a rebuilt-Agent dirty-source headless diagnostic suppressed the turn before Core with zero speech or skills.
This is diagnostic, not microphone or target evidence. Address grounded Beijing weather lookup/Goal continuity next; do not approve or resume that root.

## Work after evidence closure

After the default source-bound profile is retained and reviewed, continue one
semantic Issue at a time:

- classify and narrow broad runtime exception boundaries;
- establish typed Host configuration snapshots;
- extract playback delivery, then input/session lifecycle owners around seams
  observed in live traces;
- reduce unsupported configuration combinations;
- expand Mypy by complete contract/runtime boundaries;
- merge duplicated documentation and remove stale vocabulary and archives;
- rerun the source-bound evidence profile after structural changes.

Detailed scope and exit criteria are in
[Repository Engineering Sustainability Plan](docs/REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md).

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
