# Release Assets

This directory contains tracked release policy and human-written release notes.
Generated evidence bundles, source archives, manifests, and checksums belong
under `.chromie/releases/` and are intentionally not committed.

- [`0.0.1.md`](0.0.1.md) — release scope, Soridormi MuJoCo-executor limitations, and operator checklist.
- [`compatibility.json`](compatibility.json) — declared cross-project compatibility for the release.
- [`model-lock.json`](model-lock.json) — immutable ASR/TTS source revisions and expected Ollama model names.

Prepare a release bundle only after the selected evidence bundle passes:

```bash
python scripts/prepare_release.py \
  --allow-automated-evidence \
  --require-clean-evidence \
  --evidence-dir .chromie/acceptance/voice/<acceptance-id> \
  --text-mujoco-summary \
    .chromie/acceptance/text-mujoco/<text-run-id>/summary.json
```

The command validates evidence and repository cleanliness, runs the full test
suite, creates a Git source archive, and writes a machine-readable manifest,
`cognitive-runtime-acceptance.json`, immutable model lock, resolved build
provenance, and checksums. A publishable run requires current-revision
target-validated goal-driven text-to-MuJoCo evidence, an endpoint-reported
Soridormi revision matching the manifest and clean declared paired checkout,
running Chromie images/models bound to the candidate source, immutable image
references, Docker image IDs/digests, resolved Python dependencies from the
built images, and installed Ollama model digests. Those source/image bindings
are current compatibility blockers. `--skip-tests`, `--allow-dirty`, and
`--skip-runtime-provenance` are accepted only with `--preview`; preview bundles
are never publishable. The command does not create or push a Git tag.
Passing `tests.log` output replaces absolute candidate-repository and
operator-home paths with `<repo>` and `<home>` before it is checksummed for the
bundle.
