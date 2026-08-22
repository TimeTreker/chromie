# Chromie Development Checkpoint

Status: current resume point; incomplete development snapshot
Updated: 2026-08-22
Patch baseline: user-supplied `chromie_20260822.zip`.

The archive has no trusted `.git` history. During this audit the remote `main` head was
`d04df3762e3e829b382ce74478fb9f7587ccec12`; the archive matched the remote blob hashes
checked for `DEVELOPMENT_CHECKPOINT.md` and `agent/app/planner_validation.py`. Those spot
checks do not claim archive-wide Git identity.

## Read first

Canonical owners remain [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), and
[Acceptance](docs/ACCEPTANCE.md). Source and executable evidence win over old milestone
prose.

Current focus: **close the verified 2026-08-22 live semantic-authority leaks** without
changing the Goal-driven backbone. Planner remains the one ordinary HOW/communication
authority; Host/Runtime mechanisms must stop converting their own states into Chromie
dialogue.

## Current architecture

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

- GI owns provider-neutral Responsibility meaning only.
- GA owns canonical Goal continuity only.
- Fast/Deep are cognition passes of one Planner HOW authority.
- Runtime/Provider report execution facts; Evidence records trusted truth.
- Planner owns ordinary Communicative Activities and exact wording.
- `CognitiveOpportunity` is readiness, not another semantic owner.
- Provider-local planning/DAGs may implement one selected Capability without becoming
  Chromie's global planner.

Planner implementation remains decomposed without changing authority:
`planner_model_contract.py`, `planner_context.py`, `planner_grounding.py`,
`planner_schema.py`, `planner_validation.py`, `planner_fallback.py`,
`planner_audit.py`, and `planner_prompt.py` are implementation layers of that same owner.

## 2026-08-22 audit convergence

The repository-hygiene audit and semantic-authority audit now agree on an ordered
remediation line. Verified live defects include:

- Confirmation Dialogue had Host prompt fallback plus approve/deny/expire/ambiguous
  message payloads despite `SPEECH-OWNER-001`;
- named Goal cancellation replaces Planner output with Host-written success/failure prose;
- cognitive commit/runtime-entry failures expose pipeline jargon or collapse processing
  failure into capability inability;
- `outcome_response.py` mechanically maps terminal state to user-visible result meaning;
- Host body recovery constructs a retry plan and confirmation prompt after execution
  failure.

Verified architecture debt, but not default-turn evidence of a second live planner:
Chromie-global TaskGraph execution is wired but feature-disabled by default; its
`residual_replan` projection carries planning guidance and must later prove a distinct
execution-only role or be removed. Provider/body-local DAGs are not implicated.

Verified repository-hygiene work follows correctness: orphan legacy-agent prompts, dead
`ToolClient`, repeated whitespace normalizers, three JSON-schema/type validator copies,
missing async test dependency, stale naming, and compatibility residue.

## Current patch slice — Phase 1A

This patch starts remediation rather than only documenting it:

- `ConfirmationDialogue` has no generic English/Chinese wording fallback;
- confirmation staging reuses explicit/response Planner wording and fails closed if none
  exists;
- `ConfirmationResolution` carries authorization truth, not user-visible messages;
- rejected/expired/ambiguous confirmation no longer emits Host dialogue;
- Host-commit and Cognitive Runtime-entry failure use the existing tiny
  cognition-unavailable operational fallback instead of plan/schema jargon or a false
  "I can't do that" capability claim;
- repository policy forbids reintroducing Confirmation Dialogue phrase ownership.

This is **not Phase 1 closure**. Named-cancellation narration, deterministic outcome
wording, outcome-reconciliation warnings, and Host body-recovery planning/prompt ownership
remain next.

## Required execution order

1. Finish **Phase 1B/1C/1D**: cancellation, post-Evidence result meaning, outcome failure,
   and body recovery return facts to Planner instead of authoring Host speech/retry
   semantics. Do not add a Speech Manager or replacement Response Composer.
2. Run focused confirmation/cancellation/outcome/body-recovery regressions, semantic
   authority audit, repository policies, docs check, and `./scripts/run_tests.sh` in the
   dependency-complete environment.
3. Execute **Phase 2** documentation convergence, then **Phase 3** dormant TaskGraph
   decision, then **Phase 4** repository hygiene/duplicate-mechanism cleanup.
4. Continue structural decomposition only across existing ownership seams.
5. Retain current-revision provider/live/simulator evidence. Keep implementation,
   automated verification, target validation, and release readiness separate.

Detailed phase order and exit criteria live in `ROADMAP.md`; current facts live in
`docs/STATUS.md`.

## Verification for this slice

Current source verification on the audit workspace:

- `python -m unittest -v tests.test_confirmation_dialogue`: **13 passed**;
- confirmation/Gateway/reflex/Cognitive-Runtime/TTS-alignment/voice-acceptance focused
  pytest slice: **205 passed + 65 subtests**;
- repository policies, documentation checks, semantic-authority audit, runtime-structure
  ratchet, and test-ownership checks: **passed**;
- legacy Agent direct tests used by the canonical runner: **20 passed**.

`./scripts/run_tests.sh` reaches the repository/test-ownership gates but this audit
workspace does not contain the pinned Ruff executable, so canonical-suite completion is
not claimed here. Install the pinned `requirements-test.txt` environment and rerun that
script before treating this slice as fully verified.

Do not claim microphone, audible speaker, GPU/model, MuJoCo, or physical-robot behavior
from source tests. Those remain separate target evidence.
