# Iterate — S1: fail-safe fixes to the triage-store primitives

- **Run-ID:** `iterate-2026-07-31-triage-store-failsafe`
- **Intent:** BUG (Path C) — defects in existing behaviour, each with a named root cause
- **Complexity:** medium (locked)
- **Anchor:** `trg-4ebc928e` · **Brief:** `.shipwright/planning/iterate/iterate-2026-07-30-it1-triage-store-BRIEF.md`
- **Board:** `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md` → IT-1 / S1
- **Evidence:** `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`

This is unit **S1 of three** (S1 → PR → green → merge → S2 → … → S3), deliberately
serial: all three touch `triage.py` and the store primitives, so they are not
file-disjoint.

## Spec Impact

**NONE.** Every change is behaviour-preserving *on the success path* and only
changes what happens on a failure path that today loses data or reports a false
success. No FR changes; no `spec.md` is touched.

`change_type: tooling` · affected FRs: none.

## Root causes (each re-measured against the code on 2026-07-31)

The brief's file/line claims were re-verified before any edit. Seven of nine held
exactly; three corrections to the audit file are recorded at the bottom.

| # | Site | Root cause |
|---|---|---|
| 1 | `lib/sweep_text.py:50` | `open(..., encoding="utf-8", newline="")` with **no `errors=`**. An interrupted append truncates mid multi-byte sequence → `UnicodeDecodeError` out of the reader. Sister `lib/jsonl_records.py:159` already uses `errors="surrogateescape"` and documents why. |
| 2 | `lib/triage_header.py:48-52` | `read_text` → `write_text` = truncate-then-write on the **tracked SSoT**, on a *recovery* path, and the only whole-file rewrite that bypasses `durable_atomic_write`. `write_text` also translates `\n` → `os.linesep`, so on Windows it rewrites the whole file as CRLF — a whole-file diff on a `merge=union` artifact. |
| 3 | `lib/sweep_outbox.py:133 → :233` | The outbox is read once at `:133`; `:233` writes the survivor set from that **stale** list. Between them sit the drift adoption's own outbox write, `git add`, `git diff --cached` and a `git commit` budgeted **120 s**. Any append landing in that window is deleted and the sweep reports success. |
| 4 | `lib/jsonl_records.py:91-94` | `except (OSError, ValueError): return False` — `False` means *"safely appendable"*. Fail-**open** on the half of the module whose job is *prevention*. |
| 6 | `lib/reconcile_triage.py:231` | `git commit` on `run_git`'s default `timeout=15.0` with no `TimeoutExpired` handler, although `sweep_outbox.py:205-214` documents 120 s + a handler for the *same* commit. `run_git`'s `proc.kill()` then strands `.git/index.lock` in the **main** tree. |
| 7 | `sweep_outbox.py:189,198` · `sweep_gc.py:32` | Only the `commit` is wrapped against `TimeoutExpired`; `add`, `diff --cached` and `show` run bare at 15 s → the same crash out of `setup_iterate_worktree` step 5. |
| 8 | `artifact_sync.py:110-113` | `text=True` with **no `encoding=`** (cp1252 on Windows), **no returncode check**, **no `timeout=`**. A bad ref or a held index-lock yields empty stdout → `drift_detected: False` → F1 reads a git failure as a clean tree. |

### Why #3 is a defect and not a trade-off

The whole sweep runs under the canonical `triage._FileLock`, so a *cooperating*
producer is safe. The non-cooperating writer is real and documented in this repo:
`triage_repair.py:30-36` records that the WebUI uses `proper-lockfile`, which does
**not** compose with the Python byte lock — and the WebUI is the operator's primary
dismiss surface.

The decisive evidence is internal, not speculative. The sibling
`sweep_drift.commit_main_tracked_drift` **re-reads the outbox inside the same
critical section** (step 1) precisely so a concurrent append survives, with the
comment *"A process lock cannot stop an external `git commit` or an editor"*. So
one half of the critical section carefully preserves such an append and the other
half deletes it ~100 lines later. The two halves disagree; that is the bug.

### Why the existing concurrency test never caught it

`shared/tests/test_sweep_outbox_concurrency.py` is **structurally blind** to it,
in two independent ways:

1. Its `_concurrent_producer` appends via `triage.append_triage_item(...)`, which
   **takes the canonical lock** — so it can only ever serialize *around* the
   sweep, never interleave *inside* it. The test proves the cooperating writer is
   safe, which was never in doubt.
2. Its own comment says *"origin never advanced → nothing GC'd"*, so `gc_dropped`
   is 0 and the offending rewrite (`if gc_dropped or quarantined:`) never fires.

