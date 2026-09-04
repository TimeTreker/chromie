# Chromie Development Checkpoint

Status: the Goal-driven single-authority line remains current, and the
2026-09-04 live `voice_mujoco` Goal Interpretation failure is
source-fixed. Interactive modes now allow one complete GI transaction with a
60 s Agent watchdog and a 65 s Host GI deadline; the previously declared Host
deadline is now actually consumed by `AgentClient.interpret_turn()`. Startup
instructions also stop promising a wake-up greeting when startup speech is
disabled. Focused configuration/client tests and relevant Level-A scenarios
pass. Post-fix live voice evidence is not yet retained.

Issue #35 Planner single-authority correction and fixed-Codex offline
qualification remain complete through Fast v33 and Deep v15. Codex
`gpt-5.6-sol` was the fixed candidate Planner; no local Qwen/Ollama/vLLM model
was used to optimize or evaluate the Planner.

Updated: 2026-09-04; delivery branch: `main`

Pre-delivery base: `255499292d0116b4c7277ce26143ecee5ac63440`
(`origin/main`, clean and 0 ahead/0 behind before this repair).

Active Issue: [#35 — Fast/Deep Planner prompt qualification and optimization](https://github.com/TimeTreker/chromie/issues/35).

## Reported failure and actual workflow

Retained bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260904_163700.tar.gz`
(SHA-256 `22b13dabaa29f8094275d61639fa4e4094463d07dbfa33affbd2370ea065f85b`,
revision `255499292d0116b4c7277ce26143ecee5ac63440`).

```text
voice -> VAD/ASR -> Gateway Attention admits turn
      -> Agent GI sends one gemma4:12b /api/chat request
      -> 5400 ms Agent watchdog fires before the complete DTO exists
      -> httpx.ReadTimeout -> Ollama request cancellation
      -> typed GI unavailable / Host HTTP 503
      -> fail-closed fallback speech -> ordered TTS playback
```

The same boundary failed for both retained turns:

- `30efe1a0`, `你好。`: GI failed after about 5.44 s.
- `bbdc4c92`, `晚上重庆会不会下雨啊？`: GI failed after about 5.43 s.

| Boundary | Actual evidence | Expected contract | Verdict |
|---|---|---|---|
| VAD / ASR | Both turns accepted; final text retained | Admit usable source audio/text | Correct |
| Gateway Attention | Greeting and question admitted | Protectively filter, then admit addressed turns | Correct |
| GI request | About 3.5K–3.8K prompt tokens sent to `gemma4:12b` | One complete WHAT-only DTO or typed provider failure | In flight |
| Agent GI watchdog | Cancelled each request at the configured 5400 ms | Watchdog must cover one complete transaction; latency is measured separately | **Earliest wrong boundary** |
| Host GI deadline | Dedicated key existed but was not consumed; generic 9000 ms remained | Host deadline must exceed the Agent GI deadline | Latent second wrong boundary |
| Ollama 500/cancel | Appeared after the client timeout | Provider may finish or be cancelled by its client | Downstream symptom |
| GA / Planner / weather | Never invoked | Run only after a valid GI result | Correctly absent |
| Host fallback / TTS | Typed 503 became safe fallback; 2/2 chunks played | Fail closed without fabricated success | Correct containment |

Hybrid/SWA full-prompt reprocessing contributed latency. The early Agent warm
DNS failure was not causal because launcher warm-up later succeeded and both
models were resident. The silent startup was separately configured by
`ORCH_RUNTIME_READY_GREETING_SPEECH_ENABLED=0`; the launcher text, not runtime,
was wrong to promise a greeting.

## Implemented repair

- `services`, `speech`, and `voice_mujoco` own
  `AGENT_GOAL_INTERPRETER_TIMEOUT_MS=60000` and
  `ORCH_AGENT_GOAL_INTERPRETER_TIMEOUT_MS=65000`.
- `CognitionSettings` parses the existing Host GI deadline and
  `AgentClient.interpret_turn()` uses it. Attention and other generic Agent
  requests retain `ORCH_AGENT_TIMEOUT_MS`.
- Generated runtime manifests and startup budget summaries now expose both GI
  deadlines.
- The runtime-configuration inventory and documentation record the owners and
  mode-specific values.
- Launcher instructions condition the wake-up greeting claim on the existing
  speech-enabled setting.
- No model, prompt, context projection, Schema, DTO, retry policy, semantic
  authority, or execution policy changed. No configuration key, document, or
  architecture term was added.

This prevents a valid GI transaction from being relabelled as provider failure;
it does not make a 60-second response acceptable. GI latency remains a separate
acceptance axis and must be judged from retained deployed evidence.

## Planner qualification retained

- Fast v33: 204/204 process, Schema, Host, and hidden-target-region passes;
  same-model review 201 pass, one partial, two fail.
- Deep v15: 40/40 mechanical passes and 40/40 non-independent semantic review.
- Fast corpus: 204 cases, 17 capacities, 51 bilingual contrast sets; tree digest
  `2650948b9027071c948bb75481d203104923b4aff2bfc33750288d350679c2d8`.
- Deep corpus: 40 cases; tree digest
  `a0c79e38cf4055b7021a4dcc1cbd0a2caec915872174d41e9c2bf153a4a7406a`.
- Fast v33 artifact:
  `.chromie/benchmarks/fast-planner/20260904T-resume-fast-v33-qualified-full/`.
- Deep v15 artifact:
  `.chromie/benchmarks/deep-planner/20260904T-deep-v15-qualified-full/`.

All Planner candidate/review evidence is fixed-Codex, same-model and
non-independent. It is not deployed-model, statistical, training, voice,
simulator, or robot evidence. SFT/QLoRA remains unauthorized.

## Evidence completed for this repair

- Focused configuration/client suite: 83 passed, 43 subtests passed.
- General Ability Level A: 12/12 across `planner_goal_semantic_quality` and
  `robust_intent_understanding`.
- Actual RTX 5090 `voice_mujoco` generation resolved Agent GI 60000 ms and Host
  GI 65000 ms in both `.env.runtime` and the runtime manifest.
- Full repository gates and final commit identity are recorded in `HANDOFF.md`.

No post-fix deployed service, live text, physical microphone/speaker, simulator,
or robot run has been claimed.

## Resume point

1. Rebuild/recreate the Agent and restart the Host from the committed revision;
   generated `.env.runtime` must show GI 60000/65000 ms.
2. Run the originating greeting and weather probes through one unchanged live
   cohort, then collect exactly one debug bundle and judge both semantics and
   latency. Do not average any hard integrity failure into a pass.
3. Treat a completed but slow GI result as a latency failure, not as evidence to
   restore a 5.4-second cognition kill switch.
4. Preserve fixed Codex for any continued Planner qualification. Independently
   review Fast v33 and Deep v15 before any training decision.

## Claim boundary

The source/configuration repair closes the reproduced premature GI cancellation
mechanism and the latent Host deadline mismatch. Automated tests prove wiring,
generation, ownership, and fail-closed contracts only. Live post-fix behavior,
semantic quality of the deployed GI model, end-to-end latency, simulator/robot
execution, physical safety, and release readiness remain unproven.
