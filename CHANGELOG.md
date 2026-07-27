# Changelog

All notable user-visible changes should be recorded here.

## Unreleased

### Gateway/Core qualification workflow

- Added one maintained, resumable `collect` / `status` / `finalize` command for
  source-bound Gateway/Core qualification. The workflow fingerprints every
  retained artifact, derives cancellation inputs from the versioned manifest,
  creates only a pending human-review record, and delegates closure eligibility
  to the existing fail-closed verifier.

### Cognitive Gateway/Core mainline restored

- Restored Cognitive Gateway decomposition and Core-entry migration as the sole
  active architecture issue; Social Attention qualification is paused until the
  single-authority cognitive path is complete.
- Defined the implementation target: five explicit Gateway modules, pre-Core
  admission, envelope-first Core API, isolated compatibility route projection,
  and source-bound live-text/MuJoCo evidence.
- Implemented the five physical Gateway modules, digest-bound context snapshots,
  focused fail-open attention review, and final Turn Admission before Goal
  Interpretation.
- Changed `/cognitive-core/interpret` to require `CoreTurnRequest` and return a
  Core-owned `CoreInterpretationResult`; the Goal-driven Runtime validates and
  consumes that result while retaining `RouteDecision` only as a digest-bound
  compatibility projection.
- Added launcher-effective Gateway Attention model identity and automatic
  contract, configuration, profile, Compose, and runtime-verification coverage.
- Removed the post-admission direct-LLM fallback on Core failure. A failed Core
  turn now returns only a conservative language-matched, speech-only operational
  failure response and never creates a second semantic authority.
- Added digest-bound runtime identity capture for exact source, generated profile,
  launcher-effective models, running service images, Agent runtime identity, and
  capability manifests; cognitive evidence events now carry that identity.
- Added maintained live-service Gateway/Core qualification cases for ambient
  suppression, deterministic stop, direct admission, weather lookup, and
  evidence-backed follow-up continuity without injecting expected semantics.
- Added source-bound MuJoCo verification for endpoint-reported Soridormi revision,
  compound named-skill execution, correlated outcome evidence, and explicit
  pre/post safe idle.
- Included Tool Result Interpretation in the CosyVoice one-resident-model override
  so weather/tool turns use the recorded launcher-effective topology rather than
  cold-loading an omitted profile model.
- Added a bounded Skill Runtime execution observation, active-Goal cancellation
  qualification after real Provider start, exact stop/reflex verification, and
  post-cancel safe-idle evidence.
- Tightened Issue closure so it requires live-text, normal MuJoCo, active
  cancellation, exact identity/provenance, and a fingerprint-bound approved human
  review; release qualification remains false.

### Prior architecture corrections

- Removed legacy CapabilityAgent semantic skill substitution and argument
  reinterpretation; compatibility planning preserves the exact model-selected
  named skill and schema-valid arguments.
- Removed provider backend identity and calibrated yaw/pitch details from
  model-facing Social Attention candidates and target evidence; provider-owned
  calibration schemas fail closed from cognitive discovery.

### Social Attention qualification run-scope integrity

- Formally closed the Benchmark Suite foundation after confirming the reviewed
  scenario-migration commit is present on `main`.
- Added launcher-effective Social Attention mode to E2E run identity and changed
  baseline qualification from one mixed report to a bundle of homogeneous
  mode/style reports.
- Added fail-closed identity, scope, duplicate, unexpected-result, and complete
  128-case coverage checks without adding behavior policy, phrase mappings, model
  selection, or automatic release qualification.

### Social Attention baseline qualification foundation

- Added a versioned qualification manifest with deterministic hard gates, required effective runtime identity, and an explicit denial of Runtime policy authority or automatic release qualification.
- Added first-party environment-resolved E2E adapters, Social Attention cohort selectors, lifecycle evidence for proposal/materialization/provider completion, and fail-closed hard-gate reporting.
- Added qualification tests and documentation without adding phrase mappings, scenario-ID branches, fixed gestures, Runtime quotas, or automatic model selection.

### Benchmark scenario migration and reviewed mining closure

- Made one migration manifest authoritative for maintained scenario sources while preserving 527 inventory entries, 526 normalized semantic scenarios, stable IDs, source provenance, existing evidence claims, and criteria-based compatibility removal schedules.
- Added a Benchmark-native deterministic scenario entrypoint and removed duplicate source classification from the compatibility suites manifest.
- Connected immutable episode-derived candidates to deterministic indexing, related/historical-regression detection, fingerprint-bound human review, controlled variation authoring briefs, and approved deterministic promotion.
- Kept automatic commit, Prompt mutation, personality/safety changes, Runtime policy authority, training promotion, and release qualification disabled.

