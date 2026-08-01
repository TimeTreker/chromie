# Current Implementation Status

**Status authority:** this file owns current implementation, automatic
verification, target-validation, and deployment claims.
**Development identity:** `development`; no release version or publication target is planned.
**Status refresh date:** 2026-08-01
**Active Issue:** **Close Current-Revision Target Evidence**. The canonical
local gate and live-voice verifier implementation are complete; physical voice
validation remains open because the current microphone has not produced an
intelligible utterance for the narrow retained live-voice claim. Structural
refactors and repository-surface growth are queued
behind the remaining evidence work
unless they close a demonstrated safety or provenance blocker.

Chromie’s current runtime is Goal-driven and has one semantic authority. The Host
validates and executes; it does not replace LLM reasoning with phrase rules.
Soridormi remains the physical safety and embodiment authority.

A final core-principle audit removed Host-owned semantic delegation, phrase/
regex motion and pose agents, catalog phrase-action boosts, weather-specific
route repair, conversation follow-up/new-topic phrase classification, static
ontology wording, route-specific Core exception classification, and the legacy
ToolAgent's direct weather Provider path. Session memory now requires a typed
model-authored `MemoryUpdateProposal`. Current model, Plan, task-proposal, API,
trace, scenario, and qualification identities emit canonical
`capability_id`/`capability_ids`; retained legacy artifacts remain readable at
bounded compatibility boundaries. A later live weather trace corrected four
operational gaps without adding semantic Host rules: Agent Skill selection now
has a schema-consistent single-Goal binding and viable repair budget, Fast/Deep
clarification fields are structurally aligned, unresolved external reads cannot
become factual responses, and Chinese place bindings may receive generic Latin
provider-query forms while remaining canonically unchanged. The repository now
reviews every proposed chat turn against available non-chat affordances, keeps
attached social framing subordinate to the substantive responsibility, and
exposes bounded recent terminal Goals for model-authored continuity. A completed
external-result follow-up may use only previously delivered, Host-marked
evidence-bound dialogue; the verified-memory index alone cannot become answer
evidence. The repository
policy gate protects the authority boundaries. Pinned Ruff/Mypy execution remains
a required local static gate rather than evidence claimed from the restricted
artifact sandbox. See [Final Core-Principle Audit](FINAL_CORE_PRINCIPLE_AUDIT.md).

## Four-axis status

