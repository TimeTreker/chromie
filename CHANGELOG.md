# Changelog

- Reproduced clean source-bound active cancellation failing before Provider start on revision `1849bb5` after Fast Planner selected the exact velocity capability, `0.2` speed, `20`-second duration, and Goal ownership. Removed redundant free-text `source_ref`; the model still authors capability, arguments, mapping, and `source_goal_ids`, while deterministic validation requires explicit numeric Goal values to match the claimed step and source Goal without adding a Host semantic rule.
- Reproduced clean source-bound compound execution preserving a specific Response Composer sentence until the Host replaced unfamiliar actions with “perform the requested action.” Removed the Host phrase renderer and preserved fingerprint-bound model wording; confirmation, goal coverage, commitment state, playback barriers, schemas, and effect authorization remain typed and fail closed.
- Reproduced the clean source-bound active-cancellation case failing before Provider start after a valid Fast Planner meaning was rejected at ambiguous provenance/repair representation boundaries and a later Deep attempt exhausted its output budget. The initial correction accepted a bare or Goal-qualified verbatim span, rendered step and parameter feedback separately, and stopped treating one step as a concurrency request. The later clean replay above proved that free-text copying remained an unnecessary failure surface, so stable Goal IDs now carry that provenance.
- Reproduced the source-bound compound MuJoCo request being discarded before
  Core entry because Attention Review mislabeled a direct imperative as
  dictation. Suppression candidates now receive one independent schema-bound
  model reconsideration and fail open on disagreement or review failure; no
  Host phrase rule selects addressedness. The MuJoCo evidence runner now retains
  the exact attention request and result before admission.
- Removed the Host regular expression that inferred physical-action claims from
  spoken words. Truth reconciliation now enforces only typed effect-proposal
  counts and explicit proposal-supersession links. Evidence-bound completion
  speech therefore remains valid independent of whether the model says
  “walked” or “finished walking,” while an uncommitted effect proposal still
  fails closed for model repair independent of its wording.
- Corrected the compound-turn acceptance expectation to the paired Soridormi
  named-Skill convention: positive yaw is left and negative yaw is right. The
  earlier negative-left assertion contradicted the provider contract and could
  reject a correct plan or accept motion in the wrong direction; no runtime
  phrase-to-direction rule was added.
This file records notable current changes. Detailed earlier development history remains available in Git history.

## Unreleased

### Runtime sustainability follow-up
- Added a no-operator-speech comprehensive qualification collector that composes
  existing test owners and retains revision-bound, hash-indexed review evidence.
- Added hybrid benchmark oracles and bilingual closed-loop review bundles:
  objective fixture/audio/evidence checks remain deterministic, semantic quality
  uses retained LLM/human review, and hard-gate failures remain non-overridable.
- Centralized Agent, Goal Interpreter, and shared-runtime observability policy configuration; internal model, weather, capability, trace, event, resource, accelerator, and CLI-color helpers no longer parse environment values independently.
- Added immutable TTS service settings for transport, provider, generation, worker, speaker, alignment, and immutable model-source configuration; maintained TTS modules no longer parse environment values independently.
- Preserved completed evidence-bound results across newer ordinary turns with a non-interrupting delivery window; explicit cancellation and supersession still suppress late speech.
- Reused exact planner-authored Agent Skill selections for Response Composer and Tool Result Interpreter after validating Plan provenance, avoiding redundant downstream selection model calls without adding Host semantic choice.
- Added immutable model-generation Host settings for direct response, bounded failure speech, and runtime-ready greetings; turn-time environment reparsing was removed from those paths.
- Expanded package-owned Mypy scope to `orchestrator/runtime/cognitive_gateway_modules`; actual Mypy execution remains an environment gate.
- Added four complete operator modes with generated manifest identity, contradiction checks, and legacy direct-LLM fallback disabled.
- Ratcheted the generated ownership inventory at 450 keys, eight public choices, one public Boolean, and zero compatibility aliases.
- Made `shared/chromie_contracts` package-scoped in Mypy so new modules enter automatically.
- Consolidated eight trace documents into two, removed three dated archives, and ratcheted the 14-document core path.
- Closed specialized-document ownership: the index no longer counts as an owner, component entrypoints form a checked reachability graph, and package documents require declared mechanical contracts.
- Added revision-bound source qualification reports that fail closed on dirty source, failed gates, or unavailable pinned static tools and explicitly exclude all target/hardware claims.
- Closed the source-only sustainability backlog; remaining gates are clean dependency-environment execution and explicit target/hardware qualification, never inferred from source checks.
- Replaced 37 lifecycle property methods with delegated state aliases, reducing `VoiceAssistant` from 221 to 187 methods and 19 to one property.
- Confined the direct-LLM call to one rollback owner; maintained apply lanes use bounded fail-closed speech after Agent failure.

