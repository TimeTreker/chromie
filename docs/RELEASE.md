# Release and Packaging

## Current Position

The repository declares `0.0.1` in `VERSION` and includes tracked release
notes, compatibility metadata, an evidence verifier, source-archive generation,
a release manifest, and checksums. The compatibility declaration is currently
`candidate` and records concrete release blockers for endpoint-reported
Soridormi source identity, running Chromie image/model binding, immutable image
references, and fresh current-revision goal-driven voice and MuJoCo evidence.
No official GitHub release has been published yet.

Treat `main` as a development branch. The historical M13 text-to-MuJoCo
interaction scope is closed with retained text evidence. Clean synthetic,
virtual-microphone, and acoustic generated-speech evidence can support this
release only when the release claim remains narrowed to generated speech and
Soridormi MuJoCo `sim` execution. Physical microphone/speaker evidence is still
required for any release that claims human voice-device support. See
[Current Implementation Status](STATUS.md).

## 0.0.1 Scope

The proposed candidate scope is:

- one documented Linux x86_64 NVIDIA reference host profile;
- generated-speech voice regression through `synthetic`, `virtual-mic`, or
  `acoustic` evidence;
- structured text/speech interaction through the host Orchestrator, Router,
  Agent, trusted Skill Runtime, and pinned Soridormi capability contract;
- MuJoCo-backed named skills in Soridormi `sim` mode;
- deterministic stop, cancellation, timeout, and MuJoCo safe-idle recovery;
- no production real-hardware, Jetson distribution, unattended deployment, or
  human voice-device support claim.

## Prepare the Release Bundle

For `0.0.1`, verify a clean automated evidence bundle. The current low-cost
generated-speech device path is shown below. Start the external Soridormi MCP
endpoint separately at the pinned revision first; `--start-services` starts
Chromie services only.

```bash
python scripts/voice_acceptance.py \
  --mode acoustic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services

python scripts/verify_voice_evidence.py --allow-automated --require-clean \
  .chromie/acceptance/voice/<acceptance-id>
```

The verifier defaults to the current Git `HEAD`, `VERSION`, and the Soridormi
revision shared by `capabilities/soridormi.json` and
`release/compatibility.json`. A historical bundle fails provenance validation;
it cannot be used to package a newer source revision. The current runner's
`--soridormi-repo` argument records a `declared_paired_checkout`; it does not
prove which source the MCP endpoint executes. Only a bundle with a matching
`endpoint_reported_revision` can set `policy_evaluation_ready=true`, after
which the release preparer checks the mode against
`evidence_policy.accepted_voice_modes`. The current endpoint/runner combination
does not provide that binding, so newly generated bundles remain outside
release-policy evaluation. `human_voice_device_claim_eligible` is a separate
supervised-evidence field and remains false for generated-speech modes.

The retained M13 text-to-MuJoCo interaction scope is historically evidenced by
`.chromie/acceptance/text-mujoco/20260617T081411Z`. It does not validate the
current goal-driven authority path. Before tagging, produce a clean
current-revision text-to-MuJoCo `summary.json`. Recording a paired Soridormi
checkout is diagnostic only; target validation also requires a matching
endpoint-reported source revision, which is not yet emitted by the current
runner/endpoint path.

Create a non-publishable packaging rehearsal when runtime provenance is not
available:

```bash
python scripts/prepare_release.py --preview --skip-runtime-provenance \
  --skip-tests --allow-dirty \
  --allow-automated-evidence \
  --require-clean-evidence \
  --evidence-dir .chromie/acceptance/voice/<acceptance-id>
```

`--skip-tests`, `--allow-dirty`, and `--skip-runtime-provenance` are rehearsal
options accepted only with `--preview`. A non-preview command rejects all three.
Preview mode never makes a bundle publishable.

A publishable preparation omits `--preview`. It requires a clean committed
revision, passing evidence, no tracked closure blockers in
`release/compatibility.json`, complete runtime provenance, and a successful
full test run:

```bash
python scripts/prepare_release.py \
  --allow-automated-evidence \
  --require-clean-evidence \
  --evidence-dir .chromie/acceptance/voice/<acceptance-id> \
  --text-mujoco-summary \
    .chromie/acceptance/text-mujoco/<text-run-id>/summary.json
```

Generated files are placed below `.chromie/releases/` and include a Git source
archive, release notes, compatibility declaration, acceptance summary,
`cognitive-runtime-acceptance.json`, `model-lock.json`,
`build-provenance.json`, `manifest.json`, test log, and `SHA256SUMS`. The
cognitive artifact records whether the text-to-MuJoCo summary is
target-validated, including exact Chromie and Soridormi provenance, applied
goal-driven execution, Soridormi `sim` mode, completion, and safe idle. The
command does not create or push a Git tag.

The retained `tests.log` is sanitized after a passing test run and before
checksums are written: absolute candidate-repository and operator-home paths are
replaced with `<repo>` and `<home>`. Failed runs abort preparation and are not
publishable artifacts.

`build-provenance.json` records source-input checksums, declared image
references, resolved image IDs/repository digests, `pip freeze --all` output for
the four built Python images, the immutable ASR/TTS model lock, and installed
Ollama model digests. A publishable preparation fails if any exact dependency
pin is missing, an image reference uses a mutable tag, Docker images cannot be
inspected, a built image cannot report its resolved Python environment, or a
configured Ollama model/digest is absent. The maintained development
configuration still uses `CHROMIE_IMAGE_TAG=latest` and
`OLLAMA_IMAGE=ollama/ollama:latest`; those are intentionally tracked as release
blockers rather than represented as immutable provenance. Acceptance must also
bind the actually running Chromie service images and loaded models to the
candidate revision; host-checkout `HEAD` alone is insufficient.

