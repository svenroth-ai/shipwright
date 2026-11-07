# Events drop files (issue 978): flip readiness after S8

Status: the S8 evidence is complete on Windows; the Linux benchmark numbers come from the first CI run. The flip (S9a) is operator-driven and
the operator decides which listed follow-ups must be closed first (the "blocking-class" list below is the recommendation).

## What S8 proved (Windows, local)

| Kill criterion | Result |
|---|---|
| KC5 run-scoped read at 300 files (real 1246-event, 3.5 MB legacy log + 300 drops x 4 events) | 10.6 ms (budget 20); 22.0 ms if the whole legacy log is parsed without a raw-text prefilter |
| KC5 whole-log read at 300 files | 143 ms (budget 300) |
| Per-write cost at 300 files (in-process `append_event`) | 103 ms (dedup scans every drop; plus about 6 git calls per CLI write) |
| KC3 whole-system scenarios | 8 green (incl. two run ids in one shared worktree, stacked-base branch): wave of 4 units + retried unit + squash sequence + real `ensure_current`; old-writer / PR in flight at the flip / mid-run flip; mid-run rollback; quarantine of a torn drop; mixed versions through the real CLI; fault injection |
| Rollback rehearsal on a COPY of the real history (1246 events: 400 legacy, rest in about 1000 drops) | emergency fold and full fold both lossless; integrity check accepts the fold commit; a pre-change reader sees every event once; full fold idempotent; the real log was hashed before and after |

CI runs the benchmark with generous bounds (10x); set `SHIPWRIGHT_BENCH_STRICT=1` for the real bounds and
`SHIPWRIGHT_BENCH_OUT=<file>` to record the numbers. On the Linux runner the test writes the measured numbers into the GitHub job summary (`GITHUB_STEP_SUMMARY`); no workflow was changed. The 12-writer path is proven correct (KC4) but its timing is not benchmarked.

## Fixed in S8 because the rehearsals hit them

- `fold_events.py --stage` passed every path to one `git add`: with about 1000 drops Windows failed with
  `WinError 206` (emergency fold unusable at scale). Now one `git add --pathspec-from-file=-` call (paths on stdin), atomic and without a length limit.
- Consumer CI check (S7 follow-up): a PR open at the flip failed as soon as it merged main in (merge-base moved past the
  flip, the old legacy appends were blamed). Now judged per commit by the layout at the commit's first parent.
  A PR REBASED onto the flipped main is still flagged (its events must be re-recorded as drops).
- `$` -> `\Z` in `DROP_NAME`, `ARCHIVE_NAME`, `ARCHIVE_FOLD_NAME` (a trailing newline slipped through).

## Preconditions for S9a (the flip)

1. WebUI release containing S1 + S5b is in use; its minimum version is recorded. The bullet writer must not reach consumers before S5b.
2. A plugin release containing S2-S7 (and this unit) is installed by every teammate; the flip is a team-announced event.
3. The operator wires `check_events_layout_ci.py` and `check_events_integrity.py` into CI (CI trust boundary, not done by any unit; the consumer
   checkout needs `fetch-depth: 0`).
4. Read the Linux CI benchmark numbers from the job summary of the first run of `test_events_drops_benchmark.py` and compare them with the strict bounds (20 ms / 0.3 s); CI itself only asserts 10x. CI runs the root under `--cov`, so the summary carries `traced_by_coverage` and its numbers are inflated: use them as an upper bound, and run `SHIPWRIGHT_BENCH_STRICT=1` on a Linux box for the real figure.
5. Decide the fold cadence: per-write cost grows with the number of open drop files (about 0.34 ms per file), so run the fold before the
   count approaches 300.
6. Flip announcement: a plugin from before step 2 running F11 on a drops repo fails loudly; PRs rebased (not merged) across the flip
   must re-record their events.

## Known gaps of the S8 changes

- The layout CI check judges the PR's own non-merge commits; the content a MERGE commit itself adds to the legacy log is not judged (review finding, not fixed).
- The rehearsal and the benchmark read the live tracked `shipwright_events.jsonl`; a future event with an unusual shape could break them without a code change (pin to a snapshot if that happens).
- KC5's run-scoped read is measured with a reader spelled out in the test (own-key glob + raw-text prefiltered legacy log); the product has no dedicated run-scoped reader, production consumers use the whole-log read (143 ms). Ship a run-scoped reader if a hot path needs the 20 ms figure.
- `_DROP_NAME`/`_NAME` regexes in `events_read`, `events_stage`, `events_layout` still use `$` and accept a looser key than `events_fold_io.DROP_NAME`; unify them.
- `check_layout_ci` is not cached per rev (several `cat-file` calls) and its synthetic-merge unwrap compares HEAD^1 with the current base tip.
- Shared-worktree hop (two run ids, real `ensure_current`) is tested: a sibling run's GATE event (`work_completed`) is never absorbed. By design the absorb does commit a sibling run's non-gate events (and a gate-free file) into the branch that hops; they are unique files, so nothing is lost or duplicated. The S4 item below is therefore a hygiene issue, not a blocker.

- The CI check judges by the fork point: a PR forked before the flip that never merges main is not checked at all (S7 design). Needs `fetch-depth: 0`; a shallow clone gives a misleading verdict.
- The full fold is lossless modulo exact-content duplicates (deduped by design); the real log has none.

## Follow-ups not fixed here (listed so the operator sees what to harden)

Blocking-class candidates (recommend fixing before or right after S9a, none blocked a rehearsal):

- S4: F11 committed-check false FAIL when `project_root` is a subdirectory of the git repo (`_events_committed.py` ~57-58).
- S4: absorb can commit sibling runs' drops in a shared worktree (`events_stage.py` ~127).
- S4: F7b seal is all-or-nothing on a torn file; `_monotonic_ts` alters `ts` after the dedup comparison; a `run` key in event extras is not
  stripped (`finalize_iterate` ~269-272); `amend_commit` is not idempotent under drops.
- S6: fold can stop halfway on Windows when a reader holds a file open (PermissionError not caught, `events_fold.py` ~199-203, ~243, `events_fold_full.py` ~85).
- S6: F11 integrity check passes (skips) when git fails; it does not check drop ownership (`own_keys` not passed); CLI compares the raw `--run-id`
  without `sanitize_key`; a CRLF-corrupt drop cannot be quarantined under autocrlf; a full fold can show events twice briefly.
- S7: CI check blocks an emergency-fold rollback that the sentinel allows (`events_layout_ci.py` ~377-382 in the S7 numbering; the rollback shape is
  only accepted when the head declares legacy AND no drop is left); adopt `events_layout_key.py` ~49-56 turns an explicit null into legacy;
  the test-only env override can still split silently.

Lower priority:

- S2: identical-timestamp events can order differently in split vs unsplit logs (the rehearsal compared sets/multisets, which are equal).
- S3: grade staleness picks the newest drop by mtime (meaningless on a fresh clone); guard alias tracking is one level deep.
- S4: adopt seeder writes CRLF on Windows (`event_seeder.py` ~115); per-write cost (see the benchmark: 103 ms at 300 files).
- S5: folded bullets append at the bottom while docs list newest first.
- S0/S4: the `--jobs 2` budget was measured at `--jobs 3`; `tighten` safety; the lock test is a weak spy.
- Splitter note: a content splitter with a FIXED nonce collides on case-insensitive filesystems (run ids differing only in case); the live writer
  uses a random nonce so it is unaffected.
