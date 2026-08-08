# ADR spec-folder files are named by run_id, never a guessed number

## Context

`.shipwright/planning/adr/<NNN>-<slug>.md` spec files were named by an
agent guessing `max(existing NNN) + 1` at branch time. Two or more
parallel iterate worktrees compute the same `max` independently and
each claim the same next number — measured on this run's own tree: 15
files across 6 colliding numbers (097, 120, 125, 126, 127, 128).

Separately, four skill instructions (`context-loading.md`,
`build/first-actions.md`, `plan/first-actions.md`,
`project/step-1-interview.md`) told agents to read `decision_log.md`
"completely" — a promise a single 2,000-line-capped `Read` call cannot
keep against a 4,379-line file. Both defects share one root cause:
an unbounded artifact treated as if it were bounded, verified only by
agent judgment rather than by a mechanical guard.

## Decision

Retire numeric spec-folder filenames. A new
`.shipwright/planning/adr/` file is named
`<run_id_sanitized>-<slug>.md` (via
`lib.iterate_entry.sanitize_run_id_for_filename`). `run_id` is already
globally unique by construction, so this is collision-proof with no
allocator, lock, or watermark — nothing to coordinate across parallel
worktrees. The file's own `# ` heading must not claim a numeric
`ADR-NNN` token; that identity is a separate, independent one, assigned
later at release by `decision_log.md`'s own `aggregate_decisions.py`
(the bloat-baseline `adr: "ADR-NNN"` field references THAT identity,
not the spec-folder filename).

The four `decision_log.md` readers were changed to read
`decision_log_index.md` (331 lines) first, with a named fallback
(grep the heading, then an offset-bounded `Read`) for "the index has no
matching entry" — never a bare "read the whole file" instruction.

The 15 existing colliding files are explicitly left unrenamed — a
`.shipwright/planning/iterate/iterate-2026-08-08-index-readers-adr-lock-adr-collision-report.md`
report enumerates them with per-number citation counts and leaves the
resolution (rename now / rename opportunistically / leave forever) to
the operator, since a bulk rename touches every existing citation of
each old number in `decision_log.md` and elsewhere.

## Rejected alternatives

1. **A claim-time allocator** — a dedicated lock + durable
   cross-worktree watermark file, so a CLI could hand back the "next"
   number atomically. Internal review fixed 11 real bugs in this design
   (self-deadlock from lock reuse, watermark durability across worktree
   cleanup, a silent-degrade path, slug path-traversal). Both external
   reviewers then rejected/revised the *approach itself*: a standing
   lock + durable state is disproportionate to a rare, cheaply-detected
   problem (openai: `reject`; deepseek: `revise` toward the same
   alternative).

2. **A merge-time blocking check** (both external reviewers'
   recommendation) — no new runtime mechanism; a CI/F11 gate blocks a
   merge on a guessed-number collision instead of preventing the
   collision at claim time. Superseded when the operator asked why the
   spec-folder file needs a number at branch time at all, given that
   `decision_log.md`'s own numbering already defers exactly this
   question to release time.

3. **Leave the convention as-is, add only a post-hoc collision guard**
   — rejected: a guard that fires after the collision already happened
   does not prevent the next one; it only reports it, and this run's
   own report already demonstrates that reporting alone left 6 prior
   collisions unresolved.

## Consequences

- No file in `.shipwright/planning/adr/` claims a numeric ADR-NNN in
  its filename or heading going forward. `decision_log.md`'s own
  `ADR-NNN` numbering is unaffected — it still increments serially at
  release, resolved to a run_id via each entry's `Run-ID:` line.
- `shared/scripts/lib/adr_index.py`'s renderer and a new
  anti-ratchet drift-guard (`shared/tests/test_adr_index_no_duplicate_numbers.py`,
  baseline `shipwright_adr_collision_baseline.json`) share one
  `parse_adr_number()` helper, so they cannot disagree about what
  counts as a numbered (vs. freeform, run_id-named) filename.
- The spec-folder filename and the `decision_log.md` release-assigned
  number are now formally independent identities. Anything that needs
  to cite an ADR by number continues to do so via `decision_log.md`;
  anything that needs to cite this run's own spec file cites it by
  run_id/slug.
