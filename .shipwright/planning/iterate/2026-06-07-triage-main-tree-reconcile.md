# Iterate: triage.jsonl main-tree drift — reconcile-and-commit at integrate/sync

- **Run ID:** `iterate-2026-06-07-triage-main-tree-reconcile`
- **Type:** change (framework infra) · **Complexity:** medium
- **Risk flags:** `touches_io_boundary` (triage.jsonl producer/consumer + `json.loads`)
- **Spec Impact:** NONE (no FR change — internal tooling invariant)
- **Expands triage:** `trg-fc995a97`
- **Design source (authoritative):** `.shipwright/planning/iterate/proposed-triage-main-tree-drift-reconcile.md`
- **Completes the gap left by:** campaign `2026-06-05-track-triage-jsonl` C2 (#156)

## Problem (one paragraph)

`.shipwright/triage.jsonl` is tracked (C1 #155), main-repo-root durable (resolved
via `SHIPWRIGHT_PROJECT_ROOT` = main tree, opposite of events.jsonl's per-tree
model), and written by per-session **background** producers (plugin-sync
Stop-hook, compliance audit, `triage_add`). C2 (#156) added a leak-guard
*exemption* so those main-tree writes stop tripping the F0/F11 isolation guard —
but the exemption is not a **commit path**. The appends stay uncommitted in the
main working tree; a new iterate worktree branches off `origin/<default>` (never
the dirty main tree), so they orphan. When `origin/main` later also touches
triage.jsonl, `git merge --ff-only origin/main` / `git pull` in the main tree is
**blocked** ("local changes would be overwritten") — hit 2026-06-07 during the
post-merge plugin-cache-sync, reconciled by hand.

## Goal

Make "the main working tree stays git-pullable" an invariant the iterate/sync
**tooling** maintains automatically — without reviving the de-scoped per-tree
producer reroute and without putting `git commit` in a background hook hot-path.

## Design (implemented)

A single library op `reconcile_main_triage(project_root)` in
`shared/scripts/lib/reconcile_triage.py`, reusing C2's `validate_triage_text` +
`dedup_triage_lines` from `lib/churn_merge.py`:

1. Resolve the **MAIN** repo root from `project_root` (works when called from a
   worktree — `worktree_isolation.main_repo_root`).
2. Run safety guards (below). On any guard hit → structured no-op, git untouched.
3. Detect uncommitted drift in the tracked main-tree `.shipwright/triage.jsonl`
   (`git diff --quiet HEAD -- <path>`).
4. **Validate** the working copy (`validate_triage_text`); on error → no commit,
   `status="invalid"` (fail-closed — never commit a corrupt log).
5. **Dedup** exact lines (`dedup_triage_lines`); rewrite the file only if dedup
   changed it. Read/write **UTF-8, `\n`-preserving** (faithful round-trip — the
   log carries non-ASCII).
6. Commit **only that path** as one `chore(triage): fold N background append(s)`
   (`git commit -- <path>`), B7-exempt (Rule E non-functional `chore` type),
   no FR/Run-ID linkage. Idempotent: no drift → no commit.
7. Return a structured dict; the caller then proceeds with its FF/pull.

**Safety guards (no-op, never corrupt git state):** not a git repo · detached
HEAD · merge/rebase/cherry-pick/bisect in progress · **unrelated staged changes
in the index** · no actual drift · `CI` env set without `--allow-ci` opt-in.
Serialized with `lib/file_lock` on `.shipwright/locks/reconcile-triage.lock`.

**Wiring:**
- `tools/reconcile_main_triage.py` — thin CLI (the post-merge **sync-path**
  entrypoint the maintainer / cache-sync runs before FF'ing main).
- `tools/integrate_main.py` — calls it on the **main root** before its merge, so
  every iterate that integrates main also folds main-tree drift.
- `tools/setup_iterate_worktree.py` — calls it before snapshotting, so the
  background appends are committed (durable, not orphaned/lost) and the main-tree
  snapshot baseline is clean.

### Deliberate deviation from AC-4's literal wording (documented for review)

AC-4 says `git merge --ff-only origin/main` "succeeds" after reconcile. Once the
drift is **committed** to local `main`, local `main` is no longer an ancestor of
`origin/main`, so a literal `--ff-only` is topologically impossible. The design's
*stated mechanism* (commit as chore) and *goal* ("git-pullable") are both honored
by a normal **`git pull` (= fetch + union merge)**: once the working tree is
clean, the merge proceeds and the triage `merge=union` driver + churn resolver
fold both sides with no manual step. The AC-4 integration test therefore
reproduces the 2026-06-07 block, runs reconcile, and asserts the **`git merge
origin/main`** (pull-equivalent) now succeeds with a clean tree and **no silent
loss** of either side's lines. The literal `--ff-only` is intentionally
superseded — committing the drift is the explicitly-chosen mechanism.

### Conservative scope choice (orphan: "committed", not "branched-into")

The design marks "branch new worktrees off **local** main so they *inherit* the
appends" as *optional* ("closes the orphan fully"). Changing the worktree base
from `origin/<default>` to local `main` is a larger, riskier behavioral shift
(stale-base, divergence) outside this iterate's core. AC-6 is satisfied in the
durable-not-lost sense: after reconcile the appends are **committed to local
main history** (survive any later `checkout`/reset), and the snapshot is clean.
They reach origin via the maintainer's normal push/PR cadence.

## Acceptance Criteria

- [x] **AC-1.** `reconcile_main_triage` detects + validates + dedups + commits
      main-tree triage drift as one `chore(triage)` before any FF/pull.
- [x] **AC-2.** Commit is B7-exempt (`chore` type, Rule E) + leak-guard-clean;
      no FR linkage; no empty commit when there is no drift (idempotent).
- [x] **AC-3.** Guarded no-op when unsafe (not-a-repo / detached / merge|rebase
      in progress / unrelated staged changes / CI without opt-in) — user git
      state never mutated.
- [x] **AC-4.** After reconcile, the previously-blocked main-tree integration
      (`git merge origin/main`, the `git pull` mechanism) **succeeds** with a
      clean tree and both sides' lines present (reproduces the 2026-06-07 block).
      *(literal `--ff-only` intentionally superseded — see deviation note above.)*
- [x] **AC-5.** `integrate_main.py` invokes it before its merge; the sync-path
      CLI invokes it before FF.
- [x] **AC-6 (orphan closed).** A worktree created after reconcile: the
      background appends are committed to local main (no silent loss) and the
      main-tree snapshot is clean. *(durable-not-lost sense — see scope note.)*
- [x] **AC-7.** Validation/encoding round-trip: invalid log is never committed;
      non-ASCII preserved + mixed CRLF/LF handled robustly through read→dedup→write.

## Confidence Calibration
- **Boundaries touched:** the tracked main-durable `.shipwright/triage.jsonl`
  (producer = background hooks; consumer = `triage.read_all_items` + churn
  `merge=union`); the git index/working-tree of the **main** repo (commit op).
- **Empirical probes run:**
  - *Real git-block reproduction* — AC-4 test sets up the 2026-06-07 state
    (uncommitted main-tree drift + origin/main ahead on the same file), asserts
    `git merge --ff-only origin/main` actually fails, runs reconcile, then proves
    a normal union merge succeeds with **no line loss**. (not a mock — real bare
    origin + clone)
  - *Mixed CRLF/LF dedup* — found empirically that an autocrlf=true CRLF checkout
    + LF-writing producer yields mixed endings, so naive exact-line dedup misses
    `dup\r` ≠ `dup`. Fixed by `\r`-strip-before-dedup + EOL-preserving re-emit;
    pinned by `test_non_ascii_preserved_and_mixed_eol_handled`.
  - *Non-ASCII round-trip* — `München — café` survives read→dedup→write→commit→
    `git show`; surfaced (and corrected) a cp1252 decode bug in the TEST harness,
    confirming the impl writes correct UTF-8 bytes.
  - *B7 exemption verified against the real rule* — read
    `git_log_scan.apply_retention_rules`: Rule E `_NONFUNCTIONAL_TYPES` includes
    `chore`, so `chore(triage):` is genuinely excluded (not assumed).
  - *Boundary-probe categories:* CRLF + non-ASCII applied (above). UTF-8 BOM →
    safely **fail-closed** (a BOM'd first line fails JSON parse → validator
    rejects → no commit; the producer never writes a BOM). Operator-input probes
    (export prefix / inline `#` / quoted `#` / `KEY=`) **skipped** — triage.jsonl
    is machine-written JSONL, never hand-edited as `key=value` (per
    `boundary-probes.md` machine-only-format allowance).
- **Test Completeness Ledger:**

  | Behavior (this diff) | Disposition | Evidence |
  |---|---|---|
  | Detect uncommitted drift / no-drift no-op | tested | `test_commits_drift_as_chore`, `test_no_drift_is_noop` |
  | Validate before commit (fail-closed on invalid) | tested | `test_invalid_log_is_not_committed` |
  | Dedup exact-duplicate lines | tested | `test_dedup_folds_exact_duplicate_lines` |
  | Commit `chore(triage)`, B7-exempt, no FR linkage | tested | `test_commit_is_b7_exempt_no_fr_linkage` |
  | Idempotent (no empty commit) | tested | `test_idempotent_second_run_is_noop` |
  | Non-ASCII + mixed-EOL round-trip | tested | `test_non_ascii_preserved_and_mixed_eol_handled` |
  | Guard: CI without opt-in | tested | `test_skip_in_ci_without_optin` |
  | Guard: detached HEAD | tested | `test_skip_on_detached_head` |
  | Guard: merge in progress (pseudo-ref) | tested | `test_skip_on_merge_in_progress` |
  | Guard: rebase in progress (git-dir file) | tested | `test_skip_on_rebase_in_progress` |
  | Guard: any staged change (incl. triage.jsonl itself) | tested | `test_skip_on_unrelated_staged_changes`, `test_skip_when_triage_itself_is_staged` |
  | Guard: deleted/missing triage log | tested | `test_skip_when_triage_log_deleted` |
  | Guard: not a git repo | tested | `test_not_a_git_repo_is_skip` |
  | Resolve MAIN root from a worktree | tested | `test_reconcile_from_worktree_commits_on_main` |
  | AC-4 unblocks the pull/FF block | tested | `test_ac4_reconcile_unblocks_pull` |
  | integrate_main wiring (before merge) | tested | `test_integrate_main_reconciles_before_merge` (+ `_noop`) |
  | setup_iterate_worktree wiring (commit drift + clean snapshot) | tested | `test_setup_worktree_commits_drift_and_clean_snapshot` |
  | CLI status→exit-code mapping + CI opt-in | tested | `test_cli_allow_ci_opt_in_flips_skip_to_commit`, `test_cli_invalid_log_exits_three`, `test_cli_no_drift_exits_zero` |
  | Producer-lock acquisition around critical section | untestable | `covered-by-existing-test` (every committed-path test runs through `triage._FileLock`; a deterministic race test would be flaky — exclusion is guaranteed by reusing the canonical producer lock) |

  0 testable-but-untested behaviors; the single `untestable` row carries a valid
  closed-vocabulary `reason_code`.
- **Confidence-pattern check:**
  - *Asymptote (depth):* AC-4 is an end-to-end reproduction of the real failure
    mode (real bare origin, real `--ff-only` refusal, real union merge), not a
    stub — the deepest probe available short of dogfooding on main.
  - *Coverage (breadth):* 23 tests span library behavior, all safety guards
    (CI / op-in-progress / detached / any-staged / staged-triage / missing-log /
    not-a-repo), worktree resolution, both call-site wirings, and the CLI (incl.
    the CI opt-in flip); full shared suite + ruff green.
  - *External review:* OpenAI (via OpenRouter, `--mode code`) — ship-with-fixes;
    all actionable findings (any-staged guard, absolute `--git-path`, missing-log
    skip, two test-overclaim fixes) applied. Gemini leg returned truncated/garbled
    output (no actionable signal). Internal Opus code-reviewer: APPROVE-WITH-NITS,
    all nits applied.
