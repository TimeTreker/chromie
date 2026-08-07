# Chromie Current Status

Status: current implementation and evidence authority

Chromie remains a development project. The maintained direction is a
**Goal-driven single semantic authority**: the Cognitive Gateway owns ingress,
protective reflexes, and attention admission; the Goal-driven Cognitive Core
owns ordinary meaning, goals, planning, response composition, and outcome
reconciliation. Trusted Host and provider boundaries authorize effects.

## Current source state

| Area | Implementation | Automatic verification | Target validation | Release readiness |
|---|---|---|---|---|
| Core interpretation | Non-empty turns that cannot be interpreted now return a typed `interpretation_unavailable` outcome. They are not reassigned to chat or deep thought. | Contract, endpoint, fallback, behavior-scenario, and capability-routing tests cover unavailable and empty-input paths. | The merged `e3d57ff` diagnostic proved a live RTX 5090 Gateway/Core/Fast-Planner greeting round trip. Broader clean scenario evidence for the post-audit tree remains open. | Development only. |
| Capability repair | Semantic repair can return strict ordered action proposals only for `robot_action`; every capability and argument remains subject to catalog and policy validation. Fast and Deep Planner decoder schemas bind each exact capability ID to its provider argument schema. Explicit numeric Goal values require matching step arguments plus Goal-bound `user_supplied` provenance, and bounded same-tier repair receives structured cross-field defects. | Schema, prompt, provider-argument, numeric-provenance, bounded-repair, compound-plan, and end-to-end routing tests cover exact velocity, duration, ordering, and rejection outside the action lane. | Dirty current-tree headless MuJoCo diagnostics completed exact ordered compound execution and provider-start cancellation; clean merged revision binding and physical execution remain open. | Development only. |
| Semantic authority | Maintained profiles include memory in Goal-driven apply lanes. A disabled or unsupported mapped lane is a Core-owned authoritative fail-closed boundary and cannot enter either ordinary or legacy planning. | Semantic-authority audit, profile configuration, Orchestrator, and behavior tests cover allowlisted and excluded lanes. | Retained live service and simulator evidence must be refreshed for the patched source. | Development only. |
| Control-plane smoke | The smoke test builds an immutable Gateway/Core request and validates the current Core and Fast Planner contracts. It no longer uses the retired flat interpretation payload or ordinary `/run` planning. | Builder tests and shell syntax checks are source-verifiable. | Requires a running Agent service and configured model. | Development only. |
| Source identity | Evidence metadata uses the Git commit in a checkout or a deterministic SHA-256 source-tree identity in an archive. | Archive and checkout forms are covered by unit tests. | Runtime provenance still requires resolved image and model digests. | Development only. |
| Canonical verification | Repository, ownership, static-analysis, configuration, structure, documentation, benchmark, unit, and retained legacy checks are wired through `scripts/run_tests.sh`. GitHub Actions are pinned by immutable SHA. | The local audit environment verifies all dependency-available gates; unavailable pinned analyzers must remain reported as unavailable rather than passed. | CI and target profiles must be rerun from the final source revision. | Development only. |
| Documentation surface | Historical audits, handoffs, proposal plans, implementation plans, and duplicate registries identified by the audit have been removed. Durable rules now live in the Charter, architecture, policies, status, roadmap, API, and component guides. | Local-link, index, ownership, terminology, and surface-ratchet checks enforce the reduced tree. | Not applicable. | Maintained development documentation. |
| Reversible barge-in | VAD speech start now ducks the exact playback generation without cognitive cancellation. Likely echo/noise resumes the next unplayed chunk; confirmed external speech closes the ducked stream before output-only invalidation, then routes a new session for semantic scope. Echo comparison is order-aware so a short replay is not diluted by the rest of a long response. | Focused duck/echo/device/timeout regressions, the `deterministic_safety_controls` general-ability class, runtime exception classifications, and the canonical gate cover source behavior. The focused voice runner replays retained output PCM and enforces 250 ms duck/silence budgets, clean resume completion, distinct Gateway receipts, and no stale or duplicate output. | **Target validated for generated-speech synthetic input** on clean Chromie `94718ab` in `.chromie/acceptance/voice/issue-5-94718ab-clean`: `barge-in-echo` passed 6/6 and `barge-in` passed 7/7; VAD-start-to-duck was 0.0 ms, confirmed-speech-to-silence was 8.3 ms, the resumed echo session completed 11/11 scheduled chunks, and Gateway dispatch/provider failures were zero. Physical microphone/speaker, arbitrary human pronunciation, audible device latency, and acoustic echo-path review remain open. | Development only; automated generated speech is not physical audio or release evidence. |
| Vocal and media semantics | Goal Association separates `responsibility_kind`, `execution_lane`, `output_mode`, `provider_required`, and exact vocal/media operation. `chromie.vocal.perform` remains the qualified vocal identity. Peer media Activity uses the exact public family `chromie.media.play|pause|resume|seek|stop|volume|status`; qualified declarations own supported kinds, persistent state/progress, mixer policy, cancellation, and immutable evidence while backend identity stays private. Exact identities survive planning, Host authorization, execution, cancellation, and evidence. Singing remains Speaking, existing-audio playback remains Activity, ordinary TTS remains separate, and undeclared modes or operations fail closed. | Vocal and media fake-provider declaration/runtime/closure tests, Planner/Response Composer/projection regressions, exact cognitive-runtime scenarios, and ordinary-TTS tests cover the source contracts. Media qualification passed 15/15 focused provider tests, both focused scenarios, and the relevant `stable_capability_grounding` plus `deterministic_safety_controls` Level A classes 14/14. The canonical gate passed 2,059 maintained tests, 20 legacy Agent tests, and 102 benchmark tests. The text-to-MuJoCo runner now sends primary deterministic controls through the production Gateway reflex and retains its cancellation receipt rather than bypassing it. | **Target validated only for the default-provider distinctions and simulator body member.** Vocal evidence remains in `.chromie/acceptance/vocal-issue-6/issue-6-e558ff4-clean`. Current Issue #7 evidence under `.chromie/acceptance/media-issue-7/current-revision` retains: typed media play with an honest zero-step unavailable outcome; singing as planless Speaking with `media_operation=none`; a completed five-second Soridormi/MuJoCo walk while media stayed unavailable; and a Chinese stop-media turn that bypassed cognition, retained the exact `media_output` receipt, and left Soridormi safe-idle. No real media provider, acoustic ducking, physical microphone/speaker, or physical robot is validated. | Issues #6 and #7 meet their source and default-provider distinction criteria. The project remains development-only; this evidence qualifies neither a real vocal/media provider nor a release. |

