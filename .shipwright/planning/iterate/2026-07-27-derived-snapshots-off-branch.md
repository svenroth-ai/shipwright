# Iterate: derived snapshots leave the iterate PR

- **Run ID:** `iterate-2026-07-27-derived-snapshots-off-branch`
- **Type:** CHANGE
- **Complexity:** medium
- **Risk flags:** `touches_ci_supplychain`, `cross_component` (expected — churn/merge
  machinery + a new workflow)
- **Spec Impact:** NONE (see justification below)
- **Affected FRs:** FR-01.10 (audit-ready evidence), FR-01.11 (iterate lifecycle)

## Problem

Parallel iterates cannot merge. Empirically, on 2026-07-27 with five open PRs,
three sat `DIRTY` and two `BEHIND`. `git merge-tree` against `origin/main` shows
the conflicts are in **zero source files** — 100% of them are regenerated
snapshots:

```
.shipwright/compliance/{dashboard,traceability-matrix,test-evidence,change-history,sbom}.md
.shipwright/compliance/{ci-security,test-traceability}.json
.shipwright/agent_docs/{build_dashboard,session_handoff,triage_inbox}.md
shipwright_test_results.json
```

Every iterate regenerates all eleven at F5a/F5b regardless of what it changed,
and F6 stages them. N parallel iterates ⇒ N(N−1)/2 conflict pairs on files whose
content carries no information about the change.

### The deeper defect: the committed snapshots are already wrong

Regenerating on a *clean* main and diffing against what is committed there shows
substantive divergence, not timestamp noise:

| Artifact | Committed on main | Derived from main's actual state |
|---|---|---|
| `change-history.md` | `Total commits: 1248` | `1237` (11 too many) |
| `change-history.md` | lists commit `d762b1fd48e2` | not an ancestor of main (squashed away) |
| `traceability-matrix.md` | FR-01.06 `ok`, FR-01.11 `COVERED`, FR-01.14 `COVERED` | `MISSING`, `FAIL → trg-9e2ce202`, `2× FAIL` |

Verified: `git merge-base --is-ancestor d762b1fd48e2 origin/main` → false. Main's
audit artifact references a commit that was never on main.

This is structural, not incidental. The snapshots are generated **inside a
worktree**, where git history is the *branch's* history (pre-squash SHAs, extra
integrate commits) and the event log holds main's events plus this branch's — but
not those of concurrently merging branches. A branch-local derivation is wrong
for main by construction; which wrong version lands is decided by merge order.
So main's RTM currently under-reports three FR failures.

### `shipwright_test_results.json` is also a lossy evidence store

`iterate_latest` is a single overwritten slot. Walking the last twelve commits
that touched the file shows twelve different `run_id`s — each run's
machine-readable evidence (`test_completeness` ledger, `surface_verification`)
survives exactly one merge before the next iterate destroys it. It is
simultaneously a conflict magnet and a store that preserves one run out of N.

## Approach

`shipwright_events.jsonl` and `.shipwright/triage.jsonl` are the truth: append-only
logs with `merge=union`, which compose correctly across branches and stay in the
PR. The eleven snapshots are *derived views* over them. A derived view belongs
where the truth is complete — on main, after the merge.

Rejected alternative: resolve the conflicts server-side via `.gitattributes`.
GitHub honours only `union` and `-merge` server-side; `union` on regenerated
markdown produces garbage, `-merge` still conflicts, and custom merge drivers do
not run server-side at all (this is precisely why `ensure_current.py` exists). It
would also leave the *incorrectness* of the snapshots untouched.

## Acceptance Criteria

- **AC-1** — F6 no longer stages the eleven derived paths. They are still
  regenerated locally so F0 / F0.5 / F11 can read them; they only leave the PR
  diff. The files continue to exist on main.
