# Development Checkpoint

**Current release-prep base:** `0.0.1`
**Soridormi capability snapshot:** generated from the paired Soridormi checkout; see `capabilities/soridormi.json` metadata for provenance
**Status refresh date:** 2026-07-04
**Current focus:** Freeze `0.0.1` through the Chromie/Soridormi boundary with
Soridormi using MuJoCo `sim` execution; physical pilot preparation and human
voice-device validation remain separate tracks

This file is a short resume marker, not a second status or roadmap. Use
[Status](docs/STATUS.md) for capability claims and [Roadmap](ROADMAP.md) for
milestone intent.

## Resume point

The `0.0.1` release implementation is present:

- native strict structured interaction;
- trusted host Skill Runtime and Soridormi named skills;
- request-bound spoken confirmation;
- deterministic interruption and cancellation;
- seven-case synthetic, virtual-microphone, acoustic, and supervised acceptance
  tooling;
- evidence verification and release packaging;
- small-model quick Router classification for normal semantic routing while
  stop/cancel/ignore controls remain deterministic;
- model-assisted routing guardrails that treat `qwen3:0.6b` as a proposer, not
  the authority for capabilities, safety, or physical execution;
- short-term session memory exposed to Router and Agent prompts, plus a
  dedicated deepthinking Agent path for low-confidence or complex requests;
- three-stage routing metadata where emergency filtering, quick intent routing,
  and deepthought handoff can each contribute high-level task/action proposals
  to the merged `RouteDecision.metadata.task_list`;
- host-side task-proposal merge ledger that treats Router task list entries as
  proposals, marks effectful proposals as `not_committed` until matched by a
  final `InteractionResponse` skill, and audits committed speech/skills plus
  static preflight status and rejected deepthinking tasks without widening
  execution authority;
- experience records retain task-proposal and preflight summaries as
  owner-review-only learning signals when mismatches, blocked static checks, or
  truth reconciliation occur; these summaries do not auto-apply rules and do
  not inject raw proposal payloads into prompts;
- host truth reconciliation has a first warning-misread repair path: a mistaken
  quick proposal such as window gaze for "Look out!" is superseded by specific
  warning speech and no physical skill is emitted;
- `shared/chromie_contracts/task_proposal.py` defines the first shared
  proposal ledger contract, including preflight annotations and the
  `superseded` state; Orchestrator ledger output is validated through this
  contract, and Router now emits shared `metadata.task_proposals` alongside
  legacy `metadata.task_list`; the Agent deepthinking path now emits shared
  `metadata.deepthinking_task_proposals`; final Agent speech and skills now
  emit shared `metadata.agent_task_proposals`, including speech as the local
  `chromie.speak` skill;
- host ability registry entries for cognition, speech, memory, social, body,
  manipulation, navigation, environment, task, safety, and state abilities,
  including `known_missing` and `planned` entries for unavailable human-like
  behaviors;
- dream-broadly/execute-honestly proposal contract: quick Router and
  deepthinking may record understood but non-executable desired abilities as
  `missing_ability` task proposals, while executable work still requires exact
  catalog skill IDs and trusted runtime validation;
- simulator-bounded expressive body cues and safe defaults for underspecified
  walking requests;
- ordered TTS playback with bounded chunked generation through configured
  service workers;
- Soridormi task-agent contract loading, structured task submission,
  idempotent `client_task_ref` generation, task-event monitoring, and
  fail-closed handling for task refusal, failure, timeout, and cancellation
  with deterministic blocked-subsystem reporting, trace outcome summaries, and
  trace-only report fallbacks;
- native `chromie.task_graph.execute` Skill Runtime dispatch to the Agent
  planning executor, gated by `AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION`, with
  failed graph traces suppressing completion speech.
- no-motion task-agent bridge acceptance that requires
  `task_api_no_motion=true` before preview/submit and monitors terminal
  `soridormi.task.events`.

The M13 text interaction scope is closed. Linux RTX 5090 GPU smoke passed
21/21; clean seven-case synthetic and PipeWire virtual-mic bundles passed; and
text-to-MuJoCo evidence `20260617T081411Z` passed at Chromie revision `857c15f`
with ordered walk, nod, and turn execution in MuJoCo plus safe idle. Physical
real-microphone/speaker evidence remains open only as a separate human
voice-device release-support track. Automated acoustic generated-speech
evidence `20260704T114654Z` also passed all seven cases at Chromie revision
`842a334`, which supports the narrowed `0.0.1` generated-speech and
Soridormi MuJoCo-executor claim but not a human voice-device claim. The
robust-simulation and provider-readiness
milestone is complete with live no-motion MCP conformance, three-profile
parity, and 16/16 Soridormi-owned fault-injection scenarios.

The temporary `demo-sim-2026-06-27` tag was withdrawn on 2026-06-27 before
publication because the paired repositories needed a documentation/code
consistency audit. Do not publish or recreate that demo tag. The intended
replacement tag is `0.0.1`, after the Chromie and Soridormi validation
gates pass from the intended revisions.

## Next sequence

1. Continue the general ability acceptance reconstruction described in
   [docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md](docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md):
   the first manifest/runner slice is implemented, and the next work is better
   live-runner diagnostics, root-cause classification, broader live text
   sampling, and voice-evidence integration without turning one reported
   sentence into a special-case patch.
2. Continue the Developer Usability Tools phase described in
   [docs/DEVELOPER_USABILITY_TOOLS.md](docs/DEVELOPER_USABILITY_TOOLS.md):
   PR0-PR6 are implemented; next harden retained trace examples from real
   bundles and keep `trace explain` deferred until causal semantics are stable.