## 2026-08-07 post-merge audit

The audit started from clean merged `main` revision `e3d57ff`. The strict
comprehensive diagnostic retained 40 passing and 8 failing checks. Four failure
groups were caused by an incomplete host test environment (`pytest`, Ruff,
Mypy, and Unidecode were absent); installing the pinned `requirements-test.txt`
set restored those gates. The running RTX 5090 stack itself was healthy: all
containers passed health checks, the Gateway/Core/Fast Planner greeting round
trip passed, GPU smoke reported 19 passes and no failures, both configured
Ollama models were resident on the GPU, TTS returned non-empty PCM, and the
generated-speech barge-in case passed 7/7. The run remains diagnostic because
the voice matrix exposed hard evidence/semantic failures and the semantic
multi-model reviewer was not configured.

The audit findings are kept here because this file owns current implementation
and evidence; the stable Project Charter is not an incident log.

| Finding and earliest responsible boundary | Implemented remediation | Automatic verification | Target validation | Release readiness |
|---|---|---|---|---|
| Ordinary and final TTS played but the Host scheduling boundary did not register it in the delivered-turn ledger, leaving `delivered_text` empty. This violated evidence-before-claim discipline. | Normal interaction speech now registers its generation, orders, text, phase, role, and commitment in the same turn ledger as other speech paths. | Focused Orchestrator regression covers scheduling and ledger correlation. | Rebuilt generated-speech matrix pending. | Open. |
| Voice acceptance required the retired `goal_interpretation_done` event although maintained ordinary decisions now emit `cognitive_core_done` and deterministic stops emit a Gateway reflex receipt. | The analyzer consumes current Core and Gateway events; the retired event is compatibility-only. | Focused ordinary-speech and stop regressions pass. | Rebuilt generated-speech matrix pending. | Open. |
| Goal Association classified a mixed stable-knowledge/reminder request as capability-dependent and anchored repair of mechanically invalid action/location bindings on the invalid DTO. This could fail a valid conversational responsibility or repeat an unsupported referent. | Stable knowledge and ordinary reasoning remain spoken responsibilities; mechanical collection/location defects trigger fresh model-owned resegmentation from the admitted turn. | Focused mixed-goal, collection, and follow-up location-provenance regressions plus the general-ability suite cover the boundary. | Live model distribution remains open. | Open. |
| Goal Interpreter session-memory output added durable-only fields. Typed validation correctly rejected it, but the old retry resent the same semantic prompt; the first revised live retry also repeated the invalid fields. | Retry now includes the rejected output and typed validation error. If one repaired response still adds durable-only fields to an explicit session/ephemeral/remember proposal, a logged mechanical recovery may only remove those fields. Profile, durable, forget, and clear contradictions still fail closed. | Focused repair and no-authority-widening regressions pass. | Clean bilingual session-memory replay pending. | Open. |
| Typed `fast_speech` fields and a same-model review still allowed tool and memory sentences that claimed observed evidence or a completed commit before either existed. The Host could therefore speak a false completion even though the DTO said `claim_state=none`. | Goal Interpreter and the Host suppress model-authored pre-effect speech for tool and memory routes without inspecting phrases. A startup-primed generic cache may own latency presentation; dynamic speech follows trusted tool evidence or memory commit. Planning and physical preludes retain independent semantic review. | Goal Interpreter and Host regressions cover route-level suppression, cache eligibility, and rejection of otherwise structurally valid payloads. | Dirty focused session-memory replay in `.chromie/acceptance/post-merge-audit-failclosed-20260807T085330Z` delivered one post-commit result and one grounded recall. Final clean matrix pending. | Open. |
| Pure safe-read Response Composer speech remained a second pre-evidence semantic owner. In the live weather follow-up it replayed old evidence before the actual tool-result response, producing duplicate audio even after Goal Interpreter speech was suppressed. | A pure safe-read Plan now emits no dynamic Response Composer stage. The optional generic Host cue owns latency presentation and the evidence-bound Tool Result Interpreter owns one post-execution answer. Mixed Plans retain reviewed acknowledgement reuse. | Focused pure/mixed safe-read, no-review, fail-soft, reuse, and plan-retention regressions pass. | Dirty focused acoustic workflow `.chromie/acceptance/post-merge-audit-pure-safe-read-20260807T090032Z` delivered exactly one `post_execution` event per turn, answered the umbrella decision first, passed unique delivery, and measured CER 0.046154. External semantic review remains pending. | Open. |
| Tool Result Interpreter rejected a grounded weather answer solely because it exceeded the sentence budget, then fell back to an unavailable message despite valid evidence. | One bounded typed repair receives the rejected output, exact contract error, and immutable evidence. The repaired answer must pass the same grounding, provenance, sentence, and safety validators; otherwise the existing fail-closed fallback remains. | Focused valid-repair, altered-evidence, invalid-repair, and fallback regressions pass. | The focused weather workflow above produced grounded post-execution answers from live provider evidence. | Open pending final clean revision evidence. |
| The planless direct Response Composer validated its primary speech and optional Social Attention as one indivisible object. A malformed empty auxiliary expression could therefore discard a valid family-help answer and produce generic failure speech. | The direct path now applies the existing authority-reducing auxiliary canonicalizer before nested validation. An empty or contradictory optional expression becomes explicit stillness; it cannot rewrite or discard the model-authored primary speech. | Focused direct-composition regression preserves exact valid speech, records `canonicalized_empty_expression`, and proves that no repair call is needed. | Dirty rebuilt acoustic replay `.chromie/acceptance/targeted-family-20260807c` delivered one natural family-help sentence with one completed event, unique delivery, and CER 0.0. External semantic review and clean revision binding remain open. | Open. |
| A clean shared-GPU multi-Goal response completed the Moon explanation and bedtime reminder but invented that the user had “a busy day tomorrow.” The helpful-sounding clause was not grounded in the turn, Goals, or conversation. | Both direct and planned Response Composer contracts now require every user-specific statement to come from the newest turn, Goals, or supplied conversation. Optional friendly reasons must remain general when no personal fact exists; the Host does not inspect phrases or author replacement meaning. | The existing direct-prompt regression asserts the reusable grounding instruction. Both Chinese and English multi-part E2E rubrics now include groundedness and explicitly reject invented personal circumstances. | Clean `258d0ec` comprehensive output exposed the defect. Dirty warmed acoustic replay `.chromie/acceptance/targeted-grounding-20260807f` delivered both Goals once and in order, used only a general rest rationale, and measured WER 0.044444. Two earlier cold attempts remain retained: one failed before connection and one authored grounded text but missed the 20-second first-playback gate. Final clean binding remains pending. | Open. |
| The weather decision follow-up could begin by replaying the complete prior report instead of answering the user's practical decision. The first prompt-only remediation did not make that contract executable: both idle and shared-GPU outputs in the repaired `d3f7b62` comprehensive run still placed weather replay before the recommendation. | A typed retained-Goal response with delivered evidence now receives one bounded model-owned communication review. The existing stronger main Agent model accepts exact text or revises only response text so the latest decision, recommendation, reaction, or yes/no act comes first; the Host neither matches phrases nor authors meaning, and review failure escalates with zero effects. Pydantic retains the closed length contract after unsupported llama.cpp grammar annotations are removed. | Focused tests cover independent reviewer ownership, exact Goal coverage, decoder-compatible schema, revision, and fail-closed exception classification. The full Level A suite remains 66/66. | A dirty forced-chat deployed probe revised the old evidence-first answer to “是的，您需要带伞。” followed by one support clause. The ordinary acoustic workflow in `.chromie/acceptance/targeted-semantic-20260807b` also delivered “一定要带上伞哦！” first with one grounded clause, unique delivery, and CER 0.068966. External semantic review and clean revision binding remain open. | Open. |
| `BUILD=1` rebuilt mutable service tags but `docker compose up` did not recreate unchanged containers, leaving a running container bound to a deleted image ID. | The service launcher adds `--force-recreate` whenever it performs a build, so running services and captured image identity match the newly built source. | Runtime-configuration regression covers the generated Compose arguments. | Agent rebuild/recreate was healthy before the focused weather workflow. Final clean profile pending. | Open. |
| The comprehensive runner inherited `BUILD=1` into its nested voice-acceptance service start, replacing an image still referenced by running containers. After that lifecycle repair, the first clean committed replay exposed a second orchestration mismatch: the three-case diagnostic bundle was passed to the full seven-case MuJoCo release verifier, which necessarily rejected its absent body cases and source-bound Soridormi endpoint. | The stack is built once per comprehensive run and nested acceptance explicitly reuses it with `BUILD=0`. The selected diagnostic runner remains its own executable assertion owner; the comprehensive collector no longer misapplies the separately owned full release verifier. No weaker verification profile or compatibility flag was added. | Shell syntax, a comprehensive-runner regression, and canonical source tests cover the orchestration path. | `bed08e6` retained 47 passes and the single verifier mismatch. Repaired `d3f7b62` retained 47 passes, zero failures/timeouts, and one external-review skip; manual output inspection then correctly blocked closure on the two semantic findings above. A final clean replay of the remediated revision remains pending. | Open pending the final clean replay and output inspection. |
| The comprehensive collector described its service phase as build/start but invoked `start_services.sh` without `BUILD=1`; a clean source revision could therefore be paired with a previously built mutable image. | The outer collector now explicitly builds and force-recreates the maintained images once, while nested voice acceptance continues to reuse them with `BUILD=0`. | A runner regression binds both sides of the one-build contract; shell and canonical gates remain required. | Diagnostic commit `0e228ac` retained 45 passes, one synthetic-analyzer failure, one external-review skip, and zero timeouts under `.chromie/comprehensive/20260807T131919Z`, but its log explicitly says the image build was skipped, so it is not source-bound target evidence. | Open pending replay from the corrected runner. |
| In that diagnostic run the first synthesized “Stop talking” was intelligible as external speech but ASR did not recognize stop intent; the automatic retry produced the correct independent Gateway cancellation receipt. The analyzer returned the first barge-in chain and required the later receipt to share that failed attempt's session ID, falsely reporting a runtime safety failure even though the event stream recorded output-only requested/effective scope and zero dispatch/provider failures. | Barge-in correlation still requires the original generation-bound duck and confirmed-silence chain, but treats the later deterministic Gateway cancellation receipt as the independently owned semantic event its contract describes. The receipt and applied reflex must share their own non-empty session ID and follow confirmed silence. | A focused retry regression reproduces the exact failed-attempt/recognized-retry sequence; existing missing-receipt and stale-output failures remain blocking. | The originating diagnostic recorded 0.0 ms duck and 3.4 ms silence before the exact retry receipt. Dirty focused replay `.chromie/acceptance/post-merge-audit-precommit/20260807T135300Z-barge-retry-correlation` then passed every check with 0.1 ms duck, 5.5 ms silence, the independent output-only receipt, and no stale playback. | Open pending final clean profile. |
| Fast Planner accepted a capability ID independently from generic step arguments, and Deep Planner lacked the same explicit-numeric grounding contract. A model could therefore select `walk_velocity` while omitting `vx_mps`, silently substitute a default for `0.2`, or author a resolution that did not match the executable step. | Both decoder schemas now use an exact per-capability argument branch. Fast revalidates provider schemas after normalization. A shared contract requires every executable numeric Goal literal to appear in a matching step argument and Goal-bound `user_supplied` resolution; false Goal provenance is rejected. Fast validation evidence is propagated to Deep, whose bounded retry receives structured argument/resolution mismatches. | Focused Fast, Deep, planner-binding, and cognitive-runtime regressions pass. The relevant `stable_capability_grounding` and `deterministic_safety_controls` Level A classes pass 14/14. | Dirty current-tree evidence `.chromie/acceptance/post-merge-audit-precommit/20260807T134500Z-aggregate-numeric-live/mujoco` completed `walk_velocity(vx_mps=0.2,duration_s=10)`, `nod_yes(count=2)`, and `turn_in_place` in order, reconciled all Goals, and ended standing safe-idle. | Open pending clean revision binding; simulator evidence is not physical-robot evidence. |
| Deep Planner prompt prose promised the full executable catalog, but the unprojected catalog exceeded its 16,000-character bound; later exact capabilities, including `soridormi.walk_velocity`, were absent from the deployed prompt. This violated capability-grounding and truthful-contract principles. | Deep Planner projects every supplied capability's exact ID, description, input schema, route, confirmation, effects, safety, resource/concurrency declarations, semantic scope, and non-duplicate execution constraints before bounded serialization. Relevant capabilities are ordered first from typed advisory and validator evidence; the Host still makes no phrase-to-capability choice. | Focused prompt tests prove a terminal capability remains visible even when earlier provider hints are oversized, and exact provider argument branches retain all allowed IDs. | The compound MuJoCo diagnostic above selected the previously truncated exact velocity capability and preserved both supplied numeric values. | Open pending clean revision binding and broader live-model distribution. |
| Deep Planner's decoder schema bounded neither step count nor recursive explanatory text. For a single 20-second walk, the deployed model repeated the same step until the 8,192-token output limit, preventing the deterministic stop scenario from ever reaching the provider. | The schema now permits at most four compositional steps per Goal, instructs repetition through capability count arguments, bounds resolutions/unresolved items, and applies closed prose limits without weakening stricter zero-length route contracts. One bounded same-tier regeneration remains the only repair path. | Focused schema tests cover the per-Goal step bound and preservation of stricter vocal/media response limits; planner and runtime regressions pass. | Dirty current-tree evidence `.chromie/acceptance/post-merge-audit-precommit/20260807T140500Z-deep-bounds-cancel/mujoco` reached `soridormi.walk_velocity(vx_mps=0.2,duration_s=20)`, observed provider start, cancelled through the production Gateway reflex in 62.7 ms, and returned standing safe-idle with no active task. | Open pending clean revision binding; no physical microphone, speaker, or robot is claimed. |
| The paired-launcher child-exit regression used fixed MCP port 8000. Running the canonical source gate beside the retained live stack let that unrelated endpoint satisfy readiness, so a deliberately failed child was masked until the test's outer timeout. | The test now reserves an isolated loopback port and passes it through the public launcher option. It still exercises the real launcher process and child-exit message without depending on global service state. | The focused regression reports the simulated Soridormi child failure in 0.05 seconds while the live port-8000 stack remains running. | Not applicable; this is test isolation, not simulator or hardware evidence. | Closed as an automatic-evidence defect. |
| README, checkpoint, acceptance, semantic-authority, configuration, and Orchestrator compatibility prose lagged merged behavior. Mechanical link/terminology checks did not detect the semantic mismatch. | Existing authoritative owners were corrected; no standalone audit document, environment switch, or architectural term was added. | Documentation, semantic-authority, and repository-policy gates remain required. | Not applicable. | Documentation is current only while the final gates pass. |

