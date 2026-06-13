# Release Assets

This directory contains tracked release policy and human-written release notes.
Generated evidence bundles, source archives, manifests, and checksums belong
under `.chromie/releases/` and are intentionally not committed.

- [`v0.1.0-alpha.1.md`](v0.1.0-alpha.1.md) — candidate scope, limitations, and operator checklist.
- [`compatibility.json`](compatibility.json) — declared cross-project compatibility for the candidate.

Prepare a release bundle only after a complete alpha evidence bundle passes:

```bash
python scripts/prepare_alpha_release.py \
  --evidence-dir .chromie/acceptance/m13/<acceptance-id>
```

The command validates evidence and repository cleanliness, runs the full test
suite unless explicitly skipped, creates a Git source archive, and writes a
machine-readable manifest and checksums. It does not create or push a Git tag.