| Capability area | Implementation | Automatic verification | Target validation | Deployment state / owner |
|---|---|---|---|---|
| Cognitive Gateway and Goal-driven Core | Gateway admission, Goal Association, planning, composition, execution reconciliation, and fail-closed ownership are implemented. Attention Review now requires an explicit ambient act for `addressed=false` and permits one schema-constrained repair of an inconsistent directed/unclear pair. Goal Association can reference bounded recent terminal Goals without reopening them, while planners receive only the Goals accepted for the current turn. Independently observable physical and spoken responsibilities remain separate typed Goals. Direct authored speech completes a `spoken_response` Goal without a planner transport step; external-result delivery remains part of one `capability_dependent` Goal. Unsupported parallel timing must become an explicit confirmation-bound safe adjustment or fail closed. A structured coordinated-action Goal receives a bounded non-authorizing model coverage audit before effectful execution. Already-delivered evidence-bound dialogue is the only no-retrieval factual projection for completed external-result follow-ups. The source-bound workflow binds its generated environment; its cancellation runner and canonical evidence verifier are current. | Core, attention repair/fail-open, planning, continuity, cancellation, tool, response, current-Goal scope, coordinated-action fail-closed coverage, environment-binding, qualification-runner/verifier, general-ability, policy, and full-suite tests. The general-ability runner retains ordered multi-turn episodes, objective metrics, hard-gate failures, diagnostic scores, and earliest-suspect reports. | Diagnostic root `20260731T121727Z` validates paired-source MuJoCo and active cancellation but predates the ambient and grounded-weather corrections. The 2026-08-01 supervised voice diagnostic accurately transcribed a weather turn followed by a walk/blink/song request and exposed stale Skill provenance plus incomplete Plan coverage. Automatic C-preview replay `20260801T034330Z-live-text` passed the retained two-turn case with score 100, no hard failures, three typed action-turn Goals/outcomes, no stale weather Skill, and a confirmation-bound sequential adjustment. It used injected text, discarded audio output, and preview-only Soridormi planning, so it has no microphone, speaker, simulator-motion, or physical-robot claim. Clean fingerprint-bound review remains open. | Enabled in maintained apply lanes. Evidence owner: [Gateway/Core Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md). |
| Capabilities and Soridormi boundary | Canonical `capability_id`, one Trusted Capability Runtime, provider validation, confirmation, scheduling, and evidence joins are implemented. | Contract, runtime, TaskGraph, cancellation, and policy tests. | Current paired live provider/MuJoCo and supervised physical evidence remain open. | Chromie authorizes named contracts; Soridormi owns physical feasibility and safety. |
| Agent Skills | Read-only approved packages, model selection, role disclosure, Plan provenance, grounded external-information, and weather methods are implemented. Planner selection is scoped to current Goal Association IDs and package-owned structured route applicability; a rejected provenance join becomes a structured non-executable Plan rather than HTTP 500. | Loader, selection, route applicability, current-versus-retained Goal scope, disclosure, fail-closed provenance, discourse, verified-memory, weather, result, response, policy, and full-suite tests. | Positive weather-Skill selection and provider-backed execution are present in the rebuilt-service diagnostic. The retained multi-turn C-preview excludes that stale Skill from the following action turn, but no clean source-bound qualifying report is retained yet. | Enabled; packages are passive and cannot register or execute Capabilities. Owner: [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md). |
| Social Attention | Embodiment-independent `off`, `report_only`, and `on` behavior domain with owner-approved style and provider-safe auxiliary expression is implemented. | Dataset, mode/style, priority, stillness, provider, backend-neutrality, and qualification-foundation tests. | Current 128-case live baseline, reviewed samples, and selected MuJoCo evidence remain open. | Maintained default `on`. Owner: [Social Attention Qualification](SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md). |
| Speech stack | SenseVoice final-utterance ASR, CosyVoice3 default TTS, cancellation/watchdogs, content gates, ordered playback, and runtime OS-default audio-device following are implemented. Explicit devices remain pinned; otherwise the Host validates, monitors, and reopens the affected default stream without changing system route, mute, or volume. Input changes discard partial cross-device VAD state, while output rolls over between ordered items. A PipeWire key first published after the initial monitor burst is retained as baseline instead of reopening an unchanged default device. | ASR/TTS provider, cancellation, alignment, startup, late-key baseline, runtime device reselection, explicit-pin, stream-rollover, and voice acceptance tests. | The 2026-08-01 supervised diagnostic produced accurate transcripts and audible ordered playback, but no supervised physical device-switch proof was collected. Listening quality, shared-load recovery, live hot-plug observation, and supervised switch evidence remain open. | Local containers plus Host audio lifecycle. Owner: [TTS Evaluation](TTS_PROVIDER_EVALUATION.md) and [Acceptance](ACCEPTANCE.md). |
| Benchmark suite | Module, integration, E2E profiles, stress workloads, migration inventory, and reviewed Social Attention data are implemented. | Inventory/migration parity, dataset validation, adapters, workload, and report tests. | Real model/service/MuJoCo/physical evidence must be collected per profile. | Evaluator only; it cannot implement intelligence. Owner: [Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md). |
| Canonical local gate | The dependency-light entrypoint now declares every imported test dependency, ignores cache-only Router residue while rejecting maintained Router content, loads deployment environment explicitly, and retains its four-file Mypy scope. | On 2026-08-01, the latest canonical run passed repository policy, test ownership, Ruff, Mypy, documentation, 1,720 primary tests, and 20 legacy Agent tests. | Not a target-validation claim. | Completed prerequisite. Owner: [Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md). |
| Current live voice loop | The `current-revision-live-voice` profile is implemented alongside the unchanged default full-matrix profile. It binds clean source, generated profile, running image/model identity, Gateway/Core events, physical recordings/devices, playback, operator review, command, and artifact digests into a claim that remains `release_qualified=false`. Shared preflight/launcher validation rejects managed Python below 3.11 before evidence creation or model warm-up. | Sixty-eight focused voice/evidence tests and the current canonical suite pass, including rejection of synthetic/partial/dirty/mismatched/unbound/skill/stale/unreviewed evidence and an incompatible Python runtime. | Attempts `20260731T134457Z` and `20260731T134946Z` captured physical VAD activity; the latter retained ASR finals `I.` and `.`, neither matching the requested Moon utterance, so cognition and audible response correctly did not run. Both bundles failed and make no physical claim. | Implementation verified; rerun the physical loop only after the OS-selected microphone produces intelligible speech. Owner: [Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md). |
| Engineering safeguards | Loopback publication, first failure-path audit, repository policies, Ruff/Mypy mechanisms, and test ownership are implemented. | Repository policy, Ruff, Mypy, test ownership, documentation, and the full canonical local suite pass. The 141 broad handlers still need symbol-level classification under a later Issue. | LAN exposure acceptance and live failure evidence remain open. | Development/CI gates. Owners: [Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md), [Runtime Failure Paths](RUNTIME_FAILURE_PATHS.md), and [Static Analysis](STATIC_ANALYSIS.md). |
| Typed service configuration | Complete ASR service environment is parsed once into immutable typed settings with safe diagnostics. | ASR parsing, precedence, invalid-input, backend projection, Compose, and full-suite tests. | Host/profile startup remains operational evidence. | ASR migrated; Host still participates in a 295-key literal runtime environment surface. Owner: [Service Configuration Boundaries](SERVICE_CONFIGURATION_BOUNDARIES.md). |
| VoiceAssistant composition root | Runtime-ready greeting scheduling/playback barriers are extracted. The runtime-default blocker correction necessarily grew the existing stream owner from 8,902 to 9,164 lines, 167 to 174 methods, and a 617- to 626-line constructor; no new configuration or architecture surface was added. | Greeting, runtime-device-following, and current behavior suites are automatic evidence only; no structural closure is claimed. | The current live voice and supervised hot-plug proofs remain open. | `VoiceAssistant` remains lifecycle owner; the queued playback/input lifecycle owners should absorb device monitoring and remove the seven added root methods after evidence closure. Owner: [Composition Root](VOICE_ASSISTANT_COMPOSITION_ROOT.md). |
| Documentation governance | Authority mapping and mechanical indexing are implemented. The baseline surface is 125 Markdown files and more than 31,000 lines, including 80 directly under `docs/`, plus three 237,276-byte in-tree archives. | Authority, links, indexing, current focus, API/configuration, and reproducibility checks pass independently. | Not a runtime target-evidence claim. | Core reading path shortened; trace consolidation and archive removal are queued. Owner: [Documentation Authority](DOCUMENTATION_AUTHORITY.md). |

