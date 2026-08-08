# Mini-Plan: track-decision-drops

- **Run ID:** iterate-2026-08-08-track-decision-drops

## Problem (re-verified against the live repo, 2026-08-08)

`.shipwright/agent_docs/decision-drops/` is gitignored. 214 real JSON drops
(plus a local `INDEX.md`) sit on the operator's main checkout right now;
`decision_log.md` was last written 2026-07-20 — confirmed both counts by
reading the live tree, not just the brief. Everything in that folder is
absent from every second checkout, from CI, and is lost with the disk.

**This is not a green-field decision.** `ADR-050` (2026-05-19) already
considered and *rejected* tracking this folder: *"Un-gitignoring
decision-drops/ and committing drops per-branch — rejected: drops are
Staging, aggregated then deleted at release; committing creates merge churn
(launch-prep plan keeps them gitignored)."* The operator's brief explicitly
reverses that decision for the reason ADR-050 didn't have: 10-week release
cadence makes "aggregated at release" too slow for durability, not that the
decision was wrong in the abstract. The merge-churn concern ADR-050 raised is
real and is designed around below, not dismissed.

**Also not isolated**: ADR-127 (PR #596, merged 2026-08-07, one day before
this run) built `lib/decision_drops_index.py` on the explicit, load-bearing
premise that this directory is gitignored — its own docstring states "never
a committed artifact" three times and argues *from* that premise that no
`CHURN_ALLOWLIST` entry and no CI drift guard are needed. That reasoning
does not survive tracking the directory unchanged; it has to be re-derived,
not silently invalidated.

## What "tracking the folder" actually requires (re-derived, not assumed)

The brief's instruction to verify `test_decision_drop_ssot.py`'s guard that
drop-dir consumers resolve to the **main repo root**, "because tracking
changes both" [the resolution and the sweep semantics] — read literally, not
as "confirm unchanged" — surfaces the real problem:

`write_decision_drop.py` (iterate F3) currently writes **directly onto the
operator's main checkout's disk**, deliberately bypassing the iterate's own
worktree, because a gitignored file written into the worktree would be
destroyed by `git worktree remove` before anything could commit it. That was
the *only* reason for the main-root redirect (`resolve_main_repo_root`) —
survive deletion of unversioned data.

Once the directory is tracked, disk-survival is no longer the durability
mechanism — git history is. Keeping the main-root write unchanged would mean:
a decision-drop lands as an **untracked file directly on the main
checkout**, and nothing in this codebase commits arbitrary new files
straight onto `main` outside a PR (the one direct-to-main-adjacent mechanism
that exists — `sweep_drift.py` / the outbox — solves a *different* problem:
TRACKED-file drift from producers with no owning run, like background
triage-scan appends. Every decision-drop write has an owning iterate run
with its own F6/F11/PR already). Leaving the write path unchanged would
reproduce the exact bug being fixed — the file would sit uncommitted on one
machine until *something* (nothing, currently) adds and pushes it — while
also leaving `git status` on main permanently dirty between runs.

**Decision:** move the write into the iterate's own worktree and let F6
stage it, mirroring the established "per-tree, PR-committed" model this
codebase already uses for `shipwright_events.jsonl`, `reviews.json`,
`ci_supplychain_ack.json`, and campaign `status.json` (all documented in
`references/F6.md`). Each drop file is committed as part of the iterate that
wrote it, ships in that iterate's own CI-gated PR, and is durable and
CI-visible the moment that PR merges — not 10 weeks later at release.

This is a bigger change than "flip three `.gitignore` lines" but it's the
part that makes tracking actually solve the stated problem instead of
relocating it.

## Design

### 1. Gitignore (three locations, as briefed)

Change the rule from ignoring the whole directory to ignoring only the
**generated, per-checkout `INDEX.md`** — everything else under
`decision-drops/` becomes tracked:

- `.gitignore:172` (this repo)
- `shared/templates/shipwright-gitignore.template:45` (what `/shipwright-adopt`
  scaffolds into every new project)
- `plugins/shipwright-adopt/scripts/lib/gitignore_check.py` — **verified no
  change needed**: it's a generic `git check-ignore`-driven classifier with
  no hardcoded decision-drops rule to fight the change.

`INDEX.md` stays gitignored deliberately: it's a local convenience render
with no aggregation value once committed (unlike the ADR/decision-log
indexes), and keeping it out of git is exactly what avoids the merge churn
ADR-050 rejected. The tracked payload is the JSON facts, not their local
render.

### 2. Write path: worktree, not main root

- `write_decision_drop.drop_dir()`: drop the `resolve_main_repo_root` call,
  resolve against `project_root` directly (the worktree root during an
  iterate run).
