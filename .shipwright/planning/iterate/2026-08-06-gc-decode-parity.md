# Iterate Spec: gc-decode-parity

- **Run ID:** iterate-2026-08-06-gc-decode-parity
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal

Make the two sides of every triage-log comparison decode identically. Today a
git blob is read through `lib.git_base.run_git` (`errors="replace"`) while the
working file is read through `lib.sweep_text.read_text_verbatim`
(`errors="surrogateescape"`), so one non-UTF-8 byte yields two different strings
for the same bytes and the comparison can never match again.

## Acceptance Criteria

- [ ] **AC-1** — `run_git_bytes_soft(["show", "HEAD:<path>"])` returns the blob's
      bytes verbatim: for a tracked file whose committed content is
      `b'{"a":"caf\xff"}\n'`, `proc.stdout == b'{"a":"caf\xff"}\n'` and
      `proc.returncode == 0`.
- [ ] **AC-2** — Decode parity at the store boundary: for that same tracked file,
      `decode_store_text(run_git_bytes_soft(...).stdout) == read_text_verbatim(path)`,
      and the shared codepoint is `U+DCFF` on both sides (not `U+FFFD` on one).
- [ ] **AC-3** — GC delivers the reported case: with a **status** line carrying a
      raw `0xFF` byte present in both `origin/main`'s tracked log and the
      gitignored outbox, `sweep_outbox_to_branch(...)` reports `gc_dropped >= 1`
      and that line is absent from the outbox file afterwards.
- [ ] **AC-4** — Drift plan stops false-refusing: with a tracked log whose sole
      committed line carries a raw `0xFF` byte and a working tree byte-identical
      to `HEAD`, `plan_main_tracked_drift(...)` returns `status == "no_drift"`
      (today: `refused` / `main_tracked_diverged`).
- [ ] **AC-5** — Fold count is honest: `reconcile_main_triage(...)` on a tracked
      log whose committed line carries a raw `0xFF` byte plus one genuinely-new
      appended line reports `folded == 1` (today: `2`).
- [ ] **AC-6** — The timeout contract survives the new path: a
      `subprocess.TimeoutExpired` out of `run_git_bytes_soft` is reported as
      `returncode == TIMEOUT_RETURNCODE` with `stdout == b""` and never raises.
- [ ] **AC-7** — No regression for the 133 existing `run_git` callers:
      `run_git` / `run_git_soft` keep returning `CompletedProcess[str]` with
      `errors="replace"` semantics (a `0xFF` byte still arrives as `U+FFFD`).

## Spec Impact

- **Classification:** none
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): none
- **REMOVE** (FR retired): none
- **NONE justification:** FR-01.14 (Triage Inbox) already promises that each
  finding is "recorded once, and each one taken into work, deferred or
  dismissed". This iterate restores that promised behaviour for logs containing a
  non-UTF-8 byte; it changes no requirement, adds no capability, and retires
  none. Affected FR: FR-01.14 (behaviour restored, requirement text untouched).

## Out of Scope

- Changing `run_git`'s own decode for its ~133 call sites. Disproportionate, and
  it would leak lone surrogates into consumers that encode (JSON writes,
  subprocess args) far from this boundary.
- Repairing triage logs that *already* contain a broken byte. This iterate stops
  the comparison from mis-firing; it does not rewrite history.
- The unlanded `canonical_form` membership rule (see Design Notes) — this fix
  sits underneath it and is deliberately independent of it.

## Design Notes

n/a — no UI surface.

### Alternatives considered

1. **Switch `run_git` to `errors="surrogateescape"` globally.** Rejected:
   133 call sites, and lone surrogates would escape into code that encodes.
2. **Normalise both sides to a lossy common form** (map surrogates to `U+FFFD`
   before comparing). **Rejected, and this rejection is the load-bearing one:**
   `replace` is non-injective — two *different* broken lines both collapse to
   `…�…`. A buffer line could then match a *different* origin line and be
   GC'd. That converts today's "line stays forever, no data loss" into "line
   silently deleted", which is strictly worse than the bug.
3. **Read the blob as raw bytes and decode it with the store's own error
   handler.** Chosen. Exact, injective, round-trips. Both sides then produce
   identical strings for identical bytes, so *any* comparison rule layered on
   top — id, raw text, or the unlanded canonical form — inherits parity for free.
   The timeout handling stays shared, so the audit-1/audit-7 fix in
   `setup_iterate_worktree` step 5 is not regressed.

### Note on the reported premise — and how it changed mid-run

At the start of this run the card's premise was false: `canonical_form` had
**never been committed to any branch** (`git log --all -S canonical_form` empty),
existing only as uncommitted working-tree state in
`.worktrees/it1-audit-remainder`.

