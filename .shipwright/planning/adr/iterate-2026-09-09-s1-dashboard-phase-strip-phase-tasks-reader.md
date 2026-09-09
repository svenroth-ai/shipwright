# ADR: compliance mermaid.py dashboard phase strip reads phase_tasks[]

**Run-ID:** iterate-2026-09-09-s1-dashboard-phase-strip
**Campaign:** p4-04-retire-write-once-steps, sub-iterate s1 of 6 (dashboard-phase-strip)

## Context

The campaign `p4-04-retire-write-once-steps` retires the write-once
`current_step` / `completed_steps` config fields, migrating nine readers
one consumer at a time so each sub-iterate is independently verifiable
and revertible. `plugins/shipwright-compliance/scripts/lib/mermaid.py`'s
`_get_phase_status` renders the dashboard phase strip — the one reader
whose regression a person sees directly — and the parent campaign card
warned explicitly that dropping the writer without migrating this reader
first would empty the strip. It goes first, alone.

No database change of any kind is involved: this only changes which
JSON config field a rendering function reads. `phase_tasks[]` is already
written by `config_factory.py` / `phase_task_lifecycle.py` (shipwright-run)
on every driven run, pre-dating this campaign — this sub-iterate is a pure
reader migration.

## Decision

`_get_phase_status(phase, pipeline_status, configs)` (the `current_step`
parameter is dropped) now derives phase status from `run_config["phase_tasks"]`
via a new helper `_phase_tasks_status`, which returns `complete` only when
every entry for that phase (a split phase like `build` can hold more than
one) is `done`/`skipped`, `in_progress` if any entry is `in_progress`/`failed`,
else `pending`, or `None` when there is no phase_tasks evidence at all (falls
through to the existing per-phase `config.status == "complete"` check, then
`pending`). `current_step` / `completed_steps` are left present on the config
schema and on the fixture but are no longer read by this function anywhere.

## Consequences

- The dashboard phase strip is correct for every driven run (phase_tasks[]
  always present), matching the two `phase_quality` readers already migrated
  before this campaign.
- A config with NO `phase_tasks[]` at all (a not-yet-backfilled already-adopted
  repo, or a hand-built fixture) now renders every phase without an explicit
  `config[phase].status == "complete"` as PENDING rather than using the old
  `current_step` positional inference. This is the exact gap the campaign's
  external architecture review found and assigned to sub-iterate **s2b**
  (backfill-existing-adopted-config) — not silently reintroduced here, it is
  the sequencing the campaign already committed to.
- Two empirical boundary probes were run beyond the pytest suite (Confidence
  Calibration, Step 3.8): an empty `phase_tasks: []` list and a set of
  malformed entries (missing `status` key, non-dict list item, unknown status
  string) both render gracefully to PENDING with no exception — no crash path
  exists for adversarial/legacy config shapes. Two consecutive no-finding
  probes reached the asymptote.

## Rationale

Per-reader migration (rather than a dual-write/bridge shim) was the
architecture-approved approach (external review 2026-09-06, GPT+GLM,
`--mode architecture`, APPROVE) — a bridge that keeps both fields "correct"
converts a removal into a new standing mechanism with its own drift class,
in fields whose only remaining purpose is to be deleted.

## Rejected Alternatives

