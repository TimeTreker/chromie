# External Capability Manifests

Place trusted external capability bundle JSON files in this directory. Docker
mounts it read-only at `/app/capabilities` inside `chromie-agent`.

Enable one file:

```env
AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json
```

Enable every JSON file in the directory:

```env
AGENT_CAPABILITY_MANIFESTS=/app/capabilities
```

Multiple files or directories are comma-separated. Configured paths are
required to exist and parse successfully; otherwise the Agent fails at startup.
Do not expose raw motor, joint, or torque controls through these manifests.
