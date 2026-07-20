# ADR-110 — Change history is a query over the event log, and the log was measured against what it replaced

**Run-ID:** `iterate-2026-07-19-traceability-derived-view`
**Campaign:** `2026-07-18-requirements-catalog`, S7 (last)
**Status:** accepted
**Date:** 2026-07-19

## Context

Campaign decision D4 moved change history out of the requirement text on the
grounds that it already exists in commits, the changelog and
`shipwright_events.jsonl`. S6 executed the removal — FR-01.11 carried six
`Refined by <run_id>` blocks, FR-01.14 five — and left the catalog saying the
question is "answered by querying the append-only event log", with no query.

Two things were therefore outstanding: the query itself, and any evidence that
the claim justifying the deletion was true.

## Decision

Ship the query as `shared/scripts/lib/fr_change_history.py` with a CLI at
`shared/scripts/tools/fr_history.py`, named from the catalog so a reader can
actually reach it. Verify it against the deleted prose **recovered from the
pre-S6 commit `5eef5076`** rather than from any summary of what was removed,
and report the result unmodified.

### Three outcomes, never two

| Status | Meaning | Exit |
|---|---|---|
| `found` | The log names this requirement. If it is not a live catalog row, it is a retired requirement — still answered, flagged `in_catalog=False`. | 0 |
| `no_recorded_changes` | Live requirement, nothing recorded names it. Rendered as "No recorded changes." | 0 |
| `unknown_requirement` | Names no live row **and** appears in no event. | 3 |

Exit 3, not 2: argparse owns 2 for a malformed command line, and a caller that
could not tell "you typed the flag wrong" from "that requirement does not
exist" would be back to guessing. An empty history and a typo must never be
confusable — that conflation is FV-1/FV-2 from the golden corpus, and this
campaign has now met it three times.

## The finding — D4's claim does not hold for the event log alone

The blocks named **ten (requirement, run id) pairs across nine distinct run
ids** — `iterate-2026-05-16-backfill-historical-frs` was named by both
requirements. Counted as pairs:

| Outcome | Count | Detail |
|---|---|---|
| Returned verbatim | 5 | — |
| Present under a pre-run-id label | 1 | `iterate-20260505-plugin-hook-registration` is in the log as `ADR-030`; run-id-shaped `adr_id` values only begin 2026-05-16. Correspondence asserted against the event's own description. |
| **Name no event at all** | 4 | Three distinct run ids: `iterate-2026-05-16-backfill-historical-frs` (absent for BOTH requirements, hence four pairs), `iterate-2026-05-19-github-triage-importer`, `iterate-2026-05-20-triage-launch-surface` |

Each of the three has a commit, so the work shipped — it was never recorded
against the requirement. Pair counts and distinct-id counts differ here and are
stated separately on purpose: a first draft of this ADR reported "six returned
verbatim", arithmetic that subtracted *distinct* absent ids from a *pair* total.
Both counts are now pinned against the tables by
`test_the_published_counts_match_the_tables`.

D4 named three sources and the **disjunction survives**: all three absent run ids
are recoverable from commit messages and planning documents. But the event log is
not the complete index D4 implied, and **S7's own acceptance criterion — that the
query return at least the removed run ids — is not met.**

Measured link coverage: **61 of 342** recorded changes name any requirement
(18%).

This is recorded rather than resolved. Amending D4 or S7's acceptance criterion
is an operator decision, and writing reconciliation events would forge the
audit trail the campaign exists to protect.

## Counting: blocks, run ids, pairs

Three quantities, none equal, all published somewhere:

| Quantity | FR-01.11 | FR-01.14 | Where quoted |
|---|---|---|---|
| `Refined by` blocks | 6 | 5 | ADR-109, the S7 spec |
| Distinct run ids named | 5 | 5 | the recovery tables |
| (requirement, run id) pairs | — | — | 10 across 9 distinct ids |

The block-vs-run-id gap has a different cause per requirement, and neither is a
dropped recovery:

- **FR-01.11** — the third block reads `Refined by BP-1`. BP-1 is a
  baseline-plan identifier, not a run, so it names nothing to recover.
- **FR-01.14** — one `Refined by` is an inline cross-reference to a run id
  another block already owns, and a separate `Backfilled by` marker names the
  fifth.

Left unstated in the first publication, the six-vs-five gap read as a sixth run
id having been omitted — which would have meant the finding above was measured
against an incomplete set. It was not, and `test_no_run_id_in_the_source_was_left_out_of_the_tables`
now asserts set EQUALITY per requirement section, closing the direction the
original provenance check could not see.

## Consequences

- The gap is pinned **in both directions** by
  `integration-tests/test_fr_change_history_recovers_compacted_history.py`. A
  later backfill fails the test and forces a human to update the record; so does
  a regression that loses a currently-returned id.
