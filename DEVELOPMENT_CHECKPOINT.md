# Chromie Development Checkpoint

Status: the current Goal-driven single-authority focus and active Issue #35
delivery line have RTX 4090 Level-C-preview evidence for exact `你好。`. The prior Goal
Interpretation watchdog failure is closed in source, and this continuation
repaired the next deployed transport boundary: generic Agent semantic roles and
warm-up now use Ollama `/api/chat` rather than the non-responsive
`/api/generate` plus `think:false` transaction observed on Ollama 0.33.2. A
repaired warm-up also establishes the 32K context required by Goal Association
and Fast Planner.

The greeting still does not succeed. With transport and context residency
working, deployed `qwen3.5:4b` now reaches Fast Planner but incorrectly maps the
speech-only greeting Responsibility to `chromie.clock.local`. Host validation
correctly rejects that Plan before execution. The same result misses the
two-second immediate-commit target. An unchanged 51-case deployed must-pass
aggregate then hard-passed only 5 cases and placed 35 primary failures at Fast
Planner output or communicative coverage. The fixed-Codex Fast v33
qualification did not evaluate or qualify this deployed Qwen profile.

Updated: 2026-09-05; branch: `main`

Pre-delivery base: `46b6fe90a36179e63da36f086ac2b04ed8e7b3c1`; `main == origin/main` before this continuation. Expected resume revision: the latest normal `main` commit containing this checkpoint and `HANDOFF.md` after the authorized fast-forward push.