- **Fallback to `current_step` when `phase_tasks[]` is absent/empty** —
  considered (raised independently by both external plan-review legs, see
  below) and rejected for s1 specifically: it would reintroduce exactly the
  mode-conditional-truth pattern ("which shape is authoritative depends on
  how the config was produced") the campaign's architecture review rejected
  for the v1 `update_step` path (decision 2, refined 2026-09-06). The correct
  fix for a config genuinely missing `phase_tasks[]` is to backfill it
  (s2b's job), not to keep two authorities alive in the reader.

## External-Plan-Review-Findings

Both GLM and OpenAI reviewed the sub-iterate spec text (`--mode iterate`)
and returned `revise`, each flagging the same core concern from a different
angle (neither had visibility into the diff — plan review runs before the
diff exists):

| Finding (severity) | Disposition |
|---|---|
| GLM: reader assumes `phase_tasks[]` is already populated for existing/historical configs; no fallback documented (HIGH) | rejected-with-reason — verified `config_factory.py` already writes `phase_tasks[]` on every driven run, pre-dating this campaign; the remaining gap (already-adopted configs on disk) is explicitly s2b's scope per campaign.md, not this reader's |
| OpenAI: no data contract for mapping `phase_tasks[]` items to strip segments / ordering (MEDIUM) | rejected-with-reason — the mapping is exactly what `_phase_tasks_status` + the existing `phases` ordering tuple already implement; the fixture-pinned test proves the concrete mapping byte-for-byte |
| OpenAI/GLM: fixture test should use CONFLICTING legacy-field data to prove old fields are truly ignored, not merely present (MEDIUM) | accepted-and-fixed (already present in the build, not added post-hoc) — `test_the_write_once_fields_are_present_but_ignored` sets `current_step="build"`/`completed_steps=[]` while `phase_tasks[]` says build is done and test is running, and asserts the strip follows `phase_tasks[]` |
| GLM/OpenAI: no test for empty/missing/malformed `phase_tasks[]` entries (LOW/MEDIUM) | accepted-and-fixed — added as Step 3.8 empirical boundary probes (empty list, malformed entries); both render gracefully, no crash |

## External-Code-Review-Findings

First pass (against `git diff HEAD` only) returned two HIGH/MEDIUM findings
that the new fixture file was "missing from the diff" — a false positive:
`git diff HEAD` excludes untracked files (already-known gotcha, see
`conventions.md` 2026-09-03 entry), the fixture is untracked. Re-ran with
`git add -N` first for the full diff; both reviewers then returned `approve`
with only low-severity notes:

| Finding (severity) | Disposition |
|---|---|
| GLM: removing the old positional `current_step` inference changes behavior for a config with no `phase_tasks[]` at all, untested (LOW) | rejected-with-reason — intentional and in scope per this ADR's Consequences section; the undriven/adopted-config path is s2b's scope, and adding a test here would test a state this reader deliberately no longer special-cases |
| GLM: unknown/`failed` task status renders as `in_progress` (yellow), no distinct failure color (LOW) | rejected-with-reason — pre-existing `_COLORS` limitation (no `failed` bucket existed before this diff either), a cosmetic follow-up out of this sub-iterate's AC scope |

## Self-Review

1. Spec Compliance: pass — all 3 ACs implemented and tested.
2. Error Handling: pass — `_phase_tasks_status` guards non-list/non-dict/missing-key inputs via `isinstance`/`.get()` defaults, no exception path.
3. Security Basics: pass — pure internal JSON-config reader, no user input/secrets.
4. Test Quality: pass — 4 new/rewritten tests assert on rendered output (outcomes), including one deliberately-conflicting-legacy-field discriminating test.
5. Performance Basics: pass — one list comprehension over an in-memory list per phase, no I/O in the hot path.
6. Naming & Structure: pass — mermaid.py 254 lines, test_mermaid.py 185 lines, both under 300; new helper follows existing `_get_phase_status`/`_node_id` naming.
7. Affected Boundaries (ADR-024): pass — producer `config_factory.py`/`phase_task_lifecycle.py` (shipwright-run), consumer `mermaid.py` (new, this diff); round-trip probe is `test_pins_the_rendered_strip_against_a_fixture_config`, a real producer-shaped JSON fixture on disk read through the actual consumer function, asserted byte-for-byte.

## Confidence Calibration

Effective complexity: medium (fires the gate). Boundary: `run_config.phase_tasks[]`
(producer: `config_factory.py`/`phase_task_lifecycle.py`; consumer: `mermaid.py`,
new). Probes run:

1. Fixture round-trip (pytest, `test_pins_the_rendered_strip_against_a_fixture_config`) — no finding.
2. Empty `phase_tasks: []` list via direct function call — renders all-PENDING, no crash, no finding.
3. Malformed entries (missing `status`, non-dict list item, unknown status string) via direct function call — renders gracefully, no crash, no finding.

Two consecutive no-finding probes (2 and 3) — asymptote reached, boundary
calibrated. Edge case not probed: a `phase_tasks[]` entry with a `phase` value
outside `_DEFAULT_PIPELINE` (acceptable — the strip only ever iterates the
known `phases` tuple, so an unknown phase name in the data is inert by
construction, not merely unprobed).
