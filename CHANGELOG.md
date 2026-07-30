# Changelog

## Unreleased — Canonical Plan Agent Skill provenance

- Added a strict content-free `PlanAgentSkillProvenance` contract and
  `CanonicalPlan.selected_agent_skills` for exact selection/disclosure identity,
  selecting planner role, Skill/version, package/projection/disclosure digests,
  model-authored relevant Goal IDs, rationale, and confidence.
- Bound Fast Planner disclosure to Fast Plans and preserved exact Fast provenance
  when Deep Planner appends its own selected methods. No-Skill paths remain
  byte-for-byte behavior-neutral at the Plan boundary.
- Made Plan validation reject unknown Goal references, duplicate/conflicting
  Skill-role records, and planner-tier mismatches while leaving Capability
  registration, authorization, schemas, confirmation, Provider validation, and
  execution unchanged.
- Included provenance in Canonical Plan fingerprints, replay serialization, and
  content-free runtime summaries. Recovery and cancellation child Plans narrow
  inherited provenance only to retained Goal IDs.

## Unreleased — Executable repository engineering policies

- Added one dependency-light AST/configuration gate for production assertions,
  trivially silent broad handlers, dynamic execution, unsafe shell invocation,
  model-contract actuation fields, loopback-only Compose publication, removed
  architecture authority, passive Agent Skills, and model-authored Skill
  selection.
- Integrated the canonical gate into local tests, GitHub Actions through the
  maintained test entrypoint, and the Benchmark check. Existing specialized
  Compose and Router guards remain component-owned inputs to the aggregate gate.
- Added an exact central exception registry with reviewed reason and removal
  conditions; wildcards, weak entries, duplicate keys, and stale exceptions fail
  closed. The current registry is empty.
- Narrowed one remaining Agent Skill Goal-context degradation from a silent broad
  catch to Pydantic validation with debug evidence.

## Unreleased — Explicit runtime failure paths

- Replaced production `assert` invariants in maintained Agent, TaskGraph,
  Orchestrator, shared-contract, and generated-environment paths with explicit
  typed exceptions that remain active under Python `-O`.
- Made malformed optional Goal/referent/task context visible through bounded
  debug or warning diagnostics while preserving defined compatibility fallbacks.
- Made state-changing semantic-operation batches fail closed before mutation,
  and made corrupt Runtime Trace checkpoints archive with warning evidence.
- Preserved best-effort audio/WebSocket cleanup and episode evidence emission,
  but removed silent `pass` behavior so cleanup or evidence loss remains
  observable without replacing the primary runtime failure.
- Added the maintained failure-classification document and focused tests for
  explicit model-client invariants, atomic state safety, evidence recovery, and
  removal of production assert statements.

## Unreleased — Agent-specific progressive disclosure

- Added strict disclosure request, projection, omission, and resolution contracts
  that bind loaded text to the exact model selection, Agent role, Skill version,
  package digest, projection digest, and relevant Goal IDs.
- Integrated model-authored selection and lazy projection loading at the Goal
  Association, Fast Planner, Deep Planner, Response Composer, and Tool Result
  Interpreter boundaries. Each Agent receives only its own selected projection.
- Added per-projection, aggregate-character, and projection-count budgets.
  Oversized or unavailable projection content is omitted rather than truncated,
  and optional loading failure cannot become execution or evidence.
- Removed caller-supplied disclosure context before selection, revalidated package
  provenance at load time, and added a passive-method prompt contract that cannot
  override Goals, evidence, Capability schemas, confirmation, safety, or output
  contracts.
- Added digest-only result/trace metadata, configuration and health reporting,
  `POST /agent-skills/disclose`, and focused tests for role isolation, forged
  context/digest rejection, prompt budgets, empty-root neutrality, and unchanged
  Capability Registry authority.

## Unreleased — Agent-specific progressive disclosure

- Added strict disclosure request/resolution contracts that preserve the exact
  model-authored selection, Agent role, Goal bindings, package digest, projection
  digest, character budgets, omission reasons, and disclosure digest.
- Added a bounded disclosure service and `POST /agent-skills/disclose` that lazily
  loads only already-selected role-specific projections, revalidates repository
  content before every read, omits rather than truncates oversized content, and
  never loads complete `SKILL.md` bodies into model context.