### Stress and behavior-distribution Benchmark evaluation

- Added six versioned workload families for long sessions, repetition/cooldown, interruption, concurrency, provider degradation, and synthetic multi-user context isolation.
- Added deterministic seeded sampling, E2E evidence-profile reuse, bounded concurrent execution, explicit run conditions, partial-evidence preservation, and observational distribution reports with sample counts and 95% intervals.
- Added compatible model/Prompt/MindProfile/provider/code comparison without selecting a winner, auto-qualifying a release, prescribing gesture rates, or adding production Runtime behavior rules.

### End-to-end Benchmark execution and evidence profiles

- Added six explicit E2E evidence profiles spanning replay, live model, deployed text, virtual audio, MuJoCo simulation, and supervised physical execution without changing semantic scenario contracts.
- Added correlated evidence, execution-claim ceilings, timing observations, partial-evidence retention across timeout/failure, and fail-closed qualification summaries.
- Kept automatic reports non-release-qualified and required human approval for final qualification; no production Runtime behavior or scenario-specific policy was added.

### Comprehensive Social Attention benchmark dataset

- Added 128 reviewed Social Attention cases across 16 cohorts covering everyday interaction, tools, explicit robot actions, multi-turn context, interruption, empathy, style, user preferences, repetition/cooldown, policy modes, safety conflicts, bilingual input, ASR ambiguity, and historical regressions.
- Added deterministic coverage, normalization, duplicate, fixed-gesture, backend-leakage, stillness, `off`, and `report_only` validation without introducing production behavior policy.
- Added a deterministic coverage report, CI-safe validation command, and focused dataset tests; all cases keep `none` as a valid auxiliary decision and retain human approval for final release qualification.

### Router removal final repository audit

- Re-ran the maintained full test entrypoint after applying the complete Router-removal sequence and repaired all remaining environment, Compose, trace, scenario, and contract drift.
- Embedded all Goal Interpreter configuration in the Agent service, removed stale current-architecture Router language from authoritative documents, and retained Router wording only for explicitly historical evidence or removal guards.
- Strengthened the removal guard against stale service, endpoint, configuration, and current-document claims. The maintained test suite, documentation checks, Benchmark inventory/tests, Compose parsing, and Python compilation now pass together.

### Router removal final closure audit

- Removed the remaining 8091/Router developer-tool, documentation, test-matrix, metadata, provenance, and prompt-tier contracts.
- Restored the full repository test entrypoint after the Goal Interpreter was integrated into the Agent service.
- Removed unused Host-authored weather acknowledgement composition so dynamic fast speech remains model-authored.
- Strengthened the removal guard across active code, tests, configuration, and developer tooling.

### Router architecture removal closure

- Removed the independent Router service, client, container, health path, and runtime ownership.
- Moved ingress responsibilities to Cognitive Gateway and ordinary semantic interpretation to the Goal-Driven Cognitive Core.
- Corrected stale startup, release-provenance, API-reference, observability, and benchmark terminology left by the initial R1-R4 migration.
- Removed a fixed weather-to-tool prompt mapping; tool selection remains model reasoning over capability descriptions and bounded context.
- Strengthened the repository guard so deleted Router service paths, clients, endpoints, environment namespaces, and first-class architecture declarations cannot return.


### Cognitive Gateway benchmark alignment

- Replaced the newly introduced first-class `router` Benchmark adapter with the
  settled `cognitive_gateway` ingress boundary.
- Reclassified legacy Router and Router-dialogue scenario directories as retained
  compatibility regressions instead of current module architecture.
- Added terminology regression guards and clarified Goal-Driven Cognitive Core ownership.

### Chromie Benchmark Suite design

- Added the constitutional rule that benchmarks evaluate model intelligence but must not become phrase-, regex-, scenario-ID-, or fixed-action runtime policy.
- Defined a layered benchmark architecture for module, integration, end-to-end, stress, regression, datasets, and reports.
- Defined acceptable behavior regions, deterministic hard gates, distribution metrics, Social Attention coverage axes, and reviewed LLM-assisted scenario authoring.
- Classified existing scenario sources for index-first migration and added a staged implementation plan beginning with a deterministic manifest and inventory.

### Social Attention closure and regression matrix

