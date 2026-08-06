# Mini-Plan — `iterate-2026-08-06-triage-store-write-path`

## Chosen approach: extract-then-fix, four independent fixes, one composition test

Three of the four target files are at **exactly 300 of 300 LOC**, so growth is
structurally unavailable. Each fix therefore ships as a small extraction into a
sibling module (re-exported from the old home, the precedent `triage_validate`
already set in `churn_merge.py:14-16`) plus the behaviour change in the new
module, where it has room to be commented properly.

### Order of work (each step green before the next)

1. **`lib/triage_dedup.py`** — move `dedup_triage_lines` out of `churn_merge.py`;
   re-export. Add the identity-anchor rule: same-id appends that agree on
   `originalTs` (~~falling back to `source`+`kind`+`title`~~ — **superseded by R2
   below: the fallback was rejected and the anchor is `originalTs` alone**) collapse
   keep-last **with a warning**; appends that disagree are kept, with a loud
   collision warning naming `triage_repair.py`. `warnings` stops being
   contractually empty.
   *Callers:* `reconcile_triage` (new `warnings` on `ReconcileResult`),
   `sweep_quarantine._materialize`/`decide` (new `warnings`, folded into a
   `block`'s `errors` so they reach the operator through the existing surface),
   `resolve_churn_conflicts` (already plumbs them — correct its stale docstring).
2. **`lib/main_tree_guards.py`** — move `_op_in_progress` / `_is_detached` /
   `_has_staged_changes` out of `reconcile_triage.py`; re-export under the same
   private names. Buys the headroom step 3 needs and the guards step 5 needs.
3. **`reconcile_triage.py` rollback** — restore the pre-rewrite bytes when the
   commit definitively fails and the file on disk is still exactly what we wrote;
   refuse to restore (and say so) when it is not; no rollback on timeout.
4. **`lib/triage_gc_core.py`** — move the GC engine out of `tools/triage_gc.py`;
   re-export. Route both writes through `durable_atomic_write`; make the `.bak`
   byte-faithful (`read_bytes` once, write those bytes). Add
   `describe_post_gc_divergence()`.
5. **`tools/triage_gc.py`** — print the divergence warning after `--apply`; add
   the opt-in `--commit` behind the step-2 guards.
6. **`lib/sweep_drift_restore.py`** — the salvage-rename restore; `sweep_drift`
   delegates step 2 of `commit_main_tracked_drift` to it (that file *shrinks*).
7. **Integration coverage** — one `category:"integration"` test on a real git
   repo composing GC → warning → `--commit` → `plan_main_tracked_drift` →
   sweep, plus a late-append salvage.

### Why the salvage rename (fix 7/AC-7) rather than "narrow the window further"

The window is `[last read] → [subprocess spawn] → [git writes the file]`. The
spawn dominates and cannot be removed, so narrowing is asymptotic and the current
code already did the cheap half. `os.replace` moves the *live inode* out of the
way atomically: an append that landed before the rename is **in the salvage file**
and recoverable; git then recreates the path from HEAD with the file it would
have clobbered safely aside. The salvage lives beside the log in `.shipwright/`,
which `/.shipwright/*` already gitignores (verified with `git check-ignore`), so
it never becomes main-tree drift of its own.

Residual, stated as loss rather than as inevitability: a writer that *opens the
path by name* between the rename and git's write creates a fresh file that
`checkout` then overwrites. That is a strictly smaller window than today's, and
it is named in the module docstring.

## Alternative considered and rejected

**Make the collision case in fix 1 collapse-with-a-warning instead of keeping
both lines.** Cheaper, no new `block` path, no risk of wedging delivery — and
rejected, because it keeps the property the card objects to: a record that no
other path on this surface deletes would still be deleted, just noisily. The twin
`dedup_event_lines` already decided this exact question the other way on the same
32-bit-id reasoning, and a wedge is recoverable (`triage_repair.py`) where a
deleted record is not. Measured cost of the strictness: **0 occurrences** in the
684-append tracked log, so the block is reachable only through a genuine union
collision.

**Also considered and rejected:** auto-committing the compaction in `apply_gc` by
default (fix 5). Committing unprompted in the operator's *main* tree is the exact
class of action `reconcile_main_triage`'s guard battery exists to prevent, and
`triage_gc` is a maintenance CLI, not a pipeline step. Warn by default, commit on
request.

## Revisions after external plan review (verdict: revise ×2, both rounds)

Raw reviewer output: `iterate-2026-08-06-triage-store-write-path/external-plan-review.json`
(openrouter, openai + deepseek, 13 structured findings). Accepted changes to the
design above:

**R1 — warnings must never block delivery.** Flagged three times independently and
it is the one thing that could turn this safety change into a new wedge. Made
explicit: an anchor-matching keep-last collapse leaves the quarantine decision
`clean` and carries `warnings`; only the *collision* case (both lines kept →
`validate_triage_text` reports a duplicate append) reaches `block`. Pinned by a
test that asserts `action == "clean"` **and** `warnings != []` for the benign case.

**R2 — the identity anchor is `originalTs` alone, and only positively.** Collapse
requires `originalTs` present, a non-empty `str`, and **equal** on both records.
Missing, empty, non-`str`, or unequal ⇒ keep both + collision warning. Same-id
appends are **grouped by anchor** (not compared pairwise against the last kept
line), so three-plus records cannot match transitively. The reviewers' proposed
`source`+`kind`+`title` fallback is **rejected**: a refreshed rollup legitimately
changes its title, so a title-sensitive anchor would re-create the ADR-163 wedge
this function exists to prevent. Measured (JSON-parsed, not substring-matched):
684/684 appends in the tracked log carry
a valid `originalTs`, so requiring it costs nothing. Residual, named in the module
docstring: two distinct items minted in the same microsecond *and* colliding on a
32-bit id would collapse — the corpus does contain 2 same-microsecond timestamp
pairs, so the first half is real; the conjunction is what makes it negligible.

**R3 — `apply_gc` reads the source bytes once.** Today it reads twice
(`read_text` at :200 for the backup and JSON scan, `_iter_raw_lines_at` at :217 for
the rewrite input), so the backup can preserve a different version than the one
compacted. One `read_bytes`, both derived from it. Plus a **fingerprint re-check
immediately before the replace**: the canonical `_FileLock` is already held across
the whole section (`triage_gc.py:199` — the reviewers' "no concurrency protocol"
premise is false for cooperating writers), but the webui writer does not take it,
so GC aborts and reports rather than overwriting a file that moved.

**R4 — `--commit` refuses a pre-dirty triage path.** The inherited guards reject a
*staged* index but say nothing about the tracked log already carrying uncommitted
background drift — the normal state of a main tree here. Committing then folds
undelivered appends into a "compaction" commit under a false subject. `--commit`
now requires the triage path clean against HEAD and otherwise refuses, pointing at
`reconcile_main_triage`, printing the same consequence + remedy as plain `--apply`.

**R5 — salvage recovery is conditional throughout.** Unique salvage filename
(pid + counter, `O_EXCL`-style claim), retained until adoption *and* restore have
both succeeded. After a failed `checkout`, the salvage is moved back **only if the
target path is absent**; if something is there, both artifacts are kept under
distinct names and the result is a loud manual-recovery status. The salvage delta is
classified by an **append-only prefix check** against `plan._raw`: only a
well-formed producer-event suffix is adopted (reusing `_is_producer_event`, so a
malformed line can never raise out of the sweep); anything else preserves the
salvage and returns repair-required. Adoption is idempotent — it dedups against the
outbox exactly as `plan.fresh` already does. If the restore-back itself fails, the
tracked log would be missing, so that path reports fatally rather than returning a
soft status.

**R6 — rollback verifies HEAD, and the `git add` premise gets tested, not argued.**
Both reviewers assert a failed commit leaves the rewrite staged "because `git add`
occurred". `reconcile_main_triage` never calls `git add` — it uses
`git commit -- <path>`, which commits worktree content through a temporary index.
Rather than argue it, the fault-injection test asserts `git diff --cached --quiet`
is clean after a failed commit. Accepted regardless: a non-zero exit is not proof
that no commit happened, so rollback additionally requires **HEAD unchanged**.

**R7 — fault-injection coverage is a first-class deliverable**, not a byproduct of
the composition test: backup-write failure, replace failure, definitive commit
failure with worktree bytes unchanged vs changed, timeout, rename failure, checkout
failure after rename, failed/partial salvage adoption, CRLF and invalid-UTF-8
byte-faithfulness, and an import smoke test over **both** the old re-export paths
and the new module paths (circular-import regression from moving shared helpers).

**R8 — each re-export site carries a one-line comment** naming the extraction reason
and the new home.

### Rejected, with evidence

- *`durable_atomic_write` may not exist* (deepseek, high) — it exists at
  `shared/scripts/lib/atomic_write.py:128`, with the bounded sharing-violation retry
  and parent-dir fsync this fix needs. Read before planning.
- *Release or delete a stale `.git/index.lock` after a failed commit* (deepseek) —
  `run_git_soft` strands a lock only on the **timeout** path, which by design does
  not roll back. Deleting another process's lock is a destructive act on shared
  state; the timeout reason names the possibility and the manual remedy instead.
- *The extracted guards might omit an index-lock check* (deepseek) — the three
  guards being moved (`_op_in_progress`, `_is_detached`, `_has_staged_changes`)
  contain no such check today, so the extraction omits nothing.

## Stage-1 spec review: REJECT, then resolved by building — not by amending

The `spec-reviewer` hard-gate rejected the first cut with five divergences. All five
were real and all five were closed by changing the CODE, so nothing above needed
weakening. Recorded because "the reviewer was satisfied" is worth less than what it
was satisfied about.

1. **AC-2 named three guards; `--commit` shipped two.** `has_staged_changes` was
   omitted with the argument that `git commit -- <path>` cannot sweep up staged WIP
   elsewhere. True, but it left the extraction's own stated rationale false (the
   third guard then had no second caller), and an opt-in maintenance flag is the
   wrong place to start relaxing a precondition on someone else's main tree. Guard
   added.
