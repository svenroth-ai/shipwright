# Mini-Plan: derived snapshots leave the iterate PR

Run: `iterate-2026-07-27-derived-snapshots-off-branch` · CHANGE · medium

## Two producers put derived snapshots into an iterate PR

1. **F6 explicit `git add`** (`plugins/shipwright-iterate/skills/iterate/references/F6.md`)
   — stages `.shipwright/agent_docs/build_dashboard.md`, `shipwright_test_results.json`,
   `.shipwright/compliance/`.
2. **`integrate_main.integrate()`** (`shared/scripts/tools/integrate_main.py:169-216`)
   — after merging `origin/main` at F11's `ensure_current`, calls
   `resolve_churn_conflicts.regenerate_tracked_snapshots()` and commits
   `chore(churn): regenerate derived snapshots after <branch> merge`. This is what
   carries `session_handoff.md` and `triage_inbox.md` into the PR — they are in
   every DIRTY PR's diff but appear nowhere in F6's documented list.

Both must change, or the conflict class survives through the other path.

## Changes

### C1 — `regenerate_tracked_snapshots` stops committing on an iterate branch
`shared/scripts/tools/resolve_churn_conflicts.py` + `integrate_main.py`.
Regeneration still runs (the working tree must be correct for F0/F0.5/F11 to read),
but on an `iterate/*` branch the result is **not** staged into the follow-up commit.
Conflict resolution during the merge itself is unchanged — the resolver still picks a
side so the merge completes; it simply no longer ships the regenerated result.

### C2 — F6 drops the derived paths from the add list
`plugins/shipwright-iterate/skills/iterate/references/F6.md`. Remove
`build_dashboard.md`, `shipwright_test_results.json`, `.shipwright/compliance/`.
Add a note explaining why (mirroring the existing `events.jsonl` note, inverted).
`shipwright_events.jsonl`, `.shipwright/triage.jsonl`, `reviews.json`, the F5c
`iterates/` dir and campaign `status.json` all **stay** — they are append-logs or
per-run paths, not shared mutable snapshots.

### C3 — run evidence becomes durable per run
`shared/scripts/tools/append_iterate_entry.py` (F5c). Extend the per-run entry to
carry the machine-readable evidence currently held only in
`shipwright_test_results.json.iterate_latest` (`test_completeness`,
`surface_verification`). Today that slot is last-writer-wins: twelve consecutive
commits touching the file show twelve different `run_id`s, so evidence survives
exactly one merge. `.shipwright/agent_docs/iterates/<run_id>.json` is collision-free
and already ships in the PR.

### C4 — post-merge refresh workflow — **DEFERRED to its own iterate**
See "Revision after external review" below. Not built here.

### C5 — documentation
`docs/hooks-and-pipeline.md` artifact-write matrix (mandated by CLAUDE.md when the
write matrix changes); churn-machinery docstrings in `churn_merge.py` /
`resolve_churn_conflicts.py` / `ensure_current.py`.

## Alternative considered and rejected

Resolve server-side via `.gitattributes`. GitHub honours only `union` and `-merge`
server-side; `union` on regenerated markdown yields garbage, `-merge` still
conflicts, custom merge drivers never run server-side. It would also leave the
*incorrectness* of branch-derived snapshots untouched (main's `change-history.md`
cites a commit that is not an ancestor of main).

## Risks

- **The bot PR moves main**, making open PRs `BEHIND`; with
  `strict_required_status_checks_policy: true` that still costs a CI re-run.
  Mitigated by debouncing; removed entirely by the follow-up merge-queue iterate.
- **A workflow with write access to branches + PRs** is new CI trust surface
  (`touches_ci_supplychain`) — needs the recorded posture ack.
- **C1 must not weaken the merge resolver**: a real (non-churn) conflict must still
  abort exactly as today.

## Revision after external review (both reviewers: `revise`)

Reviews recorded in `.shipwright/planning/iterate/<run_id>/reviews.json`.

**Accepted — C4 is deferred to its own iterate.** Two findings hit the refresh
workflow specifically and are design decisions, not implementation detail:

1. *Self-reference (openai #2).* The bot PR merges → main gains a commit →
   `change-history.md` counts it → new diff → new bot PR, without end. Verified by
   reasoning about the generator: it counts commits, so its own commit always
   changes the output. Two convergent fixes exist (exclude refresh commits from the
   derivation, or ignore bot-authored pushes as a trigger); choosing between them
   belongs with the workflow.
2. *Token (both, and verified here).* This repo has no bot-PR precedent — all seven
   workflows use `secrets.GITHUB_TOKEN` only. PRs created with `GITHUB_TOKEN` do not
   trigger workflow runs, so the six required checks would never start and the PR
   could never auto-merge. Needs a GitHub App or PAT: a new secret and a new trust
   surface, which is its own decision.

**Accepted into this iterate:**

3. *Dirty worktree (both, high).* Regenerating tracked files without staging leaves
   them modified; `git merge` at F11 can refuse when local modifications overlap
   incoming paths. **C1 gains a restore step**: after the phase that consumes them,
   the derived paths are restored to `HEAD` so the worktree stays clean.
4. *F6 is documentation, not enforcement (openai #5).* **New C6**: a narrow guard
   rejects the derived paths in an iterate-branch commit, so a stray `git add -A`,
   hook, or future implementation cannot silently reintroduce the conflict class.

**Rejected, with reasons:**

5. *"The ~12 consumers of `shipwright_test_results.json` will crash" (both).* They
   will not — the file continues to exist on main; it only leaves the PR diff. The
   valid kernel (evidence written to per-run entries that nothing reads would be
   write-only) is why **C3 is dropped from this iterate**: the ledger's durable home
   is already the iterate spec's Confidence Calibration section, which does ship,
   and `iterate_latest` is demonstrably lossy today, so removing it from the PR
   regresses nothing. Making it durable is a separate improvement.
6. *"The resolver must still stage a side at conflict" (gemini #3).* True in general
   but moot here: once F6 stops staging these paths, the branch carries no diff on
   them, so they cannot conflict. Conflict resolution itself is untouched — only the
   follow-up regenerate commit goes away.

**Interim consequence, accepted by the user:** main's derived artifacts stop being
updated until the C4 iterate lands. They are demonstrably wrong today (they cite a
commit that is not an ancestor of main); frozen is strictly better than
wrong-and-merge-order-dependent.
