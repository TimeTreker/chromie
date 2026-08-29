---
name: chromie-delivery-handoff
description: Prepare project-relevant Chromie changes for Git delivery by truthfully updating DEVELOPMENT_CHECKPOINT.md and HANDOFF.md before commit or push, then verifying both files are included. Use when the user asks to commit, push, publish, hand off, prepare a delivery revision, or resume/defer project work that will be committed. Preserve the existing project checkpoint and handoff for Skill-only or agent-tooling-only changes that do not alter Chromie implementation, architecture, evidence, blockers, or resume state. Do not use for ordinary edits, diagnosis, review, or status questions that do not authorize a Git delivery.
---

# Chromie Delivery Handoff

Apply Project Charter principle 44 so the next coding session can resume from Git
without hidden chat history.

## Workflow

1. Read `docs/PROJECT_CHARTER.md` principle 44, `AGENTS.md`, the current
   `DEVELOPMENT_CHECKPOINT.md`, and `HANDOFF.md` before editing either handoff owner.
2. Classify whether the change affects Chromie's implementation, architecture,
   evidence, blockers, active issue, or resume state. A Skill-only or agent-tooling-only
   change is not project-relative merely because its files live in this repository.
3. Inspect the actual delivery state:
   - current branch, `HEAD`, upstream, and remote;
   - `git status --short`, relevant diff/stat, and recent commit subjects;
   - validation actually run in this work session, including exact failures;
   - retained evidence paths, runtime/profile identities, active Issue, and open blockers.
4. For a project-relative delivery, update `DEVELOPMENT_CHECKPOINT.md` with the stable
   resume boundary:
   - pre-delivery baseline and expected resume branch/revision;
   - implemented architecture/contract and active issue;
   - truthful evidence ledger and qualification limits;
   - ordered next work, blockers, and claim boundary.
5. For a project-relative delivery, update `HANDOFF.md` with the volatile operational
   snapshot:
   - repository, branch, pre-delivery base, scope, and cross-machine bootstrap;
   - material code/workflow changes and module boundaries;
   - exact commands and observed results;
   - retained artifact paths and runtime/profile identities;
   - current failing, dirty, untested, or unqualified state and resume commands.
6. For a Skill-only or agent-tooling-only delivery that changes none of those project
   facts, preserve both files byte-for-byte and state that the project resume point is
   unchanged.
7. Review both diffs before committing. Remove stale success claims, stale hashes,
   superseded commands, and wording that converts automated evidence into live evidence.
8. For a project-relative delivery, stage both handoff owners with the user-authorized
   change. Refuse to create the delivery commit if either file is missing from the staged
   diff or contradicts known evidence. For a non-project tooling delivery, refuse to stage
   incidental checkpoint/handoff edits.
9. Commit and push only as authorized. Never force-push unless the user explicitly
   authorizes the exact destructive operation. If the remote advanced, stop and report
   instead of rewriting history.
10. Verify the final branch/upstream state and report the commit hash, pushed ref, clean
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
  checkpoint and handoff.

## Push-only requests

For a push of existing local commits, verify the newest commit being pushed already
contains accurate versions of both handoff owners. If it does, do not create a no-op
handoff commit. If it does not, update both files and create a handoff commit before the
push.
