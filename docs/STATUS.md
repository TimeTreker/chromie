# Current Implementation Status

**Status authority:** this file owns current implementation, automatic
verification, target-validation, and deployment claims.
**Development identity:** `development`; no release version or publication target is planned.
**Status refresh date:** 2026-07-30
**Active code Issue:** none; the accepted engineering-sustainability implementation program is complete.

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
bounded compatibility boundaries. The repository policy gate mechanically
protects these corrections. The final audited tree passes 1,631 primary tests
and 20 legacy Agent tests; pinned Ruff/Mypy execution remains a required local
static gate rather than evidence claimed from the restricted artifact sandbox.
See [Final Core-Principle Audit](FINAL_CORE_PRINCIPLE_AUDIT.md).

## Four-axis status

| Capability area | Implementation | Automatic verification | Target validation | Deployment state / owner |
|---|---|---|---|---|
| Cognitive Gateway and Goal-driven Core | Gateway admission, Goal Association, Fast/terminal Deep Planning, composition, execution reconciliation, and fail-closed ownership are implemented. | Core, planning, continuity, cancellation, tool, response, policy, and full-suite tests. | Clean current live-text, active-cancellation, paired-source MuJoCo, and approved review bundle remain open. | Enabled in maintained apply lanes. Evidence owner: [Gateway/Core Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md). |
| Capabilities and Soridormi boundary | Canonical `capability_id`, one Trusted Capability Runtime, provider validation, confirmation, scheduling, and evidence joins are implemented. | Contract, runtime, TaskGraph, cancellation, and policy tests. | Current paired live provider/MuJoCo and supervised physical evidence remain open. | Chromie authorizes named contracts; Soridormi owns physical feasibility and safety. |
| Agent Skills | Read-only approved packages, model selection, role disclosure, Plan provenance, grounded external-information, and weather methods are implemented. | Loader, selection, disclosure, provenance, discourse, verified-memory, weather, result, response, policy, and full-suite tests. | Positive live selection and provider-backed weather execution are not yet retained. | Enabled; packages are passive and cannot register or execute Capabilities. Owner: [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md). |
| Social Attention | Embodiment-independent `off`, `report_only`, and `on` behavior domain with owner-approved style and provider-safe auxiliary expression is implemented. | Dataset, mode/style, priority, stillness, provider, backend-neutrality, and qualification-foundation tests. | Current 128-case live baseline, reviewed samples, and selected MuJoCo evidence remain open. | Maintained default `on`. Owner: [Social Attention Qualification](SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md). |
| Speech stack | SenseVoice final-utterance ASR, CosyVoice3 default TTS, cancellation/watchdogs, content gates, and ordered playback are implemented. | ASR/TTS provider, cancellation, alignment, startup, and voice acceptance tests. | Physical microphone accuracy, listening quality, shared-load recovery, and supervised device evidence remain open. | Local containers plus Host audio lifecycle. Owner: [TTS Evaluation](TTS_PROVIDER_EVALUATION.md) and [Acceptance](ACCEPTANCE.md). |
| Benchmark suite | Module, integration, E2E profiles, stress workloads, migration inventory, and reviewed Social Attention data are implemented. | Inventory/migration parity, dataset validation, adapters, workload, and report tests. | Real model/service/MuJoCo/physical evidence must be collected per profile. | Evaluator only; it cannot implement intelligence. Owner: [Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md). |
| Engineering safeguards | Loopback publication, explicit failure paths, repository policies, Ruff/Mypy ratchets, and test ownership are implemented. | Thirteen-family canonical policy, exposure, failure, static-runner, ownership, docs, and full gates. | LAN exposure acceptance is open; static tools must run from installed pinned dependencies. | Development/CI gates. Owners: [Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md) and [Static Analysis](STATIC_ANALYSIS.md). |
| Typed service configuration | Complete ASR service environment is parsed once into immutable typed settings with safe diagnostics. | Parsing, precedence, invalid-input, backend projection, ASR, Compose, and full-suite tests. | Container startup acceptance on maintained hardware profiles remains operational evidence. | ASR migrated; remaining map in [Service Configuration Boundaries](SERVICE_CONFIGURATION_BOUNDARIES.md). |
| VoiceAssistant composition root | Runtime-ready greeting scheduling and playback barriers are extracted; remaining lifecycle responsibilities are intentionally composed. | Collaborator, greeting, TTS alignment, startup, cancellation, and full-suite tests. | Normal live startup greeting remains covered only when retained from a source-bound deployment. | `VoiceAssistant` remains lifecycle owner. Owner: [Composition Root](VOICE_ASSISTANT_COMPOSITION_ROOT.md). |
| Documentation governance | Current authority map, concise status/checkpoint/changelog, indexed historical archives, and mechanical ownership checks are implemented. | Documentation authority, links, indexing, current focus, API/configuration, and reproducibility checks. | Not a runtime target-evidence claim. | Owners are declared in [Documentation Authority](DOCUMENTATION_AUTHORITY.md). |

## Open evidence priorities

- [Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md)
- [Social Attention Baseline Qualification](SOCIAL_ATTENTION_BASELINE_QUALIFICATION.md)
- [Physical Audio Validation](ACCEPTANCE.md)
- [User-Outcome Acceptance](USER_OUTCOME_ACCEPTANCE.md)
- [Release and evidence rules](RELEASE.md)

## Deployment truth

- The common safe base applies `chat,tool` and keeps Soridormi disabled.
- The maintained Soridormi launcher widens authority to
  `chat,robot_action,tool` only after trusted provider registration.
- Simulation is not physical evidence.
- Default-off experiments and compatibility paths are not release support.
- The repository remains a development snapshot.

Detailed narrative retained before consolidation is available in
[Implementation Status Archive — 2026-07-30](STATUS_ARCHIVE_2026-07-30.md).