A source-bound RTX 4090 Laptop launch exposed a concrete shared-GPU startup
blocker: the unchanged Ollama container retained prior model runners while the
new TTS worker attempted its first cuBLAS allocation. The launcher now resets
Ollama before the CosyVoice synthesis probe and the laptop profile permits only
one resident 32K runner. This is an implemented correction, not target evidence;
the complete current-revision closure must be initialized again and rerun.

Diagnostic root `20260731T121727Z` completed live text, compound MuJoCo, and
active cancellation on clean paired source. The final verifier exposed stale
`skill_id` reads even though current evidence emits canonical `capability_id`;
after the bounded verifier correction, MuJoCo and cancellation validate. The
same report retained two real semantic failures: inactive ambient speech entered
Core, while the Beijing weather request stayed on `chat`, executed no verified
lookup, produced no completed outcome, and lost Goal continuity on follow-up.
Both were reproduced at their earliest semantic boundaries. The attention
correction uses general speech-act contrasts plus one schema-constrained repair.
The weather correction makes substantive responsibility outrank attached social
framing, projects bounded terminal Goals, and prevents a provenance-only
verified index from becoming factual response evidence. Rebuilt-Agent headless
diagnostics now suppress the ambient turn and complete one grounded weather read
whose follow-up repeats no capability and preserves the delivered values. These
runs used dirty diagnostic source and are not target evidence; the original root
must not be approved or resumed.

## Target-evidence closure

The remaining evidence tracks are coordinated by
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md). The default
`source_bound_development` profile requires source-bound Gateway/Core, positive
Agent Skill/weather, Social Attention, and second-machine LAN evidence. Physical
voice and robot evidence remain optional and supervised; they are required only
for the stricter physical-pilot profile. No current retained bundle closes these
tracks yet, and no automatic workflow grants release qualification.

The canonical local gate is restored. The live-voice verifier remains available
for a future microphone-equipped host, but physical voice is optional for the
active default closure and cannot substitute for Gateway/Core MuJoCo, Social
Attention, LAN, or other required tracks.

During these prerequisite and evidence Issues, changes may repair a reproduced
blocker, improve provenance, or remove dead material, but must not add another
semantic authority, architecture layer, ordinary behavior flag, standalone
design document, or first-class term. The post-evidence order is owned by
[Repository Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md).

## Deployment truth

- The common safe base applies `chat,tool` and keeps Soridormi disabled.
- The maintained Soridormi launcher widens authority to
  `chat,robot_action,tool` only after trusted provider registration.
- Simulation is not physical evidence.
- Default-off experiments and compatibility paths are not release support.
- The repository remains a development snapshot.

Detailed narrative retained before consolidation is available in
[Implementation Status Archive — 2026-07-30](STATUS_ARCHIVE_2026-07-30.md).