- Added owner/operator-selectable `courteous`, `neutral`, and `reserved` Social Interaction Style presets, with reviewed `custom` guidance available through a full MindProfile JSON.
- Added `ORCH_SOCIAL_INTERACTION_STYLE_PRESET` as the ordinary deployment input while preserving owner approval, primary-task priority, and provider-owned safety.
- Added eight deterministic end-to-end Social Attention regression scenarios covering greeting, thanks, neutral factual turns, reserved stillness, cooldown/repetition, impatient users, explicit no-gesture requests, and `report_only` non-execution.
- Corrected stale mind documentation that still described Social Interaction Style as unimplemented, and extended the semantic-authority audit to guard the preset contract and regression matrix.

### Backend-neutral ability and confirmation boundary

- Completed the Social Attention architecture closure audit: stale calibration fallback language is removed and offline guards now enforce semantic-only target evidence, owner-approved MindProfiles, and the `on` health default.
- Aligned active MindProfile approval enforcement and Agent health defaults with the owner-approved, Social Attention-on runtime contract.
- Moved all Social Attention calibration, body-coordinate, joint-target, and controller-parameter ownership below the Chromie boundary; model-facing target evidence is semantic only.

- Removed backend-scoped states from Chromie's static ability
  ontology. Provider-backed body skills are no longer activated from Host dry-run,
  simulator, or hardware settings.
- Removed the legacy simulator-derived confirmation flag and every backend-mode confirmation
  branch from the Host runtime, launchers, configuration, diagnostics, tests, and
  active documentation.
- Made the live Soridormi/provider catalog authoritative for each named skill's
  effective confirmation requirement. Material alternatives and post-interrupt
  physical resume still require fresh Host-owned confirmation independent of the
  provider backend.
- Replaced backend-specific acceptance confirmation controls with an explicit,
  backend-neutral diagnostic confirmation grant.
- Deleted the legacy Host-generated deep-thought body gesture, its fixed static
  ability entry, and the coordinator metadata bypass that could silently suppress
  provider or confirmation failures. Deep-thought prelude behavior is now speech-only
  unless the model-authoritative Social Attention path independently proposes an
  auxiliary provider skill.

### Embodiment-independent Social Attention and personality policy

- Reduced the public policy to `off`, `report_only`, and `on`, with `on` as the
  maintained default. Legacy simulator-scoped configuration migrates to `on`
  only at the environment boundary.
- Added the owner-approved `SocialInteractionStyle` to `MindProfile`, covering
  bounded courtesy, expressiveness, initiative, restraint, cooldown, and
  repetition guidance.
- Supplied the style and bounded recent accepted auxiliary-request evidence to
  Response Composer without treating request acceptance as execution evidence.
- Removed provider backend filtering and Chromie-owned installation calibration
  from candidate discovery, Composer validation, compatibility planning, Host
  materialization, launch profiles, and maintained scenarios.
- Required auxiliary Social Attention to remain parallel, optional, and
  conflict-free. Explicit user actions, speech, stop, emergency handling, and
  primary execution retain priority.
- Preserved backend-stable named-skill and semantic-argument contracts while
  leaving controller adaptation, calibration, motion limits, collision safety,
  stop, recovery, and execution evidence in Soridormi/provider.

### Response-only chat planning and complete CosyVoice warmup

- Made Fast and Deep planner schemas enforce the source-route effect envelope.
  Conversational `chat` turns receive no executable capability catalog, permit
  no plan steps, and cannot become robot-action plans.
- Closed the model-facing per-goal outcome contract so `execute` outcomes cannot
  carry `response_text`; invalid execute-plus-speech output is rejected during
  bounded planner repair instead of failing after canonical materialization.
- Warm `chromie_zh`, `chromie_en`, and `chromie_mixed` explicitly before the
  microphone opens. The old default-plus-Chinese warmup left the English and
  mixed reference paths cold, causing the first English greeting to take about
  twenty seconds under shared GPU load.

### Portable TTS voice bind paths

- Normalize `TTS_VOICE_ROOT` to an absolute host path in normal startup,
  service-only startup, and candidate A/B runs before Docker Compose
  interpolation.
- Use explicit Compose bind mounts for the CosyVoice catalog and Qwen mixed
  reference, preventing relative catalog paths from being interpreted as named
  volumes.
- Fail cleanly on invalid catalogs without cascading into an unbound Bash array.

### Evidence-bound tool-result interpretation

- Made the no-active-Goal segmentation schema expose its non-empty semantic
  invariant to the constrained decoder. A standalone greeting or other social
  act must now become one model-authored conversational Goal, or a non-empty
  clarification, instead of reaching generic fail-closed speech with two empty
  alternatives.
- Added a general `ToolResultInterpretation` contract and Agent stage. Complete
  schema-validated tool output remains retained as evidence, while the model
  selects exact evidence IDs and JSON Pointers and produces only the direct,
  summarized, or explicitly requested detailed answer.
