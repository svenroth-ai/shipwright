# Mini-plan: events-writer-hardening-2

## Work breakdown
1. `events_read.py`: `DROP_NAME` (strict, `\Z`, groups `key`, `wt8`, `nonce`, key length from `KEY_MAX`) replaces the
   loose `_DROP_NAME`; the line count must not grow. Exported.
2. `events_fold_io.py`: import `DROP_NAME` from `events_read` (drop its own copy); `drop_key_of` and `name_problem`
   keep working.
3. `events_stage.py`: `_NAME` becomes the shared `DROP_NAME`.
4. `events_layout.py`: the writer validates its file name with `DROP_NAME`; the open-drop choice skips a torn file
   (`ends_without_newline`, non-empty only), keeps `not path.is_symlink()`, and returns the same open file on later
   writes. Update the module docstring sentence about torn lines.
5. `events_write._monotonic_ts`: drops layout only; when the target is missing or has no records, take the max `ts`
   over every drop whose parsed key equals the run key (valid records only, damaged files untouched) and bump to
   max + 1 microsecond when the event is not already later.
6. `tools/verifiers/events_integrity_check.py::_own_worktree_drop`: use the `wt8` group of `DROP_NAME`.
7. Tests (`test_events_writer_hardening_round2.py`; rotation and torn file are red first): name table across modules
   incl. a trailing newline and the writer's own key; rotation order incl. shuffled names, frozen and earlier clock,
   another worktree; torn file unchanged, new file reused, empty file reused, valid event then torn tail then write;
   legacy bytes pinned; extend the standalone-load test in `test_events_read.py`.
8. Docs: `docs/hooks-and-pipeline.md` writers paragraph (rotation order, torn file, the way out is quarantine).

## Alternative considered
A new `events_names.py` (first draft). Rejected on review: it needs wiring into the reader's by-path fallback (ADR-045
class), while the key rule already lives in `events_read.py`.

## Risks
Reader strictness (noted in the spec), a torn file is never reused, rotate-on-OSError under antivirus (accepted, one
extra untracked file), flat-load contexts (covered by the extended test).