The audit added no current document, public environment key, compatibility path,
or architectural term. Documentation count remains 102 and the runtime
configuration inventory remains 458 keys, four modes, one public boolean, and
zero aliases. Physical microphone/speaker behavior, physical robot behavior,
real vocal/media providers, resolved release provenance, and release readiness
remain explicitly unproven.

The post-audit source tree passed the dependency-complete canonical gate: 13
repository-policy families, test ownership, Ruff, Mypy, configuration ownership,
runtime-structure ratchets, documentation checks, 102 benchmark tests, 2,095
maintained tests, and 20 legacy Agent tests. The full Level A general-ability run
passed 66/66 across all ten classes. These are automatic source claims; the
required clean committed comprehensive runtime profile remains a separate gate.

The paired Soridormi repository-gate audit is merged on its `main` revision
`fa8080d2a4a5e1c47a1c77a1748aa65e6dec4d83`. Chromie's generated capability
snapshot and compatibility authority bind that exact revision; regeneration
changed provenance only, not the exported capability contract.

## Compatibility state

`POST /interaction` and `POST /run` remain compatibility interfaces. Their old
CapabilityAgent semantic planner is emergency-only and requires explicit service
and per-turn authority gates. Normal Goal-driven apply failures and excluded
lanes do not enter it. Exact Core action proposals may cross a deterministic
compatibility adapter, but the adapter cannot reinterpret meaning or authorize
execution.

