# Project Handoff

Last updated: 2026-07-16

This handoff records the current resume point for a developer or operator who
needs to continue Chromie without replaying the full history. Capability and
evidence claims remain authoritative in [Current Status](STATUS.md).

## Current State

Chromie's maintained semantic-planning path is the unified Goal-driven Runtime
implemented through PR1-PR8:

```text
Router classification
  -> Goal Association
  -> complete-coverage Fast Planner
  -> terminal Deep Planner when needed
  -> trusted host validation and at most one bounded replan
  -> fingerprint-bound Response Composition
  -> strict InteractionResponse preparation
  -> atomic Goal-state application
  -> confirmation / Skill Runtime / Soridormi
```

The common safe base enables structured interaction and authoritative
cognitive `apply` for `chat` while leaving Soridormi disabled. The maintained
`scripts/start_chromie.sh` Soridormi launcher enables the trusted provider and
widens authoritative lanes to `chat,robot_action`. Both profiles use
`fail_closed` after the Goal-driven Runtime acquires a turn. The standalone
Goal Association, Fast Planner, Deep Planner, Response Composer, and task
continuity observer switches are off because the unified coordinator owns
those stages.

There is one semantic authority per applied turn. Exact Router actions are
adapter-only. The old CapabilityAgent planner is not a normal fallback: it
requires the host gate, Agent gate, and an authoritative emergency claim with a
non-empty `turn_id` exactly matching the request turn. Missing, empty, and
cross-turn claims fail closed before model planning. This claim is internal
routing metadata; it is not caller authentication or a consumed replay nonce.

The Goal Association model boundary now uses the exact schema and receives at
most one bounded contract-repair attempt. The host, not the model, owns turn,
association, goal, version, and persistence identities.

Evidence and release tooling now checks provenance rather than treating any
older successful bundle as current validation:

- cognitive simulator validation requires an applied cognitive result,
  completed Soridormi `sim` execution, safe idle, a clean declared paired
  checkout, and an endpoint-reported Soridormi revision matching that checkout
  and the manifest;
- voice evidence compares its recorded host-checkout revision/version and
  Soridormi declarations with the current source, capability manifest, and
  compatibility declaration, but host `HEAD` does not yet bind the running
  Chromie images/models to that source;
- release preparation fails when those revisions or versions disagree.

The fail-closed comparison controls are implemented and have automated
coverage, but the current runners record `declared_paired_checkout` without an
endpoint-reported Soridormi revision. Running Chromie image/model source
binding and immutable release image references are also open. Retained
live-text and MuJoCo evidence for the current multi-goal and single-authority
path remains open. Do not claim target validation or release readiness from
Level A results, a newly diagnostic-only bundle, or the historical M13 bundle.

## Historical Evidence Boundary

The M13 text-to-MuJoCo interaction closure remains valid evidence for the
historical structured path:

```text
.chromie/acceptance/text-mujoco/20260617T081411Z
```

That run completed ordered `soridormi.walk_velocity`, `soridormi.nod_yes`, and
`soridormi.turn_in_place` execution and returned MuJoCo to safe idle. It does
not validate the current Goal-driven Runtime, physical microphone/speaker
quality, a physical robot, Jetson packaging, or unattended operation.

The latest recorded broad automated baseline before this authority/provenance
hardening is the 2026-07-14 checkpoint: 926 unittest cases, 20 legacy Agent
tests, 381 file-backed scenarios, and 50 General Ability Level A probes. Treat
those as historical counts, not a fresh pass for the current source. Rerun the
canonical gates before making a new automated-evidence claim.

## Resume Sequence

1. Keep physical-motion and legacy-semantic-fallback gates off.
2. Run the semantic-authority audit and focused authority tests. Confirm that a
   claim for another turn never reaches the legacy planner model.
3. Run documentation, canonical tests, cognitive scenarios, and General
   Ability Level A from the candidate source. Report actual results; do not
   copy historical test counts forward.
4. Start the maintained Soridormi/MuJoCo profile and collect isolated live-text
   cases through cognitive `apply`. Retain Goal Association, planner,
   composition, trusted execution, terminal status, safe-idle, and exact source
   provenance. First add endpoint-reported Soridormi source identity; choosing
   a sibling checkout with `--soridormi-repo` is not execution provenance.
5. Build a cognitive acceptance bundle from the new simulator summary and
   require applied `chat` and `robot_action` lanes where exercised. Reject any
   bundle with absent or mismatched revisions.
6. Keep the checked-in Soridormi capability manifest and release compatibility
   revision aligned before previewing release packaging.
7. Bind the running Chromie service images and loaded models to the candidate
   revision, and replace mutable release image references with immutable ones.
8. Do not publish `0.0.1` or clear a release blocker until the exact supported
   scope has matching implementation, documentation, and retained evidence.
9. Continue physical pilot and human voice-device validation only as separate
   tracks; neither is implied by simulator evidence.

## Useful Commands

Run static authority and Level A gates:

```bash
python scripts/semantic_authority_audit.py --check
python scripts/check_docs.py
./scripts/run_tests.sh
python scripts/cognitive_runtime_acceptance.py --mode check
python scripts/cognitive_runtime_acceptance.py --mode level-a
python scripts/general_ability_acceptance.py --mode check --no-write
python scripts/general_ability_acceptance.py --mode level-a --no-write
```

Run a natural request through the maintained cognitive text-to-MuJoCo path:

```bash
conda run -n Chromie python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --cognitive-runtime \
  --cognitive-apply-lanes chat,robot_action \
  --no-speaker
```

Check the applied event lane, then create a provenance-checked cognitive bundle
after that new run:

```bash
python scripts/cognitive_runtime_acceptance.py --mode evidence \
  --require-applied-lane robot_action
python scripts/cognitive_runtime_acceptance.py --mode bundle \
  --text-mujoco-summary .chromie/acceptance/text-mujoco/<run-id>/summary.json
```

Use `--no-cognitive-runtime` only for an explicitly labelled legacy
compatibility investigation. It is not the maintained acceptance path.

## Files To Read First

- [Project Charter](PROJECT_CHARTER.md)
- [Human-like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md)
- [Current Status](STATUS.md)
- [Roadmap](../ROADMAP.md)
- [Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md)
- [Goal-driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md)
- [Goal-driven Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md)
- [Acceptance and Evidence](ACCEPTANCE.md)
