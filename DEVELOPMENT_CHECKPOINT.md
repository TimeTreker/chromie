# Chromie Development Checkpoint

## Current resume point — promotion blocked by retained evidence

Active Issue #35; delivery branch `codex/ga-request-format`; pre-delivery baseline
`4dd7685d93d1bb530f7e186994497c8c7c7adc5c`. Owner authorized commit and push of
the completed repairs. Resume at the latest commit containing this checkpoint and
handoff. This is a development delivery; promotion remains blocked.
Remote delivery branch matched the baseline at preflight. Remote main advanced to
`ab5caeab`; this delivery neither merges into main nor qualifies that revision.
The Goal-driven single-authority architecture remains binding. Preserve unrelated
Soridormi edits. No model replacement, extra semantic judge or Host meaning repair.

Implementation: retained repairs cover GA decoder object shapes, GI visible-dialogue
location provenance and continuity shapes, complete required Fast Goal context,
SGLang two-frame decoding, and failed-stream evidence with schema property order.
The Fast context defect dropped a 1322+ character Goal snapshot through a 600-character
optional projection; the repair preserves semantic fields and fails explicitly on
required-context overflow. Decoder projection leaves original acceptance schemas
unchanged; omitted string-pattern/fractional-range hints address demonstrated native
grammar defects. This is mechanical repair, not full semantic qualification.

Automated verification: latest canonical gate passes 2319 tests / 368 subtests,
20 legacy tests and 140 benchmarks, including repository policies, static analysis,
documentation and test ownership. Latest focused diagnostics tests: 41 / 10 subtests.
Fast framing frozen exact packets improve 5/11 to 11/11 original-Schema-valid;
198/198 native framing contrasts pass. Fast context contrasts improve 4/12 to 12/12.
GI production-order replays improve 8/12 to 12/12; all 98 valid and 724 invalid
mechanical contrasts receive the intended decoder verdict. These counts are scoped.

Target validation: latest immutable full 51-case preview (framing Agent) has
28 mechanical passes and 19 reviewed acceptable initial previews; every case and
available raw call reviewed. Both continuation cases pass. Fifty completed Fast
streams are original-Schema-valid, but the 51st truncates and old success-only
logging omitted its request and partial output. Thus full stream integrity remains
open. GI: 53 valid; GA: 50 valid / 1 invalid; Deep: 3 invalid; skill: 2 invalid.
160 retained calls / 159 linked. Exactly one post-cohort bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_122434.tar.gz`.
Four deterministic reflex cases need execution evidence beyond preview.

The diagnostic candidate is deployed; 113 Agent/shared files matched at verification.
Final cleanup removes one extra EOF blank line in shared json_schema.py only;
the deployed code is behaviorally identical, with this byte-level difference recorded.
Its focused `contextless_turn_it_up` replay completes, but wrongly selects walking
for an ambiguous increase request; it does not reproduce or explain the original
2048-token truncation. A separate exact-request fault test changes only max_tokens
to 16 and proves one failed record retains exact partial output, request order,
length finish reason and output_truncated classification. No dispatch occurs in
that fault test. No full 51-case rerun of this diagnostics-only image is claimed.

Release readiness: blocked by semantic/safety errors (negative blink admitted,
ungrounded destination/velocity, wrong capabilities, omitted Goals, false promises,
resource meaning and continuity), Deep/skill contracts, the historical truncation,
and missing current-revision physical voice/default target-evidence closure.
Preview and schema validity do not establish provider execution or robot behavior.

## Current runtime and retained artifacts

RTX 5090, 32607 MiB, driver 595.84 / CUDA 13.2. Fixed Gemma4-12B FP8/SGLang,
served `chromie-gemma4-12b`, revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`,
65536 context/cache and two requests. Specialized ASR/TTS unchanged.
Agent tag `chromie-agent:stream-evidence-20260910`, image
`sha256:93a76fbf9c172c98ba098aedec300450629875273733cb53bcb510a3ac2196a4`,
container `e253f0e784d23e1763c3cccc7288ef97185495913bac8a61bcea7a4f91e1afa4`.
SGLang image `sha256:6f449f469487fe9f5d4565c2dfb14f62a08ed4f8b581681d3e3fd0bda6df7303`.
Agent, SGLang, ASR/TTS and headless Soridormi remain running; maintained-main
restoration has NOT occurred in this continuation. Verify health before resuming.

Raw evidence is retained locally and is not included in this Git delivery; transfer
these artifacts separately when resuming on another machine. The summary below
remains available from Git. Evidence roots beneath `.chromie/acceptance/`:
- `stream-evidence-20260910/`: latest gate, identity, source verification, natural
  focused replay and controlled failed-stream proof; read report.md first.
- `fast-tagged-20260910/`: latest full cohort, all-case review, ordered frozen
  packets, native grammar experiments, implementation equality and source patch.
- `fast-continuity-20260910/`: dropped-Goal diagnosis, focused proof and prior cohort.
- `gi-followup-shape-20260910/`: corrected production-order GI packets and cohort.
- `gi-referents-20260910/`: retained provenance repair; rejected ambiguity wording.
- `ga-array-20260910/`: GA decoder contrasts and primary-role qualification.
- `decoder-shapes-20260910/`: mechanical Deep/skill preparation, not implemented.

## Next work and commands

Read latest all-case review before selecting another semantic change. Reproduce the
natural failed-stream class with current exact logging; do not infer its historical
cause from the deliberate 16-token test. Use fresh artifact directories and runtime
identity. Freeze contrasts at the earliest responsible boundary; keep the fixed model.
Before another broad change or revision-level claim, run and judge one complete
immutable directory-discovered cohort, then collect exactly one debug bundle. Do not
edit source, rebuild or restart between cases. Keep unsafe candidates in preview.

Canonical checks: `./scripts/run_tests.sh`, `python scripts/check_repository_policies.py`,
`python scripts/check_test_ownership.py`, `python scripts/check_docs.py`.
Use `scripts/capture_runtime_identity.py --help` and the retained latest identity
capture/cohort commands to bind the next fresh directory. Compose uses generated
`.env.runtime`, `docker-compose.yml`, `docker-compose.sglang.yml` and
`.chromie/voice-runtime/compose.voice-mujoco.yaml`; never edit generated env directly.
Stop ASR/TTS before replacing SGLang, then restart speech after model health.
HANDOFF.md retains historical recovery commands; its current section overrides them.
