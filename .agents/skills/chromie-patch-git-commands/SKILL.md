---
name: chromie-patch-git-commands
description: Include complete, copy-ready Git commands whenever giving the owner a Chromie patch or reporting completed source, documentation, configuration, or skill edits. Cover review, add, commit, push, and final status using the actual checkout. Applies even when commit or push was not requested; providing commands does not authorize executing them.
---

# Chromie Patch Git Commands

Owner: Chromie repository maintainers. Audience: coding agents handing patches to
the project owner. This skill owns the owner's patch-response preference. It applies
before commit authorization, while the existing delivery-handoff skill owns actual
delivery preparation. Keep this preference here rather than duplicating that process.

Every patch handoff must include a fenced `bash` block containing the complete Git
sequence. A prose offer to provide commands later does not satisfy this requirement.

1. Inspect the repository path, branch, remote/upstream, changed files and staging
   state. Tailor commands to those observed values; never assume `main` or `origin`
   without checking. If a destination is unknown, state that and mark only the
   unresolved value as a placeholder.
2. Include the commands needed for the current state, in execution order:
   - `cd` to the actual repository; fetch and compare the relevant remote branch.
   - Review working changes with `git status` and `git diff`.
   - `git add --` with the exact intended paths, including deletions. Avoid staging
     unrelated changes or ignored evidence; use `git add -A` only when all changes
     have been inspected and belong to this patch.
   - Review the complete staged patch with `git diff --cached`.
   - `git commit` with a concrete message describing this patch.
   - Fetch again, verify the destination branch is an ancestor of the local revision,
     then `git push` to the explicit destination. Guard the sequence so failed
     commands or upstream divergence stop it; do not prescribe automatic rebases,
     destructive resets or force pushes.
   - Verify with `git status` and the local/upstream revision comparison.
3. When handing over a patch file that has not been applied, include its actual
   `git apply --check` and `git apply` commands before staging. Do not tell the user
   to apply an already-applied patch again.
4. Distinguish pending commands from commands already executed. For an authorized
   commit/push that is complete, show the actual command record, commit and ref,
   labelled as already executed; do not present it as work the owner must repeat.
5. Providing commands is not authorization to commit or push. Execute those actions
   only when the user has authorized them. Follow the existing
   [delivery-handoff skill](../chromie-delivery-handoff/SKILL.md) when preparing an
   actual delivery, including its skill-only exception. Preserve explicit test
   waivers and report validation truthfully; this skill adds no testing requirement.