- Added trusted validation for selected fact references, unsupported numeric
  claims, internal identifiers, raw-payload narration, sentence count, and
  spoken length. Invalid interpretation uses an adapter-owned compact fallback
  or the conservative post-execution response.
- Routed built-in weather results and canonical Skill Runtime observations
  through the same boundary. A narrow weather question now becomes one short
  answer instead of a field-by-field report and multiple TTS utterances.

### Git-controlled built-in Chromie voices

- Added a validated multi-speaker CosyVoice catalog with `chromie_zh`,
  `chromie_en`, and `chromie_mixed`; the mixed profile is the fallback while
  `speaker_id=default` routes Chinese and English requests by language.
- Added a one-time promotion tool that copies the project owner's existing
  AI-generated WAVs from ignored installation state into `assets/tts/voices`,
  generates exact transcript/hash/provenance metadata, and produces the catalog
  manifest for commit.
- Removed the default runtime dependency on `.chromie/private/tts-voice`; clean
  clones use the committed assets. Qwen comparison uses the same committed
  `chromie_mixed` reference.

### CosyVoice3 default TTS backend

- Promoted Fun-CosyVoice3 0.5B to the maintained `chromie-tts` service on port 5000 after repeated Oute Mandarin quality failures and equivalent-provider latency comparisons.
- Added an authorized local reference installer/validator with exact transcript, license identity, and WAV SHA-256 binding; default startup now fails closed when the reference is absent or inconsistent.
- Moved OuteTTS to the explicit `chromie-tts-oute` fallback on port 5001 and kept Qwen3-TTS as the port-5002 alternative. `--tts-backend` selects either without changing persistent configuration.
- Aligned Compose, model locks, GPU/profile verification, application readiness, one-worker concurrency, bounded cancellation drain/restart, fast-first cache identity, tests, and documentation with the new default.

### Fixed-reflex cancellation closure

- Added one atomic Conversation State reconciliation path for `output_only`,
  `embodied_motion`, `current_interaction`, and `global_emergency` receipts.
  Request-level cancellation now closes only the Goals whose remaining committed
  requests are proven stopped.
- Preserved domain-excluded work as recoverable, kept embodied execution unchanged
  when only pre-action speech is stopped, and retained provider failures,
  non-interruptible requests, missing broad-scope selections, and Host-preflight
  cancellation as explicit uncertainty rather than success.
- Committed synchronously revoked broad confirmation tokens with the runtime
  receipt in the same durable transaction. Persistence failure rolls Goal state
  back while the host records the final state as uncertain.
- Separated global-emergency Goal cancellation from Soridormi safe-idle evidence;
  an E-stop dispatch can cancel ledger-bound work without claiming a verified
  safe controller state.

### Named-Goal cancellation closure

- Added the trusted Core-to-runtime bridge for non-urgent named cancellation:
  the Core selects semantic Goal IDs while the host resolves exact interaction,
  plan, fingerprint, and request bindings before dispatching `specific_goal`.
- Added exact receipt validation and one Conversation State transaction that
  applies target cancellation, provider-scope collateral Goal transitions, and
  confirmation-state changes only after trusted runtime evidence is available.
- Added partial confirmation rebuilding for separable multi-Goal responses. The
  parent plan remains immutable; unaffected work receives a fresh child plan,
  new request identities, and a new single-use token. Shared-owner steps fail
  closed instead of being split implicitly.
- Propagated Goal/plan authority through cognitive speech requests and made the
  shared local output provider report truthful `output_only` widening rather
  than pretending to retract one request from global playback.
- Distinguished pre-dispatch rejection from post-dispatch uncertainty. If a
  provider cancellation was attempted but receipt reconciliation or durable
  Goal-state commit fails, Chromie reports the final state as uncertain instead
  of claiming the action never started. Shared-owner confirmation requests leave
  both the original token and Goal state unchanged.

### Core contract audit

- Added one shared validator for closed, explicit provider output schemas and
  applied it before canonical-plan commitment as well as during execution
  closure. Empty, wildcard, composed, untyped, or low-level robot schemas now
  fail before their data can become model-visible.
- Made both the Agent-visible and trusted-runtime Soridormi catalog refreshes
  atomic, aligned their nested availability/execution/confirmation parsing, and
  assigned every dynamically imported named skill a stable adapter-owned result
  schema. Successful body execution is projected into that bounded result
  envelope instead of exposing an undeclared provider payload.
