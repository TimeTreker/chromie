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
  body behavior.

### Verification and reproducibility

- Replaced the obsolete GPU control-plane smoke flow with immutable Gateway/Core
  requests, typed Core results, current Fast Planner projection, and no `/run`
  dependency.
- Added deterministic source-tree identity for archive builds that do not
  contain `.git`, while retaining Git revision and dirty-state metadata for
  development checkouts.
- Added benchmark integrity checks to the canonical test entrypoint.
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
