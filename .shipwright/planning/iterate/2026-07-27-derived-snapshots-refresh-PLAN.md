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

## CHOSEN (2026-07-28): the server-side refresh, with a bot credential

Decided after weighing the alternative below. The operator's objection to a
release cadence is the one that settles it: **stale artifacts are not visible at
the moment they mislead you.** You discover the discrepancy by tripping over it.

Note first what no design can promise: main moves between generation and merge,
so "always current" is unreachable (external review, openai #3). The real axis is
**window size** and **whether the window is visible**. This plan shortens the
window to one CI run and makes it self-declaring.

- **Trigger:** a workflow on `push: main`, so it does not depend on any session
  staying open — the objection that killed the F12 variant, and the one that
  matters once the merge queue lands.
- **Credential:** a bot token in repo secrets. This is the *only* way the required
  checks run on the refresh PR at all; `GITHUB_TOKEN`-created PRs never trigger
  them. Fine-grained PAT scoped to this repo (Contents + Pull requests, read/write)
  is the quick form; a GitHub App is the more rigorous one for an org-owned repo
  (no personal tie, short-lived tokens) and is the upgrade path.
- **Race safety:** a `concurrency` group serialises refresh runs, plus
  `--force-with-lease` and a re-check of the target main SHA before arming
  auto-merge (external review, openai #2 — deterministic output does NOT make
  last-writer-wins safe; the *older* writer can arrive last).
- **Loop guard:** the refresh PR's own merge pushes to main, so the workflow must
  skip triggers authored by the bot — otherwise it regenerates forever.
- **Checks:** the six required checks run normally on the refresh PR. Nobody waits
  on them; auto-merge handles it. Skipping them by path filter was considered and
  rejected: it would create a path-shaped hole in the gates that a human could
  also walk through.

### Provenance stamp — independent of cadence, do it regardless

The artifacts already carry a header line, and it currently states the wrong
thing:

    Source-State: run=iterate-2026-07-27-review-floor-not-chained

That names the run that last wrote the file *from a branch* — precisely the value
that is wrong by construction. Replacing it with the main SHA the derivation was
taken from, plus the distance from current main, makes staleness visible **on the
face of the artifact** instead of something discovered through a discrepancy.
This is the operator's actual concern, and it is cheap: the mechanism exists, it
just reports the wrong thing.

## Alternative, not chosen: stamp at release only

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

- **AC-1** — after a push to main, the refresh runs and main's derived snapshots
  match a regeneration from the SHA the refresh was taken from. Stated as
  eventual consistency with a named base, NOT as "main is always current" — the
  latter is unachievable and the original wording claimed it (openai #1).
- **AC-2** — two pushes in quick succession produce ONE refresh PR, not two, and
  the surviving content derives from the NEWER main. A `concurrency` group plus
  `--force-with-lease`; a lease failure re-fetches and regenerates rather than
  overwriting.
- **AC-3** — the refresh branch is reset to the triggering main SHA before
  regeneration, so its own prior refresh commit never feeds the generators.
- **AC-4** — a no-op refresh (nothing drifted) opens no PR and leaves no branch
  churn.
- **AC-5** — the bot's own merge does not trigger another refresh.
- **AC-6** — every derived artifact states the main SHA it was derived from and
  how far behind it is, so staleness is legible without running an audit.
- **AC-7** — a refresh that cannot run is recorded and visible (a triage item
  naming the main SHA), never silently skipped (openai #4).
- **AC-8** — `docs/guide.md` and `docs/hooks-and-pipeline.md` state the mechanism,
  the credential it needs, and the residual window.

## Operator prerequisite

The token cannot be created by the agent. Before this iterate can be finished:

1. Create a **fine-grained PAT** scoped to `svenroth-ai/shipwright` with
   *Contents: read/write* and *Pull requests: read/write*.
2. Store it as the repository secret `SHIPWRIGHT_REFRESH_TOKEN`.

Only the refresh workflow references it, and workflow files are Tier-3a
(pr-review-gated), so a change that redirects the credential cannot merge
unreviewed. A GitHub App is the stronger form and can replace the PAT later
without touching the workflow's logic.

## Alternative, not chosen: stamp at release only

Zero credentials, and it survives every review objection — but the window is days,
and the operator's objection stands: a stale artifact misleads silently at the
moment you rely on it. Kept here because it remains the correct fallback for any
repo unwilling to hold a credential, and because the release path should commit
the refreshed files regardless.
