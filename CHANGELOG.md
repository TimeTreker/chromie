# Changelog

This file records notable current changes. Detailed earlier development history
remains available in Git history.

## Unreleased

- Collapsed physical-object and information fetch/delivery into one canonical
  `AcquireAndDeliverResource` semantic responsibility. `resource.kind` and
  `delivery_mode` now drive provider matching; legacy `responsibility_variant` is
  input-only compatibility, not a planner concept. Capability semantic scopes may
  advertise multiple `delivery_modes`, allowing Soridormi physical delivery and
  weather/external-information acquisition to implement the same human-level
  responsibility without sharing a provider or planning authority.

### Goal Progress Communication

- Defined Fast Response as the first milestone of a shared Goal Progress
  Communication responsibility rather than task confirmation or Social Attention.
- All speech-capable cognitive stages now receive one shared progress-communication
  principle: communicate only a new, trustworthy, user-relevant milestone and use
  Interaction Context to avoid repeated acknowledgements or status narration.
- Made the initial Fast Response normally responsive rather than silence-biased:
  once Goal Interpretation has understood a nontrivial Goal that still needs
  downstream work, it should give one tiny polite prospective notification unless
  the substantive answer is immediate, an equivalent notification already exists,
  the user requested silence, or another line would only repeat or add empty chatter.
- Removed the production Fast-speech reviewer entirely. Goal Interpretation is the
  sole semantic owner of its Fast Response; Host/runtime code validates only typed,
  evidence, cancellation, and transport invariants. Semantic mistakes are fixed at
  the source prompt/model boundary and measured by regression/benchmark scenarios.
- Removed the redundant tool-only Fast Response gate and the pre-commit memory mute;
  all eligible downstream-work routes use the same source-authored prospective
  notification contract, while memory wording still cannot claim a completed commit.
- Made the model-facing Fast Response decision required-but-nullable: Goal
  Interpretation must return either one short `fast_speech` notification or explicit
  `null`; it can no longer silently omit the responsibility. The Host now derives the
  deterministic route-specific claim envelope instead of asking the fast model to
  copy those invariants.
- Removed the prompt contradiction between structured Goal Progress Communication
  and the old blanket ban on "progress text"; only free-form progress narration
  outside the structured speech field is forbidden.
- Preserve a Fast Planner progress candidate across unrelated escalation only as an
  `undelivered_advisory` for Deep Planning. It never counts as heard speech and must
  still be reconciled with Interaction Context and current evidence.

### Interaction-delta cognition contract

- Restored planner-authored prospective `response_text` for executable Plans;
  response transport remains outside task steps, while Interaction Context—not a
  blanket execute-speech ban—prevents duplicate acknowledgements.
- Made the shared Interaction Ledger / still-needed-delta rule explicit across
  Goal Interpretation, Goal Association, Fast and Deep Planning, Tool Result
  Interpretation, and Response Composition.
- Kept the Interaction Ledger as the only cross-stage continuity authority for
  Goal progress speech. Later stages infer the still-needed communication delta from
  actual delivered/pending speech and Goal/runtime evidence; the obsolete
  `fast_interaction_decision` reviewer projection was removed.
- Replaced scenario-answer instructions in coordinated-action review with
  general semantic entailment and Capability-contract principles; concrete
  distinctions remain benchmark/regression responsibilities.
- Reduced Goal Association's live completion contract to the semantic
  `output_mode` choice (plus media operation when applicable); the Host now
  materializes `responsibility_kind`, `execution_lane`, and `provider_required`
  deterministically instead of asking the LLM to copy a valid tuple.
- Removed route-specific hard-coded pre-dispatch failure speech; the bounded
  failure composer now receives the trusted facts and must describe only the
  user-visible missing result/effect without exposing planner/workflow language.

### Post-merge audit remediation

- Registered every normally scheduled interaction utterance in the same
  delivered-turn evidence ledger used by fast-first and cached speech, so played
  final speech can be correlated instead of appearing as an empty delivery.
- Updated generated-speech acceptance to recognize the current
  `cognitive_core_done` semantic receipt and deterministic
  `cognitive_gateway_reflex_applied` interrupt receipt while retaining the old
  Goal Interpretation event only for compatibility evidence.
- Made Goal Association resegment mechanical action-collection and location-
  provenance failures from the authoritative turn rather than anchoring repair
  on an invalid DTO, and clarified that stable knowledge and ordinary reasoning
  are spoken responsibilities unless fresh non-vocal evidence is required.
