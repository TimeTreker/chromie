# CLAUDE.md

Guidance for coding agents working on Chromie.

## Read first

1. `docs/STATUS.md` — current implementation and evidence authority
2. `ROADMAP.md` — milestone intent and exit criteria
3. `DEVELOPMENT_CHECKPOINT.md` — exact resume point
4. `README.md` and the relevant component README
5. `docs/ACCEPTANCE.md` — required validation level
6. `docs/README.md` — documentation ownership and update rules

Treat current source and tests as truth. Historical patches, tags, exported
archives, and old milestone prose are context only.

## Working rules

- Inspect implementation and tests before editing documentation or behavior.
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
- Keep TTS generation serialized unless the backend ownership model changes.
- Do not fabricate microphone, GPU, simulator, or hardware evidence. Use the
  guided runner and retain operator notes.
- Do not remove release blockers or mark M13 complete unless the corresponding
  implementation and evidence are present.

## Required checks

```bash
./scripts/run_tests.sh
python scripts/check_docs.py
```

For interface, configuration, status, or support changes, update the owned
source-of-truth document in the same patch. Use the four-axis status vocabulary
from `docs/STATUS.md`.
