# Current Implementation Status

**Status authority:** this file describes what is present in the repository snapshot.
**Verified base revision:** `857c15f` plus retained evidence listed below;
release tooling records the exact packaged revision
**Verified date:** 2026-06-17
**Current focus:** **Physical pilot preparation after M13 text-to-MuJoCo
closure; physical audio validation remains a separate release-support track**
**Version candidate:** `0.1.0-alpha.1` (prepared, not published)
**Soridormi capability snapshot:** `4afb4bc6411db4a4194e97349d9466a62efd2f24`

`ROADMAP.md` describes milestone intent. This file is the source of truth for
current implementation, automated evidence, target evidence, and release
readiness.

The stable project goal and ownership boundaries are defined in
[Project Charter](PROJECT_CHARTER.md).

The provider-readiness milestone is complete. A live local Soridormi MCP
endpoint passed the `sim`, recommendation-only `hardware_shadow`, and no-motion
`hardware_dry_run` conformance profiles, profile parity, and all 16 injected
fault scenarios. This is no-motion provider-contract evidence from macOS ARM64;
it is not Linux/GPU MuJoCo, audio-device, or physical-robot evidence.

On June 14, 2026, the Linux x86_64 reference host with an NVIDIA GeForce RTX
5090 retained:

- GPU smoke `20260614T130944Z`: 21 passed, 0 failed, including ASR/TTS GPU
  visibility, non-empty TTS PCM, and `gemma4:26b` loaded 100% on GPU;
- synthetic M13 `20260614T132934Z`: all seven cases passed at Chromie revision
  `f0e22ba`;
- virtual-microphone M13 `20260614T133155Z`: all seven cases passed through
  PipeWire at the same revision.

Both M13 bundles pass `verify_m13_evidence.py --allow-automated --require-clean`
with no errors or warnings. They are retained automated target-host evidence,
not release-closing physical microphone/speaker evidence.

On June 17, 2026, the same development line retained:

- synthetic M13 `20260617T075825Z`: all seven cases passed at Chromie revision
  `4604a03`, including the live Soridormi catalog and host confirmation path;
- text-to-MuJoCo `20260617T081411Z`: the text request “walk ahead at 0.2 speed
  for 10 seconds and then nod your head twice, then turn left” routed to ordered
  `soridormi.walk_velocity`, `soridormi.nod_yes`, and
  `soridormi.turn_in_place`; all three completed in MuJoCo `sim` mode and the
  status check ended standing, with no active task and no emergency stop.

That text-to-MuJoCo evidence closes the historical M13 text interaction scope.
It intentionally skips microphone and ASR. Physical microphone/speaker
validation remains open only for future voice-device release claims.

## Status vocabulary

Chromie tracks four independent states. Do not collapse them into one word such
as “done.”

| State | Meaning |
|---|---|
| Implemented | The code path exists in this repository. |
| Automatically verified | A repeatable test covers the behavior without requiring the target GPU, microphone, or robot. |
| Target validated | The behavior has retained evidence from the intended GPU, audio device, simulator, or hardware environment. |
| Release ready | The behavior is supported, documented, packaged, and included in a published release scope. |

A feature can be implemented and automatically verified while still lacking
Target validation or Release readiness.

## Current capability matrix