- `lib/decision_drops_index.py`'s `drop_dir()`: same change, for the same
  reason and to stay in lock-step with the producer (its own docstring's
  stated goal). Consequence: `write_decision_drop.py`'s CLI-triggered index
  refresh now renders the **worktree's own** `INDEX.md` (only this run's new
  drop) rather than the full main history — correct, since a worktree only
  legitimately has its own unmerged drop until the PR merges.
- `aggregate_decisions.drop_dir()`: **also** drop the resolver.
  `/shipwright-changelog` must read what's actually committed at its own
  checkout's HEAD, not reach past it to a separate main-checkout disk
  location — once tracked, jumping to "the main repo" is not just
  unnecessary, it's reading the wrong content if the changelog run itself is
  ever worktree-isolated.
- F11 verifier `iterate_checks.py` (`check_architecture_documented` /
  wherever it resolves `main_root` to build `drops_dir` for the *current
  run's own* drop lookup): same change — this run's own drop now lives in
  its own worktree, not on main.
- `test_decision_drop_ssot.py`: registries update to match — this is the
  "re-verify" the brief asked for, not a pass-through. `write_decision_drop.py`
  moves off `_WORKTREE_REACHABLE`'s resolver requirement (or the meta-test's
  contract is redefined so a worktree-local join is now the *correct* shape
  for these specific files) — exact mechanics left to implementation, but the
  test must assert the new, deliberate behavior, not silently start failing
  or silently stop meaning anything.

### 3. Backfill the existing 214 drops

They sit on the operator's main checkout today, written under the old
main-root-write behavior. `git add` them into **this iterate's own worktree**
copy of `decision-drops/` as a one-time migration commit (copy from the main
checkout into the worktree, add, ship in this PR) — otherwise "durability"
only starts working for drops written *after* this change, and the ten weeks
of already-written decisions stay exactly as lost as they are today.

### 4. Layer-1 context loading

`references/context-loading.md` item 4 currently reads only
`decision_log.md`. Add a bounded read of pending `decision-drops/*.json`
(title/decision/section — the same fields the local `INDEX.md` already
renders) so an iterate sees recent unreleased decisions, not just what's
been folded. Bounded, not "all 214 forever": once this run ships, the
backfilled 214 fold into `decision_log.md` at the next
`/shipwright-changelog` release and disappear from the drops folder
(`aggregate()` already deletes what it folds) — the steady-state read is
small (drops-since-last-release), and the historical backfill is a one-time
transient bulge, not a permanent Layer-1 cost.

### 5. Downstream consumers verified, not changed

- `shared/scripts/lib/architecture_doc.py` / `group_f.py` (compliance Group F
  detective): both resolve `main_root` to read the **committed, merged**
  state for cross-run reconciliation — this is now *more* correct than
  before (previously saw every active worktree's shared-staging drops
  regardless of merge status, which is exactly what the
  iterate-2026-06-12-arch-drift-test-scope lineage-scoping fix had to work
  around). Left unchanged; verified they still resolve to a real, now
  git-populated directory on main instead of a gitignored one.
- Campaign lineage-scoping (`events_log.finalized_run_ids` /
  `records_in_run_set`) stays as defensive code — now redundant in the common
  case (a worktree only ever contains its own drop), harmless to leave, out
  of scope to remove.
- `shared/tests/test_architecture_md_reflects_arch_impact.py::test_arch_impact_drops_found_at_all`
  — decision_log.md itself documents (ADR ~1153-1157) that this test was
  "born-red on any fresh clone or CI run" *because* the dir was gitignored.
  Once tracked, this is exactly the test-design bug that gets to be
  reassessed: verify what its skip condition currently is, and whether it
  can now assert for real.

## Alternative approach — rejected

**Keep the main-root write unchanged; add a periodic/direct-to-main
committer** (e.g. extend `sweep_drift.py`'s outbox-adoption pattern, or have
`/shipwright-changelog` `git add` accumulated stragglers). Rejected: every
decision-drop write already has an owning iterate run with its own
worktree/PR/CI — there is no "ownerless background producer" problem here
the way there is for triage.jsonl, so building or extending drift-sweep
machinery solves a problem this artifact doesn't have. A direct-to-main
commit from inside a running iterate would also bypass PR review and CI,
contradicting the project's `no_shoot_and_forget` / PR+CI-gated delivery
model for every other artifact.

## Risk / scope note for review

This plan intentionally goes beyond a literal three-file `.gitignore` edit
because a `.gitignore`-only change does not achieve durability — it just
relocates the same "sits uncommitted on one machine" failure by one layer.
Flagging this explicitly for the internal Opus review and the external
review: confirm the write-path redesign is the right call before it's built,
not after.

