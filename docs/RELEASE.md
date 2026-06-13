# Release and Packaging

## Current position

The repository now declares `0.1.0-alpha.1` in `VERSION` and includes tracked
candidate notes, compatibility metadata, an evidence verifier, source-archive
generation, a release manifest, and checksums. No official GitHub release has
been published.

Treat `main` as a development branch and the current revision as supervised
alpha validation material. The release generator intentionally refuses a
publishable bundle while tracked spoken approval/denial evidence remains open
or a real alpha evidence bundle does not pass. See
[Current Implementation Status](STATUS.md).

## Recommended first release scope

The prepared first version is:

```text
v0.1.0-alpha.1
```

Recommended supported scope:

- one documented Linux x86_64 NVIDIA reference host;
- speech-only mode;
- structured speech-only mode;
- MuJoCo-backed named social/attention skills with a pinned Soridormi contract;
- deterministic stop, cancellation, and simulation recovery;
- no production real-hardware support claim.

Jetson and physical hardware should remain experimental until separate target
matrices are complete.


## Prepare the candidate bundle

First complete and verify the guided reference-host run:

```bash
python scripts/m13_voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi

python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<acceptance-id>
```

A packaging rehearsal can be created before all blockers close:

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
`manifest.json`, test log, and `SHA256SUMS`. The command does not create or push
a Git tag.

## Required release artifacts

- signed or annotated Git tag and GitHub prerelease notes;
- source archive;
- exact supported Chromie revision;
- compatible Soridormi revision and contract-schema version;
- supported hardware/profile table;
- installation and upgrade instructions;
- known limitations and default-off gates;
- test summary and retained target evidence references;
- container image identifiers or reproducible build instructions;
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
- Docker images build from a clean checkout.
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
- [`release/v0.1.0-alpha.1.md`](../release/v0.1.0-alpha.1.md)
- [`release/README.md`](../release/README.md)

## Changelog

Maintain user-visible changes in [CHANGELOG.md](../CHANGELOG.md). Implementation
checkpoint notes do not replace release notes.