- Added a closed TaskGraph result envelope and changed missing, pending,
  running, or unknown graph states from implicit success to explicit failure.
  Only a declared terminal `success` may produce a completed SkillResult.
- Changed the legacy Action executor to fail closed when no Action Client is
  configured instead of reporting an unexecuted action as completed.
- Removed user-text weather recovery and standalone-gratitude phrase routing.
  Normal tool and social intent now remains model-authored and
  contract-validated; inconsistent weather contracts receive one semantic
  repair and otherwise clarify.

### TTS provider evaluation

- Added a versioned, stream-oriented `TTSProvider` contract for lifecycle,
  immutable model provenance, license identity, language/rate capabilities,
  native streaming, cancellation, speakers, health, PCM, and metrics.
- Migrated the maintained OuteTTS/llama.cpp worker path behind an explicit
  adapter and fail-closed registry while preserving the WebSocket and
  Orchestrator playback/interruption boundaries.
- Added one shared Mandarin, English, mixed-language, interruption/recovery,
  six-turn dialogue, and concurrency matrix plus a multi-endpoint runner that
  retains WAVs, objective metrics, and a mandatory listening-review template.
- Added separate, profile-gated Fun-CosyVoice3 0.5B and Qwen3-TTS 0.6B Base
  images with immutable runtime/model locks, one hashed local reference voice,
  restart-on-cancel workers, and an isolated build/deploy/compare/restore
  workflow; the maintained Oute default is unchanged.
- Fixed a missing Oute timing-helper import found by the deployment workflow
  and added a direct generation-stage regression test.
- Completed the initial isolated RTX 5090 deployment matrix with 6/6 objective
  cases for each candidate; retained the ordinary-latency versus
  interruption-recovery tradeoff without selecting a winner, and added
  run/source dirty-state metadata for future comparison evidence.
- Added exact-transcript OuteTTS speaker creation with pinned Whisper alignment,
  content checks, and private speaker artifacts; created English, Chinese, and
  mixed profiles from the authorized AI-generated voice candidate while
  retaining the observed longer mixed-prompt failure as an open blocker.
- Let the isolated candidate runner consume an existing authorized,
  SHA-256-bound reference and preserve its voice-license declaration. A second
  6/6-per-provider run with that voice reproduced the CosyVoice3 ordinary
  latency versus Qwen3-TTS cancellation-recovery tradeoff; candidate-output
  listening and provider-selection gates remain open.
- Tested the owner-approved voice style as a possible Oute default, then kept
  the built-in speaker after rebuilt-container checks reproduced token
  exhaustion with both mixed and Chinese-aligned profiles. A later root-cause
  audit found those profiles contained only one DAC code pair because the
  soundfile fallback returned a two-dimensional tensor where OuteTTS requires
  batch, channel, and sample axes. Fixed the loader, added acoustic-coverage
  validation and automatic invalid-profile rebuild, isolated mutable Oute
  prompt data per request, and synchronized profile reloads across workers.
- Regenerated `chromie_mixed` with 776 DAC code pairs covering all 28 aligned
  words. The corrected profile passed a 10/10 multilingual smoke and two
  complete 6/6 Mandarin/English/mixed/interruption/dialogue/concurrency runs at
  an RTX 5090 8192-token context. That profile is now the installation-local
  selected speaker; private WAV/JSON artifacts remain ignored and the portable
  repository default still falls back to Oute's built-in speaker when no local
  profile is installed.
- Diagnosed OuteTTS enrollment-prompt leakage in short Chinese
  `chromie_mixed` cues. Fast-first cache v2 now keys audio by provider/model and
  speaker revision, enforces a short-cue duration bound, and rejects requested
  text that fails an ASR round trip before playback.
- Added `--tts-trial cosyvoice` for a reversible one-session listening check
  against the owner-authorized local reference; it does not modify the normal
  provider configuration or select a winner.
- Fixed the CosyVoice candidate's ONNX Runtime/cuDNN mismatch by moving to the
  cuDNN 9-compatible 1.18.1 wheel, persisted its WeText ModelScope cache, and
  added one bounded regeneration for short cues that fail the unchanged ASR
  content gate. The rebuilt candidate initialized CUDA ONNX execution and all
  six bilingual acknowledgement cues passed; this remains trial evidence.
- Fixed the full-stack CosyVoice trial's pre-microphone failure: the temporary
  launcher now uses one compact Ollama model across all cognitive lanes, limits
  Ollama to one resident model, and avoids generating missing fast-first cues
  during startup. Individual synthesis timeout stops remaining cache work,
  total prime timeout is non-fatal on Python 3.10, and the readiness banner no
  longer claims voice interaction is ready before the host microphone starts.