The new test must therefore append **without** the lock (`_sweep_helpers.write_outbox`
does exactly that) **and** advance origin so the rewrite actually runs.

## Acceptance Criteria

- **AC-1** — `sweep_text.read_text_verbatim` decodes with `errors="surrogateescape"`.
  The sibling readers of the same store family are converted with it:
  `sweep_quarantine.append_quarantine`, `reconcile_triage`'s tracked-log read (whose
  `except OSError` cannot catch a `UnicodeDecodeError`, which is a `ValueError`), and
  **`triage_header.has_header`** — which reads one line as BYTES.
  `atomic_write` stays **strict on BOTH sides**; the leniency lives with the two
  modules that need it — `sweep_outbox`, `reconcile_triage`, `sweep_drift` and
  `sweep_quarantine` encode with `surrogateescape` themselves and pass `bytes`.
  *(Two Stage-2 corrections, both to my own first cut. (a) `has_header` was left
  strict one call earlier than the write I fixed, so `ensure_header` still raised —
  reproduced before fixing. (b) I first flipped `durable_read_text`'s DEFAULT to
  lenient "for symmetry" and that was a fail-open regression with **no beneficiary**:
  no triage-store reader goes through it, while all four real callers `json.loads` a
  run-config file where `config_io` catches `JSONDecodeError` and returns `{}` — read
  by its caller as "first run, no config yet". A strict `UnicodeDecodeError` is a
  `ValueError`, NOT a `JSONDecodeError`, so today it escapes and fails loudly, which
  `test_read_gives_up_loudly_rather_than_inventing_an_empty_config` exists to
  guarantee. Reverted to strict; the parameter stays so a triage-side caller can opt
  in when one exists.)*
- **AC-2** — `triage_header.ensure_header`'s prepend path writes via
  `durable_atomic_write` and reads **BYTES**: no truncate-then-write, no newline
  translation, no decode at all. An existing CRLF store stays CRLF.
  `triage._append_line` also moves to `newline=""` for the TRACKED store, matching the
  outbox — without it the benefit lasts exactly one append: the header would inherit LF
  and the next record would be CRLF on Windows, and `reconcile_triage` then rewrites the
  WHOLE log. Doubt review showed that coupling is load-bearing, not tidiness.
  *(Was "reads via `read_text_verbatim`" — corrected after probe #5 showed that
  importing a sibling into this module is an ADR-045 regression. Reading bytes is
  strictly stronger anyway: nothing decoded can be re-encoded differently.)*
- **AC-3** — the GC survivor set is computed from a **re-read** of the outbox taken
  after the commit window. An append made mid-window by a writer that does not hold
  the canonical lock survives the sweep.
- **AC-4** — `ends_without_newline` fails **closed**: missing or empty → `False`
  (safely appendable); any other `OSError`/`ValueError` → `True`. Rationale is an
  asymmetry, not a preference: a wrong `True` costs one blank line, which
  `read_jsonl_records` skips (`if not stripped: continue`); a wrong `False`
  concatenates two records onto one line and the reader loses **both**.
- **AC-5** — `reconcile_triage`'s commit runs with the same 120 s budget and
  `TimeoutExpired` handling as its documented sibling, returning a structured
  `commit_timeout` instead of crashing.