## Addendum — internal Opus review findings folded in (2026-08-08)

Verdict was **request changes**: design approved, scope incomplete. All
findings below are now part of this plan, not implementation-time
discoveries.

**1. HIGH — the lifecycle's two ends were missing.**
- F6 currently *forbids* staging the drop (`references/F6.md:19-23` NOTE
  block, with a stated reason that stops applying). Replace that NOTE with a
  real `git add {project_root}/.shipwright/agent_docs/decision-drops/` line
  and a rationale blockquote in the same style as the existing
  events.jsonl/reviews.json/ci_supplychain_ack.json/status.json ones
  (F6.md:80-138) — this section is its own cited precedent and gains a
  fifth member. Update the matching F3 bullets in `references/F3.md` and
  `agents/sub-iterate-runner.md`.
- `/shipwright-changelog` Step 6 never commits the deletions
  `aggregate_decisions.aggregate()` makes on disk (it unlinks folded drops,
  `aggregate_decisions.py` ~234-239) — its commit uses an explicit pathspec
  with no decision-drops entry. Once tracked, this duplicates every ADR at
  the *next* release (the deleted-but-uncommitted files come back on any
  fresh checkout/CI, and get folded again under new numbers). Add
  `git add -A {project_root}/.shipwright/agent_docs/decision-drops/` to the
  changelog Step 6 pathspec, staged AFTER `aggregate_decisions.py` runs so
  the deletions are what gets recorded. Add a test asserting a post-aggregate
  release commit contains zero tracked drop files.

