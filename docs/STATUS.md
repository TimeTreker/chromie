# Current Implementation Status

**Status authority:** this file describes what is present in the repository snapshot.
**Verified base revision:** `8c448e2de2cd8a602b0d48e31461f9be9f1b8d08`; release tooling records the exact post-patch revision
**Verified date:** 2026-06-13
**Current engineering milestone:** **M13 — Native Interaction Agent and end-to-end voice acceptance**
**Version candidate:** `0.1.0-alpha.1` (prepared, not published)
**Soridormi capability snapshot:** `a092dc704f1ab797fb1d4f542696fe75026eb171`

`ROADMAP.md` describes milestone intent. This file is the source of truth for
current implementation, automated evidence, target evidence, and release
readiness.

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
| Five Docker services plus host Orchestrator | Implemented | Compose and control-plane tests | Target GPU smoke tooling exists; retained target run is still required | Main runtime |
| Realtime microphone/VAD/ASR/TTS/playback loop | Implemented | Component tests plus automatic TTS-generated stdin and virtual-microphone acceptance modes | Supervised real-microphone/speaker reference-host bundle still open | Enabled after host audio setup |
| Deterministic Router operational controls | Implemented | Router rule tests | Exercised by deployed smoke test | Enabled by `.env.common` |
| Multi-agent `POST /run` compatibility path | Implemented | Contract and integration tests | Used by the current voice loop | Enabled by `.env.common` |
| Structured `POST /interaction` API | Native `InteractionRuntime` is the default; compatibility adapter remains selectable | Native output, strict validation, fallback, and end-to-end named-skill tests | Text-to-live-MuJoCo path exists | Host rollout flag off |
| Native structured Interaction Agent | Implemented with direct `InteractionSpeech`/`SkillRequest` accumulation | Native route, TaskGraph, validation, fail-closed, fallback, and compatibility-mode tests | Microphone retention still open | Agent default |
| Trusted host Skill Runtime | Implemented | Scheduling, confirmation, timeout, cancellation, and isolation tests | Text-to-live-MuJoCo acceptance exists | Used only by structured path |
| Local speech skill provider | Implemented | Skill Runtime tests | Exercised by text acceptance; microphone retention still open | Available in structured path |
| Soridormi named-skill provider | Implemented | Provider and interaction-coordinator tests | Live MCP/MuJoCo planning, execution, and cancellation paths exist | Provider flag off |
| Conversation state across VAD utterances | Implemented in host memory | Boundary, follow-up, and limit tests | Available in the host Orchestrator | Enabled by `.env.common` |
| Structured acceptance evidence capture | JSONL events, generated/captured audio, redacted runtime snapshot, case checks, and three explicit modes implemented | Synthetic/virtual-mic framing, isolation, and bundle-verification tests | Only supervised mode is release-closing; reviewed bundle still open | Acceptance-only |
| Capability registry and deployment probe | Implemented | Registry, manifest, pagination, and schema tests | Checked-in Soridormi manifest is pinned to an upstream commit | Manifest loading opt-in |
| LLM TaskGraph planning | Implemented | Planner validation and fallback tests | No automatic dispatch by design | Flag off |
| Read-only TaskGraph execution | Implemented | Preflight, references, parallelism, retry, timeout, fallback, and cancellation tests | Live MCP acceptance can exercise it | Flag off |
| Stateful planning-only TaskGraph execution | Implemented | Planning policy and concurrency tests | Safe Soridormi plan creation acceptance exists | Flag off |
| Guarded side-effect execution | Implemented | Authorization, one-time grant, confirmation, monitor, fallback, and cancellation tests | Soridormi dry-run and runtime-cancellation tooling exists | Flag off; bearer token required |
| Physical TaskGraph execution | Policy path implemented | Safety and sequential-execution tests | Supervised hardware acceptance remains open | Separate flag off |
| Shared bounded scheduling and resource arbitration | Implemented | Agent and Orchestrator concurrency tests | MuJoCo interaction path exercises the policy | Parallel flags off |
| Hardware profile detection and generated `.env.runtime` | Implemented | Profile-detection tests | Desktop and Jetson packaging evidence is incomplete | Automatic |
| Host hardware daemon | Legacy mock compatibility implementation | Hardware/control-plane tests | No production hardware claim | Optional; mock driver only |
| Alpha release packaging | Candidate version, notes, compatibility file, archive/checksum generator, and strict release gate implemented | Packaging/evidence unit tests and full suite | No publishable bundle until real evidence and confirmation blocker close | Candidate only |

## Verified automated evidence

The repository test command is:

```bash
./scripts/run_tests.sh
```

At the verified revision it runs:

- **155** current `unittest` cases under `tests/`;
- **20** dependency-light legacy Agent test functions under `agent/tests/`;
- documentation consistency checks after this documentation refresh.

The tests do not prove GPU performance, microphone quality, speaker quality, or
real robot safety.

## M13 open gates

M13 is not closed until all of the following are complete:

1. Non-skippable confirmation is represented as an actual spoken user
   dialogue and produces request-bound authorization evidence.
2. The automatic `synthetic` and `virtual-mic` matrices pass for regression,
   then `scripts/m13_voice_acceptance.py --mode supervised` is run on the
   reference host for all seven cases and
   `scripts/verify_m13_evidence.py --require-clean` passes.
3. The retained bundle is reviewed for audible quality, simulator safe idle,
   cancellation/recovery behavior, correlated IDs, and absence of secrets.
4. The candidate compatibility file has no remaining M13 closure blockers and
   a clean release bundle is generated from the accepted revision.

## Open target-evidence tracks

These older milestone tracks remain open but do not define the current
engineering milestone:

- **M3:** run `scripts/gpu_smoke_test.sh` on the supported NVIDIA target and
  retain the results.
- **M5:** run `scripts/m5_target_acceptance.sh` with a supervised,
  runtime-backed Soridormi endpoint and complete the documented recovery step.
- **Audio:** automatic synthetic and virtual-microphone modes are implemented;
  retain real microphone/speaker device information, timing logs, and pass/fail
  notes from the supervised M13 matrix.
- **Hardware:** real motion remains experimental until Soridormi commissioning,
  confirmation, monitor, cancellation, stop, and recovery evidence are all
  retained for the exact hardware configuration.

## Known limitations

- The default structured interaction feature flags are off.
- Native interaction output is the Agent default, but the host structured
  rollout remains default-off until M13 acceptance evidence is retained.
- `AGENT_NATIVE_INTERACTION_FALLBACK` is default-off so malformed native output
  fails closed unless an operator explicitly enables adapter fallback.
- The checked-in Soridormi manifest is a pinned contract snapshot; the live
  endpoint must be probed before execution is enabled.
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

Treat this revision as a **prepared alpha candidate suitable for supervised
validation**, not as a published or production release. The release generator
refuses a publishable bundle while tracked M13 blockers remain. See
[Release and Packaging](RELEASE.md).
