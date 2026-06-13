# Reference Robot Candidate Files

This directory owns the machine-readable input for Physical pilot preparation.
It does not contain drivers and cannot authorize physical motion.

- `reference_robot_candidate.schema.json` defines the versioned candidate
  structure.
- `reference_robot_candidate.example.json` is intentionally incomplete and
  must remain a rejected draft until real hardware and evidence are available.

Create a local candidate from the example, fill only observed facts, and run:

```bash
python scripts/verify_robot_candidate.py \
  commissioning/reference_robot_candidate.json
```

Use `--allow-draft` while collecting identity and evidence. The default command
exits successfully only for a fully reviewed candidate whose
`candidate_state` is `selected`. Every report keeps
`physical_motion_authorized=false`; selection is a preparation decision, not
motion approval.

Candidate-specific manifests and evidence may contain serial numbers, network
details, and operator identities. Keep those in ignored `.chromie/` evidence
storage unless the values are intentionally public.
