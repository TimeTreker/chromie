# Chromie Development Checkpoint

Status: current resume point

## Direction

Continue the **Goal-driven single semantic authority** architecture. The
Cognitive Gateway owns ingress, deterministic protective reflexes, and attention
admission. The Goal-driven Cognitive Core owns ordinary semantic interpretation,
goal association, planning, response composition, and outcome reconciliation.
Effects remain authorized only by trusted Host and provider boundaries.

## Current checkpoint

Issues [#17](https://github.com/TimeTreker/chromie/issues/17) and
[#18](https://github.com/TimeTreker/chromie/issues/18) are merged on `main` in
PR [#19](https://github.com/TimeTreker/chromie/pull/19). `LayeredPrompt` promotes
exact stable fragments before volatile turn state and `OllamaClient` records
only reuse candidates and provider timings, never inferred cache hits.

Issue [#20](https://github.com/TimeTreker/chromie/issues/20) owns the active P0
correctness line before model-profile qualification. The reproduced failure is
a mixed chain: qwen3.5:4b ignores the semantic-review JSON schema on Ollama
`/api/chat` while honoring the same schema through `/api/generate`; the runtime
previously treated that expected model/transport incompatibility as permission
to preserve an ungrounded chat decision; route-narrowed capability context
could omit an exact recovery ability; and planner validation could accept a
typed effectful Goal as satisfied with zero executable steps. The Issue branch
provides one same-model, same-schema transport compatibility retry,
preserves a candidate-first lossless supplied catalog for review, and rejects
unresolved effectful zero-step outcomes before canonical planning. Focused
regressions pass 191/191, the applicable Level A classes pass 13/13, and the
canonical gate passes; `docs/STATUS.md` owns the exact evidence limits.

The earlier post-merge audit and paired closure are retained in
`docs/STATUS.md`, their implementation/evidence authority. In summary, clean
Chromie `a36444b` and Soridormi `fa8080d2` retained exact compound MuJoCo
execution, deterministic provider-start cancellation, Goal reconciliation, and
safe idle. The source and generated-speech gates also closed their recorded
revision scopes. Independent semantic review, physical audio/robot evidence,
real vocal/media providers, and release qualification remain open; do not
reinterpret the retained simulator or generated-audio evidence as those claims.

The maintained source contracts and compatibility state are owned by
`docs/STATUS.md`; `/interaction` and `/run` remain emergency-only compatibility
surfaces and must not become ordinary semantic fallback.

## Resume commands

From the repository root:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_runtime_structure.py
python scripts/check_docs.py
python scripts/semantic_authority_audit.py --check
./scripts/benchmark_check.sh
python -m unittest discover -s tests -p 'test_*.py'
```

In a dependency-complete environment, use the canonical gate instead:

```bash
./scripts/run_tests.sh
```

For a running Agent service:

```bash
python scripts/control_plane_smoke.py --base-url http://127.0.0.1:8092
```

For the maintained GPU profile and service lifecycle, use:

```bash
bash scripts/gpu_smoke_test.sh
```

Do not report GPU, microphone, speaker, MuJoCo, or physical-provider validation
unless the command actually ran against that target and retained its evidence.

## Next engineering work

Publish and review Issue #20 without widening its fail-closed scope. Then
qualify the RTX 4090 Laptop model-role change and retain a same-model warm/cold prefix measurement;
separate prompt evaluation from model load and never call a repeated digest a
provider cache hit.

The merged Issues retain clean, revision-bound source and highest-safe automated
evidence for the walk/sing/blink defect, reversible barge-in, the exact
`chromie.vocal.perform` contract, and peer media Activity. The evidence paths,
counts, limits, and remaining physical/provider gaps are owned by
[Current Status](docs/STATUS.md) and [Acceptance](docs/ACCEPTANCE.md). In
particular, generated speech and MuJoCo body results do not prove a physical
microphone, speaker, robot, real vocal provider, or real media provider.

The paired Soridormi reproducibility patch is merged as `fa8080d2`; Chromie's
capability manifest and compatibility authority are bound to that revision.
Chromie PRs #12 and #13 are merged with green Python 3.11/3.12 checks; exact
compound and cancellation replay is retained against clean merged `a36444b`.
Preserve it while advancing explicit target tracks. Keep backend names out of
Goals, add no neutral media alias, and never relabel source, generated TTS, or
simulator evidence as real-provider, physical-audio, or hardware proof.

## Canonical owners

- stable boundaries: [Project Charter](docs/PROJECT_CHARTER.md)
- delivery order: [Roadmap](ROADMAP.md)
- implementation and evidence: [Current Status](docs/STATUS.md)
- target workflow: [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md)
- interfaces: [API Reference](docs/API_REFERENCE.md)
- operation: [Runbook](CHROMIE_RUNBOOK.md)
- notable changes: [Changelog](CHANGELOG.md)