**2. HIGH — the SSoT meta-test inverts, it does not relax.**
`test_decision_drop_ssot.py` currently hard-*requires*
`resolve_main_repo_root` in `write_decision_drop.py` and
`verifiers/iterate_checks.py`. Deleting/loosening that registry would
silently discard the exact protection it exists for (ADR-049: "every
iterate ADR since unconditional worktree isolation was silently lost").
Add a **`_WORKTREE_LOCAL`** registry with the same forward/coverage/reverse
triad, asserting these files (and `lib/decision_drops_index.py`,
`aggregate_decisions.py`) must **NOT** resolve against the main root — a
regression that reintroduces a main-root write must still fail red. Update
the module docstrings that currently explain the old asymmetry
(`aggregate_decisions.py`'s "deliberate asymmetry" comment,
`decision_drops_index.py`'s "gitignored... never committed" claims) to
describe the new, simpler reality instead of leaving stale rationale in
place. `write_decision_drop.py`'s `_find_existing_drop` idempotency
docstring also narrows (dedup is now per-branch, not shared) — restate it.

**3. HIGH — split the backfill from the mechanism.**
214 JSON files in the same PR as the code change risks pr-review truncation
on a Tier3a-sensitive path (where `--skip-pr-review` is ignored) and trips
the repo's own change-sizing review rule (net >1000 lines / mixed
refactor+data). Bloat gate and diff-coverage are non-issues (JSON data, no
new Python). **Split: PR 1** = gitignore (3 locations) + write-path redesign
+ verifier + SSoT test + F6/F3/changelog doc updates, small and reviewable.
**PR 2** = the 214-file data-only backfill, no code, opened after PR 1 merges
(the ignore rule must relax before PR 2's files are even addable). This run
delivers PR 1; PR 2 is scoped as an explicit, separate follow-up (name it in
F12 / triage, do not silently drop it).

**4. HIGH — security: the 214 drops have never been scanned.**
They're ten weeks of agent-authored free text, gitignored the whole time —
gitleaks/prompt-scan/CodeQL have never seen them, and this repo is public.
Before PR 2 (the backfill), run gitleaks and the prompt-scan over
`.shipwright/agent_docs/decision-drops/` and grep for the operator's local
username/home-path pattern; redact or exclude any hit. Record the scan as
evidence in that PR's ADR — this is the one step that can't be undone after
push. This run (PR 1) does not touch the 214 files, so it does not block on
this, but the plan must not let PR 2 happen without it.

**5. MEDIUM — gitignore also needs the index's temp file.**
`durable_atomic_write` writes `decision-drops/INDEX.md.<rand>.tmp` during a
refresh; a hard kill mid-write leaves a committable temp file once the
directory is tracked, and `/.shipwright/agent_docs/*.tmp` (template) does
NOT cover it (`*` doesn't cross `/`). Add
`/.shipwright/agent_docs/decision-drops/*.tmp` alongside the `INDEX.md` rule
in both `.gitignore:172` and the template — same one-line rationale style as
the two existing precedents for the ADR/decision-log indexes.

**6. MEDIUM — additional consumers, verified-and-dispositioned, not just
the ones already listed in "Downstream consumers":**
- `test_architecture_md_reflects_arch_impact.py` — resolves the drops dir
  against main-root but architecture.md against project_root; after the
  redesign these diverge for the CURRENT run (it becomes a check on merged
  history only, which is correct, but its skip/read logic needs re-reading
  against the new shape, not assumed unchanged).
- `verifiers/decision_log_gate.py` — already probes both main-root and
  local dirs (fallback becomes primary); update its comment, not its logic.
- `verifiers/common.py`'s `_MAIN_REPO_ONLY` allowlist reason for C1/C4
  checks — re-verify the reason still holds now that a raw join elsewhere
  in the registry set is changing shape.
- `lib/section_file_list.py`'s `FRAMEWORK_BOOKKEEPING` listing.
- `lib/churn_merge.py`'s comment arguing "gitignored, so git can never
  conflict" — stays TRUE only because `INDEX.md` remains gitignored; say so
  explicitly, since the premise is about to become false for everything
  else in the directory.

**7. MEDIUM — docs this repo's own rules require in the same diff:**
`docs/hooks-and-pipeline.md` (artifact-write matrix AND context-loading
matrix — CLAUDE.md makes both mandatory here since the write path moves and
Layer-1 gains a reader), `docs/guide.md`, `shared/glossary.md` ("gitignored,
main-repo path" entry), `.shipwright/agent_docs/architecture.md`, and
ADR-127's own spec file `.shipwright/planning/adr/127-decision-log-drops-index.md`
(whose premise this invalidates one day after merging — note it there, don't
rewrite history). **This run's ADR must explicitly supersede ADR-050 by
number**, stating what changed (10-week release cadence makes "aggregate
later" too slow) rather than that the original reasoning was wrong.

**8. MEDIUM — campaign contract, resolved by direct check (not left open):**
Verified `sub-iterate-runner.md:11`'s "no worktree" means no *additional*
per-sub-iterate worktree — the campaign orchestrator already runs inside one
`.worktrees/<slug>` (satisfying `check_iterate_isolation.py`'s
`not_under_worktrees` gate at the outer level), and each sub-iterate just
`git checkout -b`'s a new branch inside that SAME worktree. No contradiction:
`project_root` for a sub-iterate is that shared campaign worktree, never
main, so the redesign (write to `project_root`, F6 stages it) is correct
there unchanged. Net effect worth recording: a sub-iterate's drop no longer
persists in the campaign worktree's disk across sibling branch checkouts
(it's tracked on its own branch instead) — durability moves from "visible to
every sibling on shared disk" to "durable once that sibling's PR merges",
which is what removes the sibling-bleed the lineage-scoping code
(`architecture_doc.py` `records_in_run_set`) was built to paper over.

**9. MEDIUM — abandoned-run regression, accepted explicitly.**
Today an abandoned iterate's drop is harmless clutter on main's disk that
the next release still folds — the decision survives even if the branch
dies. After this change it lives only on an unmerged branch and is lost with
it. **Accepted, recorded in this run's ADR Consequences**: an abandoned
run's decision was never delivered under the PR+CI model either (no other
artifact from an abandoned iterate survives it). Not building a recovery
mechanism speculatively; if this becomes a real loss in practice, the
`setup_iterate_worktree.py:219-223` outbox-sweep-into-new-worktree pattern
is the named precedent to extend, not a redesign.

**10. MEDIUM — CI disposition flip, measured before PR 2, not assumed.**
`group_f.py`'s Group-F audit and
`test_every_arch_impact_drop_has_architecture_md_entry` currently `skip` on
a clean CI checkout (no drops dir) and go live once the backfill lands — 137
of the 214 drops declare a non-`none` `architecture_impact`, each needing its
`run_id` in `architecture.md`/`conventions.md`. Before PR 2: run both checks
against the real main checkout and record the result. Fix any gap or
explicitly exclude that drop from the backfill — do not discover this from a
red CI on a 214-file PR.

**11. MEDIUM — Layer-1 bound, specified numerically, not left to
discipline.** The steady state between releases is ~100+ pending drops
(10-week cadence), read on every iterate — not a one-time bulge. Bound:
render at most the **20 most recent** drops, one line each (reuse
`decision_drops_index.render_decision_drops_index`'s existing
title/date/section shape), enforced in the reader that builds the Layer-1
bundle — not left to caller discipline. State this explicitly in
`references/context-loading.md`.

**12. LOW — stale docstrings to rewrite, not just leave accurate-by-luck:**
`write_decision_drop.py`'s idempotency docstring (dedup narrows from
shared-main to per-branch) and `aggregate_decisions.py`'s "deliberate
asymmetry" comment (the asymmetry it describes no longer exists) — both
covered by item 2 above, called out separately so neither is missed as "just
a comment."