- Matched the temporary CosyVoice trial to its single model worker, replaced
  TCP-only ASR/TTS readiness with application WebSocket health, required one
  complete no-playback warm synthesis, and added bounded cancellation draining
  before fail-closed worker reload. Health now distinguishes drained
  cancellations from restart recovery.
- Made the top-level launcher check the host Orchestrator's exclusive lock
  before changing generated runtime files or recreating services. An old
  microphone/goal-state process can no longer remain silently attached to new
  containers during a service-only rebuild.
- Documented Qwen3-TTS and Fun-CosyVoice3 as primary comparison candidates,
  OuteTTS as the maintained baseline, and license/target evidence as required
  gates before changing the default.

### Router addressedness

- Added host-owned engagement evidence and semantic addressedness/subject
  ownership review so unrelated nearby technical speech can fail silently
  instead of collapsing into a Chromie capability answer. Direct questions,
  greetings, requests, Chromie's name, active tasks, and recent accepted turns
  remain engaged; ignored ambient turns do not extend engagement.
- Kept isolated low-information ASR fragments behind clarification even when
  completed tasks remain in bounded conversation history; only an explicit
  confirmation or clarification wait supplies strong follow-up context.
- Fixed the addressedness reviewer silently vetoing a correctly grounded direct
  question such as `今天北京下雨了吗？`. The focused contract now classifies
  speech act explicitly, permits suppression only for bounded inactive ambient
  acts, and fails open on direct, unclear, malformed, or question-form
  contradictions while preserving inactive contextless-reply suppression.
- Retained that July 23 failure as
  `router/inactive_direct_weather_question_false_addressedness`: the scenario
  replays inactive host engagement, a grounded weather-tool decision, and the
  false `addressed=false` question review through the real Router pipeline.
  Standalone Router fixtures can now supply bounded `stub.context` for this
  class of host-to-Router regression.

### Goal lifecycle and truthful embodied speech

- Bound semantic goal IDs to their distinct host task contexts and to scoped
  speech, skill, and confirmation request IDs, so compound goals independently
  reach completed, refused, failed, timed-out, or cancelled lifecycle states.
- Added a route-effect authority envelope: a conversation turn cannot become a
  physical terminal plan merely because both cognitive lanes are enabled.
- Removed planner-owned exact-execution speech and pre-execution progress/final
  projection. The trusted adapter now derives prospective action cues from the
  validated plan and actual confirmation state.
- Required response delivery to reach playback start before dependent physical
  effects, and invalidated all queued utterance chunks on delivery timeout so
  delayed synthesis cannot announce an action after it was stopped.

### Runtime observability

- Added a default-off, architecture-independent Runtime Trace foundation with
  stable module descriptors, nested synchronous/asynchronous spans, monotonic
  duration measurement, wall-clock correlation, bounded attributes,
  `contextvars` propagation, and immutable complete or abandoned snapshots.
- Added cross-service trace carriers and mergeable Agent fragments so the
  Orchestrator can reconstruct the actual cognitive/model topology without a
  fixed Router/Planner schema.
- Instrumented the goal-driven coordinator, canonical plan adapter, cognitive
  Agent service calls, Goal Association, Fast and Deep Planning, Response
  Composer, and Ollama model calls while retaining existing `timings_ms` fields.
- Added reproducible trace summaries with inclusive/exclusive module time,
  largest items, user-observable latency support, parallel leaf-work analysis,
  and a versioned interval/topology critical-path approximation.
- Added optional `chromie.interaction_trace` Runtime Event packages and active
  trace attachment to cognitive-integrity incidents.
- Added detached per-session Runtime Traces plus execution, action-provider,
  TTS, playback, session-lifecycle, and first-audible instrumentation.
- Added generic VAD/ASR trace items, provider acknowledgement, optional
  provider-reported first-motion milestones, and idle-timeout abandonment.
- Added generic process/host/queue/event-loop resource samples, atomic active
  trace checkpoints, process-restart recovery, normal-trace retention policy,
  and late-bound artifact correlation.
- Added default-off non-blocking accelerator telemetry with bounded NVIDIA GPU
  utilization, memory, temperature, and power observations represented as
  ordinary Runtime Trace resource items.
- Added retained Runtime Trace latency reports with environment/provenance
  binding, p50/p90/p95/p99 distributions, module/resource breakdowns, source
  digests, and per-trace correlations.
- Added an evidence-qualified baseline-versus-candidate latency gate that fails
  invalid when sample counts, evidence class, environment, or clean revision
  requirements are not satisfied. The bundled example policy remains disabled
  until a real target baseline is approved.