3. Use [docs/TRACE_SCHEMA.md](docs/TRACE_SCHEMA.md) as the trace-viewer
   contract; avoid explanations that obscure session, interaction, TaskGraph,
   Skill Runtime, Soridormi, TTS, and fallback semantics.
4. Treat Soridormi's high-level task and skill surface as declared for the
   current no-motion contract: bounded locomotion, attention, gesture,
   sequence, stop, safe-idle, and planning-hold task types are present in the
   authoritative manifest; navigation, approach, and delivery remain
   future-blocked structured refusals.
5. Keep the Chromie/Soridormi task-agent boundary aligned with Soridormi's
   authoritative manifest. Use structured task goals for rich embodied requests
   and keep concrete named skills for explicit bounded body commands. Preserve
   Soridormi refusal metadata when reporting unsupported embodied tasks.
6. Add Chromie routing and TaskGraph acceptance for Soridormi-declared task
   types only. Missing navigation, approach, gaze, gesture, recovery, or
   manipulation goals must remain structured refusals or clarifications rather
   than velocity recipes.
7. Keep Qwen/small-model routing advisory. Add or revise routing only with
   deterministic-control bypass, catalog constraints, confidence fallback,
   schema validation, Skill Runtime authorization, and Soridormi provider
   refusal/event checks.
8. Select one reference-robot candidate and complete the identity,
   independent emergency-stop, software, network, and workspace sections of
   `docs/ROBOT_COMMISSIONING.md`. Record it with the versioned
   `commissioning/reference_robot_candidate.schema.json` contract and keep the
   real manifest under ignored `.chromie/commissioning/`.
9. Keep all physical-motion gates off while validating no-motion health,
   calibration artifact ownership, stop/recovery procedures, and operator
   responsibilities.
10. If the next supported release claims real microphone/speaker voice-device
    operation, run the full seven-case `supervised` matrix on the reference host,
    review audible output and MuJoCo safe-idle/recovery behavior, verify the
    bundle with `--require-clean`, then clear the compatibility blocker.
11. Before publishing `0.0.1`, record the paired Chromie and Soridormi
    revisions, rerun the Chromie documentation/test/scenario gates, rerun the
    Soridormi task-agent and locomotion-readiness gates, and keep the tag claim
    limited to generated-speech and Soridormi MuJoCo-executor evidence.

Do not start physical motion until the first reference robot satisfies the
commissioning checklist and Soridormi has retained simulator/physical evidence
for the exact bounded motion path. Do not train a Soridormi motion-control
model until the task semantics, target body or simulator, calibration,
telemetry, safety envelopes, and task-level acceptance metrics exist.

## Verification baseline

```text
Focused refresh after f4bbb2f:
python scripts/check_docs.py passed
python -m unittest tests.test_robot_candidate_verifier passed: 12 tests
python scripts/test_matrix.py taskgraph passed: 48 tests
python scripts/test_matrix.py soridormi passed: 56 tests
python -m unittest tests.test_soridormi_acceptance passed: 16 tests
Local Soridormi dry-run MCP --task-agent-bridge acceptance passed:
  graph=soridormi-task-agent-acceptance-115cc864fd04
  backend=local_tool_dry_run, no_motion=true, safe_idle=true
  nodes=capabilities, preview, submit, events
Focused interaction/catalog task-agent tests passed: 29 tests
Focused host Skill Runtime graph dispatch tests passed: 59 tests
Widened host/task-agent focused bundle passed: 95 tests, with 2
dependency-light local skips for `aiohttp` client coverage

Full Level A baseline:
640 current unittest cases and 20 legacy Agent tests passed on 2026-07-04 with
`./scripts/run_tests.sh`. The behavior scenario runner also passed 344/344
Router, interaction, and dialogue scenario files with `--no-write`.
```

The focused refresh above is not target evidence and does not replace the full
Level A gate. Retained target-host evidence is listed in `docs/STATUS.md`.

## Useful commands

```bash
./scripts/run_tests.sh
./scripts/show_profile.sh
./scripts/start_services.sh
./scripts/start_orchestrator.sh
python scripts/voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
python scripts/voice_acceptance.py --preflight-only \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi --start-services
python scripts/provider_fault_matrix.py
python scripts/provider_conformance.py
python scripts/verify_provider_readiness.py preflight
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json --task-agent-bridge
python scripts/verify_robot_candidate.py \
  commissioning/reference_robot_candidate.example.json --allow-draft
python scripts/verify_robot_candidate.py \
  .chromie/commissioning/reference_robot_candidate.json \
  --evidence-root .chromie/commissioning \
  --verify-evidence-files \
  --write-report .chromie/commissioning/candidate-verification.json
```

Live commands and recovery procedures are maintained in
[CHROMIE_RUNBOOK.md](CHROMIE_RUNBOOK.md).
First-reference-robot selection requirements are maintained in
[docs/ROBOT_COMMISSIONING.md](docs/ROBOT_COMMISSIONING.md).

## Do not regress

- Keep realtime audio and trusted Skill Runtime coordination in the Orchestrator.
- Keep embodied execution and hardware safety in Soridormi.
- Keep operational controls deterministic.
- Keep small-model routing advisory; never let Qwen or any model become the
  only authority for route, skill, task, safety, or physical execution.
- Keep physical work default-off and sequential.
- Do not expose low-level robot controls to model-facing contracts.
- Do not report automated or dry-run output as target evidence.
- Do not publish `0.0.1` or remove release blockers without retained
  evidence for the exact supported scope.