- Integrated optional selection and projection disclosure into Goal Association,
  Fast Planner, Deep Planner, Response Composer, and Tool Result Interpreter.
  Each boundary receives only its own selected projection and retains existing
  authoritative Goals, catalogs, schemas, evidence, and safety contracts.
- Removed any caller-supplied disclosure payload before selection so only the
  trusted Loader may inject projection content. Empty roots and explicit no-Skill
  decisions remain behavior-neutral and do not invoke the selection model.
- Added content-free trace/result metadata plus focused coverage for digest drift,
  role isolation, prompt budgets, selection order, forged-context removal, and
  unchanged Capability Registry authority.

## Unreleased — Model-authored Agent Skill discovery and selection

- Added strict shared request, Goal-context, closed model-output, selected-Skill,
  and observable resolution contracts for explicit no/one/multi-Skill decisions.
- Added an independent selection service and `POST /agent-skills/select` that
  discloses only bounded owner-approved summaries for the declared Agent role and
  lets the model author the semantic decision.
- Added exact Host validation for disclosed IDs, versions, requested projection,
  relevant Goal IDs, confidence, and registry content digest, with one bounded
  same-contract repair and optional no-Skill degradation on model failure.
- Kept projection text, complete `SKILL.md`, Canonical Plans, Capability
  registration, authorization, and execution outside this slice. Deterministic
  candidate caps and projection availability are structural retrieval only; no
  phrase, route, or weather selector was added.
- Added runtime configuration and health reporting plus focused tests for empty
  candidates, explicit no-Skill, one/multi-Skill order, context-sensitive model
  decisions, repair/failure, candidate bounding, provenance, and Capability
  Registry isolation.

## Unreleased — Read-only Agent Skill contracts and loader

- Added strict shared Agent Skill metadata, summary, projection, document,
  registry-snapshot, and typed loader-failure contracts with stable
  `agent_skill_id`, semantic version, owner approval, content digest, and
  Agent-specific projection identities.
- Added a repository-owned read-only `agent-skills/` root and deterministic
  loader that scans only configured roots, validates safe YAML and unique keys,
  blocks path escape and symlinks, rejects duplicate IDs and inheritance cycles,
  and verifies package-wide SHA-256 content provenance.
- Kept full `SKILL.md` and projection text out of startup summaries. Explicit
  reads recheck the package digest, apply bounded UTF-8 Markdown limits, and
  return immutable provenance-bound DTOs.
- Proved package Python remains inert and Agent Skill loading cannot register or
  execute Capabilities. Runtime inspection is metadata-only through
  `GET /agent-skills`; model-authored Skill selection remains disabled.
- Mounted the repository Skill root read-only in the maintained Compose profile
  and added a deterministic digest authoring helper plus focused contract,
  security, and runtime-surface tests.

## Unreleased — Secure local runtime exposure

- Bound all maintained ASR, maintained/evaluation TTS, Ollama, and Agent host
  publications to `127.0.0.1` without changing in-container listeners or Docker
  bridge-network service discovery.
- Added a dependency-light source and resolved-Compose exposure checker that
  rejects unspecified hosts, IPv4/IPv6 wildcards, and host networking.
- Integrated the resolved configuration check into the supported service
  launcher and added eight focused regression tests.
- Documented the local-only trust boundary; remote or multi-host exposure
  requires a separate authenticated deployment design.

## Unreleased — Agent Skills architecture and canonical Capability terminology

- Implemented the executable terminology slice: Canonical Plan steps,
  Capability requests/results/traces, execution evidence, and model-facing
  planner schemas now serialize `capability_id`.
- Added bounded `skill_id` readers that normalize immediately, accept equal
  dual fields, and reject contradictory dual identity fail-closed. Compatibility
  properties and class aliases keep existing callers readable without emitting
  new legacy payloads.
- Exposed `CapabilityRequest`, `CapabilityResult`, `CapabilityTrace`,
  `CapabilityDefinition`, `CapabilityRegistry`, and `TrustedCapabilityRuntime`
  as canonical names while retaining one underlying registry and execution
  authority.
- Kept Soridormi's native `skill_id` catalog as an explicit Provider-boundary
  compatibility input; imported Chromie contracts remain Capability-identified.
