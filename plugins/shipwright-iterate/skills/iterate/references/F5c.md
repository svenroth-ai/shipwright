# F5c — Record iterate entry (file-per-iterate)

Run **one script** that writes the entry file, handles legacy-array
migration (if this project still carries an `iterate_history` array in
`shipwright_run_config.json`), enforces retention, and records any
quarantined legacy rows for operator review:

```bash
uv run "{shared_root}/scripts/tools/append_iterate_entry.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --entry-json '{
    "type": "{feature|change|bug}",
    "complexity": "{trivial|small|medium|large}",
    "branch": "iterate/{short-description}",
    "spec": "{path to iterate spec or null}",
    "tests_passed": true,
    "adr": "{run_id}",
    "test_completeness": { ...the F5 ledger block... },
    "surface_verification": { ...the F0.5 block... },
    "declared_removals": [ {"path": "...", "reason": "..."} ]
  }'
```

**Carry the three evidence blocks here, not only in
`shipwright_test_results.json`.** An iterate does not commit that file, so the copy
a worktree is checked out with is `HEAD`'s — `main`'s, i.e. the PREVIOUS run's
evidence sitting in this run's worktree, shaped exactly like this run's would be and
separable from it by nothing but `run_id`. (F11's integration used to *rewind* it
mid-run on top of that; trg-ad29a709 now carries the bytes across the merge instead,
which closes that route and not the one above.) `check_test_completeness_ledger`,
`check_surface_verification` and the silent-revert declaration reader now refuse
a block that does not name the run being verified, and all three read this
per-run entry FIRST. The entry is not a derived snapshot, so the restore cannot
reach it.

`declared_removals` matters most of the three and is the easiest to forget: it
is the only one whose loss *blocks* rather than merely failing to catch. A
removal you declared at F5 that the restore then rewinds is a removal the F11
`no silent revert` gate will report as undeclared — with your reason sitting in
a file that now describes another run. Write it here and it survives.

If you skip them, the gates are still satisfiable — but only for as long as the
branch never falls behind, and the repair after it does is "re-run F5 and read
the numbers again". Writing them here once is the durable form.

Writes: `.shipwright/agent_docs/iterates/<run_id>.json` (atomic, under
file lock covering the full append transaction). `run_id` and `date`
are added by the tool itself (canonical ISO-8601 UTC `...Z` form) —
do NOT set them in `--entry-json`.

On first call against a project with a legacy `iterate_history` array,
the tool migrates every row into its own file; invalid or duplicate
legacy rows land in `.shipwright/agent_docs/iterates/_quarantine/` and
the count is recorded on run config as
`_iterate_migration_quarantined_count` so the handoff + verifiers
surface it.

Retention: keep the 50 most recent entry files per project (sorted by
ISO date, run_id tiebreaker). This is a **bounded window, by design** — on a
full directory each append evicts the oldest entry file (a tracked `git rm` in
the same commit). The evicted run is **not** lost: it survives in git history
and, permanently, in the append-only `shipwright_events.jsonl` (`work_completed`
events are never evicted). **Consumer rule:** anything that must show the FULL
iterate history (e.g. the WebUI Mission Requirement artifact) reads
`shipwright_events.jsonl`, NOT this directory — `iterates/<run_id>.json` is a
50-run recency cache, not the historical record.

Note: the commit hash is intentionally NOT stored here. Look it up in
`shipwright_events.jsonl` by `run_id` (F7 records the real commit
hash there). This omission is what lets F5c run pre-commit in a
single atomic F6.