| Capability | Implementation | Automated evidence | Target or live evidence | Default deployment state |
|---|---|---|---|---|
| Five Docker services plus host Orchestrator | Implemented | Compose and control-plane tests | RTX 5090 GPU smoke passed 21/21; all services healthy | Main runtime |
| Realtime microphone/VAD/ASR/TTS/playback loop | Implemented; ASR inference runs off the WebSocket event loop and cancelled native TTS generation is terminated through a restartable worker process | Component concurrency/cancellation tests plus automatic TTS-generated stdin and virtual-microphone acceptance modes | Synthetic and PipeWire virtual-mic matrices passed 7/7; physical microphone/speaker validation remains open for voice-device release claims | Enabled after host audio setup |
| Deterministic Router operational controls | Implemented | Router rule tests | Exercised by deployed smoke test | Enabled by `.env.common` |
| Multi-agent `POST /run` compatibility path | Implemented | Contract and integration tests | Used by the current voice loop | Enabled by `.env.common` |
| Structured `POST /interaction` API | Native `InteractionRuntime` is the default; compatibility adapter remains selectable | Native output, strict validation, fallback, and end-to-end named-skill tests | Text-to-live-MuJoCo evidence `20260617T081411Z` passed with ordered walk, nod, turn execution and safe idle | Host rollout flag off |
| Native structured Interaction Agent | Implemented with direct `InteractionSpeech`/`SkillRequest` accumulation and simulator-bounded expressive body cues | Native route, TaskGraph, validation, fail-closed, fallback, expressive chat attention/nod cues, and compatibility-mode tests | Text-input MuJoCo closure evidence retained; physical microphone retention remains separate | Agent default |
| Trusted host Skill Runtime | Implemented | Scheduling, confirmation, timeout, cancellation, and isolation tests | Text-to-live-MuJoCo closure evidence passed | Used only by structured path |
| Spoken request-bound confirmation | Implemented with host-owned prompt, exact request fingerprint, expiry, single-use approval, and denial | Approval, denial, ambiguity, replay, mutation, expiry, and authorization tests | Clean synthetic and virtual-mic approval/denial evidence passed; text-to-MuJoCo uses the same trusted runtime authorization boundary | Structured path; simulator exemption configurable |
| Local speech skill provider | Implemented | Skill Runtime tests | Exercised by text acceptance; physical speaker validation remains separate | Available in structured path |
| Soridormi named-skill provider | Implemented | Provider and interaction-coordinator tests | Live MCP/MuJoCo planning, execution, and cancellation paths exist | Provider flag off |
| Provider failure normalization | Strict catalog/availability/plan/monitor/completion validation, stable timeout/cancellation terminal states, deterministic language-matched speech fallback, and a versioned 16-scenario replayable fault matrix with configurable latency thresholds, status snapshots, and safe-idle enforcement | Matrix, threshold and safe-idle evaluation, provider restart, unavailable skill, deterministic jitter, dropped monitor status, malformed completion, mismatched identity, disconnect-during-cancel, timeout, fallback, and completion-suppression tests | Live Soridormi-owned injection passed 16/16 scenarios; all ended safe-idle with no threshold violations | Used by Soridormi named skills |
| Provider conformance | Shared versioned checks and replayable high-level traces for simulator, recommendation-only hardware shadow, and no-motion hardware dry-run profiles, plus manifest preflight and strict retained-evidence verification | Local three-profile parity, trace-drift detection, opaque-identity normalization, profile-specific no-motion proofs, unsafe-output rejection, manifest preflight, and complete/unsafe bundle tests | Live no-motion `sim`, `hardware_shadow`, and `hardware_dry_run` profiles passed with parity; real hardware mode remains refused | Test tooling; real hardware mode refused |
| Conversation state across VAD utterances | Implemented in host memory | Boundary, follow-up, and limit tests | Available in the host Orchestrator | Enabled by `.env.common` |
| Structured acceptance evidence capture | Readiness preflight plus JSONL events, generated/captured audio, redacted runtime snapshot, case checks, and three explicit voice modes implemented; text-MuJoCo evidence writes route, interaction, execution, status, events, and summary artifacts | Preflight, synthetic/virtual-mic framing, isolation, text-MuJoCo, and bundle-verification tests | Clean synthetic, virtual-mic, and text-MuJoCo evidence retained; physical supervised mode remains optional release-support evidence for real audio claims | Acceptance-only |
| Capability registry and deployment probe | Implemented | Registry, manifest, pagination, and schema tests | Checked-in Soridormi manifest is pinned to an upstream commit | Manifest loading opt-in |
| LLM TaskGraph planning | Implemented | Planner validation and fallback tests | No automatic dispatch by design | Flag off |
| Read-only TaskGraph execution | Implemented | Preflight, references, parallelism, retry, timeout, fallback, and cancellation tests | Live MCP acceptance can exercise it | Flag off |
| Stateful planning-only TaskGraph execution | Implemented | Planning policy and concurrency tests | Safe Soridormi plan creation acceptance exists | Flag off |
| Guarded side-effect execution | Implemented; diagnostics are bearer-protected and trace/grant retention is bounded | Authorization, one-time grant, retention, confirmation, monitor, fallback, and cancellation tests | Soridormi dry-run and runtime-cancellation tooling exists | Flag off; bearer token required |
| Physical TaskGraph execution | Policy path implemented | Safety and sequential-execution tests | Supervised hardware acceptance remains open | Separate flag off |
| Reference robot candidate gate | Versioned schema, intentionally incomplete template, and fail-closed semantic verifier implemented | Identity, revision, timestamp, emergency-stop, calibration, exclusion, low-level-field, and no-motion authorization tests | No real candidate has been recorded or selected | Preparation only; cannot authorize motion |
| Shared bounded scheduling and resource arbitration | Implemented | Agent and Orchestrator concurrency tests | MuJoCo interaction path exercises the policy | Parallel flags off |
| Hardware profile detection and generated `.env.runtime` | Implemented | Profile-detection tests | RTX 5090 profile and CUDA arch 120 validated; Jetson packaging evidence is incomplete | Automatic |
| Host hardware daemon | Legacy mock compatibility implementation | Hardware/control-plane tests | No production hardware claim | Optional; mock driver only |
| Alpha release packaging | Candidate version, notes, compatibility file, archive/checksum generator, and strict release gate implemented | Packaging/evidence unit tests and full suite | M13 text scope is closed; publishable voice-device scope still requires its declared physical audio evidence or a narrowed compatibility claim | Candidate only |