- Defined Agent, Agent Skill, Plan, and Capability as separate architectural
  objects. Agents make semantic decisions, Agent Skills provide passive
  reusable methods, Plans record current proposals, and Capabilities remain the
  only executable contracts.
- Accepted model-authored zero/one/multi-Skill selection, bounded Agent-specific
  progressive disclosure, owner approval, version/digest provenance, and Plan-
  level Skill traceability.
- Preserved the existing typed capability registry, provider validation,
  confirmation, evidence, and Soridormi physical-safety boundaries as the only
  execution-authoritative path; adopted Trusted Capability Runtime as the
  canonical architecture term while retaining legacy runtime aliases during
  migration.
- Opened the implementation Issue with semantic delivery slices for generic
  contracts, a secure read-only loader, model selection, Agent projections,
  Plan provenance, grounded external information, the weather vertical slice,
  and maintained module/integration/E2E qualification.
- Explicitly deferred third-party installation, arbitrary Skill scripts,
  automatic provider registration, a second execution registry, and made the `skill_id` to `capability_id` compatibility migration the first
  implementation slice before Agent Skill selection.

## Unreleased — Scoped discourse referents and verified result retrieval

- Added model-authored, Host-validated discourse referents with conversation,
  task, and Goal scopes plus a bounded focus stack. Multiple locations and other
  entities can coexist; there is no global `current_location`, and robot physical
  position remains outside conversational reference state.
- Extended Goal Association to resolve references and task mentions explicitly,
  emit correction/focus updates, and bind material entities such as location into
  canonical Goals before planning. The same LLM association path handles phrases
  such as “the last task I told you”; Host code contains no phrase-to-Goal map.
- Removed tool-result contents from Goal Association, Fast/Deep Planner, and
  pre-execution Response Composer boundaries. Old results are advertised only as
  a provenance/binding index and become available through an executed exact-match
  `chromie.memory.retrieve_verified_tool_result` capability.
- Added generic binding-provenance validation so Planner arguments cannot
  contradict Goal Association’s immutable typed bindings. The validator compares
  names and values only; it never decides what a user reference means.
- Removed fixed character, word, and sentence-count limits from safe-read
  acknowledgements. Response Composer owns natural wording while the Host keeps
  the immediate-stage, no-completion-claim, and evidence-before-result contracts.
- Fixed the nested Goal Association reference contract so indirect reference
  confidence is decoder-required instead of silently defaulting to zero. Directly
  named entities remain Goal bindings/referent updates and are no longer misclassified
  as resolved references, preventing valid explicit weather requests from failing
  before planning.
- Added exact-first weather geocoding with bounded provider-only retry forms for
  hierarchical places. The canonical Goal binding remains unchanged while the
  adapter may query equivalent locality forms and qualify same-named results by
  administrative context; a mismatched province is rejected rather than guessed.
- Added typed `location_not_found` propagation from the weather provider through
  Skill Runtime outcome facts so the model-authored failure response can say that
  the provider did not recognize the place instead of claiming weather data or the
  network was unavailable.
- Added the Chongqing-to-Henan-Neixiang multi-turn scenario plus provider integration
  coverage for full administrative names, locality fallback, candidate qualification,
  and total geocoding failure.

## Unreleased — Safe-read speech, grounded result delivery, and explicit concurrency

- Removed the Host-owned greeting-length classifier and brevity veto. Ordinary
  greeting wording and length are now authored by the LLM under the same truth,
  language, typed-response, and bounded-output contracts as other conversation.
- Require one model-authored micro acknowledgement for safe-read/external-read work while starting speech and lookup in parallel, so Chromie naturally tells the user she is checking a current source without delaying retrieval.
- Fix tool-result sentence counting so decimal points such as `40.3` do not consume the sentence budget and cause a valid evidence-bound answer to be discarded.
- Require every planner-model step to author `timing` explicitly, preserving the model's ordering or concurrency decision instead of silently defaulting missing timing to sequential.
- Clarify planner semantics that a prohibition or hold-state constraint cannot be satisfied by executing the positive action it forbids.

All notable user-visible changes should be recorded here.

## Unreleased

### Goal-grounded body execution and speaker-echo suppression