### Grounded response latency contract

- Recorded the reproduced serial-cognition delay as the first queued
  post-evidence behavior Issue without changing the active target-evidence
  closure.
- Defined the intended direct conversational, terminal Fast, and exceptional
  Deep paths while preserving one Core semantic authority and every existing
  validator, confirmation, and evidence boundary.
- Required independently valid commitment/evidence-bound speech stages instead
  of raw token-to-TTS delivery, and distinguished provider transport streaming
  from the separately queued incremental PCM playback work.
- Mapped realtime, nonblocking-tool, durable-task, multi-agent, memory, and
  embodied-control ideas onto existing Chromie contracts without adding a new
  lane, event bus, ledger, framework dependency, or execution authority.
- Recorded the current global playback-generation/session staleness boundary
  that can suppress an earlier independent Goal's eventual result speech, plus
  the queued ordered/urgent/internal-only delivery scenarios that must close it.

### Multi-turn continuity

- Preserve independent ordinary routed turns when another request arrives,
  including every ordinary turn waiting behind an active protective reflex.
- Keep cancellation explicit and scoped: deterministic control or a
  Core-authorized interruption may cancel foreground work, while ordinary
  speech no longer acts as an implicit cancel command.
- Retain a fail-first Level A overlap scenario plus focused lifecycle,
  addressedness, reflex-queue, and scoped-cancellation regression coverage.

### Shared-GPU startup reliability

- Reset stale Ollama runners before the CosyVoice synthesis readiness probe so
  an unchanged long-running LLM container cannot retain GPU allocations from a
  previous launch.
- Limit the RTX 4090 Laptop profile to one resident 32K Ollama runner while
  preserving distinct Qwen fast and Gemma quality model roles.
- Emit GPU-process and Ollama-runner diagnostics when the TTS readiness probe
  still fails.

### Proof-first repository simplification

- Re-audited the current tree against an external maintainability review and
  recorded reproducible baselines for the Orchestrator, configuration surface,
  broad exception handlers, Mypy scope, and documentation surface.
- Reproduced and repaired the non-hermetic local test setup: declared `pytest`,
  distinguished ignored Router cache residue from maintained source, isolated
  generated runtime configuration behind explicit startup, and restored the
  pinned Mypy ratchet without ignores or scope removal.
- Passed the canonical gate with repository policy, test ownership, Ruff,
  Mypy, documentation, 1,656 primary tests, and 20 legacy Agent tests.
- Activated the retained current-revision microphone-to-audible-response loop
  before structural or feature work.
- Added the strict `current-revision-live-voice` verifier profile, runtime
  identity/event binding, physical recording and device checks, exact command
  retention, and digest-bound bundle manifests while preserving the default
  seven-case voice/MuJoCo verifier.
- Added focused rejection coverage for synthetic input, incomplete events,
  dirty or mismatched source, missing service identity, executable work,
  timeout/truncation/fallback, stale playback, artifact tampering, and missing
  operator review. The supervised target bundle remains to be collected from
  the committed implementation revision.
- Added a shared Python 3.11+ runtime gate to supervised preflight and the
  Orchestrator launcher after a real clean attempt exposed a stale Python 3.10
  managed environment; incompatible runtimes now stop before evidence creation
  or model warm-up.
- Queued independently closable exception, typed Host configuration,
  playback/input lifecycle, configuration-profile, package-level typing, and
  documentation-reduction Issues.
- Shortened the README and core reading path, corrected stale Agent Skill
  guidance, and added repository-surface growth rules for documents, flags,
  compatibility paths, and terminology.

### Live Agent weather and planning reliability

- Route verified memory retrieval by its declared `read_only` effect as a trusted
  tool capability; only a declared `memory_write` effect enters the model-authored
  memory-update lane. The model still decides whether a turn calls for verified
  prior evidence or a fresh lookup. This corrects an executor mismatch that sent
  a valid model-selected read capability around the Goal-driven runtime and into
  the legacy memory writer.
- Made the live text qualification runner load the generated runtime profile
  before applying its diagnostic I/O overrides, so deployed model and timeout
  ownership matches normal startup.
