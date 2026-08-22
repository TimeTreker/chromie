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
- Host body recovery historically constructed a retry Plan and confirmation prompt after
  execution failure; Phase 1D removes that authority and preserves only bounded
  provider-declared retryability facts in terminal Evidence.

Verified architecture debt, but not default-turn evidence of a second live planner:
Chromie-global TaskGraph execution is wired but feature-disabled by default; its
`residual_replan` projection carries planning guidance and must later prove a distinct
execution-only role or be removed. Provider/body-local DAGs are not implicated.

Verified repository-hygiene work follows correctness: orphan legacy-agent prompts, dead
`ToolClient`, repeated whitespace normalizers, three JSON-schema/type validator copies,
missing async test dependency, stale naming, and compatibility residue.

## Current patch line — Phase 1A through 1D

The live semantic-authority audit remediation is now source-closed across confirmation,
cancellation, ordinary result meaning, and recoverable body failure:

- Phase 1A: `ConfirmationDialogue` owns authorization facts only and requires exact
  Planner-authored confirmation wording;
- Phase 1B: named cancellation preserves the current Planner response/Work, revokes stale
  confirmation scope without rebuilding child Plans/prompts, and keeps only the narrow
  deterministic stop/cancel failure-or-uncertainty warning;
- Phase 1C: the deterministic `outcome_response.py` status-to-sentence owner is removed;
  reconciliation/Goal-state failures no longer narrate Host machinery; all terminal
  statuses can re-enter Planner as bounded `ToolResultEvidence`; and a separate trusted
  execution-outcome projection carries aggregate/Goal status plus mechanical completion
  qualification without authoring meaning. If Planner re-entry is unavailable, Evidence is
  retained and no Host result sentence is manufactured;
- Phase 1D: `body_recovery.py` and its Host-generated retry child Plan/prompt path are
  removed. Execution Evidence now retains bounded provider-declared `recoverable`,
  `retryable`, and `failure_class` facts; the same Planner owns retry, alternative,
  clarification, wait, or no new Work. Runtime/Soridormi still own confirmation
  enforcement, safety, preflight, and execution.

This closes the verified live Phase 1 semantic-authority findings in source. Qualification
remains separate from source closure.

## Required execution order

1. Run focused confirmation/cancellation/outcome/body-failure regressions, semantic
   authority audit, repository policies, docs/configuration checks, and
   `./scripts/run_tests.sh` in the dependency-complete environment.
2. Run current-revision bilingual/provider/simulator qualification for failed recoverable
   body Work and verify Planner owns retry/alternative/clarification/wait/silence while
   Runtime/Soridormi still enforce physical confirmation and safety.
3. Execute **Phase 2** documentation convergence, then **Phase 3** dormant TaskGraph
   decision, then **Phase 4** repository hygiene/duplicate-mechanism cleanup.
4. Continue structural decomposition only across existing ownership seams.
5. Retain current-revision provider/live/simulator evidence. Keep implementation,
   automated verification, target validation, and release readiness separate.

Detailed phase order and exit criteria live in `ROADMAP.md`; current facts live in
`docs/STATUS.md`.

## Verification for this slice

Current source verification on the uploaded `chromie_2026082206.zip` baseline plus applied
Phase 1C and this Phase 1D change:

- execution-outcome truth/reconciliation, terminal-Evidence re-entry, cognitive turn-loop,
  Interaction Runtime, and confirmation regressions: **105 passed + 26 subtests**;
- Planner prompt/internal-layer, Fast/Deep Planner, and behavior-scenario regressions:
  **197 passed + 9 subtests**;
- combined non-overlapping focused verification: **302 passed + 35 subtests**;
- `python -m compileall -q agent orchestrator shared scripts tests`: **passed**;
- runtime configuration inventory, Host/service configuration ownership, runtime
  exception-boundary inventory, repository policies, documentation checks, semantic-authority
  audit, runtime-structure ratchet, and test-ownership checks: **passed**;
- the Host structural ratchet is reduced to **103 methods / 301 init lines / 108
  initialized attributes / 0 direct LLM calls**.

A broader `PYTHONPATH=agent:. python -m pytest -q tests agent/tests` run reached about 61%
with no failure before this environment's 120-second command limit. Full canonical-suite
completion is therefore not claimed by this patch handoff; run `./scripts/run_tests.sh` in
the pinned `requirements-test.txt` environment after applying.

Do not claim microphone, audible speaker, GPU/model, MuJoCo, or physical-robot behavior
from source tests. Those remain separate target evidence.
