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

## Working rules

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
- Fix the earliest responsible boundary. Hardcoded phrase rules are acceptable
  only for deterministic operational controls or as a last-resort guard after
  the architecture, contract, and prompt boundary have been checked.
- Keep microphone, VAD, playback, interruption, conversation state, and trusted
  Skill Runtime coordination in the host Orchestrator.
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
- Use generated `.env.runtime`; do not edit it directly.
- Use Docker service names inside containers and loopback ports from the host.
- Run the Orchestrator from repository root with
  `python -m orchestrator.orchestrator`.
- Keep audible TTS playback ordered. TTS generation may run with bounded
  concurrency only through independently owned service workers; do not raise
  concurrency beyond the configured worker/resource contract.
- Do not fabricate microphone, GPU, simulator, or hardware evidence. Use
  synthetic/virtual-mic modes for automated regression and supervised mode for
  release-closing microphone/speaker evidence with operator notes.
- Do not remove release blockers or publish the alpha unless the corresponding
  implementation and evidence are present.

## Required checks

```bash
./scripts/run_tests.sh
python scripts/check_docs.py
```

For interface, configuration, status, or support changes, update the owned
source-of-truth document in the same patch. Use the four-axis status vocabulary
from `docs/STATUS.md`.