- Generalized Soridormi's trusted preflight bridge from reviewed auxiliary Social
  Attention to any Goal-grounded named body skill whose committed request, live
  capability contract, and freshly created Soridormi plan all agree that no extra
  confirmation is required. The execution context still records `confirmed=false`;
  provider-required confirmation, safety monitoring, refusal, and recovery remain
  body-owned.
- Preserved user-requested concurrency in Fast and Deep Planner guidance: compatible
  simultaneous actions must use `timing=parallel`, while unsafe or unsupported
  concurrency must be clarified or presented as an explicit adjustment rather than
  silently serialized.
- Added playback-generation transcript evidence so an ASR utterance that began during
  playback and substantially matches Chromie's own scheduled speech is suppressed
  before Cognitive Gateway admission. Genuine semantically different barge-in speech
  continues through the normal reflex and routing path.
- Routed post-execution failures through the quality-model failure composer using only
  Host-owned aggregate status facts. This removes normal live phrases such as
  `第1件没弄成` while preserving the existing per-goal deterministic evidence response
  as the final fail-closed fallback.

### Grounded failure speech and maintained GPU model topology

- Restored a fast/quality cognitive split on both maintained development GPUs:
  RTX 4090 Laptop now uses `qwen3:4b` for fast stages and `gemma4:e2b` for Goal
  Association, Deep Planner, Response Composer, tool-result interpretation,
  and review; RTX 5090 retains `qwen3:4b` plus `gemma4:12b`.
- Tightened tool-route decoder schemas so Fast and Deep Planner cannot place
  greetings, acknowledgements, or guessed tool results in planner
  `response_text`; verified post-execution speech remains evidence-grounded.
- Prevented identity/personality guidance and polite framing from becoming
  artificial Goals, and kept one lookup plus an interpretation of its result as
  one semantic responsibility.
- Replaced misleading service-status fallbacks with structured failure facts
  phrased by the configured Response Composer model, retaining a short natural
  deterministic fallback when that final wording call is unavailable.

### Voice feedback-loop and grounded execution closure

- Bound each VAD utterance to the playback state and playback generation at its
  start, so low-energy speaker echo cannot become a new user turn merely because
  playback ended before the segment closed. Continuous overlong audio now waits
  for a real silence gap before VAD rearms instead of producing endless discarded
  20-second segments.
- Resolved the authoritative spoken language at Gateway capture and rejected
  Response Composer speech that switches a Chinese turn into an English answer
  or vice versa. Greeting style remains model-authored rather than inferred from
  a Host-side greeting-length category.
- Required fresh tool-routed turns to execute an eligible tool or return an
  explicit escalation/clarification/unavailable outcome. Fast and Deep Planner
  decoder contracts no longer permit a pure model-memory response for a tool
  lane, and Deep per-goal fields are inlined so structured decoding cannot omit
  disposition or satisfaction silently.
- Bridged the generic Soridormi execution-plan confirmation gate only for a
  reviewed auxiliary Social Attention request whose live named-skill contract and
  Soridormi-created plan both require no user confirmation. This trusted
  preflight is not recorded as user approval, and Soridormi retains planning,
  monitoring, refusal, execution, and recovery authority.
- Reduced clarification output to one waiting-for-user question and finalized
  no-trace voice sessions exactly once, preventing contradictory follow-up speech
  and repeated idle-timeout evidence for the same completed session.

### Runtime authority and embodied-response root fixes

- Reconciled adapter-authorized safe-read parallel timing against immutable
  canonical timing without weakening timing checks for physical or forged
  requests. Runtime timing provenance is now explicit and evidence-bound.
- Preserved an admitted Cognitive Core `clarify` disposition through Goal
  Association, so low-information ASR fragments cannot become invented goals or
  unsolicited self-introductions.
- Unified the single-goal Fast Planner decoder with the strict per-goal contract;
  it now authors the required outcome and prospective satisfaction instead of
  being instructed to emit values the validator must reject.
- Restored a practical wake-up greeting bound, removed ungrounded clock/state
  prompting, and rejected model greetings that end without sentence-final
  punctuation rather than speaking truncated clauses.
- Calibrated courteous Social Attention so meaningful direct engagement is
  positive evidence for one subtle model-selected behavior; stillness remains
  valid when the supplied scene or recent evidence provides a concrete restraint.

### Explicit Social Attention decisions and bounded compatibility join

