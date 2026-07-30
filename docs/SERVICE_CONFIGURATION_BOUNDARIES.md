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

## Migrated boundary: ASR

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

## Remaining migration map

The remaining services keep their current behavior and are future ratchet work:

| Boundary | Current concentration | Recommended next seam |
|---|---|---|
| Agent service | `agent/app/main.py` | extract Agent startup settings by functional groups, preserving generated profile authority |
| TTS service | `tts/server.py`, `tts/candidate_server.py` | common transport/watchdog snapshot with provider-owned model settings |
| Host Orchestrator | `orchestrator/orchestrator.py` | compose typed audio, cognition, playback, and evidence settings rather than one global object |
| Shared runtime | trace/resource modules | inject narrow typed policy values where repeated reads remain |

Each future migration must be independently tested and must not become one global
cross-service settings object.
