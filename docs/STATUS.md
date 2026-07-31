# Current Implementation Status

**Status authority:** this file owns current implementation, automatic
verification, target-validation, and deployment claims.
**Development identity:** `development`; no release version or publication target is planned.
**Status refresh date:** 2026-07-31
**Active Issue:** **Close Current-Revision Target Evidence**. The canonical
local gate and live-voice verifier implementation are complete; physical voice
validation is deferred because the current host has no microphone. Structural
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
provider-query forms while remaining canonically unchanged. The repository
policy gate protects the authority boundaries. Pinned Ruff/Mypy execution remains
a required local static gate rather than evidence claimed from the restricted
artifact sandbox. See [Final Core-Principle Audit](FINAL_CORE_PRINCIPLE_AUDIT.md).

## Four-axis status

| Capability area | Implementation | Automatic verification | Target validation | Deployment state / owner |
|---|---|---|---|---|
| Cognitive Gateway and Goal-driven Core | Gateway admission, Goal Association, Fast/terminal Deep Planning, composition, execution reconciliation, and fail-closed ownership are implemented. The source-bound workflow loads the launcher-generated Orchestrator environment into every cognitive stage, binds its digest for resume, and rejects profile-budget drift before evidence collection. Its cancellation runner now commits the exact Host conversation-state execution binding and observes the coordinator-owned trusted Skill Runtime. | Core, planning, continuity, cancellation, tool, response, environment-binding, qualification-runner, policy, and full-suite tests. | Clean current live-text, active-cancellation, paired-source MuJoCo, and approved review bundle remain open. Diagnostic root `20260731T115108Z` proved the timeout correction and compound MuJoCo path, then exposed the corrected cancellation-runner observation/binding defect; it is not qualifying evidence. | Enabled in maintained apply lanes. Evidence owner: [Gateway/Core Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md). |
| Capabilities and Soridormi boundary | Canonical `capability_id`, one Trusted Capability Runtime, provider validation, confirmation, scheduling, and evidence joins are implemented. | Contract, runtime, TaskGraph, cancellation, and policy tests. | Current paired live provider/MuJoCo and supervised physical evidence remain open. | Chromie authorizes named contracts; Soridormi owns physical feasibility and safety. |
| Agent Skills | Read-only approved packages, model selection, role disclosure, Plan provenance, grounded external-information, and weather methods are implemented. | Loader, selection, disclosure, provenance, discourse, verified-memory, weather, result, response, policy, and full-suite tests. | Positive live selection and provider-backed weather execution are not yet retained. | Enabled; packages are passive and cannot register or execute Capabilities. Owner: [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md). |
| Social Attention | Embodiment-independent `off`, `report_only`, and `on` behavior domain with owner-approved style and provider-safe auxiliary expression is implemented. | Dataset, mode/style, priority, stillness, provider, backend-neutrality, and qualification-foundation tests. | Current 128-case live baseline, reviewed samples, and selected MuJoCo evidence remain open. | Maintained default `on`. Owner: [Social Attention Qualification](SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md). |
| Speech stack | SenseVoice final-utterance ASR, CosyVoice3 default TTS, cancellation/watchdogs, content gates, and ordered playback are implemented. | ASR/TTS provider, cancellation, alignment, startup, and voice acceptance tests. | Physical microphone accuracy, listening quality, shared-load recovery, and supervised device evidence remain open. | Local containers plus Host audio lifecycle. Owner: [TTS Evaluation](TTS_PROVIDER_EVALUATION.md) and [Acceptance](ACCEPTANCE.md). |
| Benchmark suite | Module, integration, E2E profiles, stress workloads, migration inventory, and reviewed Social Attention data are implemented. | Inventory/migration parity, dataset validation, adapters, workload, and report tests. | Real model/service/MuJoCo/physical evidence must be collected per profile. | Evaluator only; it cannot implement intelligence. Owner: [Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md). |
| Canonical local gate | The dependency-light entrypoint now declares every imported test dependency, ignores cache-only Router residue while rejecting maintained Router content, loads deployment environment explicitly, and retains its four-file Mypy scope. | On 2026-07-31, the latest canonical run passed repository policy, test ownership, Ruff, Mypy, documentation, 1,670 primary tests, and 20 legacy Agent tests. | Not a target-validation claim. | Completed prerequisite. Owner: [Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md). |
| Current live voice loop | The `current-revision-live-voice` profile is implemented alongside the unchanged default full-matrix profile. It binds clean source, generated profile, running image/model identity, Gateway/Core events, physical recordings/devices, playback, operator review, command, and artifact digests into a claim that remains `release_qualified=false`. Shared preflight/launcher validation rejects managed Python below 3.11 before evidence creation or model warm-up. | Sixty-eight focused voice/evidence tests and the 1,670-test canonical suite pass, including rejection of synthetic/partial/dirty/mismatched/unbound/skill/stale/unreviewed evidence and an incompatible Python runtime. | No retained microphone → audible-response bundle. Attempt `20260731T110834Z` ran on Python 3.11.15 but produced no input because this PC has no microphone; no claim is made. | Implementation verified; physical target validation deferred to a host with input hardware. Owner: [Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md). |
| Engineering safeguards | Loopback publication, first failure-path audit, repository policies, Ruff/Mypy mechanisms, and test ownership are implemented. | Repository policy, Ruff, Mypy, test ownership, documentation, and the full canonical local suite pass. The 141 broad handlers still need symbol-level classification under a later Issue. | LAN exposure acceptance and live failure evidence remain open. | Development/CI gates. Owners: [Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md), [Runtime Failure Paths](RUNTIME_FAILURE_PATHS.md), and [Static Analysis](STATIC_ANALYSIS.md). |
| Typed service configuration | Complete ASR service environment is parsed once into immutable typed settings with safe diagnostics. | ASR parsing, precedence, invalid-input, backend projection, Compose, and full-suite tests. | Host/profile startup remains operational evidence. | ASR migrated; Host still participates in a 295-key literal runtime environment surface. Owner: [Service Configuration Boundaries](SERVICE_CONFIGURATION_BOUNDARIES.md). |
| VoiceAssistant composition root | Runtime-ready greeting scheduling/playback barriers are extracted; the remaining root is 8,886 lines with 167 methods and a 615-line constructor. | Greeting collaborator and current behavior suites are automatic evidence only; no structural closure is claimed. | The current live voice proof remains open. | `VoiceAssistant` remains lifecycle owner; typed settings and playback/input lifecycle extractions are queued. Owner: [Composition Root](VOICE_ASSISTANT_COMPOSITION_ROOT.md). |
| Documentation governance | Authority mapping and mechanical indexing are implemented. The baseline surface is 125 Markdown files and more than 31,000 lines, including 80 directly under `docs/`, plus three 237,276-byte in-tree archives. | Authority, links, indexing, current focus, API/configuration, and reproducibility checks pass independently. | Not a runtime target-evidence claim. | Core reading path shortened; trace consolidation and archive removal are queued. Owner: [Documentation Authority](DOCUMENTATION_AUTHORITY.md). |

A source-bound RTX 4090 Laptop launch exposed a concrete shared-GPU startup
blocker: the unchanged Ollama container retained prior model runners while the
new TTS worker attempted its first cuBLAS allocation. The launcher now resets
Ollama before the CosyVoice synthesis probe and the laptop profile permits only
one resident 32K runner. This is an implemented correction, not target evidence;
the complete current-revision closure must be initialized again and rerun.

The first clean paired-source Gateway/Core collection then reached Goal-driven
processing but stopped before planning because its evidence subprocesses did not
load the generated Orchestrator environment and used the 3.5-second
Goal-Association code default. The launcher now materializes the profile-owned
budgets, runtime identity verifies their exact alignment, and the workflow loads
and fingerprints that environment. This is an implemented provenance/runtime
correction. Diagnostic root `20260731T115108Z` subsequently completed all five
live-text cases and the compound walk/nod/turn MuJoCo execution with safe idle,
but active cancellation stopped before Provider observation because the
qualification runner inspected the Host coordinator rather than its owned Skill
Runtime and had not committed the production conversation-state execution
binding. The runner now mirrors both production boundaries. A new
committed-source evidence root is still required; the diagnostic root is not a
qualification claim.

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
