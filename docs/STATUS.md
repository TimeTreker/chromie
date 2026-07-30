# Current Implementation Status

**Status authority:** this file owns current implementation, automatic
verification, target-validation, and deployment claims.
**Development identity:** `development`; no release version or publication target is planned.
**Status refresh date:** 2026-07-30
**Active code Issue:** none.
**Active evidence Issue:** Close Current-Revision Target Evidence.

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
| Cognitive Gateway and Goal-driven Core | Gateway admission, Goal Association, Fast/terminal Deep Planning, composition, execution reconciliation, and fail-closed ownership are implemented. | Core, planning, continuity, cancellation, tool, response, policy, and full-suite tests. | Clean current live-text, active-cancellation, paired-source MuJoCo, and approved review bundle remain open. | Enabled in maintained apply lanes. Evidence owner: [Gateway/Core Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md). |
| Capabilities and Soridormi boundary | Canonical `capability_id`, one Trusted Capability Runtime, provider validation, confirmation, scheduling, and evidence joins are implemented. | Contract, runtime, TaskGraph, cancellation, and policy tests. | Current paired live provider/MuJoCo and supervised physical evidence remain open. | Chromie authorizes named contracts; Soridormi owns physical feasibility and safety. |
| Agent Skills | Read-only approved packages, model selection, role disclosure, Plan provenance, grounded external-information, and weather methods are implemented. | Loader, selection, disclosure, provenance, discourse, verified-memory, weather, result, response, policy, and full-suite tests. | Positive live selection and provider-backed weather execution are not yet retained. | Enabled; packages are passive and cannot register or execute Capabilities. Owner: [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md). |
| Social Attention | Embodiment-independent `off`, `report_only`, and `on` behavior domain with owner-approved style and provider-safe auxiliary expression is implemented. | Dataset, mode/style, priority, stillness, provider, backend-neutrality, and qualification-foundation tests. | Current 128-case live baseline, reviewed samples, and selected MuJoCo evidence remain open. | Maintained default `on`. Owner: [Social Attention Qualification](SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md). |
| Speech stack | SenseVoice final-utterance ASR, CosyVoice3 default TTS, cancellation/watchdogs, content gates, and ordered playback are implemented. | ASR/TTS provider, cancellation, alignment, startup, and voice acceptance tests. | Physical microphone accuracy, listening quality, shared-load recovery, and supervised device evidence remain open. | Local containers plus Host audio lifecycle. Owner: [TTS Evaluation](TTS_PROVIDER_EVALUATION.md) and [Acceptance](ACCEPTANCE.md). |
| Benchmark suite | Module, integration, E2E profiles, stress workloads, migration inventory, and reviewed Social Attention data are implemented. | Inventory/migration parity, dataset validation, adapters, workload, and report tests. | Real model/service/MuJoCo/physical evidence must be collected per profile. | Evaluator only; it cannot implement intelligence. Owner: [Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md). |
| Engineering safeguards | Loopback publication, classified failure paths, repository policies, Ruff/Mypy ratchets, and test ownership are implemented. | Canonical policy, exposure, failure, static-runner, ownership, docs, and full gates. | LAN exposure acceptance is open. Broad exception boundaries still require a post-evidence narrowing audit; static tools must run from installed pinned dependencies. | Development/CI gates. Owners: [Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md), [Runtime Failure Paths](RUNTIME_FAILURE_PATHS.md), and [Static Analysis](STATIC_ANALYSIS.md). |
| Typed service configuration | ASR parses its maintained environment once into immutable typed settings with safe diagnostics. Other services still read substantial environment surfaces directly. | ASR parsing, precedence, invalid-input, backend projection, Compose, and full-suite tests. | Container startup acceptance on maintained hardware profiles remains operational evidence. | First boundary migrated; profile consolidation remains post-evidence work in [Service Configuration Boundaries](SERVICE_CONFIGURATION_BOUNDARIES.md). |
| VoiceAssistant composition root | Runtime-ready greeting scheduling and playback barriers are extracted. The remaining class is still a large maintenance and regression-risk surface. | Collaborator, greeting, TTS alignment, startup, cancellation, and full-suite tests. | Source-bound runtime evidence must close before further structural extraction begins. | `VoiceAssistant` remains lifecycle owner; evidence-driven decomposition is queued in [Composition Root](VOICE_ASSISTANT_COMPOSITION_ROOT.md). |
| Documentation governance | Current authority map, concise status/checkpoint/changelog, indexed history, and mechanical ownership checks are implemented. The maintained documentation set remains larger and more repetitive than desired. | Documentation authority, links, indexing, current focus, API/configuration, and reproducibility checks. | Not a runtime target-evidence claim; semantic duplication still needs human consolidation. | Owners are declared in [Documentation Authority](DOCUMENTATION_AUTHORITY.md); consolidation is queued after runtime simplification. |

A source-bound RTX 4090 Laptop launch exposed a concrete shared-GPU startup
blocker: the unchanged Ollama container retained prior model runners while the
new TTS worker attempted its first cuBLAS allocation. The launcher now resets
Ollama before the CosyVoice synthesis probe and the laptop profile permits only
one resident 32K runner. This is an implemented correction, not target evidence;
the complete current-revision closure must be initialized again and rerun.

## Target-evidence closure

The remaining evidence tracks are coordinated by
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md). The default
`source_bound_development` profile requires source-bound Gateway/Core, positive
Agent Skill/weather, Social Attention, and second-machine LAN evidence. Physical
voice and robot evidence remain optional and supervised; they are required only
for the stricter physical-pilot profile. No current retained bundle closes these
tracks yet, and no automatic workflow grants release qualification.


During this evidence Issue, the architecture is frozen: changes may repair a
reproduced evidence blocker, improve evidence provenance, or remove dead/stale
material, but they must not add a new semantic authority, architecture layer,
ordinary behavior flag, standalone design document, or first-class term. The
post-evidence simplification order is owned by
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
