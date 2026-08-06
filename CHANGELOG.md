# Changelog

This file records notable current changes. Detailed earlier development history
remains available in Git history.

## Unreleased

### Semantic authority and failure honesty

- Added a typed `CoreInterpretationUnavailable` response. A non-empty turn that
  cannot be interpreted no longer becomes generic chat or another invented
  semantic lane.
- Added strict catalog-backed action proposals to capability-grounding repair,
  including ordered compound robot actions with schema validation.
- Moved maintained memory turns into the Goal-driven apply lanes and made
  excluded mapped lanes fail closed without legacy semantic re-entry.
- Kept emergency compatibility planning separately gated and unavailable to
  ordinary maintained turns.
- Split vocal Goal semantics into typed completion modality, lane, output mode,
  and exact-provider need. Mode-specific vocal performance now fails closed
  instead of being completed by generic response text, ordinary TTS, media, or
  body behavior. Mutually inconsistent typed Goal tuples now trigger a fresh
  model-owned resegmentation from the authoritative turn without supplying the
  invalid DTO as semantic evidence.

### Verification and reproducibility

- Replaced the obsolete GPU control-plane smoke flow with immutable Gateway/Core
  requests, typed Core results, current Fast Planner projection, and no `/run`
  dependency.
- Added deterministic source-tree identity for archive builds that do not
  contain `.git`, while retaining Git revision and dirty-state metadata for
  development checkouts.
- Added benchmark integrity checks to the canonical test entrypoint.
- Restored the incremental Mypy gate to its last dependency-complete, verified
  four-file baseline after an unexecuted package-scope expansion exposed 169
  pre-existing type errors in CI. Package expansion remains separate cleanup
  work and may return only after the complete added scope passes.
- Added a fail-closed vocal Issue #1 closure runner that binds the canonical gate,
  deployment identity, exact typed Goal/Plan evidence, Soridormi/MuJoCo body
  completion, honest singing unavailability, and optional authenticated Issue
  closure to one clean revision. The runner now understands the canonical keyed
  `goal_outcomes` map, reuses or starts the maintained headless paired stack,
  stops before downstream work when a prerequisite fails, and retains the exact
  command error instead of a generic failure label.
- Pinned third-party GitHub Actions by commit and added Python 3.11/3.12 CI
  coverage for the GPU-free control plane.
- Reduced default unit-test console noise while preserving warnings and errors.

### Architecture and documentation

- Updated semantic-authority, runtime-rollout, API, configuration, runbook, and
  status documentation to match the maintained lanes and typed unavailable
  contract.
- Replaced stale copied source metrics with executable ratchets and marked the
  composition-root method-count reduction as active rather than complete.
- Removed obsolete implementation plans, handoff snapshots, historical audit
  narratives, and legacy runtime documents after migrating durable facts to
  current architecture, policy, status, roadmap, API, and operations owners.
- Lowered documentation-surface ratchets to the consolidated current tree.

### Existing maintained foundations

- Cognitive Gateway admission, immutable turn envelopes, Goal Interpretation,
  Goal Association, Fast/Deep planning, response composition, trusted capability
  execution, and outcome evidence remain the maintained control-plane path.
- Deterministic stop, cancellation, confirmation revocation, playback ordering,
  typed configuration ownership, repository policies, benchmark integrity, and
  release-provenance checks remain in force.
- Agent Skills remain passive cognitive content; capability providers and the
  Host retain effect authorization and execution authority.