Active Issue: [#35 — Fast/Deep Planner prompt qualification and optimization](https://github.com/TimeTreker/chromie/issues/35).

## Current exact workflow

Retained formal case: `.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/`.
It is private Level C-preview live text on dirty source with incomplete identity.

```text
explicit text `你好。` -> Gateway admits the turn
  -> GI /api/chat -> correct greeting speech Responsibility (~5.50 s)
  -> concurrent downstream work
       -> GA /api/chat -> correct one-Goal association (~6.08 s)
       -> Fast /api/chat stream
            -> valid empty PresentationCommit (~8.246 s after GI handoff)
            -> invalid terminal Plan: clock Capability + `现在的时间是。`
  -> Host rejects speech-to-clock mapping before execution
  -> typed safe failure; no normal greeting response
```

| Boundary | Authoritative input and actual output | Expected output | Verdict |
|---|---|---|---|
| Explicit text / Gateway | Exact `你好。`; turn admitted | Admit the usable addressed turn | Correct |
| Goal Interpretation | Source turn; one greeting speech Responsibility in ~5.50 s | WHAT-only greeting Responsibility | Correct, slow |
| Goal Association | Immutable GI result; one speech Goal in ~6.08 s | Preserve exact Responsibility and Goal coverage | Correct, slow |
| Fast presentation commit | Same GI/context; empty commit after ~8.246 s | One natural immediate greeting within 2 s | Semantically incomplete and late |
| Fast terminal Plan | Speech ref `r1`; proposed `chromie.clock.local` plus `现在的时间是。` | `complete_response` satisfying the greeting, with no Capability | **Earliest remaining wrong semantic boundary** |
| Host validation | Invalid terminal Plan | Reject unauthorized/incorrect mapping without rewriting it | Correct containment |
| Capability/TTS/playback | Not reached for a successful Plan | Execute only after a valid bound Plan | Correctly absent |

Before this run, microphone session `fe7a5819` had exact ASR and correct GI, but GA/Fast
timed out. Ollama 0.33.2 `/api/generate` with `think:false` returned no bytes while
`/api/chat` worked; repaired warm-up then established 32K. The later aggregate repeated
the Fast failure; all 39 retained commits missed target, median 12.228 seconds.

A later supervised device-mode session retained two diagnostic turns. `你好。` reached
a correct greeting Responsibility but Fast again invented `chromie.clock.local`; a
Chongqing rain request failed when GI translated `重庆` to `Chongqing`. Both calls ended
normally, Host validation contained both invalid results, and the same failure utterance
made distinct faults sound identical. This indicts the deployed model transaction, not
the fallback.

## Aggregate failure distribution

Valid aggregate: `.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/`.

| Primary result bucket | Cases | Representative failure |
|---|---:|---|
| Passed | 5 | Simple blink/head-shake/walk and one social response |
| Goal Interpretation | 5 | Rewritten numeric binding, invalid duration provenance, invalid relationship/unresolved output |
| Goal Association | 2 | Structured-output validation failure |
| Fast Planner | 35 | Invalid JSON/DTO, invented args/Capabilities, ordering/resource conflict, truncation, or omitted communicative activity |
| Deep Planner | 1 | Invalid Goal-outcome coverage |
| Preview evidence limitation | 3 | Deterministic reflex requires non-preview execution evidence |

This is a non-overlapping primary-failure classification for triage. Some
concurrent cases also retained a second failing semantic role. Semantic review
is pending, and hard failures are not averaged into a pass.

## Implemented continuation

- `OllamaClient` uses `/api/chat` for complete/streaming calls, separate
  system/user messages, `message.content`, and non-thinking enforcement.
- `scripts/warm_ollama.sh` now warms the same `/api/chat` production transport,
  so configured context residency is exercised instead of a different endpoint.
- Configuration documentation records the transport/warm-up contract.
- The exact standalone greeting is now a discovered must-pass
  `speech_identity_latency` scenario with no Capability, required speech,
  required Fast communicative act, no Fast contract failure, and the existing
  two-/three-second warm latency budgets.
- The reviewed streaming exception hash changed; classification remains `narrow_reraise`.
- No prompt, Schema, DTO, semantic authority, model, model profile, Capability,
  retry, configuration key, architecture term, or execution policy changed.
  Surface growth is zero keys, zero documents, and zero architecture terms.

## Why prior optimization did not make `你好。` work

Fast v33 and Deep v15 were offline fixed-Codex `gpt-5.6-sol` qualifications, not
tests of local `qwen3.5:4b`. Fast retained 204/204 mechanical and 201 pass/1
partial/2 fail same-model review; Deep retained 40/40 mechanical/review passes.

Earlier Qwen evidence had 0/50 must-pass hard passes. Offline transaction
progress was mistaken for product progress. Because the schema already forbids
Capability mapping for speech-only input, treat this deployed transaction as
unqualified rather than tuning the phrase.

## Evidence completed

- Focused transport/runtime/scenario suite: 65 passed.
- Canonical local gate: repository policy 15 rule families with zero exceptions;
  test ownership, configuration, documentation, and static stages passed; 140
  pytest, 2058 unittest, and 20 legacy Agent tests passed.
- Formal exact greeting: 0/1, score 40, hard failure, Level C-preview.
- Exact workflow: `.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/01-must_pass-speech_identity_latency-standalone_greeting_one_natural_reply/session-workflows/20260904T14094030079-65f84c93.json`.
- Focused bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260904_221033.tar.gz`, SHA-256 `386c50d9bd1844dead9a2e12da71705535c8da74054ea12c5d37dc8841c2660b`.
- Unchanged must-pass aggregate: 5/51 hard-passed, 46 hard-failed, semantic
  review pending, Level C-preview. Evidence:
  `.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/`.
- Aggregate bundle (one post-run collection): `/home/chromie/Downloads/chromie_debug_bundle_20260904_230315.tar.gz`, SHA-256 `e26db4bbaee0bfa9de7374d7ec81564e78a72e77993963e59b5150fde4907f4a`.
- Latest supervised device-mode diagnostic bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260904_232045.tar.gz`, SHA-256 `4c8644003dad8f013999f98133bd2493aca52ae5af3a28e6d7cb0515cef3e959`. It retains greeting SID `97957fa9` and weather SID `17c7c47a` on dirty base `46b6fe90`.

The latest trace is supervised diagnostic device microphone/speaker evidence, not a
formal acceptance cohort. None is clean committed-revision, independent-review,
simulator, robot, safety, or release evidence.

## Resume point

1. Do not tune `你好。` in isolation. Use the retained 5/51 aggregate to qualify
   the smallest deployable model/resource-profile change. The RTX 4090 profile
   currently assigns every semantic role to one `qwen3.5:4b` runner with one
   Ollama sequence slot, so it cannot realize designed GA/Fast concurrency and
   has not demonstrated any warm Fast-commit latency pass. The latest voice
   trace also alternated 16K GI and 32K Fast requests and retained multi-second
   provider load durations; preserve this as a latency contributor to verify.
2. Preserve the frozen scenarios and one-authority contracts while comparing
   candidates. Reproduce the dominant Fast DTO/semantic failures first, then
   verify the five GI, two GA, and one Deep primary failure buckets rather than
   hiding them behind Fast improvements.
3. After an aggregate-justified minimal profile/model change, rerun the full cohort on the
   changed revision before another broad change. Then rerun the originating
   greeting/weather voice cohort and retain one bundle.
4. Rerun formal supervised physical microphone/speaker evidence and the
   `current_revision_qualification` profile only after service, semantic, and
   provenance integrity close on a committed revision.

## Claim boundary

The source change repairs the reproduced Ollama endpoint mismatch and makes the
warm-up establish the downstream 32K context. Automated tests prove that
transport contract. Current Level-C-preview evidence proves that the greeting
can now reach all three semantic roles and that Host validation contains the
bad Fast Plan. The unchanged aggregate proves the failure is broad—5/51 hard
passes—and that every retained Fast timing misses the target. The later voice
trace proves two distinct invalid semantic outputs collapse to the same safe
utterance, but does not qualify normal voice behavior or prove which broader
model/profile change will close the aggregate, simulator/robot behavior,
safety, or release readiness.
