# Service Configuration Boundaries

Status: current engineering contract

## Ownership

Generated runtime configuration remains authoritative:

```text
env/profiles/*.env + env/validation/*.env + allowed local overrides
        ↓
scripts/generate_runtime_env.py
        ↓
.env.runtime
        ↓
service-owned typed startup snapshot
        ↓
internal collaborators
```

A service-owned settings object validates and normalizes its environment once at
startup. Internal modules receive typed values; they do not reinterpret the same
environment variable independently. This boundary does not change hardware
profile precedence and does not move owner-editable identity or personality into
Python defaults.

## Source-complete typed boundaries

`asr.settings.ASRServiceSettings` owns the complete maintained ASR service
environment surface. It provides:

- strict boolean, integer, float, optional-text, port, sample-rate, and duration
  parsing;
- one immutable snapshot copied from the startup environment;
- an `ASRBackendConfig` projection for the backend factory;
- a safe health-diagnostic projection that omits installation-local override
  file paths;
- explicit startup failures naming the invalid environment variable.

`asr/server.py` no longer calls `os.getenv`. The server, warm-up, health response,
transcription executor, and backend factory all consume the same immutable
settings instance.

`tts.settings.TTSServiceSettings` now owns the maintained TTS transport,
provider, generation-budget, worker-pool, speaker, alignment, and immutable
model-source environment surface. `tts/server.py`, `tts/candidate_server.py`,
`tts/create_speaker.py`, and `tts/model_sources.py` receive one typed snapshot
instead of reparsing environment values independently. Invalid ports, ranges,
booleans, and missing immutable model references fail with the owning key.

`agent.app.settings` now owns the Agent service and Goal Interpreter startup
surfaces. Main composition, model clients, weather, capability planning,
conversation, deep thinking, Goal Interpreter diagnostics, and manifest
expansion consume typed snapshots or explicitly supplied standalone settings.
Maintained startup passes the same Agent snapshot into every model and provider
client; compatibility factories remain only for isolated callers and tests.

`shared.chromie_runtime.settings.RuntimePolicySettings` owns narrow tracing,
retention, checkpoint, resource, accelerator, event-path, and CLI-color policy.
Trace, event, resource, accelerator, and logging helpers no longer parse process
environment independently. Each call receives one typed policy snapshot; this
does not create a global settings object spanning services.


## Closure and remaining evidence

The Agent, ASR, TTS, maintained Host, and shared-runtime policy boundaries are
source-complete and mechanically enforced by
`scripts/check_service_configuration_ownership.py`. The generated inventory is
owned by `scripts/runtime_configuration_inventory.py`; documentation does not
copy its changing key counts. Both checks must pass whenever configuration is
added, renamed, removed, or re-owned.

Standalone factories retained for focused tests must still instantiate their
own typed settings objects. Maintained service composition passes one startup
snapshot inward. Physical startup, device behavior, provider loading, and
profile-specific operational proof remain target evidence rather than source
configuration work.

See [Repository Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md).
