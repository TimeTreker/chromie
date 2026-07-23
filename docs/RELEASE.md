# Optional Development Artifact Packaging

Chromie currently has **no planned release version or publication target**.
`VERSION` and `release/compatibility.json` identify the working tree as
`development`; they are used only to bind evidence and generated artifacts to
the source that produced them.

The repository retains a generic artifact-packaging rehearsal because it is
useful for engineering review, reproducibility checks, and handoff between
machines. It must not be interpreted as release preparation or a support
promise.

## Development compatibility

The maintained declarations are:

- [`VERSION`](../VERSION): `development`;
- [`release/development.md`](../release/development.md): maintained engineering
  scope and explicit non-claims;
- [`release/compatibility.json`](../release/compatibility.json): paired
  Chromie/Soridormi development compatibility and known evidence gaps;
- [`release/model-lock.json`](../release/model-lock.json): immutable speech
  model and expected Ollama identities.

The compatibility state must remain `development` and must not declare a Git
release tag while no publication target exists.

## Preview-only artifact rehearsal

The existing command is retained for compatibility, but the development state
permits **preview mode only**:

```bash
python scripts/prepare_release.py \
  --preview \
  --allow-automated-evidence \
  --evidence-dir .chromie/acceptance/voice/<acceptance-id>
```

The command may:

- verify that evidence matches the current source and compatibility manifest;
- run `./scripts/run_tests.sh` unless explicitly skipped for a preview;
- create a Git source archive;
- write `build-provenance.json` and `model-lock.json`;
- write sanitized evidence summaries, a manifest, and `SHA256SUMS`;
- optionally attach current Goal-driven text-to-MuJoCo evidence.

Generated artifacts are written under `.chromie/artifacts/` and are not
committed.

Preview mode never creates a Git tag, never emits publication commands, and
always records `publishable=false`.

## Evidence boundaries

Artifact rehearsal does not change the evidence vocabulary:

- implementation is not automatic verification;
- automatic verification is not target validation;
- target validation is not physical-device or hardware support;
- historical evidence does not validate a newer source revision;
- generated-speech evidence does not prove arbitrary human speech quality;
- E-stop dispatch does not prove safe idle without correlated provider
  postcondition evidence.

## Provenance requirements

Useful engineering artifacts should retain:

- exact Chromie revision and dirty state;
- exact declared Soridormi checkout and manifest revision;
- endpoint-reported Soridormi execution revision when available;
- resolved Docker image identities;
- installed Ollama model digests;
- sanitized test output and checksums.

Missing provenance keeps an artifact diagnostic. It does not become stronger
because it was packaged.

## No current publication procedure

There is intentionally no current version-selection, tagging, GitHub release,
upgrade, or public-support procedure. Add those only after the project owner
explicitly establishes a future distribution plan.
