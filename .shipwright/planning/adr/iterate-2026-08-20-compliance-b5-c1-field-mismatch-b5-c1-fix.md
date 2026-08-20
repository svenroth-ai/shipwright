# Fix B5 phase-task field mismatch and C1's column-count-brittle Screens parser

## Context

A user-reported bug (already investigated and written up as ADR-037/ADR-038
in a downstream adopted project, but never fixed upstream because the fault
is in this shared plugin) described two independent compliance-audit false
positives:

- **B5** (`plugins/shipwright-compliance/scripts/audit/group_b.py`) read
  `task.get("id")` from `phase_tasks` entries, but every producer
  (`phase_task_lifecycle.py`, `single_session_loop.py`, `config_factory.py`)
  writes the schema-required field `phaseTaskId`
  (`shared/schemas/run_config.v2.schema.json`, pattern `^ptk-[0-9a-f]{4,}$`).
  B5 therefore reported "no matching task" for every completed phase in every
  project, unconditionally.
- **C1** (`shared/scripts/tools/verifiers/design_checks.py`,
  `check_design_fr_coverage`) parsed the design-manifest `## Screens` table
  with a regex anchored to an exact 5-column layout. Any manifest with an
  extra column (the reported case: a "Split" column distinguishing
  frontend/backend screens) made every row fail to match, so the parser
  silently produced zero rows and every declared FR was reported as
  "no screen mapping" — including FRs a project had deliberately decided
  (via its own ADRs) were backend-only and would never have a screen.

Both were reproduced empirically with real schema-shaped fixtures before any
fix was written (TDD Iron Law), not merely inferred from the report.

## Decision

**B5**: one-line field-name fix, `task.get("id")` → `task.get("phaseTaskId")`.
The existing regression tests' fixtures used the buggy field shape
(`"id": "build:01"`), which is why the bug survived — fixtures were rewritten
to the schema-correct shape (`"phaseTaskId": "ptk-a1b2c3d4"`).

**C1**: rewrote the Screens-table parser to locate the "File" and "Linked
FRs" columns by **header name** rather than position, so an inserted column
no longer zeroes out parsing. Added a new, optional `## Non-UI FRs` manifest
section: an FR listed there with a cited `ADR-NNN` is exempted from the
screen-mapping requirement, closing the second half of the report (backend-
only FRs being misreported as violations) without weakening the gate for FRs
that have no such waiver.

**Extraction**: the new parsing + coverage-summary logic was extracted into
a new sibling module, `shared/scripts/tools/verifiers/design_screens_parser.py`,
instead of growing `design_checks.py` in place — that file is pinned at its
current line count in `shipwright_bloat_baseline.json`, and the established
mitigation pattern for a bloat-capped file is a new sibling module (see
`shared/glossary.md`, Anti-Ratchet). `design_checks.py` net-shrank from 342
to 282 lines; the stale baseline entry was removed as part of this same
change since 282 < 300 no longer needs a pin.

**Header-matcher hardening**: three real ambiguity bugs were found and fixed
across internal + external review (see Learnings below) before the header-
name approach was considered safe to ship: a loose `file|screen` pattern
matching the wrong column, a bare `\bfr\b` matcher shadowed by an earlier
unrelated "FR Status"-style column, and a missing word-boundary letting
"Unlinked FRs" match a pattern meant for "Linked FRs".

**Deliberately NOT fixed**: external review (openai, round 4) pointed out
that `parse_screens_table` returning `[]` conflates "the table is
syntactically valid but genuinely has zero rows" with "the table's
header/columns could not be identified at all" — `summarize_fr_coverage`
cannot tell these apart and its diagnostic wording is accordingly
non-committal ("empty table, or unrecognized manifest format") rather than
picking one. The reviewer's suggested fix (a richer parser-result type, e.g.
`table_found_and_valid: bool`) was not implemented in this run.

## Rationale

The wording was softened (from "check manifest format" to "empty table, or
unrecognized manifest format") to at least stop the message from
overclaiming a diagnosis it doesn't have — the reviewer's own framing of this
as "low severity" and "optional" was taken at face value given three points:
(1) `check_design_manifest_screens_exist`, an untouched sister function in
the same file, has the exact same rows-vs-empty ambiguity and shipped that
way already — fixing it only in the new function would leave the codebase
internally inconsistent; (2) a parser-result-type refactor changes a public
function's return contract (`parse_screens_table` is called from more than
this one gate) and is a larger structural change than a "small"-complexity
bug-fix iterate's scope; (3) YAGNI — no report or user complaint has actually
hit this specific ambiguity (unlike the two bugs in the original report,
which were both empirically confirmed against real manifests).

