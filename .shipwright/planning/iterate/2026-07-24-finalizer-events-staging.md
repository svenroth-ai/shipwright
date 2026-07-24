# Iterate: finalize_security_compliance leaves shipwright_events.jsonl dirty

- **Run ID:** `iterate-2026-07-24-finalizer-events-staging`
- **Intent:** BUG
- **Complexity:** medium (history-calibrated; risk floor small via `touches_io_boundary`)
- **Spec Impact:** NONE — bug fix to internal finalization tooling. No FR or
  `spec.md` governs the finalizer's git-staging path list; the fix aligns the
  finalizer with the *existing* iterate F6 convention (`references/F6.md`:
  explicit per-path `git add` incl. `shipwright_events.jsonl`). No AC reworded.

## Symptom

`plugins/shipwright-security/scripts/tools/finalize_security_compliance.py`
(Step 7.5 of `/shipwright-security`) commits the compliance MDs but leaves
`shipwright_events.jsonl` **dirty** in the working tree afterward.

## Root cause (F-debug — investigation before fix)

1. **Read the state.** After the finalizer commits, `git status` shows
   `M shipwright_events.jsonl` (and, on the first security scan, also
   `M shipwright_compliance_config.json`).
2. **Reproduce.** Running the finalizer a second time on a *clean* tree still
   commits **and** re-leaks a fresh `grade_snapshot` line into
   `shipwright_events.jsonl`. Every run leaks — not just the first.
3. **Component-boundary instrumentation.** `update_compliance.py --phase
   security` writes **three** artifact groups:
   - `.shipwright/compliance/*.md` (+ `ci-security.json`)
   - `shipwright_events.jsonl` — `emit_grade_snapshot()` appends **one
     `grade_snapshot` per regen, UNCONDITIONALLY** (its own docstring; no
     producer-side dedup)
   - `shipwright_compliance_config.json` — `phases_covered.append("security")`
     (diff only on the first security run)

   The finalizer's dirty-check (`_compliance_dirty`) **and** its staging
   (`git add COMPLIANCE_DIR`) are both hardwired to `.shipwright/compliance/`
   only. The other two writes are never staged → left dirty.

**Root cause:** the finalizer stages a strict *subset* of what
`update_compliance` writes. It is a boundary defect between the two scripts'
contracts, not a logic error inside either.

## Impact

- A dirty `shipwright_events.jsonl` makes `ensure_current` abort with **exit 6
  (merge_failed)** on the next pre-merge refresh. The known workaround is
  `git checkout -- shipwright_events.jsonl`, which **discards the
  `grade_snapshot`** — the only durable record the repo reached a given grade.
- Violates the repo's own binding rule: iterate F6 explicitly stages
  `shipwright_events.jsonl`, and `shared/scripts/tools/verifiers/iterate_checks.py:198`
  *fails* a run that does not.

## Why the existing tests missed it

`test_finalize_security_compliance.py` monkeypatches the `_run_update_compliance`
seam with fakes that write **only** an MD — never appending to
`events.jsonl`/config. So the real writer's side effects never ran under test.
`test_finalize_idempotent_across_two_runs` further *encodes* the false
idempotency assumption (second run = no commit) that the reproduction disproves.

## Fix (this iterate)

Scope: `plugins/shipwright-security` only (finalizer + its tests). One category.

1. **Stage the full write-set.** Replace the `COMPLIANCE_DIR`-only dirty-check
   and staging with an explicit artifact tuple
   `(.shipwright/compliance/, shipwright_events.jsonl,
   shipwright_compliance_config.json, .shipwright/triage.jsonl)`,
   mirroring F6's explicit list. Stage exactly the subset git reports as dirty
   via `git status --porcelain -- <paths>`, which naturally honours the F6
   "skip a path only if gitignored / untracked / absent" convention (ignored &
   absent paths never appear in porcelain; a gitignored `events.jsonl` therefore
   never triggers a `git add` error).
2. **Fix the derived no-diff path.** Because the dirty-check now includes
   `events.jsonl`, the "MDs unchanged but a snapshot was appended" case commits
   the event instead of early-returning "unchanged" with a dirty tree.
3. **Correct the false idempotency claim.** The module/test docstrings claim
   "second invocation … finds no diff and exits without committing." That is
   factually false (unconditional snapshot). Reword to the honest contract:
   *safe to re-run — each run records one post-scan snapshot and never leaves
   the tree dirty; a genuinely empty regen (no MD change AND no event) is a
   clean no-op.*

### Alternative considered (rejected)