**It landed while this run was in progress.** Stage-3 doubt review caught it.
`origin/main` moved from this branch's base `83d15989` to `5bad6c31` — three PRs
(#578 GC by record not by id, #579 corruption vs absence, #581 proportional
disposition) that rewrote the very functions this iterate changes. The branch was
**rebased onto `5bad6c31`** and the `sweep_gc.py` conflict resolved to keep
*both* rules; every gate was then re-run against the merged tree, because a green
F0 on a stale base proves nothing.

Two consequences worth recording:

- **The premise is now true, and the fix matters *more* under it.** An id is pure
  ASCII, so the old rule left only status/unparseable lines stranded.
  Canonicalizing runs over the whole record, so every line carrying an invalid
  byte is affected. Landed `sweep_gc.py` even carried an explicit *KNOWN
  LIMITATION* comment deferring this exact bug to card **`trg-94d3cb73`**
  (P2.19f) — this iterate removes the comment and closes the card.
- **The naive conflict resolution was a live hazard.** Taking this branch's
  `sweep_gc.py` wholesale would have deleted `partition_outbox`, which
  `sweep_outbox.py:52` imports — an `ImportError` inside
  `setup_iterate_worktree` step 5, i.e. the orphaned-worktree failure the module's
  timeout design exists to prevent. Verified resolved: the only `is_delivered`
  call is `partition_outbox`'s keyword-only one.

The bug was real on `main` before those PRs too, by two paths the card does not
name, both reproduced before any fix:

| Site | Symptom on `main` today |
|---|---|
| `sweep_gc.delivered_membership` | status / unparseable lines use text membership → never GC'd (the reported class, reached without `canonical_form`) |
| `sweep_drift._head_lines` | a byte-identical working log reads as `main_tracked_diverged` → **the whole sweep returns `skipped`**; no outbox delivery at all |
| `reconcile_triage._head_line_set` | `folded` count inflated → wrong number in the `chore(triage)` commit subject |

Fixing the decode rather than the comparison is what makes this forward-compatible
with the canonical-form change when it lands.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `sweep_outbox.sweep_outbox_to_branch` (`.encode('utf-8', 'surrogateescape')`) | `sweep_text.read_text_verbatim` (`errors='surrogateescape'`) | JSONL bytes on disk |
| `git` object store (blob written from the above) | `sweep_gc.delivered_membership` via `run_git_bytes_soft` + `decode_store_text` | JSONL bytes out of `git show` |
| `git` object store | `sweep_drift._head_lines` via `run_git_bytes_soft` + `decode_store_text` | JSONL bytes out of `git show` |
| `git` object store | `reconcile_triage._head_line_set` via `run_git_bytes_soft` + `decode_store_text` | JSONL bytes out of `git show` |
| `reconcile_triage._atomic_write` (`.encode('utf-8', 'surrogateescape')`) | `sweep_text.read_text_verbatim` — this module's own hand-rolled `open(errors='surrogateescape')` was a second copy of the rule and is now gone | JSONL bytes on disk |

## Confidence Calibration

- **Boundaries touched:** the five producer/consumer pairs above — every one of
  them a bytes→str→bytes round trip over the triage JSONL store.

- **Empirical probes run:**
  1. *Pre-fix repro, GC path* — seeded a real git repo with a committed status
     line carrying a raw `0xFF`; the blob decoded to `U+FFFD`, the file read to
     `U+DCFF`, and `is_delivered` returned `False`. **The reported bug is real on
     `main` today, without the `canonical_form` rule the card blames.**
  2. *Pre-fix repro, drift path* — a working log **byte-identical to `HEAD`**
     (asserted on raw bytes) produced `refused: main_tracked_diverged`, which
     makes `sweep_outbox_to_branch` return `skipped`. Second, worse site found.
  3. *Genuine RED* — after landing the primitive but **before** rewiring the call
     sites, the new suites failed 4/22 on real logic (GC not dropping, drift
     refusing twice, `folded=2`), not on a missing symbol.
  4. *Round-trip probe (`touches_io_boundary`)* — drove the full trip (disk →
     blob → decode → compare → survivor re-encode → disk) through the real sweep;
     the survivor's `0xFF` bytes are identical afterwards.
  5. *Anti-promiscuity probe* — a broken line that is **not** in origin, differing
     from a delivered one only in the `0xFF`'s **position**, still survives the GC.
     This is the probe that would fail if parity had been bought with a lossy
     comparison, which is the failure mode that would cause data loss.
  6. *No-regression probe* — 91 existing sweep/drift/reconcile/quarantine tests
     green, so the ordinary valid-UTF-8 path is unchanged.
  7. *Blast-radius probe* — repo-wide sweep for other `git show`-vs-file
     comparisons and for tests pinned to the moved seam. **Found 3 fail-safe tests
     still patching `run_git_soft`**, which is what probe 6 alone would have
     missed; all three re-pinned to `run_git_bytes_soft` and green.
  8. *Lint* — `uvx ruff@0.15.15 check .` clean.
  9. *Injectivity probe (isolated)* — built a pair that COLLIDES under `replace`
     but stays distinct under `surrogateescape`, then ran real membership over it:
     shipped rule drops 1 (the delivered line, `other` survives); lossy rule drops
     **2** — deleting an undelivered operator finding. Re-run after the rebase
     against the landed canonical-form rule: identical result. This is what proves
     parity did not become promiscuous, and it is the probe the *original* test
     pair could not have failed (Stage-2 finding).
  10. *Moved-base re-verification* — after rebasing onto `5bad6c31`, all of the
      above were re-run against the merged tree: 196 tests green under `CI=true`,
      ruff clean, `verify_local.py` 3/3 including the end-to-end sweep-delivery gate.