## Consequences

- B5 and C1 both now correctly report zero false positives against the
  real (schema-correct, multi-column) inputs that triggered the original
  report.
- A project can now formally waive the Non-UI FR requirement per-FR, with
  an auditable ADR citation, instead of every audit run re-surfacing an
  intentional design decision as a violation.
- `screen_registry.py`'s `write_manifest` does NOT preserve a hand-added
  `## Non-UI FRs` section on regeneration — filed as triage item
  `trg-44f49504` rather than fixed in this run (out of scope: this run
  fixes the *reader*, not the *writer*, of the manifest format).
- The `rows == []` diagnostic-ambiguity in `summarize_fr_coverage` (and its
  pre-existing twin in `check_design_manifest_screens_exist`) remains,
  documented here for any future iterate that wants to pick it up.

## Rejected alternatives

- **Fix in the downstream project instead of upstream**: rejected — the bug
  is in the shared plugin; every project (not just the reporter's) using
  `design-manifest.md` with any non-5-column Screens table, or any
  `phase_tasks` entry (i.e. every project, since this is the schema-required
  field name), hits both bugs. Fixing downstream would need to be re-applied
  after every plugin update.
- **Position-tolerant regex (e.g. allow 5 OR 6 columns)**: rejected — brittle
  in the same way, just with a wider brittle window; the next manifest with a
  7th column reproduces the exact same failure mode.
- **Grow `design_checks.py` in place**: rejected — the file is bloat-capped;
  growing it in place would either ratchet the baseline (against project
  convention) or require a baseline-refresh negotiation for no benefit over
  extraction.
- **Full parser-result-type refactor for the `rows==[]` ambiguity**: deferred,
  not rejected outright — see Rationale above. Left as a documented,
  discoverable gap rather than either silently ignored or scope-crept into
  this run.

## Learnings (bugs found and fixed during review, not in the original report)

1. Self-caught before Stage 1: `_FILE_HEADER_RE` matching `file|screen`
   matched the "Screen" (display-name) header instead of "File" (path),
   since "Screen" contains "screen".
2. Stage 1 spec-reviewer (non-blocking observation), fixed before Stage 2:
   loose `\bfile\b` / `\bfr\b` matchers could still miss "Files" or match
   "Frame"-like headers; tightened to `\bfiles?\b` / `\bfrs?\b`.
3. External review round 1 (openai): a bare `\bfrs?\b` matcher is shadowed
   by an earlier, unrelated column literally containing the substring "FR"
   (e.g. "FR Status"); `_find_column` returns the first match. Fixed by
   trying a `\blinked\s*frs?\b` pattern first via a new `_find_frs_column`
   helper.
4. External review round 2 (openai): the new linked-FRs pattern lacked a
   leading `\b` before "linked", so "Unlinked FRs" (containing "linked" as a
   substring) would incorrectly match. Fixed: `linked\s*frs?\b` →
   `\blinked\s*frs?\b`.
5. External review round 3 (deepseek): a misspelled/stale `## Non-UI FRs`
   entry was silently invisible whenever an unrelated orphan already caused
   `summarize_fr_coverage` to take the failure branch, because the
   stale-entry report only executed on the success path. Fixed by hoisting
   the stale-entry computation above the branch so it appears in both.
6. Self-caught while fixing (3): `_find_frs_column`'s first draft used
   `a or b` to combine the two lookups — broken because a column index of
   `0` is falsy in Python, so a legitimately-found column at index 0 would
   incorrectly fall through to the fallback lookup. Fixed with an explicit
   `is not None` check.
7. Stage 2 code-reviewer: the Step-6 design-manifest template's
   `## Non-UI FRs` example used a realistic-looking `FR-03.01 — ADR-004`
   entry — copy-pasting the template verbatim into a real manifest would
   silently exempt a real FR id. Changed to a deliberately non-parsable
   placeholder (`FR-XX.YY`) that cannot be copy-pasted into a fail-open
   state by accident.
