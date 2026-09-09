# Backfilling `phase_tasks[]` on already-adopted projects

Campaign `p4-04-retire-write-once-steps`, sub-iterate s2, started seeding
`phase_tasks[]` entries into `shipwright_run_config.json` at adoption time
(`write_run_config`, via `write_all`). That only serves **new** adoptions —
a project adopted before s2 landed (2026-09-09) has `completed_steps` and no
`phase_tasks[]` at all.

Several readers have been migrated to consult `phase_tasks[]` as the
authority for per-phase progress and no longer fall back to
`completed_steps` (`plugins/shipwright-compliance/scripts/lib/mermaid.py`'s
`_get_phase_status` — the dashboard phase strip, sub-iterate s1). A project
adopted before s2 that is later picked up by `/shipwright-run` for a new
feature will show its adoption-era phases (project/plan/build/test) as
**pending** in that reader, even though they are not outstanding — they
just predate the writer that would have recorded them.

## When to run this

Only for a project that:

1. Was onboarded via `/shipwright-adopt` (its `shipwright_run_config.json`
   has an `adoption` key), and
2. Has `completed_steps` but no `phase_tasks[]` entry for one or more of
   them — i.e. it was adopted before 2026-09-09.

A fresh adoption already gets this from `write_all` and does not need it. A
non-adopted config (no `adoption` key) is out of scope — the tool reports
`applicable: false` and touches nothing.

## Running it

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/backfill_phase_tasks.py" \
  --project-root <path-to-project> [--dry-run]
```

`--dry-run` reports `added_phases` / `skipped_phases` without writing the
file — use it first to confirm what would change.

## What it does

For each phase in `completed_steps` not already represented in
`phase_tasks[]` (by its `phase` key, regardless of who wrote the existing
entry), it appends one entry built the same way `write_run_config` builds
one for a fresh adoption (`build_adopted_phase_task` —
`establishedAtAdoption: true`, a terminal `done`/`skipped` status). The
timestamp used is the project's own `adoption.adopted_at`, not the moment
the backfill runs, so the entries read as having happened at adoption time.

**Idempotent** — a phase already represented in `phase_tasks[]` is left
alone, so running this twice (or running it against a project s2 already
seeded) changes nothing; the second run does not even rewrite the file.
Real, later `phase_tasks[]` entries from an actual `/shipwright-run` (e.g. a
`build` entry from a new feature, sitting alongside the adoption-era ones)
are never touched — only the gap is filled.

## Verification

`plugins/shipwright-adopt/tests/test_backfill_phase_tasks_cli.py` runs this
tool against `tests/fixtures/backfill_phase_tasks/leadwright_run_config.json`
— a verbatim copy of a real project's on-disk config from before s2 landed
— and against the real dashboard phase strip reader
(`plugins/shipwright-compliance/scripts/lib/mermaid.py`), so the backfilled
shape is proven against both a real prior config and the reader it exists
to unblock, not only a synthetic fixture.

Sub-iterate s2b additionally ran `--dry-run` against the actual live
leadwright checkout on disk (not a copy), producing exactly the
`added_phases` the fixture predicted with zero write — real-config proof
beyond the committed fixture, without mutating a repository outside this
one. Writing that live config is a deliberate operator decision (this tool
performs it, `--dry-run` only previews it) and is out of scope for this
sub-iterate to perform unattended against a repository it does not own.

## No fleet-wide discovery mode

This tool takes one `--project-root` and backfills that project only —
there is no `--scan <root>` that walks a filesystem looking for other
legacy-shape configs. Shipwright keeps no registry of the repositories
`/shipwright-adopt` has onboarded, so there is nothing in this monorepo to
enumerate against; an unbounded filesystem walk would also cross into
directories the operator never asked this tool to touch. This mirrors the
existing `backfill-iterate-config.md` precedent (a manual one-liner run
per project, no scanner) — run this tool explicitly for each project known
to need it, leadwright being the one currently known to this campaign.
