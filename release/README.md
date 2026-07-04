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
  --evidence-dir .chromie/acceptance/voice/<acceptance-id>
```

The command validates evidence and repository cleanliness, runs the full test
suite unless explicitly skipped, creates a Git source archive, and writes a
machine-readable manifest, immutable model lock, resolved build provenance, and
checksums. A publishable run requires Docker image IDs/digests, resolved Python
dependencies from the built images, and installed Ollama model digests. It does
not create or push a Git tag.