- The CLI reports coverage beside every answer and points at the commit log for
  what it cannot account for, so the reader is not handed a lossy tool with the
  caveat buried in a test.
- The catalog's claim that *"Every completed change records the requirements it
  affected and the ones it introduced"* is removed as **false**, and its absence
  is pinned.
- Retired requirements stay answerable: the log is consulted before catalog
  membership is judged, because
  `collect_requirements_from_planning` projects `read_active_fr_rows` and would
  otherwise deny a requirement that demonstrably existed.
- Amendment folding is pinned to the compliance collector's by
  `integration-tests/test_fr_history_amendment_parity.py`, so the RTM and this
  query cannot report different histories for one requirement.
- One read per query: history and the coverage figure printed beside it come
  from the same snapshot. The log is appended to while it is read — including by
  this campaign — so two reads could describe a state the log was never in.

## Rejected

- **Writing reconciliation events for the three missing run ids.** Appending
  records today for May work forges the audit trail. Suggested by external
  review (GPT #1) as one of two options; the other — amending the acceptance
  criterion — is the operator's call, so the finding is escalated instead.
- **Unioning `git log --grep` into the query** (external review, Gemini #2).
  Scope creep and fragile matching. The CLI names the command for the reader
  instead of guessing on their behalf.
- **An event-schema alias field for the `ADR-030` mapping** (GPT #2). It would
  invent a mapping the data does not carry. The CLI claims no alias — it returns
  the event's own id; the correspondence lives in the test, backed by evidence.
- **Adding any event-schema field.** Every fact the query needs is already
  present: identity, time, FR links, and a human sentence. The real weakness
  (`commit` populated on 71 of 342 events) is missing *data*, which no new field
  retrofits.
- **Rendering into the RTM.** Regenerates a churn artifact on the final PR of a
  six-step campaign, for a surface the CLI already provides. Its own decision.

## Second review round

Nine further findings; five changed code. Recorded because three of them are
instances of defects this ADR already claims to have removed:

- **The count pin read no document.** It compared a Python dict to Python
  tables while `degraded[]` claimed it "fails if prose and table diverge".
  Editing this ADR's table from 5 to 6 left the suite green. Replaced by checks
  that open the files, plus a detector-fires test so the guard cannot go vacuous.
- **The empty-state asserted existence it never verified** — fourth instance of
  the campaign's signature defect, in the module whose docstring says it exists
  to remove it. `No recorded changes.` printed "This requirement exists"
  unconditionally, contradicting its own NOTE twelve lines later.
- **Sanitising covered one field of six.** `strip_control_chars` ran inside the
  summary wrapper only, so `adr_id`, `commit`, `spec_impact` and `ts` rendered
  raw — and `strip_control_chars` deliberately preserves newlines, so even the
  covered field relied on its wrapper's `split()`. Moved to the boundary, with
  whitespace folding.
- **`OSError` was swallowed into a positive answer**: an unopenable log rendered
  as "No recorded changes.", exit 0, no warning. Now `EventLogUnreadable`, exit 4.

One finding was **rejected on measurement**: catching `UnicodeDecodeError`
alongside `OSError`. The type reasoning is right (it is a `ValueError`), but
`read_jsonl_records` opens with `errors="surrogateescape"`, so it cannot be
raised. The handler was written, probed, found unreachable, and removed — along
with the test for it, which passed by never raising anything.

## Third review round

One blocker and five fail-open holes; all closed. Two are worth recording
because of what they say about the shape of the mistakes here:

- **A frozen denominator on a growing log.** The commit-population check was
  written as `len(events) == 342`. Every iterate's F5b appends a
  `work_completed` event, so the next one — here or merging ahead of this
  branch — would have reddened `integration-tests` for a change that did
  nothing wrong. Ten lines below, a sibling docstring explains exactly why an
  equality pin is wrong. The right design was written and then defeated in the
  same file. Both figures are now monotonic.
- **A test that could skip itself out of existence.** The reachability check —
  the sole coverage of AC-4, and the one a scripted de-duplication had already
  deleted once — gained a `pytest.skip` when it moved to the documented
  `uv run` form. A skipped test fails nothing, exactly like a deleted one. It
  now executes unconditionally via `sys.executable` AND runs the documented
  form, with missing `uv` a hard failure and timeouts on both.

The other four: `pre_s6_sections()` skipped on a shallow clone, silently
deleting the six-node completeness check that is the fix for the headline
finding (now a hard failure with the `fetch-depth: 0` remedy); FR-01.14's
published reason for its block gap was asserted by nothing (now asserts the
`Backfilled by` marker and the four-distinct-ids-from-`Refined by` count); a
retracted TECHNICAL claim stood as current in the mini-plan because the
retraction detector covered only numeric claims (now covers both); and the
mutation total was published as "28 across three rounds" while enumerating two
(now stated as a checkable sum, 9 + 8 + 1 + 11 = 29, with a test that re-adds it).

## What the scanner caught

CodeQL went red on the final commit, after three human review rounds had passed
it. Nine alerts; two were worth acting on, and neither fix is appeasement:

- **One error, a genuine false positive** — "local variable may be used before
  it is initialized", on a guard whose value is bound in the only branch that
  reaches the use, because the other two end in `pytest.fail()`. CodeQL cannot
  see that `pytest.fail` never returns; it carries no `NoReturn` annotation.
  Suppressing was declined. The assertions moved into the handler that binds the
  value, which makes the binding local and obvious to a reader as well — and
  leaves the `BaseException` guard, which is the point of the test, untouched.
- **Seven warnings, ambiguous by construction** — "implicit string
  concatenation, maybe missing a comma?" on hand-wrapped operator output built
  as adjacent literals inside a list of display lines. The intent was correct in
  all seven, but that is *exactly* the shape a real missing comma takes, and a
  silent merge of two output lines is the defect class this change exists to
  remove. Body text is now written as one logical string and wrapped at runtime
  (`_para` / `_fold`), so no display list contains adjacent literals at all. A
  scan of every file this step touched confirms zero remain.

The note ("except block directly handles BaseException") is left standing: it is
the deliberate, documented mechanism that stops a reintroduced `pytest.skip`
from skipping the guard against skipping. Weakening it to satisfy a notice would
reverse the fix.

Extracting the renderer also moved it across the coverage boundary — out of
`tools/` (unmeasured) into `lib/` (measured) — while every test drove it by
subprocess. It reported 30% and took the diff-coverage gate below its floor,
though nothing about its behaviour had changed. CI caught what local F0 could
not. Driving it in-process fixed both: all three new library modules are at
100%.

## Final round

Four fixes, two of which found real defects the guard they belonged to could not
see:

- **The AST guard was narrower than its own claim.** It flagged an element only
  when the literal spanned lines, so `["a" "b", "c"]` — the single-line form,
  and the *more* likely accident, since nobody hand-breaks a forty-character
  string — was invisible, in a module containing exactly that shape. Detection
  now counts string TOKENS, which also stops it false-flagging a triple-quoted
  string. Broadening it to `Dict` immediately caught two more instances the
  original could not reach.
- **Broadening it then over-reached, and that was informative too.** It began
  flagging `("a" "b")` — a parenthesised group, which has no comma-separated
  sibling to merge with and where a stray comma yields a tuple that fails
  loudly. The real rule is not "does it span lines" but "could a dropped comma
  merge two siblings", so explicitly grouped literals stay permitted.
- **The width sweep did not pin the width.** Flipping `_fold`'s `> width` to
  `>= width` breaks one character early on every line and survived the entire
  suite: `<=` assertions are satisfied by a short line, and the parity sweep
  compares two callers of the same `_fold`, so they drift together. Maximality
  is the property that fixes the boundary — for every line but the last, the
  first word of the next must genuinely not have fitted.
- **The library is now safe standalone, not safe by convention.** Extracting the
  renderer put `change_history_for_fr` and `_render_text` in the same package as
  a usable pair, while the queried id was sanitised only by the CLI. A caller
  skipping the CLI could put a raw escape in the heading. `_clean` on a
  well-formed id is identity, so the fix is behaviour-neutral — and it makes the
  module docstring's "applied to EVERY field at the boundary" true of the one
  field it did not cover.

Both "which files does this campaign step own" lists are now **derived from a
filename rule** rather than hand-maintained. Two hand-kept copies had already
drifted after one round, each missing a module the other had; a glob cannot.

## Honest limits

- Coverage is a snapshot of this tree's log at read time, not an audited figure.
- The `ADR-030` correspondence rests on the event's description text. That is
  evidence, not a structured link, and it is labelled as such wherever it appears.
- This run's own `work_completed` event records the coverage measurement as
  `60 of 341` while every document says `61 of 342`. **Both are correct**: the
  event states the measurement as of the moment before it was appended, and
  appending it is precisely what moved the count. It is left unamended. The log
  is append-only, and rewriting a true record so it agrees cosmetically with a
  later one is the class of edit this campaign exists to prevent — the divergence
  is recorded here instead.
- `no_recorded_changes` has **no live example** in this repo — every requirement
  here has events — so it is exercised only by fixtures. A branch with no example
  is a branch nobody has watched run, which is why it carries dedicated tests and
  a mutation check rather than being taken on faith.