- Replaced the repeated invalid Goal Interpreter retry with an error-directed
  typed-contract repair. If the repaired model response still adds durable-only
  fields to explicit session/ephemeral memory, a logged mechanical recovery may
  only remove authority; durable, profile, forget, and clear contradictions
  remain fail-closed.
- Restored source-authored tool acknowledgements under the exact
  `acknowledge_and_check`/`checking_only` claim contract. Playback start remains
  the delivery boundary and de-duplication uses event identity and structured act
  state rather than text comparison. The Interaction-delta contract above
  supersedes the temporary pure-safe-read mute: later stages reuse an equivalent
  Fast act, or may author only a genuinely new prospective conversational delta
  before grounded result/failure speech.
- Added the independently controlled, typed, versioned
  `chromie.interaction_session_capture` Data Loop policy. Each SID snapshots its
  policy at start, reuses existing input/trace/Episode evidence providers, and
  seals complete, abandoned, or recovered immutable packages with explicit
  artifact digests, missing state, governance, runtime identity, and downstream
  candidate provenance. Debug audio and offline evaluation remain independent.
- Added one bounded evidence-preserving repair when Tool Result Interpreter
  output is otherwise grounded but violates its response contract, and made
  decision follow-ups answer the requested decision before the smallest useful
  supporting evidence. Retained-Goal responses now receive an executable
  model-owned communication review from the existing stronger Agent model;
  review may revise response text only and fails closed without effects.
- Preserved valid planless direct speech when optional Social Attention is
  malformed or empty by reducing the auxiliary proposal to explicit stillness
  before nested validation, without selecting behavior or rewriting speech.
- Required direct and planned response composition to ground user-specific
  circumstances in the current turn, Goals, or supplied conversation instead
  of inventing a helpful-sounding personal schedule or situation.
- Corrected semantic-authority, compatibility-fallback, current-status,
  acceptance, configuration, latency, scenario-authoring, and resume-point
  documentation found stale by the audit. Executable weather scenarios now
  assert dynamic pre-effect suppression instead of the obsolete acknowledgement
  requirement.
- Prevented the comprehensive runner from rebuilding an image underneath its
  own running containers, made built services recreate against the new image,
  removed an unsupported dirty-verifier option, and stopped applying the full
  seven-case MuJoCo release verifier to a three-case diagnostic voice bundle.

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
- Added the exact `chromie.vocal.perform` contract. Qualified providers declare
  mode-specific retained evidence, streaming, timing, sample, concurrency,
  cancellation, and immutable provenance properties; unsupported modes and
  silent downgrades fail closed. Provider vocal Goals now pass through canonical
  planning instead of the ordinary direct-speech shortcut, remain in Vocal
  during cross-lane coordination, and retain one identity through cancellation
  and outcome evidence. The default catalog still advertises no qualified mode.
- Retained clean default-provider Level C evidence for `e558ff4`: the original
  walk/sing/blink turn completed both body members in Soridormi/MuJoCo, kept
  singing unavailable with no step, played all four ordinary-TTS chunks without
  failure, and returned to safe idle. This closes Issue #6's declared source
  scope without claiming a real singing provider or physical audio.
- Added the exact peer-media Activity family
  `chromie.media.play|pause|resume|seek|stop|volume|status`. Qualified providers
  now declare supported media kinds, persistent lifecycle/progress,
  cancellation, mixer parameters, immutable provenance, and operation-specific
  evidence. Exact operation/state mismatches fail closed, speech overlap carries
  an explicit ducking contract without Goal mutation, and stop-talking,
  stop-media, and stop-all produce distinct scoped receipts. The default catalog
  remains unavailable and no physical playback claim is implied.
- Retained default-provider text-to-MuJoCo evidence that keeps media play as an
  unavailable Activity, keeps singing as planless Vocal, completes the
  independent Soridormi walk in a mixed request, and returns safe-idle. The
  primary-text live runner now dispatches deterministic controls through the
  production Cognitive Gateway path and retains its cancellation receipt; a
  Chinese stop-media probe bypasses cognition with exact `media_output` scope.

### Verification and reproducibility

- Made speech-start barge-in reversible: the Host now ducks only the active
  playback generation while ASR distinguishes external speech from likely TTS
  echo, compares distorted ASR against the relevant scheduled output chunks,
  then either resumes the next unplayed chunk or closes and invalidates output
  before the Cognitive Gateway owns semantic cancellation. Focused voice
  acceptance now replays retained output PCM, enforces 250 ms acoustic budgets,
  waits for clean case completion, and retains application-level TTS readiness.
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
