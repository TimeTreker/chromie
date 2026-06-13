# Contributing to Chromie

Chromie combines realtime audio, local models, capability contracts, and
robot-safety boundaries. Small, well-evidenced changes are preferred over broad
refactors.

## Before editing

Read:

1. `docs/PROJECT_CHARTER.md`
2. `docs/STATUS.md`
3. `ROADMAP.md`
4. `DEVELOPMENT_CHECKPOINT.md`
5. the relevant component README
6. `docs/ACCEPTANCE.md` for the evidence level affected by the change

## Development setup

For GPU-free control-plane work:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
./scripts/run_tests.sh
```

Component-specific runtime dependencies are listed in each component’s
`requirements.txt`. The full voice stack additionally requires Docker, NVIDIA
Container Toolkit, Conda or an equivalent host environment, and audio devices.

## Change rules

- Keep microphone, playback, VAD, interruption, and trusted Skill Runtime
  coordination in the host Orchestrator.
- Keep robot-body execution and physical safety in Soridormi.
- Do not expose raw motors, joints, torques, or actuator arrays to the LLM.
- Keep stop, cancel, emergency, silence, and unusable-audio decisions
  deterministic.
- Add new side effects behind explicit policy, confirmation, monitoring, and
  default-off rollout gates.
- Preserve compatibility adapters until a documented migration and rollback
  path exists.

## Tests

Run the full dependency-light suite:

```bash
./scripts/run_tests.sh
```

Add focused tests for contract, policy, cancellation, fallback, and concurrency
changes. GPU, audio, simulator, or hardware changes also require the relevant
higher-level evidence from `docs/ACCEPTANCE.md`.

## Documentation

Update documentation in the same change when behavior, defaults, interfaces,
status, or support scope changes. Run:

```bash
python scripts/check_docs.py
```

Use the four-axis vocabulary from `docs/STATUS.md`: implemented, automatically
verified, target validated, and release ready.

## Pull requests

A useful pull request description includes:

- the problem and ownership boundary;
- implementation summary;
- safety impact;
- feature-gate/default changes;
- tests and target evidence;
- documentation updated;
- rollback behavior.

Never include execution tokens, private model credentials, device serials, or
unredacted acceptance logs.