- Replaced accelerator collection through the event loop's default executor
  with an owned bounded daemon collector. A timed-out telemetry utility can no
  longer hold Python 3.13 event-loop shutdown open for five minutes.

### Consistency and safety audit

- Reconciled Runtime Observability status, roadmap, index, changelog, and
  component documentation with the implemented observability coverage.
- Aligned standalone Agent, Router, ASR, and Orchestrator fallbacks with the
  documented common safe defaults.
- Removed a Sun-specific deterministic conversational rewrite so factual
  wording remains model-authored under the general interaction contract.
- Added a fail-closed capability visibility policy that retains raw planar
  controller-array compatibility tools for trusted runtime use while hiding
  them from language-model catalogs and rejecting visible manifest regressions.

### Goal-driven cognitive runtime rollout

- Integrated Goal Association, complete-coverage Fast Planning, terminal Deep
  Planning, bounded trusted-validator replanning, Response Composition, and
  runtime adaptation behind `off`, `report_only`, and lane-gated `apply` modes.
- Enabled structured interaction and authoritative `chat` apply in the common
  safe base; the maintained Soridormi launcher enables that provider and widens
  authority to `chat,robot_action`. Both fail closed after ownership.
- Made exact Router actions adapter-only and reduced the old CapabilityAgent
  semantic planner to an emergency path requiring host and Agent gates plus a
  non-empty authoritative claim whose `turn_id` matches the request.
- Constrained Goal Association with the exact model-facing schema, one bounded
  contract repair, and host-owned transport/persistence identities.
- Hardened Fast and Deep Planning around an exact flat semantic DTO: canonical
  identity remains host-owned, multi-goal outcomes are keyed exactly once by
  authoritative Goal IDs, satisfaction is prospective plan adequacy, and typed
  plan-relation/confirmation fields reject unsafe alternatives.
- Aligned the Fast multi-goal decoder schema with deterministic validation:
  per-goal outcome schemas are goal-scoped, satisfaction bands are strict,
  step cardinality is bounded, aggregate disposition is cross-field
  constrained, and one bounded repair may narrow only the redundant aggregate
  enum from the model's own complete per-goal outcome map.
- Required planners to preserve explicit, unambiguous, schema-valid numeric
  arguments instead of silently replacing them with catalog defaults; uncertain
  mappings escalate and material adjustments remain confirmation-gated.
- Added generic source-cited numeric provenance validation across executable
  plan arguments. A Fast plan that changes an explicit user number now gets one
  bounded same-tier repair and then visibly escalates to Deep Planning instead
  of executing the substituted value.
- Raised the maintained Router structured-output allowance to 512 tokens after
  live compound requests proved that both 96- and 256-token limits truncated
  otherwise valid route JSON; truncation remains a hard integrity failure.
- Sized Response Composer's maintained context/output envelope for a complete
  multi-goal canonical plan plus its exact response schema, preventing
  truncation from being hidden behind fallback speech or partial execution.
- Moved response-transport speech out of goal-driven task steps: conversational
  goals use `respond` outcomes, while Response Composition uses its own exact
  schema, host-owned coordination envelope, and one bounded same-stage repair.
- Applied Goal-state updates atomically only after trusted response preparation.
- Added privacy-conscious operational evidence, deterministic cognitive
  scenarios, and a cognitive text-to-MuJoCo evidence entry point.
- Hardened cognitive, voice, and artifact evidence provenance: target
  validation now requires the current Chromie revision, a clean declared
  Soridormi checkout, matching endpoint-reported Soridormi source, and applied,
  completed, safe-idle cognitive `sim` execution; artifact verification rejects
  source, development identity, manifest, compatibility, or retained-evidence
  drift.
- Replaced the abandoned fixed-version metadata with a neutral `development`
  identity and explicit known evidence gaps. No deployment or
  physical-execution claim is added by these changes.


## Development packaging and evidence snapshot - 2026-07-04

This section records the July 4 engineering snapshot. It is historical
development context, not a release candidate or publication plan.

- Added development compatibility metadata, bounded engineering scope, and
  preview-only artifact packaging.
- Scoped generated-speech regression, structured text/speech interaction, and
  MuJoCo `sim` execution through the pinned Soridormi contract.
- Added automated acoustic acceptance, which generates TTS prompt audio, plays
  it through the host output, and captures it through the configured host input
  without requiring a human speaker for every regression run.
- Kept human microphone/speaker support, verified Jetson packaging, unattended
  deployment, and physical robot support outside the release claim.

### Implemented in that development line