2. **R2 was contradicted by an added third arm.** The code collapsed anchorless
   same-id appends and merely warned, defended in a module docstring as a departure
   from an accepted revision. The defence assumed anchorless appends are common
   enough that refusing would wedge, while collisions are rare — but both of
   `triage.py`'s append constructors set `originalTs` unconditionally (`:408`,
   `:530`) and 684 of 684 real appends carry one, so the two populations are the
   same size. With no asymmetry to trade on, the data-retention direction wins: the
   arm is gone, R2 is implemented as written. Fallout, and the more useful finding:
   three existing fixtures (`test_churn_merge`, `test_sweep_outbox`'s trg-60ef91fb
   regression, the integration fixture) modelled a "refresh" with anchorless lines,
   which no producer can emit — they were misrepresenting the case they named and
   now carry `originalTs`.
3. **R5's "reports fatally" returned the soft status.** A `git checkout` failure
   whose put-back also fails leaves the tracked log MISSING, and `buffered` promises
   the next sweep completes the restore. It now returns `error`, and `sweep_outbox`
   stops on it instead of reading only `reason`.
4. **R7's fault-injection list was half-built** — backup-write failure, publish
   failure, invalid-UTF-8, failed salvage adoption, and the old/new import smoke
   test were all missing. Added, plus the missing-log case from (3).
