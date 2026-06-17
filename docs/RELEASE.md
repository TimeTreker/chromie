# Release and Packaging

## Current position

The repository now declares `0.1.0-alpha.1` in `VERSION` and includes tracked
candidate notes, compatibility metadata, an evidence verifier, source-archive
generation, a release manifest, and checksums. No official GitHub release has
been published.

Treat `main` as a development branch. The historical M13 text-to-MuJoCo
interaction scope is closed with retained text evidence. Clean synthetic and
virtual-microphone evidence is also retained on the RTX 5090 reference host.
Physical microphone/speaker evidence is still required only for a release that
claims real voice-device support. The checked-in compatibility declaration still
contains that voice-device blocker, so the release generator refuses a
publishable bundle until either the supervised evidence passes or the supported
release scope is deliberately narrowed. See [Current Implementation
Status](STATUS.md).

## Recommended first release scope

The prepared first version is:

```text
v0.1.0-alpha.1
```

Recommended supported scope for a voice-device alpha:

- one documented Linux x86_64 NVIDIA reference host;
- speech-only mode;
- structured speech-only mode;
- MuJoCo-backed named social/attention skills with a pinned Soridormi contract;
- deterministic stop, cancellation, and simulation recovery;
- no production real-hardware support claim.

Jetson and physical hardware should remain experimental until separate target
matrices are complete.


## Prepare the candidate bundle

For a release that claims real microphone/speaker operation, first complete and
verify the guided reference-host run:

```bash
python scripts/m13_voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi

python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<acceptance-id>
```

The M13 text-to-MuJoCo interaction scope is already evidenced by
`.chromie/acceptance/text-mujoco/20260617T081411Z`. A packaging rehearsal can be
created before all blockers close:

```bash
python scripts/prepare_alpha_release.py --preview \
  --evidence-dir .chromie/acceptance/m13/<acceptance-id>
```

A publishable preparation omits `--preview`. It requires a clean committed
revision, passing evidence, no tracked closure blockers in
`release/compatibility.json`, and a successful full test run:

```bash
python scripts/prepare_alpha_release.py --require-clean-evidence \
  --evidence-dir .chromie/acceptance/m13/<acceptance-id>
```

Generated files are placed below `.chromie/releases/` and include a Git source
archive, release notes, compatibility declaration, acceptance summary,
`model-lock.json`, `build-provenance.json`, `manifest.json`, test log, and
`SHA256SUMS`. The command does not create or push a Git tag.

`build-provenance.json` records source-input checksums, declared image
references, resolved image IDs/repository digests, `pip freeze --all` output for
the four built Python images, the immutable ASR/TTS model lock, and installed
Ollama model digests. A publishable preparation fails if any exact dependency
pin is missing, an image reference uses a mutable tag, Docker images cannot be
inspected, a built image cannot report its resolved Python environment, or a
configured Ollama model/digest is absent.

A preview remains useful on a development host without Docker or Ollama. Such a
bundle is explicitly non-publishable and its provenance file lists the missing
runtime evidence. To avoid even attempting runtime collection during an
offline preview, add `--skip-runtime-provenance`.

## Required release artifacts

- signed or annotated Git tag and GitHub prerelease notes;
- source archive;
- exact supported Chromie revision;
- compatible Soridormi revision and contract-schema version;
- supported hardware/profile table;
- installation and upgrade instructions;
- known limitations and default-off gates;
- test summary and retained target evidence references;
- `model-lock.json` plus complete `build-provenance.json` with image, dependency, and Ollama digests;
- security and support policy links.

## Compatibility declaration

Every release should publish a table like:

| Chromie | Soridormi capability revision | Runtime mode | Support state |
|---|---|---|---|
| `0.1.x-alpha` | pinned commit and schema | MuJoCo `sim` | Supported alpha scope |
| `main` | current checked-in manifest | Development | No compatibility promise |
| Physical hardware | device-specific | `hardware` | Experimental until commissioned |

The checked-in manifest’s `upstream_commit` is necessary but not sufficient.
The release process must also probe the live endpoint and retain the result.

## Release gate checklist

### Documentation

- `docs/PROJECT_CHARTER.md`, `docs/STATUS.md`, `ROADMAP.md`, and
  `DEVELOPMENT_CHECKPOINT.md` agree.
- All local Markdown links pass `python scripts/check_docs.py`.
- Configuration defaults and feature gates match source and examples.
- API reference contains every implemented Router, Agent, and hardware endpoint.
- Supported and unsupported modes are visible on the first README screen.

### Engineering

- `./scripts/run_tests.sh` passes.
- Docker images build from a clean checkout using versioned base/runtime references.
- All direct Python dependencies are exact `==` pins and the release provenance captures resolved transitive dependencies.
- `release/model-lock.json` matches every maintained ASR profile and the configured TTS snapshot.
- `build-provenance.json` is complete, including Docker image and Ollama model digests.
- `START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh` passes on the reference host.
- The selected Ollama, ASR, and TTS models are documented and obtainable.
- Structured interaction and Soridormi compatibility are probed against the pinned revision.

### Alpha acceptance

- Native `InteractionResponse` generation is enabled and validated; compatibility rollback is documented.
- Non-skippable spoken confirmation dialogue is verified and request-bound.
- All seven guided cases in `ACCEPTANCE.md` are retained with correlated JSONL events.
- `scripts/verify_m13_evidence.py --require-clean` passes.
- Barge-in and body cancellation leave no stale speech or orphaned motion.
- Stop/emergency exercises include operator recovery confirmation.
- Evidence is reviewed for private speech, secrets, and unsafe state before publication.

### Packaging and operations

- Secrets are absent from source, logs, images, and evidence bundles.
- Upgrade and rollback instructions are tested.
- Release notes identify default-off features and unsafe combinations.
- An operator can diagnose the active hardware profile, service health, loaded
  capabilities, and scheduler state using documented commands.

## Versioning guidance

Use semantic versions for public releases. Before `1.0`, a minor version may
change experimental APIs, but release notes must call out contract changes.
Capability schema changes should update their schema version and compatibility
table rather than relying only on repository commit hashes.

## Tracked candidate files

- [`VERSION`](../VERSION)
- [`release/compatibility.json`](../release/compatibility.json)
- [`release/model-lock.json`](../release/model-lock.json)
- [`release/v0.1.0-alpha.1.md`](../release/v0.1.0-alpha.1.md)
- [`release/README.md`](../release/README.md)

## Changelog

Maintain user-visible changes in [CHANGELOG.md](../CHANGELOG.md). Implementation
checkpoint notes do not replace release notes.