- Added artifact reproducibility checks for container references, exact direct
  dependency pins, immutable ASR/TTS model revisions, runtime image/Ollama
  digest capture, resolved dependency provenance, and fail-closed preview bundle
  generation.
- Added versioned provider conformance traces, recommendation-only hardware
  shadow coverage, safe-idle status checks, and a first-reference-robot
  commissioning checklist.
- Normalized provider catalog and unavailable-skill failures into stable
  terminal results and expanded the deterministic fault matrix to 16 scenarios.
- Added provider-readiness manifest preflight, explicit live/stub evidence
  provenance, and strict target evidence bundle verification.
- Added live Soridormi-owned fault injection, three safe no-motion provider
  modes, MCP error normalization, and opaque-plan-aware profile parity.
- Added a versioned reference-robot candidate schema, rejected draft template,
  and fail-closed verifier for Physical pilot preparation.
- Fixed the Ollama container healthcheck to use a reachable loopback client
  address while the service continues listening on all interfaces.
- Scoped voice-acceptance capability probing to the production surface while retaining
  strict full-manifest probing for provider-readiness conformance.
- Prevented host proxy variables from intercepting Agent-to-Ollama traffic on
  the trusted Compose network.
- Retained passing RTX 5090 GPU smoke plus complete synthetic and PipeWire
  virtual-microphone voice-pipeline evidence; supervised physical audio remains open.
- Aligned status and roadmap wording with sherpa-onnx as the maintained ASR
  default and scoped supervised audio blockers to physical voice-device claims.

- Structured `InteractionResponse` contracts with recursive low-level-field
  rejection.
- Trusted host Skill Runtime with bounded scheduling, confirmation, timeout,
  cancellation, traces, and provider isolation.
- Soridormi named-skill catalog import and MCP planning/monitor/execute path.
- TaskGraph validation, dry run, read-only execution, planning-only execution,
  guarded execution, one-time confirmation grants, cancellation, and retained
  in-memory traces.
- Shared process-local resource arbitration and bounded parallel read/planning
  execution.
- Short-term host conversation state across VAD utterances.
- Host-owned spoken request-bound confirmation with exact request fingerprints,
  expiry, single-use approval, deterministic denial, and evidence events.
- Operational stop, cancel, and emergency phrases cancel any pending
  confirmation and continue through the deterministic Router control path.
- Hardware-aware generated runtime configuration and multiple NVIDIA profiles.
- GPU, Soridormi, text-interaction, and supervised target acceptance tooling.
- Correlated JSONL session-event evidence that cannot break the realtime loop.
- Four-mode seven-case voice/MuJoCo runner: automatic TTS-generated stdin
  injection, PulseAudio/PipeWire virtual microphone capture, acoustic
  host-output/input capture, and final supervised real-microphone evidence.
- Strict evidence verifier for native mode, clean revisions, all cases,
  correlated sessions, and separation of automated evidence from supervised
  human voice-device evidence.
- `development` identity, compatibility declaration, development scope, source
  archive generation, manifest, tests log, and checksums.

### Documentation refresh

- Reclassified the project from stale historical milestone documentation to the
  current MuJoCo-executor engineering scope.
- Added a stable project charter and a focused capability sequence covering
  Soridormi MuJoCo execution, robust/provider-ready simulation, and a physical
  reference pilot.
- Consolidated duplicated setup, status, and handoff prose into their owning
  documents; removed redundant `CLAUDE.md` and `LLM_CONTEXT.md` copies.
- Reduced the Chinese guide to a maintained project overview and navigation
  entry instead of duplicating the full runbook and acceptance manual.
- Added authoritative implementation, API, configuration, acceptance, artifact packaging,
  security, support, and contribution documentation.
- Reconciled `/interaction` documentation with the native output path and explicit compatibility controls.
- Clarified that the host hardware daemon currently uses only the mock driver.
- Added automated documentation consistency checks.

### Native interaction output

- Added `InteractionRuntime`, which accumulates strict speech and skill objects
  directly instead of converting a final `AgentResult`.
- Added serialized contract revalidation, fail-closed default behavior,
  explicit `legacy-adapter` mode, and opt-in validation fallback.
- Kept `/run` unchanged for compatibility and switched the named-skill
  integration test to the native path.

### Still open before a human voice-device release

- Reviewed reference-host microphone/MuJoCo evidence bundle for a physical
  voice-device claim.
- Clean reviewed supervised spoken approval/denial evidence for real
  microphone/speaker support.
- Physical microphone/speaker and supervised recovery evidence for
  voice-device support.
- A future release must declare physical voice-device compatibility separately;
  `development` intentionally does not include that claim.