5. **R1's named unit pin did not exist** (only the end-to-end proof). Added at
   `sweep_quarantine.decide`, which is the function a refactor would actually break.

Two non-blocking notes were also taken: the integration test's docstring claimed to
compose finding 14 (out of scope — corrected to 23), and the Design table names four
new modules where six shipped, because `triage_gc_core.py` landed at exactly 300 and
the publish half plus the rollback needed their own homes.

## Risk / blast radius

- `cross_component` (`churn_merge`) — integration coverage mandatory, enforced at
  F11 at every complexity.
- Four modules are consumed by the sweep that runs at **every** iterate's worktree
  setup. A regression here breaks every future run's delivery, so the re-exports are
  verified by running the *existing* suites, and by a contracts test asserting each
  old/new name pair is the same object plus a per-module import in an isolated
  subprocess.
- **Existing tests edited, exhaustively** (the earlier draft of this bullet claimed
  only one class of edit and was wrong — corrected after the Stage-1 review):
  1. two `warnings == []` assertions in `test_churn_merge.py` — the contract this
     card exists to reject;
  2. three *fixtures* that modelled a "refresh" with anchorless same-id appends
     (`test_churn_merge.py`'s `_A1`/`_A2`, `test_sweep_outbox.py`'s trg-60ef91fb
     regression, the integration fixture). No writer on this surface can emit those,
     so they were modelling an impossible shape; they now carry `originalTs` and
     their assertions are unchanged;
  3. one monkeypatch TARGET in `test_main_tree_git_timeout_paths.py`, forced by the
     guard extraction — patching the old module would have left real git running and
     read `False`, so the test would have passed while asserting nothing;
  4. one `commit_timeout` exact-equality assertion, now a prefix check plus two
     assertions on the consequence the reason must name.
- Serial to P2.19e by the card's instruction; both touch `reconcile_triage.py`.