The compatibility planner should be removed after current replay, live-service,
and operator rollback evidence shows that no maintained profile depends on it.

## Open source issues

- Close the post-merge remediation with a clean dependency-complete canonical
  gate and rebuilt generated-speech/GPU comprehensive profile.
- Keep the vocal-hosting decision deferred until a measured synchronization,
  cancellation-latency, platform-adaptation, or resource-contention blocker is
  retained.
- Reduce the Orchestrator composition root while preserving current structural
  ratchets and exception boundaries.
- Remove remaining compatibility planner code after equivalent retained
  evidence exists.
- Keep dependency-complete Ruff and Mypy execution available in the maintained
  CI environment.
- Continue replacing development-only mutable runtime aliases with resolved
  digests in publishable provenance rather than pretending local aliases are
  immutable.

## Open target evidence

- a clean full generated-speech scenario matrix for the final post-audit
  revision (the `e3d57ff` Gateway/Core/Fast-Planner smoke is diagnostic);
- clean merged-revision binding for the exact compound body execution and
  provider-start voice-to-MuJoCo cancellation diagnostics retained on the dirty
  candidate tree;
- microphone intelligibility and first-audible TTS latency;
- physical microphone/speaker barge-in, echo rejection, and resume latency;
- mode-specific target evidence for any real vocal-performance provider;
- operation-specific lifecycle, progress, cancellation, and mixer evidence for
  any real peer media provider;
- physical-speaker playback and speech-over-media acoustic ducking evidence;
- shared-GPU warm/cold latency and contention behavior;
- investigation of the observed 36-second first synthesis after a cold TTS
  worker start; warmed median first audio was about 1.03 seconds in the same
  diagnostic and no release latency budget is claimed;
- physical-provider commissioning, stop, recovery, and rollback;
- resolved container and model artifact digests for any future publication.

## Verification commands

```bash
./scripts/run_tests.sh
python scripts/semantic_authority_audit.py --check
./scripts/benchmark_check.sh
bash scripts/gpu_smoke_test.sh
```

The first three commands are source gates. The GPU smoke requires running
services. Physical audio and robot claims require retained target evidence under
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md).

## Status vocabulary

- **Implemented:** source and contracts exist.
- **Automatically verified:** maintained automated checks pass for the source.
- **Target validated:** retained evidence exists from the required runtime,
  simulator, GPU, audio device, or robot.
- **Release ready:** publication inputs, compatibility, provenance, support, and
  rollback are closed for a declared release target.

Do not collapse these states into “done.”
