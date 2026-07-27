# Plan: unfreezing the derived snapshots

Follow-on to `iterate-2026-07-27-derived-snapshots-off-branch` (PR #480), which
stopped an iterate from committing eleven regenerated snapshots and left main's
copies **frozen**. This plan unfreezes them.

## The constraint that rules out the obvious design

A GitHub Actions workflow using the built-in `GITHUB_TOKEN` cannot do this: a PR
it creates does not trigger workflow runs (GitHub's guard against recursive
workflows), so the six required status checks never report and the PR is blocked
forever. Unblocking it costs either a stored credential (App/PAT) or a ruleset
bypass for the Actions app — the latter repo-wide, so any workflow could then
write to the protected branch.

## Rejected: trigger it from the iterate's own F12

Attractive because it removes the credential entirely — the actor is the
session's `gh` credentials, so the PR is user-authored and the checks run
normally. **External review rejected it, correctly** (gemini `reject`, openai
`revise`), and the decisive objection came from this repo's own roadmap:

- **It breaks against the merge queue** (the step planned right after this one).
  A queue means PRs no longer merge on delivery; they queue, possibly for hours.
  A watcher in a local session cannot be relied on to still be running — closed
  terminal, lost network, sleeping machine — and the refresh silently never
  happens.
- **`AC-1` as originally written is unachievable.** A refresh's own merge changes
  main, so "main matches a fresh regeneration" is false immediately afterwards.
  Ignoring the bot's own merges stops the *loop* but leaves the artifact
  permanently one commit behind — the invariant has to be restated, not patched.
- **The standing-branch force-push is not race-safe.** Deterministic output does
  not save it: the *older* writer can arrive last and win.
- **Failure would be silent.** A local step that fails (session closed, missing
  permissions, PR merged by another route) leaves the artifacts frozen with
  nobody notified.

## Chosen: stamp at release, plus a manual refresh

The release phase already regenerates these files — `update_compliance.py
--phase <name>` fires after every completed phase, including `changelog`. It
simply does not commit them: Step 6 of the changelog skill stages `CHANGELOG.md`
and nothing else. The change is to include the derived paths in that commit.

This survives every objection above, and not by accident:

- A release is a **deliberate, synchronous act**. It never waits on someone
  else's merge, so a merge queue does not affect it.
- A release does not trigger a release — the feedback loop cannot form.
- It claims something achievable: the artifact carries the state **as of a
  release**, not "always current". For an audit document that is the better
  semantic anyway.
- A release branch is cut from main, so the derivation sees main's complete
  state — the exact condition a worktree-local derivation could never meet.
- No credential, no bypass, no workflow, no async dependency.

Between releases the artifacts are stale, and the Group-E staleness audit reports
that truthfully — which is the visible signal openai asked for, with no new
machinery.

A second entry point runs the same regeneration on demand, for when the
release cadence is too slow.

## Acceptance criteria

- **AC-1** — a release commit contains the derived snapshots regenerated from the
  release branch's own tree.
- **AC-2** — the manual refresh command produces the same result as the release
  path (one producer, no second implementation).
- **AC-3** — a no-op refresh (nothing drifted) commits nothing.
- **AC-4** — both paths work in an adopted repo with no secret and no ruleset
  change; `/shipwright-adopt` needs to scaffold nothing new.
- **AC-5** — `docs/guide.md` and `docs/hooks-and-pipeline.md` state the cadence,
  so "stale between releases" is documented rather than discovered.

## If freshness between releases is later required

Then the correct build is the one gemini prescribed, and it should be built as
such rather than approximated client-side: a bot App/PAT, a workflow on
`push: main`, a `concurrency` group to serialise refreshes, and an actor guard so
the bot's own merges do not re-trigger it. That is a deliberate trade — one
credential for continuous freshness — and it is a decision to take when the
cadence actually hurts, not before.