- Required Response Composer to return an explicit `decision=none` or
  `decision=express` Social Attention plan whenever policy is enabled and
  reviewed candidates are available. The Host still never chooses a gesture.
- Made the owner-approved Social Interaction Style an active model preference
  while preserving scene-specific stillness, cooldown, repetition restraint,
  primary-task priority, and deterministic capability/safety validation.
- Added model-decision, candidate-count, validation, proposed-skill, and
  materialized-skill evidence so live runs distinguish no candidate, explicit
  stillness, validation rejection, and successful body-action delivery.
- Restored the compatibility planner's configured bounded post-response join.
  A zero budget remains non-blocking; a positive budget is now honored instead
  of being recorded and ignored.

### Parallel safe reads and recoverable query continuity

- Started validated `safe_read` capabilities in parallel with optional micro
  acknowledgement speech. Read-only tools no longer wait for TTS synthesis or
  playback start; effectful and confirmation-bound capabilities retain their
  existing delivery barriers.
- Kept safe-read acknowledgement structurally bounded to one pre-result stage
  while leaving its natural wording and length model-owned.
- Bound execution evidence and active task snapshots to exact tool arguments.
  Interrupted or missing-result safe reads remain `recoverable`, so status
  follow-ups resume or retry the same location/date instead of reusing another
  task's result.
- Constrained Tool Result Interpreter fact references to decoder-enumerated
  scalar JSON Pointers, eliminating invented `/data/...` paths and preserving
  natural evidence-grounded answers.
- Tightened wake-up speech to 12 characters and rejected invented relationship
  terms when nobody nearby has been identified.

### Spoken-output boundary hardening

- Changed the runtime wake-up greeting to a strict structured `{"text": ...}`
  contract with thinking disabled, a 32-token generation ceiling, one-sentence and
  language validation, and a 12-character spoken limit. Raw prose, incomplete
  generations, analysis, and malformed output are logged as rejected evidence and
  never enter TTS.
- Applied the same explicit spoken-text envelope to the rare Host direct-LLM
  fallback. Any separate model `thinking` field is counted for observability but
  discarded; only the validated `text` field can be chunked and spoken.
- Kept the natural `嗨，我醒啦！` fallback so startup remains usable when the model
  violates the spoken-output contract.

### Internal truth, external humanity

- Added an owner-approved `personality_expression` contract to the Mind Profile.
  Chromie experiences herself as Chromie, a person and six-year-old girl; her
  body and internal components remain truthful background facts rather than her
  ordinary social identity. The active personality is smart, curious, warm,
  simple, playful, innocent, and occasionally naive, with direct answers before
  one or two useful details.
- Propagated the same identity and personality projection through Goal
  Association, Fast/Deep Planning, Response Composition, Tool Result
  Interpretation, conversation, and direct fallback. Concrete personality values
  remain owner-editable configuration rather than Python defaults.
- Removed fixed safe-read acknowledgement sentences. Response Composer now owns
  specific everyday pre-execution wording, while the Host validates that a real
  read step exists and preserves the playback-before-effect barrier.
- Changed post-execution delivery so the evidence-bound Tool Result Interpreter
  answers the original user question from trusted observations. Complete outcome
  bundles, status, evidence, and traces remain in logs and experience records, but
  normal speech no longer announces task completion or observation labels.
- Reduced the deterministic outcome formatter to an exceptional boundary. It may
  use only an explicit provider-authored user summary; arbitrary structured fields
  are never converted into a spoken report.
- Extended Cognitive Gateway/Core qualification with a direct self-identity turn
  and human-review gates for person-identity consistency, age-appropriate natural
  voice, direct-answer-first behavior, and absence of internal workflow narration.

### Gemma 4 12B multimodal-core migration

- Replaced the maintained `gemma4:26b` quality model with `gemma4:12b` for RTX
  5090 and Jetson Thor, and made Gemma 4 12B the future visual-quality source
  plan for RTX 4090 Laptop. The smaller dense model preserves image-capable
  reasoning while avoiding the retained live failure where Gemma 26B, Qwen 4B,
  and CosyVoice exhausted a 32GB GPU during synthesis.
- Restored the RTX 5090 CosyVoice topology to two resident 32K models:
  `qwen3:4b` for narrow fast stages and `gemma4:12b` for Goal Association, deep
  planning, tool-result interpretation, response composition, and review.