## Required Release Artifacts

- annotated or signed Git tag `0.0.1` and GitHub release notes;
- source archive;
- exact supported Chromie revision;
- compatible Soridormi revision and contract-schema version;
- supported hardware/profile table;
- installation and upgrade instructions;
- known limitations and default-off gates;
- test summary and retained target evidence references;
- `model-lock.json` plus complete `build-provenance.json` with image,
  dependency, and Ollama digests;
- security and support policy links.

## Compatibility Declaration

Every release should publish a table like:

| Chromie | Soridormi capability revision | Runtime mode | Support state |
|---|---|---|---|
| `0.0.1` | pinned commit and schema | Soridormi MuJoCo `sim` | Proposed candidate scope; not yet published |
| `main` | current checked-in manifest | Development | No compatibility promise |
| Physical hardware | device-specific | `hardware` | Experimental until commissioned |

The checked-in manifest’s `upstream_commit` and a clean user-selected paired
checkout are necessary but not sufficient. The release process must retain an
endpoint-reported executing source revision that matches both. That endpoint
identity is not available from the current runner, so publication remains
blocked. Compatibility validation also requires a non-empty unique
`chromie.runtime_modes` list and currently accepts only
`soridormi.supported_mode=sim`; an empty or unsupported release scope fails
closed.

## Release Gate Checklist

### Documentation

- `docs/PROJECT_CHARTER.md`, `docs/STATUS.md`, `ROADMAP.md`, and
  `DEVELOPMENT_CHECKPOINT.md` agree.
- All local Markdown links pass `python scripts/check_docs.py`.
- Configuration defaults and feature gates match source and examples.
- API reference contains every implemented Router, Agent, and hardware endpoint.
- Supported and unsupported modes are visible on the first README screen.

### Engineering

- `./scripts/run_tests.sh` passes.
- `python scripts/general_ability_acceptance.py --mode check --no-write`
  passes.
- `python scripts/general_ability_acceptance.py --mode level-a --no-write`
  passes, and any failed ability class has a root-cause report before release
  work continues.
- Docker images build from a clean checkout using versioned base/runtime
  references.
- Running Chromie service image identities and loaded model digests are bound
  to the candidate Chromie revision in retained acceptance evidence.
- All direct Python dependencies are exact `==` pins and the release provenance
  captures resolved transitive dependencies.
- `release/model-lock.json` matches every maintained ASR profile and the
  configured TTS snapshot.
- `build-provenance.json` is complete, including Docker image and Ollama model
  digests.
- `START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh` passes on
  the reference host when the release claims target GPU performance.
- When a release claims latency stability, a retained target-environment Runtime
  Trace baseline and candidate report pass an enabled, reviewed latency policy
  through `python scripts/runtime_trace_latency.py gate`. A disabled example
  policy or automated/simulator-only report is not target latency evidence.
- The selected Ollama, ASR, and TTS models are documented and obtainable.
- Structured interaction and Soridormi compatibility are probed against the
  pinned revision.
- The Soridormi endpoint reports its executing source revision, which matches
  the pinned manifest and clean declared paired checkout.

### Simulator Acceptance

- Native `InteractionResponse` generation is enabled and validated;
  compatibility rollback is documented.
- Request-bound confirmation dialogue is verified and request-bound.
- Automated voice evidence is accepted only for this narrowed generated-speech
  and Soridormi MuJoCo-executor claim.
- Barge-in and body cancellation leave no stale speech or orphaned motion.
- Stop/emergency exercises include recovery confirmation when the live simulator
  path is used.
- Evidence is reviewed for private speech, secrets, and unsafe state before
  publication.

### Packaging and Operations

- Secrets are absent from source, logs, images, and evidence bundles.
- Upgrade and rollback instructions are tested.
- Release notes identify default-off features and unsafe combinations.
- An operator can diagnose the active hardware profile, service health, loaded
  capabilities, and scheduler state using documented commands.

## Human Voice-Device Releases

A later release that claims real microphone/speaker operation must first
complete and verify the guided supervised reference-host run:

```bash
python scripts/voice_acceptance.py \
  --mode supervised \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services

python scripts/verify_voice_evidence.py --require-clean \
  .chromie/acceptance/voice/<acceptance-id>
```

Do not clear a physical voice-device blocker by pointing to text-input,
synthetic, virtual-mic, or acoustic generated-speech evidence.

## Versioning Guidance

`0.0.1` names a pre-1.0 semantic release. Public production releases should
continue to use semantic versions. Before `1.0`, a minor version may change
experimental APIs, but release notes must call out contract changes. Capability
schema changes should update their schema version and compatibility table
rather than relying only on repository commit hashes.

## Tracked Release Files

- [`VERSION`](../VERSION)
- [`release/compatibility.json`](../release/compatibility.json)
- [`release/model-lock.json`](../release/model-lock.json)
- [`release/0.0.1.md`](../release/0.0.1.md)

## Changelog

Maintain user-visible changes in [CHANGELOG.md](../CHANGELOG.md). Implementation
checkpoint notes do not replace release notes.