## Verified automated evidence

The repository test command is:

```bash
./scripts/run_tests.sh
```

For focused Level A development checks, `python scripts/test_matrix.py --list`
shows roadmap-aligned module groups and declared combinations. These checks are
convenience slices over the existing automated tests and do not replace the
canonical full-suite gate above.

At the current working revision it runs:

- **278** current `unittest` cases under `tests/`;
- **20** dependency-light legacy Agent test functions under `agent/tests/`;
- documentation consistency checks after this documentation refresh.

The tests alone do not prove GPU performance, microphone quality, speaker
quality, or real robot safety. The retained RTX evidence above separately
validates the target GPU and automated host audio paths.

`scripts/interaction_text_mujoco_check.py` is available for text-input,
speaker-output, live-MuJoCo checks that skip microphone and ASR. The retained
`20260617T081411Z` bundle is the historical M13 text interaction closure
evidence. It does not prove physical microphone recognition or speaker quality.

`scripts/interaction_text_skill_sweep.py` is available for text-input
preview sweeps across maintained Soridormi skill prompts. It reports live
available skills without text cases and executes motion only when explicitly
run with `--execute` against a supervised simulator endpoint.

## Open release-support gates

M13 text interaction is closed. A release that continues to claim physical
voice-device support is not publishable until all of the following are complete:

1. Run `scripts/m13_voice_acceptance.py --mode supervised` on the reference
   host for all seven cases and ensure
   `scripts/verify_m13_evidence.py --require-clean` passes.
2. The retained bundle is reviewed for audible quality, simulator safe idle,
   cancellation/recovery behavior, correlated IDs, and absence of secrets.
3. The candidate compatibility file has no remaining release blockers and
   a clean release bundle is generated from the accepted revision.

## Open target-evidence tracks

These legacy evidence tracks do not define the current delivery:

- **Target GPU:** complete on the RTX 5090 reference host with a retained 21/21
  smoke pass; repeat on any hardware claimed by a release.
- **Combined target runner:** run the legacy-named
  `scripts/m5_target_acceptance.sh` with a supervised, runtime-backed Soridormi
  endpoint and complete the documented recovery step.
- **Audio:** automatic synthetic and virtual-microphone modes passed; real
  microphone/speaker device information, timing logs, and pass/fail notes are
  still needed only for a physical voice-device release claim.
- **Hardware:** real motion remains experimental until Soridormi commissioning,
  confirmation, monitor, cancellation, stop, and recovery evidence are all
  retained for the exact hardware configuration.

## Known limitations

- The default structured interaction feature flags are off.
- Native interaction output is the Agent default, but the host structured
  rollout remains default-off until alpha acceptance evidence is retained.
- `AGENT_NATIVE_INTERACTION_FALLBACK` is default-off so malformed native output
  fails closed unless an operator explicitly enables adapter fallback.
- The checked-in Soridormi manifest is a pinned contract snapshot; the live
  endpoint must be probed before execution is enabled.
- Provider-readiness preflight passes for the pinned Soridormi snapshot.
  Physical motion still requires an exact robot selection and supervised
  commissioning evidence.
- Jetson profiles select model/runtime values, but this repository does not yet
  include verified Jetson-specific Dockerfiles or Compose overrides.
- The host hardware daemon currently constructs `MockRobotDriver` regardless of
  serial-related modules or environment variables. It is not a production
  hardware backend.
- TaskGraph and Skill Runtime schedulers are process-local. Cross-process robot
  exclusivity remains Soridormi’s responsibility.
- Candidate release notes, compatibility metadata, archive generation, and
  checksums exist, but there is no published GitHub release or support promise
  in this snapshot.

## Release classification

Treat this revision as a **completed M13 text-to-MuJoCo candidate and a
prepared voice alpha candidate**, not as a published or production release. The
release generator refuses a publishable bundle while tracked release blockers
remain. See [Release and Packaging](RELEASE.md).
