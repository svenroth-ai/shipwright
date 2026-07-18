# Iterate: Outbox newline corruption — silent record loss on an append-only log

- **Run ID:** iterate-2026-07-18-outbox-newline-corruption
- **Date:** 2026-07-18
- **Type:** bug
- **Complexity:** medium (`prior_source: history`, n=20)
- **Spec Impact:** MODIFY
- **Risk flags:** `touches_io_boundary` (JSONL producer/consumer boundary)

## Problem

A record in the triage outbox was written without a trailing newline, so the next
writer appended onto the same physical line. The reader fails to parse that line
and skips it with a warning, discarding **both** records on it.

Observed: one line held an `append` followed by a `status` record written by the
WebUI. The status marked an item `dismissed` with the note that it had been
implemented. That dismissal never propagated — the item still reads as open in the
main log while the person who closed it believes it is done.

This is the same failure family as the earlier orphaned-status incident
(`.shipwright/triage.outbox.quarantine.jsonl` holds three `orphan-status`
records from 2026-07-01/02).

## Root cause

The "every record is newline-terminated" invariant is a **convention each writer
holds independently, with no enforcement at the append boundary**:

- `shared/scripts/triage.py:322` `_append_line` opens the target in `"a"` mode and
  writes its own `"\n"`-terminated line, but **never verifies the file it is
  appending to is itself terminated**.
- `shared/scripts/lib/atomic_write.py:37-39` `durable_atomic_write` documents that
  it writes "verbatim — no newline translation, **no invented trailing newline**",
  explicitly delegating termination to every caller.

So any unterminated predecessor — an interrupted/partial write, an external writer,
an operator edit, or a future caller that forgets — silently concatenates the next
record onto the previous physical line.

The reader then converts that corruption into **absence**:
`shared/scripts/triage.py:267-278` `_iter_raw_lines_at` catches `JSONDecodeError`,
emits `warnings.warn(...)` (stderr, easily missed, swallowed by warning filters)
and **drops the line entirely** — losing both records. On an append-only log whose
whole contract is "nothing is ever lost", corruption must never read as absence.

Aggravating factor: the outbox is **untracked**, so a corrupted line has no git
history to recover from. Repair must preserve both records.

Secondary defect found while probing: `_iter_raw_lines_at` iterates
`path.open(...)` directly with no context manager, leaking the file handle
(`ResourceWarning: unclosed file`).

## Empirical probes

| Probe | Finding |
|---|---|
| Reproduce observed corruption (write record without `\n`, then append a status) | Both records land on physical line 1. `_iter_raw_lines_at` returns **0 records** — confirms both are lost, matching the report exactly. |
| Warning visibility | `Corrupt triage line at triage.outbox.jsonl:1, skipping` via `warnings.warn` — non-fatal, stderr only, no side channel. Invisible in normal use. |
| `json.JSONDecoder().raw_decode()` loop on the corrupted line | Recovers **2 of 2** records, both fully intact (`append` + `status` with `newStatus: dismissed`). Record-boundary splitting is viable. |
| Live corpus scan (main root + all worktrees, outbox + quarantine) | 0 corrupt lines currently on disk — the observed line was already consumed/swept. The repair pass must therefore be safe on a clean corpus (no-op) as well as a dirty one. |
| File-handle leak | `ResourceWarning: unclosed file` raised on every read. |

## Acceptance criteria

1. **AC1 — Writer guarantees termination.** `_append_line` — and only that writer,
   under the canonical lock it already holds — ensures the target file ends with a
   newline before appending. An append onto an unterminated file produces two
   physical lines, not one. A missing or zero-byte file is safely appendable (no
   leading newline); a file ending `\r\n` counts as already terminated.
2. **AC2 — Reader recovers concatenated records, partially if need be.** A physical
   line holding N concatenated JSON records yields all N, in order, instead of zero.
   A line holding valid records followed by an unrecoverable fragment yields the
   valid records **and** surfaces the fragment verbatim — never all-or-nothing.
   Blank lines are ignorable formatting; non-dict JSON is a fragment, not a record.
