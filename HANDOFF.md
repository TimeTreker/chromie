# Chromie Latest Handoff

Audience: the project owner or coding agent resuming live Goal Interpretation
verification or Issue #35 fixed-Codex Planner qualification.

Owner: project owner. Current source, tests, retained artifacts, this handoff,
and `DEVELOPMENT_CHECKPOINT.md` override chat history.

## Repository and delivery state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `main`
- Pre-delivery base: `255499292d0116b4c7277ce26143ecee5ac63440`
  (`origin/main`, 0 ahead/0 behind before this repair).
- Expected resume revision: the latest normal `main` commit containing this file
  and `DEVELOPMENT_CHECKPOINT.md`.
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35).
- Delivery target: fast-forward `main` to `origin/main`; verify the final remote
  ref after push rather than treating this pre-push statement as proof.

## Reproduced defect and root cause

The one retained originating bundle is:

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_163700.tar.gz
SHA-256: 22b13dabaa29f8094275d61639fa4e4094463d07dbfa33affbd2370ea065f85b
Revision: 255499292d0116b4c7277ce26143ecee5ac63440
Profile/mode: rtx5090 / voice_mujoco
```

Both admitted voice turns reached the same first wrong boundary:

```text
microphone -> VAD -> ASR final -> Gateway Attention admit
           -> one WHAT-only GI request to gemma4:12b
           -> Agent 5400 ms httpx watchdog expires
           -> Ollama request is cancelled
           -> typed interpretation_unavailable / HTTP 503
           -> safe fallback speech -> ordered TTS playback
```

Turn `30efe1a0` (`你好。`) failed at GI in about 5.44 s. Turn `bbdc4c92`
(`晚上重庆会不会下雨啊？`) failed at GI in about 5.43 s. The requests carried
roughly 3.5K–3.8K prompt tokens. Ollama was still processing the primary request
when the client cancelled it; the later Ollama 500/cancel messages were symptoms,
not evidence of an initiating provider crash.

| Module/boundary | Authoritative input and actual output | Expected output | Judgment |
|---|---|---|---|
| VAD / ASR | Usable audio; exact greeting/weather text | Final admitted source text | Correct |
| Gateway Attention | Bounded context; greeting/question admitted | Admission decision only | Correct |
| Goal Interpretation | One `gemma4:12b` request; no DTO before 5400 ms | Complete WHAT-only DTO or typed real provider failure | In flight until cancellation |
| Agent GI watchdog | `AGENT_GOAL_INTERPRETER_TIMEOUT_MS=5400`; `ReadTimeout` | Cover one complete primary semantic transaction | **Earliest wrong boundary** |
| Host Agent client | Dedicated GI key declared but ignored; generic 9000 ms used | A dedicated deadline greater than the Agent GI watchdog | Latent second wrong boundary |
| GA / Fast / Deep / weather | Not invoked because GI failed closed | Start only after valid GI | Correctly absent |
| Failure/TTS | Typed 503 became generic safe speech; two chunks played | No fabricated semantic/tool success | Correct containment |

Contributing condition: Gemma hybrid/SWA processing did not provide useful full
prompt cache reuse, so the prompt prefill did not fit a 5.4-second watchdog. An
early Agent warm-up DNS error was non-causal because launcher warm-up later
succeeded and both configured models were resident.

The startup instruction was independently inaccurate. Runtime correctly logged
that orientation was silent because
`ORCH_RUNTIME_READY_GREETING_SPEECH_ENABLED=0`, while the launcher told the
operator to wait for a wake-up greeting.

## Implemented repair

Interactive `services`, `speech`, and `voice_mujoco` modes now set:

```text
AGENT_GOAL_INTERPRETER_TIMEOUT_MS=60000
ORCH_AGENT_GOAL_INTERPRETER_TIMEOUT_MS=65000
```

`HostSettingsSnapshot` now parses the existing Host GI key and passes it through
`build_agent_client()`. `AgentClient.interpret_turn()` uses that dedicated
deadline; Gateway Attention, health, and unrelated calls retain the generic
`ORCH_AGENT_TIMEOUT_MS` behavior. The runtime generator records both values in
its manifest and prints both in its cognitive-budget summary.

The launcher now promises a wake-up greeting only when the existing speech flag
is enabled; otherwise it tells the operator to wait only for `Microphone
started` and states that startup speech is disabled.

The repair adds no model invocation, retry, configuration key, architecture
term, or document. It does not change the GI prompt, context, Schema, DTO,
semantic authority, model identity, Capability routing, or execution policy.
Configuration/document surface growth is therefore zero keys, zero terms, and
zero documents.

Why this restores the contract: the Agent can finish its single primary GI
transaction before its own watchdog, and the Host will continue waiting five
seconds longer for the Agent's typed response. A slow completion remains a
latency failure; 60 seconds is a workflow watchdog, not a latency target.

## Verification and evidence ceiling

- Focused configuration/client suite: 83 passed, 43 subtests passed.
- General Ability Level A: 12/12 passed across
  `planner_goal_semantic_quality` and `robust_intent_understanding`.
- Actual RTX 5090 `voice_mujoco` runtime generation produced Agent GI 60000 ms
  and Host GI 65000 ms in `.env.runtime` and
  `.chromie/runtime_profile.json`; the startup summary exposed both values.
- Canonical local gate passed: repository policy 15 rule families with zero
  exceptions, ownership/configuration/static/docs stages passed, 140 pytest,
  2057 unittest, and 20 legacy Agent tests passed.

No service rebuild/restart or post-fix live voice run was performed in this
delivery. Therefore the evidence proves source/configuration wiring only. It
does not prove deployed GI semantics, end-to-end latency, live microphone or
speaker behavior, simulator/robot behavior, target hardware behavior, physical
safety, or release readiness.

## Fixed-Codex Planner state retained

Planner qualification remains outside the local GI model involved in this live
defect. The candidate Planner is fixed as Codex `gpt-5.6-sol`; no local or
deployed Qwen/Ollama/vLLM model was invoked, compared, tuned, or used as a proxy
for Planner optimization.

- Fast v33 artifact:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v33-qualified-full/`
  — 204/204 process/Schema/Host/hidden-target passes; same-model review 201
  pass, one partial, two fail.
