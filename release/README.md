# Development Artifact Assets

This directory contains tracked compatibility and model-lock inputs used by
optional development artifact rehearsals. Generated evidence bundles, source
archives, manifests, and checksums belong under `.chromie/artifacts/` and are
intentionally not committed.

- [`development.md`](development.md) — maintained engineering scope and explicit non-claims.
- [`compatibility.json`](compatibility.json) — current cross-project development compatibility.
- [`model-lock.json`](model-lock.json) — immutable ASR/TTS source revisions and expected Ollama model names.

There is no active release version or publication target. The existing bundle
tool may be used only in preview mode to rehearse reproducible artifact
collection:

```bash
python scripts/prepare_release.py --preview \
  --allow-automated-evidence \
  --evidence-dir .chromie/acceptance/voice/<acceptance-id>
```

The preview validates evidence and repository consistency, can run the test
suite, and writes source/provenance/checksum artifacts for engineering review.
It does not create a tag, a publishable bundle, or a support promise.
