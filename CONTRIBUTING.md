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

- Follow the active Issue in `DEVELOPMENT_CHECKPOINT.md`. Until the canonical
  local gate is reproducible and the current-revision live voice loop is
  retained and the default target-evidence profile closes, feature,
  architecture, flag, and terminology growth is frozen except for work that
  closes those prerequisites or a demonstrated safety/provenance blocker.
- Keep microphone, playback, VAD, interruption, and Trusted Capability Runtime
  coordination in the host Orchestrator.
- Keep robot-body execution and physical safety in Soridormi.
- Do not expose raw motors, joints, torques, or actuator arrays to the LLM.
- Keep stop, cancel, emergency, silence, and unusable-audio decisions
  deterministic.
- Add new side effects behind explicit policy, confirmation, monitoring, and
  default-off rollout gates.
- Preserve compatibility adapters until a documented migration and rollback
  path exists.
- Treat `agent-skills/` as passive reviewed prompt content: never add an
  executable entrypoint, provider registration, permission, confirmation
  exemption, phrase selector, or hidden mutable state. Regenerate and review the
  package digest after any content change.
- Do not use production `assert` statements for runtime, state, execution, or
  evidence invariants. Classify failure handling according to
  `docs/RUNTIME_FAILURE_PATHS.md`; expected cleanup may be debug-visible, while
  operational and evidence failures must fail closed or remain observable.
- Run `scripts/check_repository_policies.py` for stable architecture and
  deployment boundaries. Policy exceptions must be exact, reviewed, and recorded
  only in `config/repository_policy_exceptions.json`; stale exceptions fail.
- Prefer an existing owner over a new document, environment variable,
  compatibility path, or architectural term. Any necessary addition must name
  its owner, supported lifetime, validation, and the overlapping surface it
  replaces or why none can be removed. Report before/after counts when one of
  these repository surfaces grows.
- Treat defect analysis, implementation, explanation, and verification as one
  deliverable. A patch without a causal explanation is incomplete, even when
  the code is correct.

## Required defect-fix report

Every user-reported or internally discovered defect fix must include a concise,
evidence-grounded report with all of the following:

1. **Observed failure and impact.** State what happened, what should have
   happened, and which user or system outcome was affected.
2. **Reproduction and evidence.** Identify the retained scenario, trace, log,
   failing test, or deterministic code path that demonstrates the defect.
3. **Expected contract and owner.** Name the contract that was violated and the
   component responsible for enforcing it.
4. **Root cause at the earliest responsible boundary.** Explain the causal chain
   from the initiating trigger to the first incorrect decision or state
   transition. Distinguish the root cause from downstream symptoms, unrelated
   failures, and contributing conditions.
5. **Fix mechanism.** Explain why the chosen change restores the violated
   contract, why it belongs at that boundary, and which behavior intentionally
   remains unchanged. Listing changed files or describing the diff is not a
   substitute for this explanation.
6. **Regression and evidence.** Show the pre-fix failure where practical, the
   focused post-fix regression, the broader gates run, and the highest evidence
   level actually reached. State any simulator, service, audio, or physical
   evidence still missing.
7. **Operational impact.** Report safety, compatibility, rollout, rollback,
   configuration, and documentation consequences when applicable.

A plausible story is not a root-cause finding. Each material claim must be tied
to retained evidence or clearly marked as an inference that still needs proof.
The final delivery may include a patch, commit, or pull request, but none of
those artifacts replaces the required explanation.

## Tests

Run the full dependency-light suite:

```bash
python scripts/check_repository_policies.py
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

- the observed failure, violated contract, and ownership boundary;
- the evidence-backed root cause at the earliest responsible boundary;
- the fix mechanism and why it restores the contract;
- safety impact;
- feature-gate/default changes;
- tests and target evidence;
- documentation updated;
- rollback behavior.

Never include execution tokens, private model credentials, device serials, or
unredacted acceptance logs.

## Static analysis

Run the pinned incremental static-analysis gates through `./scripts/run_tests.sh`. The reviewed scope, rules, and ratchet policy are documented in [Static Analysis Ratchets](docs/STATIC_ANALYSIS.md). Do not add blanket ignores or remove checked paths to make a gate pass.

## Test ownership

Behavior belongs in executable assertions, forbidden architecture in the repository policy checker, and literal source checks only in reviewed generated-artifact contracts. See [Test Ownership](docs/TEST_OWNERSHIP.md) and run `python scripts/check_test_ownership.py`.