- **AC-2 — WITHDRAWN from this iterate** (was: the F5c per-run entry carries the
  run's machine-readable evidence). Withdrawn, not silently unmet: `iterate_latest`
  is *already* last-writer-wins — twelve consecutive commits touching
  `shipwright_test_results.json` carry twelve distinct `run_id`s — so removing it
  from the PR regresses nothing that is durable today. Making evidence durable is a
  real improvement but a separate one; shipping the writer without migrating any
  reader would be write-only. External review (openai, high) flagged the original
  wording, correctly.
- **AC-3 — DEFERRED to its own iterate** (was: a post-merge refresh workflow).
  Two blocking decisions belong with it, not here: the refresh PR is
  self-referential (its own merge changes `change-history.md`, so it does not
  converge without excluding refresh commits or ignoring bot-authored pushes), and
  a `GITHUB_TOKEN`-created PR does not trigger workflow runs, so the six required
  checks would never start — it needs an App/PAT, a new trust surface. External
  review (openai, high) said "do not merge this as the completed change … or
  formally narrow and re-approve as an interim change." This is that narrowing,
  approved by the user, with the consequence accepted: **main's derived artifacts
  stay frozen until the refresh iterate lands.** They are demonstrably wrong today,
  so frozen is not worse than wrong.
- **AC-4 — MET** — `docs/hooks-and-pipeline.md` (artifact-write matrix) and the
  churn machinery's docstrings reflect the new ownership; `docs/guide.md` gained
  the parallel-iterate and merge-queue sections.
- **AC-5 (added during the run)** — a gate rejects a derived snapshot that reached
  the commit. F6's add-list is prose, and prose does not stop `git add -A`.

## Spec Impact justification

`spec_impact: none`. FR-01.10 requires audit-ready evidence and FR-01.11 the
iterate lifecycle; both requirement texts stay true verbatim. This change alters
*where and when* the evidence is derived — and makes it correct for the first
time — without changing what is required. No `change_type` applies.

## Affected Boundaries

- Git merge boundary (branch → main): which paths appear in an iterate's diff
- `shipwright_test_results.json` producer/consumer boundary (~12 consumers)
- F5c per-run entry writer/reader boundary (schema extension)
- CI trust boundary: a new workflow with write access to a branch and PRs

## STATUS — work in progress, resumable

Worktree: `.worktrees/derived-snapshots-off-branch`, branch
`iterate/derived-snapshots-off-branch`, based on `3c13001a`. **Not committed, not
pushed, no PR.** Finalization F0–F11 has NOT run.

**Done and verified:**

- `shared/scripts/lib/derived_snapshots.py` (new) — `DERIVED_SNAPSHOTS` registry +
  `restore_derived_to_head()`. Own module because `churn_merge.py` and
  `resolve_churn_conflicts.py` both carry bloat-baseline entries this would have
  ratcheted (`resolve_churn_conflicts.py`: limit 300, current 357, ADR-099).
- `integrate_main.integrate()` passes `only=set()` and calls
  `restore_derived_to_head()` after the merge; its module docstring now records
  the `find_snapshot_commit` consequence (item 2 below).
- `regenerate_tracked_snapshots` no longer treats an EMPTY `only` as "all":
  `only or set(DERIVED_MDS)` → `set(DERIVED_MDS) if only is None else set(only)`.
  A latent bug — the parameter could not express "no derived targets" — and
  fixing it removed the need for a new flag, keeping the file at its exact
  bloat-baseline size (357; limit 300, ADR-099 exception) instead of ratcheting it.
- Lint clean (`ruff@0.15.15`, `shared/`). The bloat anti-ratchet pre-commit hook
  passes on the staged tree (exit 0). `integrate_main.py` 291 LOC (< 300).
- 55 tests pass across the churn / integrate / ensure_current / doc-sync suites;
  the 2 failures below are the OLD contract being correctly detected, not
  regressions. Notably `restore_derived_to_head` also defeats a producer that
  *stages* a derived path — worth pinning as a test.

**Also done:**

- **Tests rewritten to the new contract.** New `shared/tests/test_derived_snapshots.py`
  (7 tests: registry shape, restore-defeats-a-staged-producer, no-op on a clean
  tree, untracked path skipped, and end-to-end "the snapshot matches main and the
  worktree is clean"). `test_ensure_current` now asserts `regenerate-noop` plus a
  clean worktree. `test_integrate_main`'s AC-6 test is renamed
  `test_integrate_followup_is_a_run_id_commit_the_audit_no_longer_claims` — the
  follow-up's SHAPE still holds (non-merge, `Run-ID:` trailer) but
  `find_snapshot_commit` now returns `None`, proven rather than assumed: a campaign
  status commit is NOT a snapshot commit, so item 2 below is real, not theoretical.
  63 tests green across the seven affected suites; the 506-test iterate plugin
  suite is green.
- **`restore_derived_to_head` bug found by its own test** and fixed: an UNTRACKED
  path was reported as restored though `git checkout HEAD --` cannot restore it.
- **C2 done** — F6's add list no longer stages the eleven derived paths, with the
  rationale recorded inline.

**Verified — the restore had to move, and a probe found the real bug:**

Reasoning had predicted that `check_build_dashboard_has_run_id` would fail after a
behind-integrate. A probe showed something worse and different: **the merge did not
happen at all** (`status=merge_failed`). With F6 no longer committing the dashboard
it sits tracked-and-dirty, and `git merge` refuses outright once mainline touches
the same path — the normal case, since every other iterate rewrites it too. This is
external review openai #1, and the restore was on the wrong side of the merge.
Fixed: `restore_derived_to_head` now runs BEFORE the merge (step `restored-derived`).
Re-probed: `status=ok`, worktree clean. Pinned by
`test_a_behind_branch_still_merges_and_the_run_stays_evidenced`.

*Then* the original prediction did reproduce — the dashboard holds mainline's
marker, so the check reports the run missing. Correction to an earlier claim: this
was NOT blocking. The branch is already `Severity.WARNING`, and F11 invokes the
verifier without `--strict`. Resolved anyway: the check now stands down (SKIPPED)
when the F5c per-run entry evidences the run, and still fails when NEITHER source
has it, so it is quieted rather than blinded. A by-design warning on every
behind-iterate is how a gate teaches people to stop reading warnings.

**C5 (partial) — `docs/guide.md`** gained "Why parallel iterates no longer collide
at merge time" + "Merge queues" under §8's parallel-iterates section, including the
ordering rule (a queue cannot rescue an already-conflicted PR).

Totals: 155 tests green across the affected suites; lint clean; anti-ratchet PASS;
`integrate_main.py` 300, `resolve_churn_conflicts.py` 357 (= baseline),
`iterate_checks.py` 1054 (< 1062 baseline).

**Open — next actions in order:**

1. **Client repos inherit this immediately — decide before merging.**
   `scripts/update-marketplace.sh` syncs `shared/` into the plugin-cache root that
   every adopted repo's plugins resolve, and F6 lives in the iterate skill. So every
   client repo stops committing its derived views too — and has no refresh workflow,
   so its compliance artifacts freeze indefinitely. They are equally wrong there
   today for the same structural reason, so frozen is not worse than wrong; but a
   repo that never runs parallel iterates takes the downside without the upside.
   C4 must therefore also be scaffolded by `/shipwright-adopt`, or C1 needs a way
   to stay opt-out for single-iterate projects.
2. **Reconcile the Group-E staleness audit.** `find_snapshot_commit` keys on a
   commit touching a snapshot path AND carrying a `Run-ID:` trailer — proven (not
   assumed) to return `None` now, since a campaign-status commit does not qualify.
   Correct for the frozen interim, but the C4 refresh must restore a recognized
   producer commit.
3. **C6** — the enforcement guard (F6 is documentation, not a gate; external review
   openai #5). Own `verifiers/` module — `iterate_checks.py` has only 8 lines of
   baseline headroom left.
4. **C5 (rest)** — `docs/hooks-and-pipeline.md` artifact-write matrix.
5. Then Step 7 / 7.5 (self-review, Confidence Calibration, Test Completeness
   Ledger), the code-review cascade, and full finalization F0–F11.

Follow-on iterates, in order: **C4** (post-merge refresh workflow — needs the
self-reference and bot-token decisions), then **merge queue** (`merge_group:`
triggers on the six required checks + the ruleset rule, which removes the cost of
a PR being `BEHIND`).

## Self-Review

1. **Does it do what the spec says?** AC-1 yes (F6 add-list + both stagers). AC-3
   and AC-4 partly: the refresh producer is deferred by decision, and
   `hooks-and-pipeline.md` is updated while `guide.md` gained the merge-queue
   section. AC-2 was **dropped** with a recorded reason — `iterate_latest` is
   already lossy, so removing it from the PR regresses nothing.
2. **Anything beyond the spec?** The `only`-parameter fix (empty set meant "all")
   was not planned. It is a latent bug in the function this change had to touch,
   and fixing it removed the need for a new flag — kept, and stated.
3. **Tests prove behaviour, not implementation?** Yes — every assertion is about
   what reaches a commit, what a merge does, what a gate reports. The one
   implementation-shaped assertion (`"restored-derived" in steps`) is load-bearing:
   it is the only way to distinguish "restore ran before the merge" from "the merge
   happened to succeed".
4. **Error paths?** `restore_derived_to_head` never raises (untracked, absent,
   unreadable git all covered). The gate fails open on an unreadable commit. The
   `followup_commit_failed` path is still exercised.
5. **Anything weakened to make it pass?** Two test assertions were loosened —
   `all(r.ok ...)` → `r.ok is not False` in the verifier suite. Justified: `None`
   is `CheckResult`'s documented "deliberately skipped" state, and the docstring
   says explicitly it must not count as pass OR fail. The test was stricter than
   the design. Returning `True` from a check that inspected nothing would have been
   the weakening, and was rejected (it is what #466 forbids).
6. **Reversible?** Yes — no data migration, no schema change. Reverting the commit
   restores the previous behaviour; the frozen snapshots resume being written by
   the next iterate.
7. **Affected Boundaries** — enumerated under Confidence Calibration below.
   The one with reach beyond this repo is the plugin-cache boundary: `shared/`
   syncs into every adopted repo, so the behaviour ships to clients on merge.
   That is filed as `trg-2f89afcf` and is the open decision.

## Confidence Calibration

- **Boundaries touched:** the git merge boundary (which paths appear in an
  iterate's diff); the `integrate_main` → `resolve_churn_conflicts` producer
  boundary; the F11 verifier check-list contract (`CheckResult` tri-state);
  the `audit_staleness.find_snapshot_commit` provenance boundary; the
  plugin-cache boundary (`shared/` reaches every adopted repo).

- **Empirical probes run:**
  - *Is the merge race a source race?* `git merge-tree` on all three DIRTY PRs →
    **zero** conflicting source files, 11 derived snapshots. It is not.
  - *Are main's committed snapshots correct?* Regenerated on clean main and
    diffed → `change-history.md` over-counts commits by 11 and cites
    `d762b1fd48e2`; `git merge-base --is-ancestor d762b1fd48e2 origin/main` →
    **false**. They are wrong today.
  - *Is `iterate_latest` a durable evidence store?* Walked the last 12 commits
    touching `shipwright_test_results.json` → 12 distinct `run_id`s. It is a
    last-writer-wins slot; evidence survives exactly one merge.
  - *Does a behind-branch still integrate?* **Probe overturned the prediction.**
    Expected the dashboard check to fail; got `status=merge_failed` — `git merge`
    refuses outright on a dirty tracked snapshot. The restore was on the wrong
    side of the merge. Moved before it → `status=ok`, tree clean.
  - *Can AC-6 be rescued via the campaign path?* No — `find_snapshot_commit`
    returned `None`; a campaign-status commit does not qualify as a snapshot
    commit. The staleness consequence is proven, not assumed.
  - *Does the new gate see a real violation?* `git add -A` with a derived file →
    gate reports it. Not blind.
  - *Full-suite blast radius:* `shared/tests` root, 7 failures surfaced beyond the
    63 tests under direct edit; all traced to the old contract and resolved.
    Final: **5884 passed, 0 failed**.

- **Test Completeness Ledger:** every behaviour this diff introduces or changes.

  | # | Behaviour | Disposition | Evidence |
  |---|---|---|---|
  | 1 | `DERIVED_SNAPSHOTS` names exactly the eleven shared mutable snapshots | tested | `test_registry_covers_every_derived_md_plus_the_two_json_snapshots` |
  | 2 | Append-logs and per-run paths are NOT swept into the registry | tested | `test_registry_excludes_the_append_logs_and_per_run_paths` |
  | 3 | `restore_derived_to_head` undoes a snapshot a producer already STAGED | tested | `test_restore_undoes_a_derived_snapshot_a_producer_already_staged` |
  | 4 | It is a no-op on a clean tree and never raises | tested | `test_restore_is_a_noop_on_a_clean_tree_and_never_raises` |
  | 5 | It skips an UNTRACKED path instead of claiming to restore it | tested | `test_restore_ignores_a_snapshot_the_project_does_not_track` (found a real bug) |
  | 6 | `integrate` makes no derived follow-up; the snapshot matches main; PR diff excludes it | tested | `test_integrate_makes_no_followup_for_derived_snapshots` |
  | 7 | A BEHIND branch still merges (restore runs BEFORE the merge) | tested | `test_a_behind_branch_still_merges_and_the_run_stays_evidenced` |
  | 8 | `check_build_dashboard_has_run_id` stands down when the F5c entry evidences the run | tested | same test, second half |
  | 9 | …and still reports when NEITHER source has it | tested | same test |
  | 10 | The F11 gate catches a derived snapshot that reached the commit | tested | `test_gate_catches_a_derived_snapshot_that_reached_the_commit` |
  | 11 | The gate passes a clean commit | tested | `test_gate_passes_a_commit_that_touches_only_real_files` |
  | 12 | The gate skips rather than invents on an unreadable commit | tested | `test_gate_skips_rather_than_invents_when_it_cannot_read_the_commit` |
  | 13 | `regenerate_tracked_snapshots` treats EMPTY `only` as "none", not "all" | tested | `test_integrate_makes_no_followup_for_derived_snapshots` + the cascade suite exercise both branches |
  | 14 | Three concurrent iterates drain serially with no cascade and no snapshot reaching main | tested | `test_three_concurrent_iterates_drain_without_cascade` (**`category:"integration"`** — the `cross_component` behaviour) |
  | 15 | A LEGACY branch that still carries the snapshots resolves rather than blocks | tested | `test_ci_security_json_conflict_resolves_through_cascade` |
  | 16 | The campaign-status follow-up still commits with its `Run-ID:` trailer | tested | `test_integrate_followup_is_a_run_id_commit_the_audit_no_longer_claims` |
  | 17 | `find_snapshot_commit` no longer finds an iterate-authored snapshot commit | tested | same test |
  | 18 | Integrate leaves no half-applied scan in the tree (CR-1 non-regression) | tested | both forward-staging suites |
  | 19 | A refused follow-up still reports `followup_commit_failed` + exit 8 | tested | `test_integrate_main_commit_failures` (both) |
  | 20 | Adopted repos inherit this without a refresh producer | untestable | `requires-manual-visual-judgment` — a product decision (scaffold vs opt-out), not a code path; recorded as triage `trg-2f89afcf` |

  0 testable-but-untested.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the probes stopped changing the design after the
    restore-ordering fix; each subsequent probe confirmed rather than revised.
    The one that overturned a prediction did so before any code shipped.
  - *Coverage (breadth):* full `shared/tests` root (5884) plus the
    `shipwright-iterate` plugin root (506), not only the files under edit — which
    is what surfaced the 7 downstream contract tests.
  - *Integration composition:* `cross_component` fires (merge/churn resolver +
    pipeline validators). Behaviour 14 is the real-scenario integration test —
    three serially-drained branches on real git — and it was strengthened rather
    than merely repaired: it now proves the class is resolved by ABSENCE.