- Deep v15 artifact:
  `.chromie/benchmarks/deep-planner/20260904T-deep-v15-qualified-full/`
  — 40/40 mechanical passes and 40/40 non-independent semantic review.
- Fast scenario-tree SHA-256:
  `2650948b9027071c948bb75481d203104923b4aff2bfc33750288d350679c2d8`.
- Deep scenario-tree SHA-256:
  `a0c79e38cf4055b7021a4dcc1cbd0a2caec915872174d41e9c2bf153a4a7406a`.

These are same-model offline findings, not independent semantic truth,
statistical model reliability, deployed behavior, or training approval. Every
case remains training-ineligible; SFT/QLoRA remains unauthorized.

## Resume commands

```bash
git switch main
git status --short --branch
CHROMIE_OPERATOR_MODE=voice_mujoco ./scripts/build_runtime_env.sh
./scripts/start_chromie.sh
```

After rebuilding/recreating the Agent and restarting the Host from the committed
revision, run the greeting and weather probes as one unchanged live cohort. Then
collect exactly one bundle:

```bash
./scripts/collect_debug_bundle.sh
```

Judge the complete workflow, semantic result, and latency. A hard service,
provenance, semantic, safety, or safe-idle failure cannot be averaged into a
pass. Retain physical microphone/speaker notes as supervised evidence rather
than inferring them from source tests.

For repository-only revalidation:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

For Planner work, preserve the fixed Codex candidate and obtain independent
review of Fast v33 and Deep v15 before changing surrounding contracts or making
any training decision.

## Claim boundary

This delivery fixes the reproduced premature GI cancellation mechanism, wires
the previously inert Host GI deadline, and corrects the startup instruction.
Automated evidence confirms the source/configuration contract only. Post-fix
live behavior, deployed GI quality and latency, simulator/robot execution,
physical safety, independent Planner semantics, training readiness, and release
readiness remain open.