- Kept RTX 4090 Laptop voice mode fail-safe: CosyVoice still collapses cognition
  to one resident `qwen3:4b`; Gemma 4 12B is reserved for explicit no-TTS or
  remote-TTS multimodal qualification until peak-VRAM evidence proves co-residency.
- Updated the release model lock, experience evaluator default, profile docs, and
  automatic-profile tests. This change prepares the model plan but does not yet
  implement the camera observation envelope.

### Owner-editable Chromie identity and cognitive propagation

- Moved the maintained Chromie name, age, self-description, pronouns, internal-component boundary, and identity-answer guidance from Python defaults into `config/mind/chromie_default.json`, selected by `ORCH_MIND_PROFILE_PATH`.
- Made `MindProfile.identity` required schema data and kept code responsible only for loading, validation, owner-approval boundaries, and prompt-safe projection.
- Added one owner-approved identity context shared by Goal Interpretation, Goal Association, Fast Planner, Deep Planner, Response Composer, conversation fallback, and direct LLM fallback. Identity questions remain model-understood conversation rather than Host phrase rules.
- Changed direct fallback speaker labeling to use the configured identity name instead of a hard-coded prompt suffix.

### Development/qualification LLM budget integrity

- Raised the maintained RTX 5090 cognitive runner topology from 8192 to 32768
  tokens and assigned generous stage-specific output ceilings while architecture
  correctness remains the priority. The generated runtime profile retains every
  context, output, timeout, estimator, and safety-margin value.
- Added fail-closed request preflight that estimates the complete prompt, reserves
  the full declared output budget plus a safety margin, and rejects requests that
  cannot fit instead of allowing silent prompt clipping.
- Added completion gates for both shared Ollama clients and the independent Goal
  Interpreter chat path. `done_reason=length`, exhausted `num_predict`, and
  prompt-context exhaustion are untrusted LLM-budget failures and cannot be
  reinterpreted as user ambiguity.
- Changed the rare host direct-LLM fallback to buffer the complete stream, verify
  completion diagnostics, and only then schedule TTS, preventing truncated partial
  speech from becoming audible.

### RTX 5090 cognitive topology and contract hardening

- Restored the intended RTX 5090 two-model topology while CosyVoice is active:
  `qwen3:4b` owns narrow fast stages and `gemma4:12b` owns Goal Association,
  Deep Planning, Tool Result Interpretation, and Response Composition. The
  profile explicitly opts out of the low-memory one-model compact override.
- Unified every active RTX 5090 cognitive stage on one runner context
  so Ollama does not repeatedly evict and reload the same model merely because stages request different context sizes.
- Replaced mutually exclusive Goal Association payload branches with an explicit
  decision discriminant; inactive branch content is structurally ignored rather
  than triggering another self-repair call. Runtime routing/validation failures
  are no longer supplied as semantic evidence to Goal Association.
- Replaced generic RouteDecision repair output with a minimal
  `route`/`intent`/`confidence` schema and uses the configured review model for
  correctness recovery.
- Added deterministic structural normalization for redundant planner response
  fields, without inventing goals, capabilities, arguments, or response text.

### Goal-scope and read-only tool truthfulness

- Preserved temporal/comparison qualifiers through Goal Association and exposed
  capability semantic-scope limits to Fast/Deep Planning so unsupported broad
  requests clarify or report unavailable instead of silently narrowing to a
  short forecast.
- Propagated the admitted turn language into trusted local tools, so Chinese
  locations use Chinese geocoding and Chinese evidence summaries.
- Classified effects from capability metadata instead of `chromie.*` name
  prefixes, rendered safe-read work as an information lookup rather than robot
  motion, and stopped treating a failure phrase such as `执行失败` as an
  unverified execution claim.
- Unified the CosyVoice one-resident-model context size across the maintained
  Gateway, Interpreter, Planner, Composer, and Tool Result stages to avoid
  repeated context-size cold reloads on the first turn.

### Gateway/Core qualification preflight

- Added a read-only fail-fast preflight before runtime identity, live-model, or
  MuJoCo collection. It rejects dirty paired repositories, capability-manifest
  revision drift, unhealthy or ungrounded Agent deployments, non-sim/non-idle
  providers, and missing or mismatched endpoint-reported Soridormi revisions.

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
