---
name: chromie-delivery-handoff
description: Prepare project-relevant Chromie changes for Git delivery by truthfully updating docs/STATUS.md, DEVELOPMENT_CHECKPOINT.md and HANDOFF.md before commit or push, then verifying all three files are included. Use when the user asks to commit, push, publish, hand off, prepare a delivery revision, or resume/defer project work that will be committed. Preserve the existing status, checkpoint and handoff for Skill-only or agent-tooling-only changes that do not alter Chromie implementation, architecture, evidence, blockers, or resume state. Do not use for ordinary edits, diagnosis, review, or status questions that do not authorize a Git delivery.
---

# Chromie Delivery Handoff

Apply Project Charter principle 44 so the next coding session can resume from Git
without hidden chat history.

## Workflow

1. Read `docs/PROJECT_CHARTER.md` principle 44, `AGENTS.md`, the current
   `docs/STATUS.md`, `DEVELOPMENT_CHECKPOINT.md`, and `HANDOFF.md` before editing any
   of the three delivery owners.
2. Classify whether the change affects Chromie's implementation, architecture,
   evidence, blockers, active issue, or resume state. A Skill-only or agent-tooling-only
   change is not project-relative merely because its files live in this repository.
3. Inspect the actual delivery state:
   - current branch, `HEAD`, upstream, and remote;
   - `git status --short`, relevant diff/stat, and recent commit subjects;
   - validation actually run in this work session, including exact failures;
   - retained evidence paths, runtime/profile identities, active Issue, and open blockers.
4. For a project-relative delivery, update `docs/STATUS.md`: the four-axis current-state
   table and the single ordered "Current open work" list (blockers included).
5. Update `DEVELOPMENT_CHECKPOINT.md` with the stable resume boundary:
   - active Issue and the resume point of the latest delivery;
   - repairs and owner decisions in force;
   - truthful evidence limits and claim boundary.
6. Update `HANDOFF.md` with the volatile operational snapshot only:
   - checkout, branch and expected resume revision;
   - runtime/profile identities and retained artifact paths;
   - exact deploy, run and verify commands.
7. For a Skill-only or agent-tooling-only delivery that changes none of those project
   facts, preserve all three files byte-for-byte and state that the project resume point
   is unchanged.
8. Replace the current sections of all three files; never append a dated delivery entry.
   Add a short `CHANGELOG.md` entry for a notable change. Review the diffs before
   committing and remove stale success claims, stale hashes, superseded commands, and
   wording that converts automated evidence into live evidence.
9. For a project-relative delivery, stage the three delivery owners with the
   user-authorized change. Refuse to create the delivery commit if any of them is missing
   from the staged diff or contradicts known evidence. For a non-project tooling delivery, refuse to stage
   incidental status/checkpoint/handoff edits.
10. Commit and push only as authorized. Never force-push unless the user explicitly
   authorizes the exact destructive operation. If the remote advanced, stop and report
   instead of rewriting history.
11. Verify the final branch/upstream state and report the commit hash, pushed ref, clean
   or remaining worktree state, tests actually run, and known failures.

## Evidence rules

- Never claim an unrun check passed. Write `not run` when the user waived testing.
- Never turn a failed gate into a pass by omitting it or changing expected behavior.
- Preserve exact retained artifact paths; mark unavailable evidence as unknown.
- Distinguish focused tests, full local gates, live service/model evidence, simulator,
  audio, and physical robot evidence.
- Do not rerun tests solely to make the handoff look current when the user explicitly
  says not to test. Record the latest observed evidence and its revision limit instead.
- Do not place the not-yet-created commit hash in the documents. Record the pre-delivery
  baseline and say that the expected resume revision is the latest commit containing the
  three delivery owners.

## Push-only requests

For a push of existing local commits, verify the newest commit being pushed already
contains accurate versions of the three delivery owners. If it does, do not create a
no-op handoff commit. If it does not, update them and create a handoff commit before the
push.
