# Bloat exception — `shared/scripts/lib/campaign_status.py` raised to 415-LOC

- **Status:** proposed
- **Date:** 2026-09-21
- **Re-Review-Date:** 2026-12-21
- **Incident Reference:** campaign `campaign-dag-scheduler` sub-iterate R1
  (`iterate-2026-09-21-r1-depends-on-schema`),
  `.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md`
  § "R1 — `depends_on` schema, `campaign_graph.py`, campaign-design
  conversation, resume-safe readiness".

## Context

`campaign_status.py` was already at 299 of its own 300-line limit with no
baseline entry before this sub-iterate — a pre-existing, undocumented gap
this plan explicitly called out. R1 adds a `depends_on` column to the
campaign.md skeleton: `parse_campaign_skeleton` needed a header-indexed
column lookup (with a legacy positional fallback) instead of the old fixed
`cells[0]/cells[1]/cells[2]` indices, so a new column never silently
misaligns id/slug/title; `project_campaign_status` needed to carry
`depends_on` and `merged_commit` through to each `status.json` sub-iterate
row, plus an optional `skeleton=` override parameter so
`lib.campaign_graph.safe_project_campaign_status` can pass in an
already frozen-contract-reverted skeleton without a re-parse undoing that
reversion. The three new validators (`id_charset_ok`,
`validate_dependency_graph`, `check_frozen_contracts`) and the new
`safe_project_campaign_status` wrapper were deliberately split into a
BRAND NEW module (`campaign_graph.py`) precisely to avoid growing this file
further — but the header-indexed rewrite and the carry-through, both squarely
IN this file's own existing responsibility, still added a net ~45 lines even
after compacting the column-lookup helpers. (`campaign_graph.py` itself later
crossed 300 too, from case-fold-consistency fixes an external code review
found necessary — see its own, separate bloat-exception ADR.) A Step 3.8
confidence-calibration probe (empirical, not review-triggered) then found a
real UTF-8-BOM bug in `parse_campaign_skeleton` itself — a BOM prefixing a
frontmatter-less file's literal first line broke `## Sub-Iterates` section
detection entirely — fixed with a one-line `lstrip("﻿")` plus its
docstring explanation, pushing the file to 357. The 3f-bis code-reviewer
(medium, correctness) then found the write-side escaping fix for a `|`
embedded in `title` (`campaign_init.py`, own bloat ADR) was necessary but
not sufficient: `parse_campaign_skeleton`'s cell split was a literal
`stripped.strip("|").split("|")`, which does not know `\|` is an escape —
an escaped pipe still contains the character `|`, so the split still cut
the cell in two and shifted every later column on that row regardless of
the write-side fix. Closing it required an escape-aware split
(`_split_row_cells`, splitting only on an unescaped `\|` via a negative
lookbehind regex, then unescaping `\|` -> `|` per cell) rather than the
naive one, pushing the file to 375. The 3f-bis doubt reviewer (medium,
boundary & contract) then disproved that fix too: a single-char lookbehind
only inspects the ONE character immediately before a `|`, so a title ending
in an unescaped, unpadded literal backslash directly adjacent to the real
delimiter still merged the next cell into the title (concrete repro traced
by hand). The correct fix requires escaping `\` itself (`\` -> `\\`, ahead
of `|` -> `\|`) at write time and reading with a pair-consuming scan (`\` +
the next character is always one unit) instead of a fixed-width lookbehind
— `_split_row_cells` was rewritten around that scan plus a new
`_unescape_cell` helper, pushing the file to 409. An external Tier-3 PR
review (blocking) then found the header-row detector itself only recognized
a header when `cells[0]` literally read `id`, contradicting this same
docstring's "columns are looked up by the header row's own labels, not
fixed positions" claim: a reordered header (`Depends On` before `ID`) fell
through to the legacy positional fallback and silently misaligned every
column. The fix scans all cells for an `id` alias regardless of position,
plus a corrected docstring, pushing the file to 415.

## Ousterhout Argument

`campaign_status.py` is a deep module: its public interface is four
functions (`parse_campaign_skeleton`, `project_campaign_status`,
`merge_status`, `regenerate_campaign_status`) plus one alias
(`all_subs_complete`), each with a narrow, well-documented contract. Behind
that interface sits genuinely substantial logic — the never-downgrade status
ladder, event-log projection with corrupt-line tolerance and ts-based
recency, markdown-emphasis stripping, and (as of this exception)
header-indexed column resolution with a legacy fallback. Splitting the
column-lookup helpers into yet another module would not shrink genuine
complexity — it would relocate three tightly-coupled private helpers
(`_parse_header_row`-equivalent logic, `_row_from_cells`,
`_depends_on_tokens`) that exist ONLY to serve `parse_campaign_skeleton` and
have no other caller, trading one file at 357 lines for two files whose
combined complexity is unchanged and whose read-time cost (two files to
open instead of one) is strictly worse for this narrow a boundary.

## YAGNI Check

Every addition here is load-bearing for R1's stated acceptance criteria: the
header-indexed lookup is what "an existing campaign.md with no `depends_on`
column still parses unchanged" requires; the `depends_on`/`merged_commit`
carry-through in `project_campaign_status` is what R4's state mechanics and
this sub-iterate's own `is_unit_ready` predicate need populated on
`status.json`. Nothing here is speculative scope for a future sub-iterate —
R2 through R6 read this exact shape.

## Chesterton-Fence Check

The file's original 299-line size was never itself an ADR-blessed limit —
it was simply un-flagged because nothing had crossed 300 yet. There is no
prior design decision pinning `campaign_status.py` at exactly 300 lines; the
fence here is the REPO-WIDE 300-line convention, not a file-specific one,
and the convention itself provides the exception mechanism used here rather
than mandating an immediate split.

## Decision

Grant an exception raising `campaign_status.py`'s allowed `current` to 415.
Retirement plan: if `campaign_status.py` gains a FOURTH cross-cutting
concern beyond skeleton-parsing / event-projection / merge-status ladder
(e.g. a second new schema column with its own multi-helper extraction), that
is the trigger to split the header-indexed column-lookup helpers into a
dedicated `campaign_skeleton_columns.py` — re-review this exception at that
point rather than waiting for the calendar date alone.

## Consequences

No downstream consumer's call signature changed except the additive,
default-preserving `project_campaign_status(..., *, skeleton=None)`
parameter — every existing caller (four call sites across `shared/tests`,
plus `regenerate_campaign_status` itself) is unaffected. The bloat-baseline
anti-ratchet now holds this file at 415 as its ceiling; a future PR that
grows it further without its own exception is correctly blocked.

## Rejected alternatives

- **Leave it at the old (unenforced) 300 limit and split immediately.**
  Rejected: no other file naturally hosts `parse_campaign_skeleton`'s
  column-lookup helpers without introducing a new module whose only caller
  is this one function — see the Ousterhout argument above.
- **Move `project_campaign_status` itself into `campaign_graph.py`.**
  Rejected: `campaign_graph.py` already imports `project_campaign_status`
  FROM `campaign_status.py` (`safe_project_campaign_status` wraps it); moving
  the callee into the caller's own module would require restructuring the
  import direction entirely and duplicate `_project_events`/`merge_status`
  reach-across, a strictly worse shape than one small, documented exception.
- **Do a shallow refactor splitting only `_row_from_cells`.** Rejected: that
  helper is three lines: extracting it into its own file for LOC-counting
  purposes alone (not genuine encapsulation) is exactly the kind of
  premature abstraction this repo's own bloat-checklist rejects.