- **Test Completeness Ledger:** 7 ACs, 28 behaviors enumerated, 0 untested-testable.

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `run_git_bytes_soft` returns the blob byte-for-byte | tested | `test_git_base_bytes::test_blob_comes_back_byte_for_byte` PASSED |
  | 2 | its `stderr` is bytes, never mixed with str | tested | `test_git_base_bytes::test_stderr_is_bytes_too` PASSED |
  | 3 | a missing blob reports instead of raising | tested | `test_git_base_bytes::test_a_missing_blob_reports_rather_than_raises` PASSED |
  | 4 | timeout → `TIMEOUT_RETURNCODE` + `b""`, partial output discarded | tested | `test_git_base_bytes::test_timeout_is_reported_not_raised` PASSED |
  | 5 | `run_git_soft`'s own timeout mapping is unchanged | tested | `test_git_base_bytes::test_text_soft_timeout_mapping_is_unchanged` PASSED |
  | 6 | `run_git` text mode still yields `U+FFFD`, not a surrogate | tested | `test_git_base_bytes::test_text_mode_still_replaces_the_broken_byte` PASSED |
  | 7 | `run_git` text `stderr` still decodes to `str` | tested | `test_git_base_bytes::test_text_mode_stderr_decodes_to_str` PASSED |
  | 8 | `check=True` still raises `GitError` | tested | `test_git_base_bytes::test_check_true_still_raises_giterror` PASSED |
  | 9 | `check=False` still reports the exit code | tested | `test_git_base_bytes::test_check_false_reports_the_exit_code` PASSED |
  | 10 | blob and file decode to the SAME string for a `0xFF` byte | tested | `test_store_decode_parity::test_git_blob_and_file_read_agree_on_a_broken_byte` PASSED |
  | 11 | ordinary UTF-8 reads are unchanged | tested | `TestDecodeStoreText::test_plain_utf8_is_unaffected` PASSED |
  | 12 | LF **and** CRLF survive verbatim (no translation) | tested | `TestDecodeStoreText::test_line_endings_survive_verbatim[both params]` PASSED |
  | 13 | surrogateescape round-trips to the original bytes | tested | `TestDecodeStoreText::test_surrogateescape_round_trips_to_the_original_bytes` PASSED |
  | 14 | a BOM is preserved, not stripped | tested | `TestDecodeStoreText::test_a_bom_is_preserved_not_stripped` PASSED |
  | 15 | a missing file still reads as `""` | tested | `TestDecodeStoreText::test_missing_file_is_empty_string` PASSED |
  | 16 | a delivered broken **status** line is GC'd from the outbox | tested | `test_sweep_store_decode_parity::TestGcDeliversABrokenLine::test_a_delivered_status_line_with_a_broken_byte_is_gc_d` PASSED (`CI=true`) |
  | 17 | an **undelivered** broken line still survives the GC | tested | `test_sweep_store_decode_parity::TestGcDeliversABrokenLine::test_an_undelivered_line_still_survives` PASSED (`CI=true`); now also asserts the sweep RAN, so it cannot pass vacuously |
  | 18 | full round trip preserves the survivor's bytes exactly | tested | `test_sweep_store_decode_parity::TestBoundaryProbeRoundTrip::test_a_surviving_broken_line_is_byte_identical_after_the_sweep` PASSED (`CI=true`) |
  | 19 | an unchanged log with a broken byte is **not** `diverged` | tested | `test_sweep_store_decode_parity::TestDriftPlanStopsFalseRefusing::test_an_unchanged_log_with_a_broken_byte_is_not_diverged` PASSED (`CI=true`) |
  | 20 | genuine drift is still detected over a broken HEAD line | tested | `test_sweep_store_decode_parity::TestDriftPlanStopsFalseRefusing::test_real_drift_is_still_detected_over_a_broken_head` PASSED (`CI=true`) |
  | 21 | `reconcile` counts a committed broken line as already-folded | tested | `test_sweep_store_decode_parity::TestReconcileFoldCount::test_a_broken_head_line_is_not_counted_as_newly_folded` PASSED (`CI=true`) |
  | 22 | GC timeout fail-safe holds on the new seam | tested | `test_store_git_timeout_paths::test_delivered_membership_gcs_nothing_on_timeout` PASSED |
  | 23 | drift `head_unreadable` refusal holds on the new seam | tested | `test_main_tree_git_timeout_paths::test_unreadable_head_refuses_instead_of_claiming_no_blob` PASSED |
  | 24 | `_head_line_set` timeout → `None` holds on the new seam | tested | `test_main_tree_git_timeout_paths::test_head_line_set_timeout_is_an_error_not_an_empty_head` PASSED |
  | 25 | the sweep composes end-to-end over real git (integration) | tested | `category:"integration"` — `TestBoundaryProbeRoundTrip` + `TestGcDeliversABrokenLine` drive `sweep_outbox_to_branch` over a real repo/worktree/origin |
  | 27 | adopting drift over a broken HEAD moves it without loss | tested | `test_sweep_store_decode_parity::TestDriftPlanStopsFalseRefusing::test_adopting_drift_over_a_broken_head_moves_it_without_loss` PASSED (`CI=true`) — added at Stage-3 doubt review: the fix newly UNBLOCKS a `git checkout --` against main's tracked log, and that was the one irreversible path no test drove. Asserts the drift reached the branch/buffer, main's log matches HEAD line-wise (byte-wise would false-fail under `core.autocrlf`), the invalid byte survived, and the drift was **moved, not copied** |
  | 28 | the fix composes with the newly-landed canonical-form rule | tested | `category:"integration"` — `test_sweep_gc_canonical.py` (18 cases, main's own) green against this branch, plus an isolation probe showing `partition_outbox` drops 1 (delivered only) under the shipped rule and 2 (**deleting an undelivered finding**) under a lossy one |
  | 26 | `reconcile`'s working-file read now uses the shared rule | untestable | `covered-by-existing-test` — `test_reconcile_triage*` (17 cases) exercise this read on every path. The **decode** is byte-equivalent; the **absence** case is not, and the difference is benign: the old inline `open()` raised `FileNotFoundError` → `error: read_failed`, while `read_text_verbatim` returns `""` → `invalid`. Only reachable if the log is deleted between the `exists()` guard and the read; traced to a safe end (empty text fails validation and returns *before* the commit, so the deletion still cannot be auto-committed). `test_main_tree_git_timeout_paths` still pins the injected-`ValueError` → `read_failed` path, because `Path.read_bytes` is implemented via `Path.open` |

- **Confidence-pattern check:**
  - **Asymptote (depth):** YES, the pattern fired this run. After the 22 new tests
    went green I would have said the change was complete — and probe 7 then found
    3 existing fail-safe tests still pinned to the seam I had moved. So one more
    probe was run rather than stopping: a repo-wide enumeration of every
    `git show` blob read and every `setattr(..., "run_git_soft")`. That returned
    the three already fixed plus no further instances, and `run_written_ledger.py`
    was found to already read its blob as bytes. Depth is now flat.
  - **Coverage (breadth):** 28 behaviors, 27 `tested` + 1 `covered-by-existing-test`,
    **0 untested-testable**. Enumeration (28) exceeds the AC count (7).
  - **Known uncovered line pair, stated rather than hidden:** `_popen_git`'s
    `proc.kill(); proc.communicate()` reap is executed by no test, in either mode —
    every timeout test stubs the function containing it. This is a **pre-existing**
    gap (coverage was equally zero before), but the diff MOVES those lines, so they
    are changed lines. Not closed here because a deterministic cross-platform
    slow-git test is flaky by construction; the behaviour it guards (no stranded
    `.git/index.lock`) is unchanged and shared by both wrappers.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --extra dev python -m pytest shared/tests/test_store_decode_parity.py shared/tests/test_sweep_store_decode_parity.py shared/tests/test_git_base_bytes.py shared/tests/test_sweep_outbox.py shared/tests/test_sweep_outbox_gc_reread.py shared/tests/test_sweep_drift.py shared/tests/test_reconcile_triage.py shared/tests/test_main_tree_git_timeout_paths.py shared/tests/test_store_git_timeout_paths.py -v`
  (widened per external plan review finding 3 — the existing callers whose
  behaviour must be unchanged are driven alongside the new parity tests; the two
  timeout modules are included because Stage-1 review showed their fail-safes had
  been silently unpinned by the seam move)
- **Evidence path:** `.shipwright/planning/iterate/iterate-2026-08-06-gc-decode-parity/surface-verification.txt`
- **Justification (only if surface=none):** n/a — the sweep is driven end-to-end
  through its real entry point over a real git repo.