- Kept additive Agent Skill selection model-owned: the weather specialization
  declares its grounded-information dependency, but the Host neither inserts
  that parent nor treats `extends` as inherited prompt content.
- Consolidated Goal Association's model-owned semantic review so it handles
  both genuinely independent spoken/capability responsibilities and material
  corrections to retained Goals. Existing typed bindings remain
  provenance-stable; when user meaning changes one, the model creates a fully
  bound replacement Goal instead of relabeling the old Goal and its evidence.
- Defined `continue`, `reference`, and association-level `clarify` in the
  Goal Association schema and model prompt. The model still owns which semantic
  relationship applies; typed validation only rejects `modify`, `replace`, or
  association-level `clarify` outputs that claim a Goal mutation without an
  updated description or resolved gap, then permits one model repair. The exact
  Beijing weather follow-up diagnostic passes both turns without another lookup.
- Added an independent Response Composer model review for pending safe reads.
  It receives the immutable Plan and candidate DTO without prior result
  contents, preserves natural acknowledgements, and removes unsupported
  pre-evidence claims. Host code triggers this only from typed safety metadata,
  validates the DTO, fails closed, and never inspects wording.
- Retained the review result in cognitive runtime evidence and require a
  successful `model_owned_pre_evidence_speech_review` for every fresh weather
  read in the qualification verifier.
- Aligned Agent Skill selection schema, validation, repair prompts, context, and
  timeout budgets so single-Goal provenance no longer enters an impossible repair
  loop under the maintained local models.
- Added a typed evidence guard preventing unresolved external reads from becoming
  unsupported factual responses, and aligned Fast/Deep clarification contracts.
- Added generic Latin provider-query normalization for Chinese administrative
  locations while preserving the canonical Goal binding.
- Strengthened Goal Interpretation guidance so current facts use exact trusted
  lookup identities rather than non-executable domain intent labels.

### Agent Skills and grounded information

- Added passive owner-approved Agent Skill contracts, read-only loading,
  model-authored selection, role-specific disclosure, and content-free Canonical
  Plan provenance.
- Added grounded external-information and weather methods while preserving Goal
  Association, verified-memory, Capability, Provider, and Soridormi authority.

### Final core-principle audit closure

- Removed Host-owned conditional deep-thinking delegation, re-enableable
  phrase/regex motion and pose agents, catalog phrase-action boosts, weather-
  specific route repair, and conversation follow-up/new-topic phrase classifiers.
- Made session-memory meaning an exact typed model proposal and routed the legacy
  weather ToolAgent through the common trusted local-tool boundary.
- Removed Host-authored semantic correction, route-specific Core exception
  classification, ontology speech templates, and default deep-thinking wording.
- Completed canonical `capability_id`/`capability_ids` output across remaining
  current model, Plan, API, task-proposal, trace, scenario, and qualification
  contracts while retaining bounded historical readers.
- Extended the executable repository policy gate to protect the corrected
  semantic-authority, wording, conversation, Provider, and identity boundaries.

### Runtime and repository safeguards

- Canonicalized executable `capability_id` terminology with bounded legacy
  readers.
- Bound local development services to loopback and added executable repository
  policies for failure paths, architecture, Agent Skills, and deployment.
- Added high-signal Ruff and incremental Mypy ratchets plus explicit behavioral,
  architecture-policy, and generated-artifact test ownership.

### Maintainability

- Added immutable typed ASR startup configuration without changing generated
  profile precedence.
- Extracted runtime-ready greeting scheduling and playback barriers into an
  independently tested collaborator while retaining `VoiceAssistant` lifecycle
  ownership.
- Consolidated documentation authority, archived detailed superseded narratives,
  and added a machine-checked authority registry.

### Target-evidence closure

- Bound every required track to the exact revision captured when the closure is
  initialized and reject collection, attachment, or finalization from a dirty or
  moved checkout.
- Retained non-semantic provider-resolution metadata so weather qualification
  proves canonical Goal arguments and the provider-native `neixiang` lookup key
  independently.
- Added one resumable source-bound closure workflow for Gateway/Core, positive
  Agent Skill/weather, Social Attention, and second-machine LAN evidence.
- Added fingerprint-bound Agent Skill/weather verification and loopback/LAN
  exposure reports without granting Runtime policy or release authority.
- Retired the overlapping broad supervised shell runner; physical voice and robot
  evidence now enter only through their dedicated supervised contracts.
- Automated repository gates remain distinct from live target evidence, and every
  closure report remains `release_qualified=false`.
