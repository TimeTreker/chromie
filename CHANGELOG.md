# Changelog

- Reproduced the clean source-bound active-cancellation case failing before
  Provider start after a valid Fast Planner meaning was rejected at ambiguous
  provenance/repair representation boundaries and a later Deep attempt
  exhausted its output budget. Numeric provenance now accepts either a bare
  verbatim Goal span or the same span qualified by its declared Goal ID;
  repair feedback renders step and parameter fields separately; and a lone
  step is no longer treated as a concurrency request. These are typed
  representation and arity checks only: the Host still does not select the
  capability, argument mapping, timing among multiple steps, or Goal meaning.
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

This file records notable current changes. Detailed earlier development history is
preserved in [Changelog Archive — through 2026-07-30](CHANGELOG_ARCHIVE_2026-07-30.md).

## Unreleased

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