3. **AC3 — Corruption is loud, not silent.** Unrecoverable text is returned as data
   on an explicit side channel (`RecordRead.corrupt`, mirroring the established
   `scan_errors` degraded-marker idiom). The leaf library never prints; stderr
   reporting happens at the command boundary. Corruption is never read as absence.
4. **AC4 — Repair pass.** A CLI repairs already-corrupted lines in place, splitting
   concatenated records onto their own lines and preserving **both** records;
   unrecoverable text is quarantined verbatim (never dropped), appended durably
   *before* the source is replaced and keyed by content hash so retries dedupe.
   Reporting is the default; mutation requires `--apply` **and**
   `--writers-quiesced`, because the atomic replace swaps the inode and the WebUI
   writer does not share the lock primitive. Scope is explicit resolved paths within
   the given root — no worktree wandering, no symlink traversal.
5. **AC5 — No handle leak.** The reader closes its file handle.
6. **AC6 — No bloat ratchet.** `shared/scripts/triage.py` (ADR-100 exception at 704)
   does not grow; new logic lands in a new <300 LOC neutral leaf module.

## Mini-plan

New neutral leaf module `shared/scripts/lib/jsonl_records.py` (<300 LOC), following
the `lib/sweep_text.py` precedent (extracted specifically to avoid the CodeQL
import-cycle findings of #281):

- `ends_without_newline(path) -> bool` — byte-level probe of the final byte.
- `split_concatenated_records(line) -> list[dict] | None` — `raw_decode` loop.
- `read_jsonl_records(path) -> RecordRead(records, corrupt)` — the tolerant reader,
  moved out of `triage.py` so that file **net-shrinks**.

`triage.py` changes stay minimal:
- `_load_jsonl_records()` — **lazy** loader mirroring the existing
  `_load_file_lock_cls()` idiom. This is load-bearing: `triage.py` lives outside
  `lib/` per ADR-045, and an eager `from lib.x import ...` binds
  `sys.modules['lib']` to `shared/scripts/lib`, shadowing each plugin's own `lib`
  package in cross-plugin pytest (green locally / red in CI).
- `_iter_raw_lines_at` delegates to the leaf (fixes the handle leak).
- `_append_line` gains the termination guard.

New CLI `shared/scripts/tools/triage_repair.py` — scans tracked + outbox, reports by
default, repairs under `--apply` via `durable_atomic_write` under the canonical
lock, quarantining unrecoverable text through the existing
`lib/sweep_quarantine.append_quarantine`.

### Alternative considered — reader raises on corruption (fail-closed)

Rejected. Fail-closed on *read* means one bad byte blackouts the entire triage
board and every background producer, converting silent partial loss into loud total
outage. The append-only log's value is partial availability. Recover what is
recoverable, surface the rest loudly through a side channel, and repair out-of-band.

### Out of scope (separate repo)

The WebUI has its own writer, `server/src/core/triage-write.ts:148`
(`appendFileSync(targetPath, line)`), with the identical missing guard. It is a
separate repository — this monorepo fix does not reach it. Filed as a triage anchor.

## External plan review (GPT-5.4 + Gemini 3.1 Pro, 2/2 succeeded, not degraded)

Accepted, folded into the design above and the ACs below:

1. **(both, high)** `split_concatenated_records -> list | None` was all-or-nothing: a
   valid record followed by a truncated one would return `None` and drop the valid
   record — reintroducing this very bug. Signature changed to
   `split_records(line) -> tuple[list[dict], str]` (recovered records + verbatim
   unrecoverable remainder). **AC2 amended.**
2. **(both, high)** `ends_without_newline` must treat a missing and a zero-byte file
   as safely appendable, and must regard a file ending `\r\n` as terminated.
   **AC1 amended**; explicit test matrix.
3. **(both, medium)** Parser contract pinned: skip JSON whitespace between records,
   blank/whitespace-only lines are ignorable formatting (never a corruption event),
   non-dict JSON values are rejected as fragments rather than accepted.
4. **(GPT #1, high)** `durable_atomic_write` replaces the inode. The WebUI writer
   uses `proper-lockfile` (directory-based) which — as `triage-write.ts` documents —
   does **not** compose with the Python `msvcrt`/`fcntl` byte-lock. A WebUI
   `appendFileSync` against the pre-replacement inode would be lost by repair.
   `--apply` therefore requires an explicit `--writers-quiesced` acknowledgement.
   **AC4 amended.**
5. **(GPT #4, medium)** A reusable leaf must not print. The leaf returns
   `RecordRead(records, corrupt)`; stderr reporting lives at the command boundary.
   **AC3 amended.**
6. **(GPT #7, medium)** Repair persistence ordering: quarantine is appended durably
   **before** the source is replaced, keyed by a content hash so a retry after a
   crash deduplicates instead of double-quarantining. **AC4 amended.**
7. **(GPT #5, medium)** AC1 overclaimed a system-wide guarantee. Scoped explicitly to
   `_append_line`; the WebUI writer remains a known gap tracked separately.
8. **(GPT #8/#9, low)** Repair scope pinned to explicit resolved paths inside the
   given root — no worktree wandering, no symlink traversal; report mode prints each
   resolved path and its kind.

**Rejected — Gemini, "drop the `triage_repair.py` CLI entirely" (high).** Its premise
is that the tolerant reader handles corruption dynamically and no corruption persists
on disk. That holds for *readers*, but `lib/sweep_outbox.py` folds the outbox into the
tracked log via **raw text lines** (`normalize_lines` + stripped set-membership), not
parsed records. A concatenated line therefore survives verbatim into the
**git-tracked** `triage.jsonl` and can trip `validate_triage_text`, blocking the sweep.
Corruption does persist and propagate, so an out-of-band repair remains necessary.

## Code review round (spec-reviewer + code-reviewer, post-build)

Both reviewers independently found that `test_apply_is_idempotent` was a **false
green** — it re-ran `main` on an already-repaired file, exited early at "Nothing to
repair", and never reached `_repair`, so the entire content-hash dedupe could be
deleted with the suite still passing. All findings below are fixed and each is pinned
by a test verified to fail when the fix is reverted:

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | high | `test_apply_is_idempotent` vacuous; dedupe untested | Replaced with `test_retry_after_a_crashed_replace_does_not_double_quarantine`, which injects a failing `durable_atomic_write` so the fragment is still on disk on retry, plus a within-run duplicate test |
| 2 | high | **TOCTOU** — the scan ran outside the lock, so a *cooperating* writer appending between scan and atomic replace was silently overwritten (the very bug class this iterate fixes) | `--apply` now scans **inside** the lock; report mode stays lock-free. Pinned by `test_apply_scans_inside_the_lock` + `test_report_mode_takes_no_lock` |
| 3 | high | Whole-file **EOL reflow**: re-serializing every line rewrote a CRLF tracked log to LF — a whole-file diff on a `merge=union` artifact, a defect this repo already has a regression test for | Minimal rewrite: untouched lines are re-emitted byte-for-byte and the detected EOL is preserved (reusing `lib.sweep_text.normalize_lines`). Pinned by `test_crlf_tracked_log_is_not_reflowed_to_lf` + `test_healthy_lines_are_preserved_byte_for_byte` |
| 4 | medium | Strict UTF-8 decode raised `UnicodeDecodeError` **outside** the try, blacking out every reader on one bad byte — exactly the fail-closed outcome this spec's rejected alternative argues against, and an interrupted write (a documented cause here) produces it | Read with `errors="surrogateescape"`; such a line degrades to a fragment |
| 5 | medium | `except ValueError` misses `RecursionError`, which `json`'s scanner raises on deeply nested input | Widened to `(ValueError, RecursionError)` |
| 6 | medium | A wholly-unrecoverable file was truncated to zero bytes, dropping the schema header and wedging the sweep the repair exists to unblock | `unsafe` guard refuses to rewrite; reported instead |
| 7 | medium | Re-serialization broke `churn_merge` byte-identity dedup (can duplicate `status` events into the tracked log) | Subsumed by fix 3 |
| 8 | low | `str.isspace()` accepts NBSP/U+000C between records, diverging from JSON | Explicit `" \t\r\n"` set |
| 9 | low | Lock/quarantine used the unresolved root while targets used the resolved one | `Path(...).resolve()` once in `main` |
| 10 | low | "VERBATIM" overstated (the reader strips surrounding whitespace) | Wording narrowed |

Also reported and **accepted as-is**: undecodable text is visible to `triage`-level
consumers only as a warning, because AC3 deliberately pins the side channel to the
leaf's `RecordRead.corrupt` and no current consumer needs more. A conscious choice,
not an oversight.

## Confidence Calibration

- **Boundaries touched:** JSONL append-only log producer/consumer boundary
  (`.shipwright/triage.jsonl`, `.shipwright/triage.outbox.jsonl`,
  `.shipwright/triage.outbox.quarantine.jsonl`); cross-process lock boundary.
- **Empirical probes run:** see the Empirical probes table above — corruption
  reproduced (0/2 records survive), `raw_decode` recovery verified (2/2), live
  corpus confirmed clean, handle leak observed.
- **Adversarial parser probes (post-build):** the `raw_decode` loop was probed against
  the inputs most likely to break a naive splitter — `}{` inside a string value,
  escaped quotes and Windows backslash paths, nested objects/arrays, unicode + emoji,
  an escaped newline inside a value: **2/2 records recovered in every case, remainder
  empty, values byte-exact**. Termination probed on `{{{`, an embedded NUL, a bare
  `nul`, `[2]`, empty and whitespace-only input: every case terminates and **always
  preserves the valid prefix**. 5000 concatenated records on one physical line parse
  in 0.001 s (no pathological backtracking).
- **Mutation testing (non-vacuity, empirical):** every fix was reverted in turn and the
  suite re-run. Writer guard off → 2 failures (the AC1 tests); record recovery off →
  13; content-hash dedupe off → 2; EOL preservation off → 1; scan moved back outside
  the lock → 1; strict UTF-8 restored → 1; `RecursionError`/`isspace` reverted → 2.
  Each mutation is caught by exactly the test written for it; restored, 51 pass.
- **Test Completeness Ledger:** 52 behaviors — 51 `tested`, 1 `untestable`. Machine
  readable copy at `shipwright_test_results.json` → `iterate_latest.test_completeness`.
  The single `untestable` row is the cross-primitive write race between this tool's
  `fcntl`/`msvcrt` byte-lock and the webui's directory-based `proper-lockfile`
  (`reason_code: requires-external-nondeterministic-service`) — it is why
  `--writers-quiesced` exists, and the *guard* itself is tested
  (`test_apply_requires_the_quiesced_acknowledgement`). 0 untested-testable.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the fix was driven by a reproduction, not by inspection —
    the pre-fix reader was measured returning **0 of 2** records on the exact reported
    shape, and each of the three fixes has a test that fails when reverted.
  - *Coverage (breadth):* both writers (tracked + outbox), both readers (leaf + public
    `read_all_items`), both EOL styles, unicode, first-write/empty/absent files, the
    repair CLI's report / refuse / apply / idempotent-retry paths, and a no-op run
    against the real on-disk corpus.
  - *Integration composition:* not applicable — `cross_component` does not fire for
    this diff (no merge/churn resolver, hook, phase validator or campaign-drain file
    is touched). Verified against `classify_complexity.CROSS_COMPONENT_FILE_PATTERNS`;
    the F11 verifier recomputes the flag from the diff independently.
  - *Known residual:* the guarantee is scoped to this repo's writer. The webui writer
    can still emit the corrupt shape until its own fix lands (triage `trg-a20314c2`);
    reader-side recovery is what makes that survivable in the meantime.
