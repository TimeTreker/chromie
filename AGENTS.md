# AGENTS.md

Guidance for coding agents working on Chromie.

## Read first

1. `docs/PROJECT_CHARTER.md` — stable goal, boundaries, and non-goals
2. `docs/HUMAN_LIKE_INTERACTION_CONTRACT.md` — root-cause rules for natural, grounded robot behavior
3. `docs/STATUS.md` — current implementation and evidence authority
4. `ROADMAP.md` — milestone intent and exit criteria
5. `DEVELOPMENT_CHECKPOINT.md` — exact resume point
6. `README.md` and the relevant component README
7. `docs/ACCEPTANCE.md` — required validation level
8. `docs/README.md` — documentation ownership and update rules

Treat current source and tests as truth. Historical patches, tags, exported
archives, and old milestone prose are context only.

## Current delivery constraint

Until the canonical local gate, narrow current-revision live voice proof, and
default target-evidence closure are retained and reviewed, treat that sequence
as the only active delivery line. Do not add a new architecture layer, ordinary
behavior flag, standalone design document, compatibility path, or first-class
project term unless required to remove a reproduced blocker. When one must be
added, remove or merge an equivalent item in the same change or record the
exception in the active Issue.

After evidence closure, follow the semantic Issue order in
`docs/REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md`. Do not use file length,
method count, or document count as mechanical gates; extract or consolidate only
when ownership, independent testing, configuration authority, or failure
semantics become clearer.

## Working rules

- Follow the active Issue in `DEVELOPMENT_CHECKPOINT.md`. Until the canonical
  local gate is reproducible and the current-revision live voice proof is
  retained and the default target-evidence profile closes, do not add product
  features, new architecture, new runtime switches, or new terminology unless
  the change directly closes those prerequisites or a demonstrated
  safety/provenance blocker.
- Inspect implementation and tests before editing documentation or behavior.
- For user-visible robot weirdness, diagnose the root architectural or
  interaction-policy cause before changing prompts or phrasing.
- Do not submit symptom-only interaction fixes. Before changing behavior for a
  user-reported robot problem, write or report the observed turn, the expected
  contract, the evidence or trace used, the earliest component that went wrong,
  whether the fix is architecture, contract/schema, prompt, runtime policy, or
  test evidence, and the regression boundary that would have caught it.
- Treat reported utterances as probes into general ability classes, not as
  isolated targets. Fix robust intent understanding, stable capability
  grounding, natural uncertainty handling, composable high-level action
  planning, truthful embodied speech, or evidence coverage rather than tuning
  Chromie only to pass one pasted example.
- For user-visible behavior changes, run or update the relevant
  `scripts/general_ability_acceptance.py` ability class and report the evidence
  level. Do not claim live robot behavior from Level A output.
- Fix the earliest responsible boundary. Hardcoded phrase rules are allowed
  only for deterministic operational controls such as stop, cancel, emergency,
  silence, or unusable input. They must never select semantic lanes, Goals,
  Agent Skills, Capabilities, memory content, deep-thinking delegation, or
  social behavior. Semantic uncertainty must use model repair, clarification,
  or fail-closed behavior rather than a phrase fallback.
- For every user-reported behavior defect, follow the executable
  scenario-driven loop without waiting for the user to request it again:
  retain the originating single- or multi-turn episode, reproduce the earliest
  wrong boundary, implement the general fix, rerun the focused scenario until
  it passes, run its general-ability class, then run the canonical gates. When
  deployed services are available, rebuild or verify the current revision and
  run the same scenario through the highest safe automated live profile. Score
  and inspect the retained output yourself; do not ask the user to copy logs or
  act as the integration-test harness. A hard safety, provenance, Goal omission,
  HTTP/service, LLM-integrity, or safe-idle failure cannot be averaged into a
  pass. Physical microphone, speaker, or robot evidence remains supervised;
  report that evidence gap explicitly instead of claiming it from text,
  virtual-audio, or simulator results.
- Keep microphone, VAD, playback, interruption, conversation state, and Trusted
  Capability Runtime coordination in the host Orchestrator.
- Keep embodied planning, execution, resource safety, stop/emergency behavior,
  and hardware commissioning in Soridormi.
- Do not add new robot work to the legacy host hardware daemon.
- Do not expose raw motor, joint, torque, actuator, or controller-array fields
  to model-facing contracts.
- Keep stop, cancel, emergency, silence, and unusable-audio paths deterministic.
- Keep risky feature gates default-off and fail closed when providers are
  disabled or unavailable.
- Preserve confirmation, monitor, cancellation, timeout, and fallback semantics.
- Keep physical TaskGraph nodes sequential.
- Log fallback causes; do not hide model or service failures.
- Do not use production `assert` for runtime invariants; classify and handle
  failures according to `docs/RUNTIME_FAILURE_PATHS.md`. Stable mechanical
  boundaries are enforced by `scripts/check_repository_policies.py`; do not
  bypass it with local source-string guards or unreviewed exceptions.
- Use generated `.env.runtime`; do not edit it directly.
- Use Docker service names inside containers and loopback ports from the host.
- Run the Orchestrator from repository root with
  `python -m orchestrator.orchestrator`.
- Keep audible TTS playback ordered. TTS generation may run with bounded
  concurrency only through independently owned service workers; do not raise
  concurrency beyond the configured worker/resource contract.
- Do not fabricate microphone, GPU, simulator, or hardware evidence. Use
  synthetic/virtual-mic modes for automated regression and supervised mode for
  physical microphone/speaker evidence with operator notes.
- Do not convert automated or historical evidence into unsupported target,
  hardware, or deployment claims.

## Repository surface budget

- Prefer changing an existing owner over creating another document, environment
  variable, compatibility path, or architectural term.
- A new current document must name its audience and authoritative owner, and
  explain why an existing owner cannot hold the fact. Documentation-only index
  links do not by themselves justify a document.
- A new environment variable must name its owning profile or service, default,
  supported combinations, validation, and removal or compatibility plan. Do not
  add a boolean merely to postpone a design decision.
- A new architectural term must be defined once in an authority document and
  replace or clearly distinguish any overlapping term.
- Changes that grow one of these surfaces must report the before/after count and
  identify a consolidation or deletion opportunity. Net growth requires an
  explicit project need; a mechanical one-in/one-out deletion is not required
  when it would remove useful evidence or a real contract.

## Required checks

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

For interface, configuration, status, or support changes, update the owned
source-of-truth document in the same patch. Use the four-axis status vocabulary
from `docs/STATUS.md`.

## Static analysis

Run the pinned incremental static-analysis gates through `./scripts/run_tests.sh`. The reviewed scope, rules, and ratchet policy are documented in [Static Analysis Ratchets](docs/STATIC_ANALYSIS.md). Do not add blanket ignores or remove checked paths to make a gate pass.

## Test ownership

Behavior belongs in executable assertions, forbidden architecture in the repository policy checker, and literal source checks only in reviewed generated-artifact contracts. See [Test Ownership](docs/TEST_OWNERSHIP.md) and run `python scripts/check_test_ownership.py`.