- **AC-6** — every git call reachable from inside the sweep's locked section is
  covered against `TimeoutExpired`, and each site's timeout branch takes the
  **fail-safe** direction for that site, which is NOT always the same as its ordinary
  non-zero branch. Modules: `sweep_outbox`, `sweep_gc`, **`sweep_drift`** (reached via
  `plan_main_tracked_drift` / `commit_main_tracked_drift`, and the one that runs
  `git checkout --` in the **main** tree), plus `reconcile_triage`. Specifically:
  `sweep_gc.delivered_membership` keeps its documented empty-sets direction (drop
  nothing); `_op_in_progress` and `_index_diverged` answer "yes" when they cannot
  tell, so the sweep skips; the `diff --cached` probe must NOT fall through to its
  non-zero branch, which means "there IS a delta, go commit"; and
  `sweep_drift._head_lines` refuses rather than reporting `main_tracked_no_head_blob`,
  a confident diagnosis of a question git never answered.
  In `reconcile_triage` this covers **all seven** calls, not just the commit:
  `_op_in_progress` / `_is_detached` / `_has_staged_changes` answer "skip" when they
  cannot tell, and `_has_drift` / `_head_line_set` return `None` rather than a
  confident `False` / empty set — `git status --porcelain` refreshes the index and
  takes `.git/index.lock`, so a timeout there both strands that lock in the
  operator's own repo and would otherwise report "no drift" from an answer never
  received.
  *(Scope widened twice, both times by review: Stage 1 found five bare calls in
  `sweep_drift` inside the same lock; Stage 2 found six more in `reconcile_triage`,
  two of them inside the lock. Narrowing the AC was the alternative each time and was
  rejected each time — these are exactly the modules where a stranded
  `.git/index.lock` lands in the operator's main tree.)*
- **AC-7a** — a ref that names nothing to compare against (a one-commit or shallow
  repo) is reported as a **no-op, not an error**, so F1 stays `ok`. `HEAD` is probed
  first: if even that fails this is a broken repo, which stays a real error. Without
  this the returncode check turned every greenfield first iterate into an aborted
  finalization bundle (doubt review).
- **AC-7** — `artifact_sync.detect_drift` routes its `git diff` through
  `lib.git_base.run_git` (utf-8, `-C`, `--no-pager`, bounded timeout, kill+reap),
  **checks the returncode**, and reports a git failure as an explicit `error` rather
  than as `drift_detected: False`. F1's consumer (`finalize_bundle._f1_record`)
  reports that as `failed`, not `ok`.
- **AC-8** — `atomic_write` counts sharing-violation retries and exposes the count;
  an unobstructed write records **0**. (`trg-0a294ef3` — counter only, no operator
  warning, per the operator's 2026-07-30 decision.)
- **AC-9** — a triage append made under CI routes to the **tracked** store, not to
  the gitignored outbox. (`trg-6af8dc72`)
- **AC-10** — one shared `ci_active()` helper; the existing copies delegate to it
  instead of a fifth copy being written.

## Mini-Plan

1. New neutral leaf `lib/ci_env.py` (`CI_TRUTHY` + `ci_active()`); the four existing
   copies delegate. Required by AC-9/AC-10 — the brief forbids writing a fifth copy.
2. `atomic_write`: counter + accessors (AC-8).
3. Leaf fixes: `sweep_text`, `jsonl_records`, `triage_header`, `sweep_quarantine`,
   `reconcile_triage` read (AC-1/2/4).
4. Timeout hardening: `reconcile_triage`, `sweep_outbox`, `sweep_gc` (AC-5/6).
5. `sweep_outbox` GC re-read (AC-3) — the one behavioural change with real blast radius.
6. `artifact_sync` + `finalize_bundle._f1_record` (AC-7).
7. `triage.should_route_to_outbox` CI guard (AC-9).

**Alternative considered and rejected for AC-3:** hold a second, sweep-private lock
across the commit window instead of re-reading. Rejected — `triage._lock_path`
documents that the outbox deliberately shares the **one** canonical lock ("do NOT add
a separate outbox lock (Codex Q4 data-loss invariant)"), and a second lock would not
bind the non-cooperating writer either, which is the whole failure mode. Re-reading
costs one file read and matches what the sibling path already does.

**Alternative considered and rejected for AC-7:** fix the three defects inline with a
hardened `subprocess.run`. Rejected — it would duplicate `run_git`'s hygiene a fourth
time, which is exactly the duplication class the audit already flagged (findings 20-29).

## Affected Boundaries

- `.shipwright/triage.jsonl` (tracked SSoT, `merge=union`) — read + write
- `.shipwright/triage.outbox.jsonl` (gitignored buffer) — read + write
- `.shipwright/triage.outbox.quarantine.jsonl` — read + write
- `shipwright_sync_config.json` — read (`artifact_sync`)
- git subprocess boundary — `artifact_sync`, `sweep_gc`, `sweep_outbox`, `reconcile_triage`
- `$CI` environment variable — new read in the triage routing decision
- `artifact_sync` stdout JSON → `finalize_bundle._f1_record` (F1 contract), **and**
  its process **exit code**: a new `2` for "could not determine drift", distinct from
  the existing `1` for "drift found" and `0` for "clean". `_f1_record` reads stdout,
  not the exit code, so this is additive for that consumer; it matters for anyone
  invoking the script directly.
- `lib/git_base` public surface — new `run_git_soft`, `HOOK_GIT_TIMEOUT`,
  `TIMEOUT_RETURNCODE`. Purely additive; `run_git` itself is untouched, so no
  existing caller changes behaviour.

## Confidence Calibration

- **Boundaries touched:** the tracked triage log, the gitignored outbox, the
  quarantine log, `shipwright_sync_config.json`, the git subprocess boundary, `$CI`,
  and the `artifact_sync` → `finalize_bundle` stdout contract (all listed above).

- **Empirical probes run:**
  1. *Does the GC actually lose the append?* Wrote the repro before the fix.
     **Finding: yes, deterministically.** `trg-race` ended in neither the outbox nor
     the branch while the sweep returned `status="committed"`. 100% → 0% after the fix.
  2. *Why did the existing concurrency test not catch it?* **Finding: two independent
     structural blindnesses** — its producer takes the canonical lock (so it can only
     serialize around the sweep), and its own comment records that origin never
     advances, so `gc_dropped` is 0 and the offending rewrite never runs. Both are
     now covered by the new module.
  3. *Is the non-cooperating writer real?* **Finding: yes, documented in-repo** —
     `triage_repair.py:30-36` records the WebUI's `proper-lockfile` not composing
     with the Python byte lock. Corroborating: the sibling
     `sweep_drift.commit_main_tracked_drift` re-reads the outbox in the same critical
     section for exactly this reason, so the two halves contradicted each other.
  4. *Does `surrogateescape` on the reader break the writer?* **Finding: yes it
     would have** — `durable_atomic_write` encoded strictly, so text read through the
     new decode and written back would raise `UnicodeEncodeError`, moving the crash
     one step later. Writer made symmetric; round-trip asserted byte-for-byte.
  5. *Is `triage_header` safe to give sibling imports?* **Finding: NO — my first
     attempt was an ADR-045 regression.** `triage.py` reaches it through
     `shared_lib_loader.load_shared_lib`, whose docstring states the by-file-location
     fallback is *"only safe for lib modules with no intra-package imports"*. Reverted
     to a stdlib-only leaf that reads BYTES, which needs no sibling at all for the
     read and reaches `atomic_write` back through the loader. This class fails green
     locally and red in CI, so it was checked before trusting, not after.
  6. *Which risk flags does the DIFF carry?* (the classifier matches message prose,
     which is not evidence). **Finding:** `is_cross_component_change` → **True**
     (`gitattributes_selfheal.py` is in the pinned pattern list), `is_io_boundary_change`
     → **False**, `touches_build_files` → **False**, `is_ci_supplychain_change` →
     **False**. The message-based `touches_migrations` is a **false positive** — this
     repo has no `supabase/migrations/`, so `down_sql` does not apply.
  7. *Do the new gates actually bite?* Mutation-checked three of them by flipping
     production and re-running: `_f1_record`'s error branch disabled → a git failure
     reports `ok` (the false-clean, reproduced); `ci_active()` pinned False → 4
     integration tests fail; pinned True → the 4 opposite-direction tests fail.
  8. *How many copies of the CI helper are there?* **Finding: four, not the three the
     audit claims** — `gitattributes_selfheal`, `gitignore_selfheal`,
     `reconcile_triage`, `sweep_outbox`.
  9. *Are the new tests order-independent?* Every suite run above used
     `-p no:randomly`, which is exactly how an ordering defect hides. Operator
     flagged a failure; reproduced it, then **instrumented `sys.modules["tools"]`
     rather than guessing**. **Finding: `sys.modules['tools']` was binding to
     `shared/tests/tools/`** — a test package with the same name as
     `shared/scripts/tools/` — because several `shared/tests` modules put their own
     directory ahead of `shared/scripts` on `sys.path`, and `finalize_bundle.py`
     imports its sibling by the BARE name `tools`. Whichever binds first wins for the
     process (ADR-044/045).
     **Second finding, from a control run: the hazard is PRE-EXISTING, not mine.**
     Two untouched files — `test_sweep_outbox_concurrency.py` then
     `test_finalize_bundle_cli.py` — reproduce the identical `ModuleNotFoundError`.
     What this run added was a third import site using a non-established idiom, which
     made a latent collision manifest in the default alphabetical order. Matching the
     established `from tools.finalize_bundle import …` idiom was **measured and
     rejected** — it fails in the reverse order too, i.e. the established idiom is
     itself only lucky. Resolved by moving the two `_f1_record` tests to
     `shared/scripts/tools/tests/`, the root where `tools` has no competitor. Verified
     green in all four orderings that previously failed.

- **Test Completeness Ledger:**

| # | Behavior | Disposition | Evidence |
|---|---|---|---|
| 1 | A store truncated mid multi-byte sequence reads instead of raising | `tested` | `test_triage_store_failsafe.py::test_read_text_verbatim_survives_truncated_multibyte` |
| 2 | The verbatim contract (CRLF, no invented newline) survives the decode change | `tested` | `…::test_read_text_verbatim_preserves_crlf_and_adds_no_newline` |
| 3 | An unreadable file is treated as UNTERMINATED (fail-closed) | `tested` | `…::test_unreadable_file_is_treated_as_unterminated` |
| 4 | Missing/empty stay safely appendable (fail-closed ≠ fail-always) | `tested` | `…::test_missing_and_empty_stay_safely_appendable` |
| 5 | The cost of a wrong `True` is nil — the reader skips the blank line | `tested` | `…::test_blank_line_from_a_defensive_prefix_is_skipped_by_the_reader` |
| 6 | Header prepend preserves the pre-existing bytes and line endings | `tested` | `…::test_ensure_header_prepend_preserves_crlf_bytes` |
| 7 | A failed header prepend leaves the original store intact (atomic) | `tested` | `…::test_ensure_header_prepend_is_atomic` |
| 8 | `ensure_header` stays idempotent | `tested` | `…::test_ensure_header_is_still_idempotent` |
| 9 | **An append during the commit window survives the GC** | `tested` | `test_sweep_outbox_gc_reread.py::test_append_during_commit_window_is_not_deleted_by_the_gc` (verified RED first) |
| 10 | The re-read does not weaken the GC — a delivered line is still dropped | `tested` | `…::test_delivered_line_is_still_gcd_when_an_append_races` |
| 11 | A git failure in `detect_drift` reports an error, not a clean tree | `tested` | `test_triage_delivery_failsafe.py::test_git_failure_reports_error_not_clean` |
| 12 | The error result keeps the published key shape | `tested` | `…::test_error_result_keeps_the_published_shape` |
| 13 | "No sync config" stays a no-op, distinct from a failure | `tested` | `…::test_missing_sync_config_is_not_an_error` |
| 14 | The git diff is routed through `run_git` with `check=False` | `tested` | `…::test_git_diff_is_bounded_and_utf8` (asserts the OUTBOUND call) |
| 15 | F1 reports an errored `artifact_sync` as `failed`, not `ok` | `tested` | `shared/scripts/tools/tests/test_finalize_bundle_f1_record.py::test_f1_record_reports_a_git_failure_as_failed` (mutation-checked) |
| 16 | A genuinely clean F1 run still reports `ok`; real drift still reports `drift`; an empty `error` string does not hijack a clean verdict | `tested` | same module, 3 further tests |
| 17 | A card filed under CI routes to the tracked store | `tested` | `…::test_ci_routes_to_the_tracked_store` + 6 truthy spellings |
| 18 | A falsy `$CI` does not trigger the guard | `tested` | `…::test_non_ci_values_do_not_trigger_the_guard` |
| 19 | All four consumers delegate; no module re-declares `_CI_TRUTHY` | `tested` | `…::test_every_ci_predicate_delegates_to_the_shared_leaf` — drives `$CI` through **four values**, not the ambient one (a module hardcoding `False` passed locally and `True` passed in Actions) |
| 20 | `ci_env` has no intra-package imports (ADR-045) | `tested` | `…::test_shared_leaf_has_no_intra_package_imports` (AST, not grep) |
| 21 | An unobstructed write records ZERO retries | `tested` | `…::test_unobstructed_write_records_zero_retries` |
| 22 | The counter increments once per retry actually performed | `tested` | `…::test_counter_increments_when_a_retry_actually_happens` |
| 23 | Surrogate-escaped text round-trips reader → writer byte-for-byte | `tested` | `…::test_surrogate_text_round_trips_through_the_writer` |
| 24 | **The CI guard composes across all four consumers on real git** | `tested` · **`category: integration`** | `test_ci_predicate_composition_integration.py` (7 tests, mutation-checked BOTH directions) |
| 25 | `run_git_soft` turns a timeout into a failed process rather than an exception | `tested` | `test_store_git_timeout_paths.py::test_run_git_soft_reports_a_timeout_as_a_failed_process` |
| 26 | …and passes an ordinary outcome through untouched | `tested` | `…::test_run_git_soft_passes_a_normal_result_through` |
| 27 | `_op_in_progress` answers "yes" when it cannot tell — in **both** loops | `tested` | `…::test_op_in_progress_says_yes_when_it_cannot_tell` (pseudo-refs) **+** `…::test_op_in_progress_says_yes_when_only_the_gitpath_probe_times_out` and its `reconcile` twin, which time out ONLY the `--git-path` probes. Mutation-checked: removing the second-loop guard turns both red while the original test stays green — it patched every call, so the first loop short-circuited and the second never ran |
| 28 | The sweep SKIPS rather than raising out of setup step 5 | `tested` | `…::test_sweep_skips_when_the_guard_times_out` |
| 29 | A `diff --cached` timeout is not read as "there is a staged delta" | `tested` | `…::test_staged_probe_timeout_does_not_read_as_a_staged_delta` |
| 30 | A commit timeout is reported as `commit_timeout` | `tested` | `…::test_commit_timeout_is_reported_structurally` |
| 31 | `delivered_membership` GCs nothing on timeout (its documented safe answer) | `tested` | `…::test_delivered_membership_gcs_nothing_on_timeout` |
| 32 | `reconcile_triage` returns `commit_timeout` instead of crashing (**AC-5**) | `tested` | `…::test_reconcile_commit_timeout_returns_a_structured_error` |
| 33 | `reconcile_triage` returns a structured `read_failed` on a decode-class `ValueError` | `tested` | `…::test_reconcile_read_failure_is_structured_not_raised` (creates real drift first, else it short-circuits on `no_drift` and proves nothing) |
| 34 | `sweep_drift` refuses instead of claiming `main_tracked_no_head_blob` | `tested` | `…::test_unreadable_head_refuses_instead_of_claiming_no_blob` |
| 35 | `_index_diverged` stays fail-closed under timeout | `tested` | `…::test_index_probe_timeout_refuses` |
| 36 | Two failed HEAD reads never license the restore that destroys the operator's drift | `tested` | `…::test_two_failed_head_reads_do_not_read_as_unchanged` — asserts the drift LINE survives on disk, and **mutation-checked**: reverting to the pre-fix two-clause condition returns `adopted`, i.e. `git checkout --` ran and wiped it |
| 37 | `append_quarantine` round-trips an UNDECODABLE line through the quarantine log | `tested` | `test_triage_store_failsafe.py::test_quarantine_round_trips_an_undecodable_line` — the cited existing suite had no surrogate case, so the new encode was executed by nothing |
| 38 | `artifact_sync` exits **2** when it could not determine drift | `tested` | `test_triage_delivery_failsafe.py::test_main_exits_2_when_it_could_not_determine_drift` — asserts `SystemExit.code` directly |
| 39 | …and still exits **0** clean / **1** on real drift, so the three states stay distinct | `tested` | `…::test_main_still_exits_0_on_a_clean_run`, `…::test_main_exits_1_on_real_drift` |
| 40 | The `_f1_record` tests are immune to test-collection ORDER | `tested` | Placed in `shared/scripts/tools/tests/`, where no competing `tools` package exists. Verified in four orderings that previously failed. |
| 41 | **`has_header` answers instead of raising on a truncated-multibyte store** | `tested` | `test_triage_store_failsafe.py::test_ensure_header_survives_a_truncated_multibyte_store` — reproduced RAISING first (`UnicodeDecodeError` out of `ensure_header`), then fixed |
| 42 | The header line takes the file's OWN EOL, so line 1 is not a permanent diff | `tested` | `…::test_ensure_header_takes_the_files_own_eol` + `…::test_ensure_header_creates_a_new_store_with_lf` (both directions) |
| 43 | `atomic_write` stays strict on BOTH sides; a surrogate `str` is REFUSED | `tested` | `test_triage_delivery_failsafe.py::test_the_primitive_still_refuses_a_surrogate_str` + `…::test_the_triage_callers_carry_the_leniency_themselves` (both directions) + the existing `test_read_gives_up_loudly_rather_than_inventing_an_empty_config` |
| 44 | `reconcile_triage`'s guards answer "skip"/error when git cannot be asked | `tested` | `test_main_tree_git_timeout_paths.py::test_has_drift_timeout_is_an_error_not_no_drift` and `…::test_head_line_set_timeout_is_an_error_not_an_empty_head` — the tri-state is now DRIVEN, not inferred from a sibling's reason string |
| 45 | `artifact_sync`'s `run_git` is imported lazily (ADR-045) and stays patchable | `tested` | `…::test_git_diff_is_routed_through_run_git_with_check_false` patches the module-level seam, which only exists because the import is behind an indirection |
| 46 | A non-Latin-1 path in the diff decodes rather than reading as a failed fetch | `tested` | `test_artifact_sync_drift_failsafe.py::test_git_diff_decodes_a_non_latin1_path_for_real` — REAL git, no stub, `core.quotepath=false` |
| 47 | `has_header` is TOTAL: a bare JSON scalar on line 1 answers, never raises | `tested` | `test_triage_store_failsafe.py::test_bare_json_scalar_first_line_answers_rather_than_raising` |
| 48 | A newly created store's header matches what appends the NEXT line | `tested` | `…::test_ensure_header_creates_a_new_store_matching_the_appender` (asserts against `os.linesep`, not a hardcoded byte) |
| 49 | An `ImportError` from the lazy `run_git` reaches the structured result | `tested` | `test_artifact_sync_drift_failsafe.py::test_import_error_from_the_lazy_seam_reaches_the_structured_result` — raises `ModuleNotFoundError` from the seam, which the cited test never did |
| 50 | A one-commit / shallow repo is a NO-OP, not a finalization abort | `tested` | `…::test_a_one_commit_repo_is_a_no_op_not_a_finalization_abort` (real one-commit repo) |
| 51 | …and a genuine git failure is STILL an error | `tested` | `…::test_a_real_git_failure_is_still_an_error` — the escape hatch must not swallow the false-clean AC-7 exists to close |
| 52 | A killed `git checkout` reports that the log may be PARTIALLY restored | `tested` | `sweep_drift` returns `main_tracked_restore_timeout`; the old message promised a recovery the next plan cannot perform (`main_tracked_diverged` forever) |
| 53 | The unresolvable-ref probe's OWN git calls are inside the structured handler | `tested` | Covered by `test_a_real_git_failure_is_still_an_error` + the handler now spanning both calls. Doubt round 2 found I had reintroduced the unguarded-call hole one statement after widening it for `ImportError` |
| 54 | A SHALLOW checkout is named as shallow, not conflated with one-commit | `tested` | `_nothing_to_compare_against` returns `"shallow"`/`"history"`; the message tells the operator the drift check did not run and that `fetch-depth: 0` enables it — different states, different remedies |
| 55 | An all-CRLF store survives an LF append and still folds | `tested` | `test_main_tree_git_timeout_paths.py::test_an_all_crlf_store_survives_an_lf_append_and_folds` — this repo's live store is **1145/1145 CRLF** and `_append_line` now writes LF; the transition had no test |
| 56 | **The CI routing test actually exercises the guard** | `tested` | `test_triage_delivery_failsafe.py` — a REAL repo with an `origin` on the default branch, plus a control asserting routing IS `True` without CI. The previous version used a plain `tmp_path`, where `should_route_to_outbox` already returns `False` via the no-origin path, so it passed with OR without the guard (measured) |
| 57 | An UNKNOWN ref stays a loud error, not a no-op | `tested` | `test_artifact_sync_drift_failsafe.py::test_an_unknown_ref_is_an_error_not_missing_history` — a real two-commit repo + a bad name, the case the HEAD-first guard does NOT catch |
| 58 | …and a repo with enough history still compares normally | `tested` | `…::test_enough_history_still_compares_normally` (asserts `drift_detected is True`, so the escape hatch cannot swallow a real comparison) |

  **0 testable-but-untested.** 58 behaviors against 11 ACs.

  *Rows 41-46 come from Stage-2 review. The sharpest, row 41, is the one worth
  recording: the first cut fixed `ensure_header`'s WRITE and left `has_header`'s
  strict `read_text` one call earlier, so the crash simply moved — and a comment in
  the same diff asserted the class had been removed from that module. My own change
  made it MORE reachable, because the now-lenient writer can persist a byte the strict
  reader refuses. Confirmed by running it before fixing it.*



  *Rows 36 and 38 were marked `tested` in an earlier draft on evidence that did not
  reach the behaviour — row 36's test passed green against the unfixed guard. Stage-1
  review caught both. Same class as rows 25/26, so the same standard applied: each is
  now pinned by a test proven to fail without the fix.*

  *Rows 25-36 replace two rows that an earlier draft dispositioned
  `covered-by-existing-test`. Stage-1 review was right to reject that: nothing
  pre-existing pinned them, and three of the branches are the OPPOSITE of the
  ordinary non-zero branch they claimed to inherit coverage from. They were
  "could-test-but-didn't", which is abolished — a `subprocess.TimeoutExpired` is a
  plain exception and needs no hung subprocess to raise.*

- **Confidence-pattern check:**
  - *Asymptote (depth):* the deepest defect (#3) was driven to a deterministic repro
    and back — 100% loss before, 0% after — rather than to a "looks right" reading.
    Three further gates were mutation-checked by flipping production code, because
    this repo has shipped a green suite over a reverted fix before.
  - *Coverage (breadth):* the briefed site list was treated as a starting point, not
    the scope. Sweeping the class found **three** readers in the triage-store family
    (brief named one), **four** CI-helper copies (audit named three), and — only after
    Stage-1 review pushed back — **five further bare git calls in `sweep_drift`**
    executing inside the same lock, which my first pass missed because I swept the
    modules the brief named rather than the calls the lock actually spans. The
    adjacent `record_event.py:505` / `validate_event_log.py:40` readers are the same
    idiom on a *different* store (`shipwright_events.jsonl`) and were deliberately NOT
    swept — named here so the decision is visible rather than silently omitted.
  - *Integration composition:* `cross_component` is True (recomputed from the diff, not
    self-reported), and behavior #24 is the real-scenario test proving the four
    de-duplicated consumers still compose, asserted on whether a real git COMMIT was
    created rather than on a returned status word.
  - *Known limits, stated rather than discovered later.* (a) The GC re-read now
    PRESERVES torn lines the sweep never read, where the old code silently deleted
    them — so the next sweep's validator blocks loudly (`status="invalid"`) instead of
    losing data. That is the direction this whole change argues for, but it is a
    behaviour change and is named here, not buried. (b) `_head_lines` distinguishes a
    timeout from a benign "no such blob", but NOT from a real git failure — both exit
    128, and telling them apart means parsing stderr, which is locale-dependent. That
    ambiguity is pre-existing and untouched. (c) A racing duplicate of a `plan.fresh`
    line can now survive to the outbox where the old in-memory write collapsed it;
    `dedup_triage_lines` absorbs it downstream.
  - *A pattern in my own ledger, named because it recurred.* **Eleven** rows across
    this run were marked `tested`/`covered` on evidence that did not execute the
    behaviour claimed: rows 25/26 (`covered-by-existing-test` for branches nothing pinned), row
    36 (a test green against the unfixed guard), row 38 (an exit code inherited from a
    consumer that ignores exit codes), and the first `utf-8` test (which stubbed out
    the very statement that does the decoding, and would additionally have been
    vacuous under git's default `core.quotepath`). Every one was caught by review, not
    by me, and each shares one shape: **I cited the test I had written for the
    neighbourhood rather than checking which line it executes.** Rounds 3-4 found six
    more of the same (rows 19, 27, 37, 43, 44, 49) — including one that was a
    tautology against the implementation and would have gone RED once the code became
    correct. The rule that falls out — and the reason this is recorded rather than
    quietly fixed — is mechanical: **name the line of production code the test must
    execute, and confirm the test does not stub or bypass it.** That single check
    catches all eleven. Every load-bearing row on this run has now been shown red
    without its fix.
    The eleventh is worth naming separately because it shows the internal cascade is
    not sufficient on its own: **GPT found it after all three internal stages had
    passed.** The AC-9 routing tests ran against a plain `tmp_path`, where
    `should_route_to_outbox` already returns `False` through its pre-existing
    no-origin path — so every one of them passed with OR without the guard they
    existed to pin. Measured before fixing: `False` both with `$CI` set and unset.

## Corrections to the evidence files

Recorded here because the audit file is the anchor's `evidencePath` and these
claims would otherwise be inherited by S2/S3.

| Claim | Measured 2026-07-31 |
|---|---|
| audit: `tools/triage_gc.py` = 301, over the 300 limit | **300** — exactly on it, no crossing. Not touched by S1. |
| audit: `lib/worktree_isolation.py` = 371 vs baseline 370 | **370** — matches the baseline exactly. |
| brief/audit finding 29: the CI helper exists in **three** copies | **four** — `gitattributes_selfheal.py`, `gitignore_selfheal.py`, `reconcile_triage.py`, `sweep_outbox.py`. |
| brief: `artifact_sync.py` under `shared/scripts/tools/` | it is `shared/scripts/artifact_sync.py`. |

**Correction to the brief's plan for `trg-0a294ef3`.** The brief names
`plugins/shipwright-run/tests/test_runconfig_concurrency.py` as the counter's
consumer via `assert retries == 0`. That assertion is **not soundly assertable
there**, for two measured reasons: (a) the test drives three writer families in
separate **OS processes**, and a module-level counter is per-process, so the parent
cannot observe the workers' counts at all; and (b) `atomic_write`'s own docstring
(lines 33-39) records a *deliberate, still-live* unlocked reader in exactly that path
(`step_planning._read_standalone_flag`, run on every `update_step`), so retries > 0 is
expected-and-accepted there — `== 0` would be red by design or flaky. The counter is
therefore given **deterministic in-process consumers** instead, which pin the same
property the brief wanted (an unobstructed write retries zero times, so a newly
introduced handle held across a write turns a test red) without asserting something
the code says is false. Recorded rather than silently dropped.

## Bloat

No gate blocks S1. Of the touched files only `shared/scripts/triage.py` is baselined
(696, `state: exception`, ADR-100); the anti-ratchet rule is `measured > current` →
block, so the CI guard must land without growing it past 696, or `current` is bumped
deliberately in the same commit under the existing ADR-100 exception. Every other
touched file is far below 300. `triage_gc.py` sits exactly on 300 and is **not**
touched, deliberately — audit finding 9 lives there.
