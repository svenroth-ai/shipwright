# Bloat exception — `plugins/shipwright-iterate/scripts/tools/campaign_init.py` raised to 416-LOC

- **Status:** proposed
- **Date:** 2026-09-21
- **Re-Review-Date:** 2026-12-21
- **Incident Reference:** campaign `campaign-dag-scheduler` sub-iterate R1
  (`iterate-2026-09-21-r1-depends-on-schema`),
  `.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md`
  § "R1 — `depends_on` schema, `campaign_graph.py`, campaign-design
  conversation, resume-safe readiness".

## Context

`campaign_init.py` was at 300 lines (already at its unflagged limit) before
this sub-iterate. R1 requires `campaign_init.py` to accept a `depends_on`
list per sub-iterate and call `lib.campaign_graph.validate_dependency_graph`
at write time, treating BOTH structural and charset findings as a hard
reject (unlike the read side, which only warns on charset) — this is
explicitly "where 'canonical' is actually enforced" per the plan. It also
needs a non-blocking `stacked`-branch_strategy deprecation warning
(`depends_on` supersedes it), and the generated `campaign.md` table /
`status.json` sub-iterate rows both need the new `Depends On` column /
`depends_on` + `merged_commit` fields. The validation helper
(`_validate_depends_on_for_write`) plus its lazy `shared/scripts` sys.path
bootstrap (mirroring the existing `_read_triage_item` pattern already in
this file) and the CLI's new `try/except ValueError` around `init_campaign`
add roughly 40 net lines. An external code-review finding (medium) then
added a further ~16 lines: `list(si.get("depends_on") or [])` silently
re-splits a bare string into characters (`list("AB") == ["A", "B"]`) instead
of raising, and a non-list/non-string value would have reached `list(...)`
and raised an uncaught `TypeError` past `main()`'s `except ValueError`
boundary — an explicit type-and-membership check ahead of the coercion
closes both. Stage-2 code review (medium, security) then found that `slug`
— unlike `id` — flowed unvalidated into `filename = f"{id}-{slug}.md"` and
`spec_path`, so a `slug` such as `"../../../../evil"` could write outside
the campaign directory; ~15 more lines apply the existing
`lib.campaign_graph.id_charset_ok` check (already imported for structural
validation) to every `slug` at the same write-time boundary. The doubt
reviewer (3f-bis) then found two adjacent gaps: `campaign_slug` itself —
strictly more powerful, since it picks the campaign's ROOT directory before
the first `mkdir` — was validated nowhere; and individually-valid `id`/
`slug` pairs can still collide on the single `-` the spec filename joins
them with (e.g. `id="A"`/`slug="b-c"` vs. `id="A-b"`/`slug="c"` both produce
`A-b-c.md`), silently clobbering one sub-iterate's spec with another's.
~35 more lines close both: the same `id_charset_ok` check on `campaign_slug`,
plus an explicit collision check on the computed `f"{id}-{slug}"` set. A
third, unrelated doubt-review finding (a non-dict `sub_iterates` element
raising an uncaught `AttributeError` past this function's `ValueError`
contract) added one more guard clause. The 3f-bis code-reviewer (medium,
correctness) then found a sub-iterate `title` flowed unescaped into the
generated `campaign.md` table row — a literal `|` in a title shifts every
later cell under the new header-indexed `column_map` (`campaign_status.py`,
own bloat ADR) — closed with a one-line escape ahead of the row's
f-string, pushing the file to 410. The doubt reviewer then found that
escape incomplete: a title containing a literal `\` could still defeat the
reader's single-char-lookbehind split (`campaign_status.py`'s own bloat
ADR has the full repro). Closing it properly required also escaping `\`
itself (`\` -> `\\`, ahead of `|` -> `\|`) so every backslash the reader
sees is guaranteed to be the first half of a two-char escape pair — three
more lines, pushing the file to 416.

## Ousterhout Argument

`campaign_init.py`'s PUBLIC interface stays narrow: one CLI (`main`) and two
functions genuinely reused elsewhere (`init_campaign`,
`validate_independent_strategy`). Behind it: triage-promotion resolution,
campaign.md/spec-file templating, and (as of this exception) write-time
dependency-graph enforcement. `_validate_depends_on_for_write` is a natural
extension of the file's EXISTING responsibility — write-time validation
(the same role `_validate_triage_id` already plays for triage anchors) — not
a new concern that belongs elsewhere.

## YAGNI Check

Every line here is required by an R1 acceptance criterion: hard-reject
structural/charset violations at write time, `stacked` warns rather than
rejects, and the generated artifacts carry `depends_on` so
`campaign_progress.py list-units` (R1's own consumer, unchanged) can feed it
straight into `autonomous_loop.py`'s `_load_units_from`. Nothing speculative
is added for a future campaign-mode feature not yet built.

## Chesterton-Fence Check

The prior 300-line size was, again, simply un-flagged — not an ADR-pinned
limit. No earlier design decision requires this file stay under 300; the
repo-wide convention is what applies, and it is the convention itself that
supplies this exception mechanism.

## Decision

Grant an exception raising `campaign_init.py`'s allowed `current` to 416.
Retirement plan: if a FUTURE sub-iterate (R2's per-unit worktree work is the
most likely candidate, since it also touches campaign initialization) adds
another write-time validation concern to this file, that is the trigger to
extract `_validate_triage_id` + `_validate_depends_on_for_write` into a
shared `campaign_init_validation.py` module — re-review at that point rather
than waiting for the calendar date alone.

## Consequences

No existing caller's signature changed (`init_campaign`'s new validation
happens INSIDE the function, raising `ValueError` on rejection — a new
failure mode any caller must handle, matching the existing
`_validate_triage_id`-raised `ValueError` the CLI already catches). Tests
that call `init_campaign` with a self-referential or unknown `depends_on`
must now expect a `ValueError` instead of a silently-accepted campaign — this
sub-iterate's own new test file
(`plugins/shipwright-iterate/tests/test_campaign_init_depends_on.py`) is the
only place that exercises the new path; no PRE-EXISTING test asserted the
old, unvalidated behavior.

## Rejected alternatives

- **Leave it at the unflagged 300 and split immediately.** Rejected: the new
  validation logic has exactly one caller (`init_campaign`) and reuses the
  file's own existing lazy-import-of-`shared/scripts` pattern; a same-file,
  same-caller helper does not meet the bar for its own module.
- **Skip the `stacked`-deprecation warning to save lines.** Rejected: the
  plan explicitly requires it (`branch_strategy` reconciliation, R1 spec) —
  cutting it to stay under a line count would trade a real acceptance
  criterion for a cosmetic one.
- **Move the CLI's `try/except ValueError` handling into `init_campaign`
  itself (swallow-and-return-code there).** Rejected: `init_campaign` is
  called directly by tests and by campaign-mode tooling that need the raised
  exception, not a swallowed return code; only the CLI (`main`) should
  translate it into a clean `ERROR:`/exit-1 message.