Have `update_compliance.py` **return** its full write-path set and let the
finalizer stage exactly what was returned (drift-proof). Rejected: it widens
the change into a shared cross-plugin script consumed by other callers, against
the user's tight-scope constraint. Instead, the write-set is hardcoded in the
finalizer (consistent with F6's own hardcoded list) and **pinned by a
real-invocation test** so any future drift in `update_compliance`'s write
surface fails loudly here.

## Test plan (tests exercise the REAL side-effects, per the enforcement)

- **Regression pin:** faithful fake that writes an MD **and** appends to
  `events.jsonl` **and** touches config → after `finalize()`,
  `git status --porcelain` is **empty** (no leak). Fails on current code.
- Commit **contains** `shipwright_events.jsonl` (git show --stat).
- **Derived edge:** fake appends only the event (no MD change) → still commits,
  tree clean.
- **gitignored** `events.jsonl` → no `git add` error, MD commits, tree clean.
- **absent** `events.jsonl` → no error.
- **Genuine no-op:** fake writes nothing → no commit, tree clean.
- **Re-run safety** (replaces false-idempotency test): faithful fake appends
  each call → each run commits, tree clean after each.
- **Real-invocation drift guard:** call the real `update_compliance --phase
  security` in a synthetic pipeline repo; assert `finalize()` leaves a clean
  tree regardless of which files it wrote.

## Doubt review — finding (drove a 4th artifact)

The adversarial pass asked: *does `update_compliance --phase security` write
any OTHER tracked file the finalizer doesn't stage?* It does. The regen fires
`emit_sbom_triage` + `emit_test_failure_triage`; when a project has **no
`origin` remote**, `should_route_to_outbox()` is False and those append DIRECT
to the tracked `.shipwright/triage.jsonl` (with an origin they route to the
gitignored outbox — harmless). Empirically the current repo has no `test_run`
events and green tests, so no append fires today — but the leak is latent and
identical in class. Resolution: add `.shipwright/triage.jsonl` to
`FINALIZE_ARTIFACTS` (zero-risk — the candidate is simply never dirty in the
routed case) and pin it with `test_finalize_stages_direct_triage_append`.

## Confidence Calibration
- **Boundaries touched:** git working-tree staging (`git add` / `git status
  --porcelain` parsing); the finalizer↔`update_compliance` write-set contract;
  the `shipwright_events.jsonl` and `.shipwright/triage.jsonl` append-logs;
  `shipwright_compliance_config.json`.
- **Empirical probes run:**
  - Ran the fixed finalizer's tests against the **unmodified** code → 7 RED on
    the dirty-tree leak (reproduces the bug under test).
  - Drift-guard test invokes the **real** `update_compliance --phase security`
    subprocess → surfaced a previously-unknown artifact
    (`shipwright_events.jsonl.lock`, transient, gitignored in prod) and confirms
    `finalize()` leaves a clean tree end-to-end.
  - Confirmed via git `check-ignore` that the append-log mutex + outbox are
    gitignored in the real repo, and `triage.jsonl` is tracked.
- **Test Completeness Ledger:**
  | Behavior | Disposition | Evidence |
  |---|---|---|
  | Full write-set staged → clean tree | tested | `test_finalize_leaves_clean_tree_after_commit` |
  | Commit carries events + config | tested | `test_finalize_commit_includes_events_and_config` |
  | Direct triage append staged | tested | `test_finalize_stages_direct_triage_append` |
  | Event-only regen still commits | tested | `test_finalize_commits_when_only_event_changed` |
  | Gitignored events.jsonl → no error | tested | `test_finalize_tolerates_gitignored_events_log` |
  | Absent events.jsonl → no error | tested | `test_finalize_tolerates_absent_events_log` |
  | Genuinely empty regen → no-op | tested | `test_finalize_no_commit_when_nothing_written` |
  | Re-run never leaves dirty tree | tested | `test_finalize_reruns_safely_without_dirty_leak` |
  | Run-ID trailer + subject | tested | `test_finalize_creates_snapshot_commit_with_runid_trailer` |
  | Commit qualifies as audit snapshot | tested | `test_finalize_commit_qualifies_as_snapshot` |
  | Real producer → clean tree (drift guard) | tested | `test_finalize_real_update_compliance_leaves_clean_tree` |
  | Standalone / CI skip unchanged | tested | `test_finalize_skips_in_standalone_mode`, `_in_ci` |
- **Confidence-pattern check:** depth — porcelain parsing exercised for
  modified / untracked / absent / gitignored / directory-prefix cases; breadth —
  faithful-fake suite (fast, deterministic) + one real-producer drift guard
  (catches future write-set drift). No `cross_component` machinery touched →
  no integration-composition behavior required.
