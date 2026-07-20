# Mini-plan — traceability as a derived view (campaign S7)

**Run id:** `iterate-2026-07-19-traceability-derived-view`
**Campaign:** `2026-07-18-requirements-catalog`, sub-iterate S7 (last)
**Mode:** feature — additive. **Spec impact: none** (no requirement row, title or
acceptance criterion changes; the catalog edit is to the trailing
"Where the work detail lives" prose).
**Complexity:** medium.

## Problem

Campaign decision D4 removed the `Refined by <run_id>` prose blocks from the
requirements catalog, on the stated grounds that the same information already
lives in commits, the changelog and `shipwright_events.jsonl`. S6 executed the
removal and left the catalog saying change history is "answered by querying the
append-only event log" — with no query. The claim was an assertion, and the
pointer was dead.

S7 has two jobs, and the second matters more:

1. Provide the query.
2. **Check the claim** against the history S6 deleted, recovered from git, and
   report the result whatever it is.

## What was built

| Artifact | Role |
|---|---|
| `shared/scripts/lib/fr_change_history.py` | The query. Given an FR id, the recorded changes that named it, ordered by instant. |
| `shared/scripts/lib/_fr_history_events.py` | The read layer — record boundaries, amendments, ordering. Split out to keep both modules under the size limit. |
| `integration-tests/test_fr_history_amendment_parity.py` | Pins the amendment fold to the compliance collector's, so the RTM and this query cannot report different histories. |
| `shared/scripts/tools/fr_history.py` | The reader surface: `uv run shared/scripts/tools/fr_history.py FR-01.11`. |
| `.shipwright/planning/01-adopted/spec.md` | "Where the work detail lives" now names the command, and drops an overclaim (below). |
| `integration-tests/test_fr_change_history_recovers_compacted_history.py` | The verification: recovered-vs-returned, pinned. |
| `shared/scripts/tests/test_fr_change_history{,_records}.py`, `test_fr_history_cli.py` | Library + CLI behaviour. |

### Three outcomes, never two

The campaign's recurring defect is an empty set read as a positive claim. The
query reports a **status**:

- `found` — the log names this requirement. If it is not a live catalog row it
  is a **retired** requirement: still answered, flagged `in_catalog=False`.
- `no_recorded_changes` — the requirement exists; nothing recorded names it. A
  legitimate answer, rendered as "No recorded changes.", exit 0.
- `unknown_requirement` — the id names no live row **and** appears in no event.
  **Exit 3**, stderr.

Exit 3 rather than 2 because argparse owns 2 for a malformed command line; a
caller that could not distinguish "you typed the flag wrong" from "that
requirement does not exist" would be back to guessing.

Existence can itself be unverifiable (no planning tree, or specs parsing to zero
rows). That degrades to `existence_verified=False` and the id is NOT called
unknown — mirroring the graduated write-side policy in `lib/fr_gates.py`, so the
read side cannot be stricter than the gate that admitted the data.

## The finding — D4's claim does not hold for the event log alone

Recovered from `git show 5eef5076:.shipwright/planning/01-adopted/spec.md` (the
pre-S6 commit), not from the S6 ADR's summary. The blocks named **ten
(requirement, run id) pairs across nine distinct run ids** —
`iterate-2026-05-16-backfill-historical-frs` was named by both requirements.
Counted as pairs:

- **5 returned verbatim** by the query.
- **1 present under its pre-run-id label** — `iterate-20260505-plugin-hook-registration`
  is in the log as `ADR-030`; the event log only began carrying run-id-shaped
  `adr_id` values on 2026-05-16. The correspondence is asserted against the
  event's own description, not assumed.
- **4 pairs name no event at all**, across 3 distinct run ids (the backfill run is absent for both requirements): `iterate-2026-05-16-backfill-historical-frs`,
  `iterate-2026-05-19-github-triage-importer`,
  `iterate-2026-05-20-triage-launch-surface`. Each has a commit, so the work
  shipped — it was simply never recorded against the requirement.

D4 named three sources (commits, changelog, event log) and the disjunction
survives: all three absent run ids are recoverable from commit messages and
planning documents. But the event log is not the complete index D4 implied, and
S7's own acceptance criterion — that the query return at least the removed run
ids — **is not met**. That gap is pinned in the integration test, in both
directions, so it cannot silently drift or silently re-green.

Measured coverage: **61 of 342** recorded changes name any requirement (18%).
The CLI reports this next to every answer, so a short history reads as thin
coverage rather than as a stable capability.

## Second finding — an overclaim in the catalog

S6 wrote: *"Every completed change records the requirements it affected and the
ones it introduced."* Measured, that is false (18%). Corrected, and pinned by
`test_the_catalog_does_not_promise_coverage_the_log_does_not_have`.

## Event schema

**No new field was needed**, and none was invented to satisfy the option. Every
fact the query requires is already on `work_completed`: identity (`adr_id` /
`run_id`, falling back to `id`), time (`ts`), the FR links (`affected_frs` /
`new_frs`), and a human sentence (`summary`, falling back to `description`).
The genuine weakness — `commit` is populated on 71 of 342 events — is missing
*data*, which a new field cannot retrofit.

## Deliberately not done

- **No RTM rendering.** It would regenerate a churn artifact on the final PR of a
  six-step campaign, for a surface the CLI already provides. Its own decision.
- **FR-01.15 is left as it is.** The query shows it `introduced` once and never
  affected since, which is exactly what compliance D1/D3 report. Making it
  legible is the job; clearing it is not.
- **No backfill of the three missing events.** Writing events dated today for
  work done in May would forge the audit trail this campaign exists to protect.

## External plan review (ADR-029, Step 3.5)

OpenRouter, both legs substantive — neither degenerated. Nine findings; the
dispositions that changed code:

| # | Finding | Disposition |
|---|---|---|
| Gemini 3 / GPT 3 (M) | Judging on the live catalog blocks querying a **retired** requirement — it would answer "no such requirement" about one that demonstrably existed. | **accepted-and-fixed.** Real defect, confirmed: `collect_requirements_from_planning` projects `read_active_fr_rows`, so retired rows are absent. The log is now asked first and outranks the catalog; typo detection survives because a typo appears in neither. |
| Gemini 2 (H) | Documenting the coverage gap only in a test still leaves the reader a lossy tool. | **accepted-and-fixed.** Partial coverage now prints where the missing history actually is (commit log + planning doc). A `git log --grep` union was rejected as scope creep and fragile. |
| GPT 8 (L) | Free-text summaries printed raw permit terminal spoofing. | **accepted-and-fixed, then RETRACTED AND RE-FIXED in round 2.** The first fix applied `strip_control_chars` inside the summary wrapper only and claimed "newlines already collapsed by `split()`" — true for that one field of six, and only because its renderer happened to split. `tty_sanitize` deliberately PRESERVES `\n` and `\t`, so stripping alone never stopped a newline in `adr_id` from forging a numbered row. Sanitising now happens at the boundary (`_clean`) with whitespace folding, over every field including argv. |
| Gemini 1 / GPT 5 (H/M) | A partial trailing record during concurrent append. | **accepted-and-fixed** in reporting: already non-crashing via the shared reader, but fragments were silently swallowed. They are now counted and surfaced. |
| GPT 9 (L) | The coverage figure reads as an audited metric. | **accepted-and-fixed.** Labelled as a snapshot of this tree's log at read time. |
| GPT 1 (H) | The AC is not met; do not present it as complete. | **accepted** — reported as not met, here and in the return value. **Rejected**: writing reconciliation events. Appending records today for May work would forge the audit trail this campaign protects. The AC/D4 amendment is an operator decision, escalated rather than self-granted. |
| GPT 2 (M) | The `ADR-030` alias is asserted from prose. | **rejected-with-reason.** The CLI claims no alias — it returns the event's own id. The mapping lives only in the test, backed by the event's description. Adding a schema alias field would invent data the log does not carry. |
| GPT 4 (M) | Ordering underspecified for ties/malformed. | **already-addressed**, and now tested: instant order, event-id tie-break (total), malformed sorts last but is still reported. |
| GPT 7 (L) | The git-provenance test breaks on shallow clones. | **already-addressed** — skips with a reason; expectations are committed constants, not fetched. |

Self-review additionally caught a defect no reviewer raised: the CLI read the
event log **twice** (history, then coverage) and printed the two beside each
other as one answer. On an append-only log being written during the campaign,
that pair can describe a state the log was never in. Collapsed to one read and
pinned by counting reads, not by comparing values.

## Verification

- **191 tests** across fourteen modules (plus two data/helper modules); the
  three new library modules are at 100% line coverage each.
- **43 mutations across six rounds and one inline check, all killed** (one
  deliberate no-op control survived, as designed; two apparent survivors turned
  out to be no-op mutations that never applied — see Round 5).
  Stated as a sum so it is checkable rather than asserted: **9 + 8 + 1 + 11 + 8 + 4 + 2 = 43**.
  - *Round 1 (9)* — unknown-FR branch removed; lexicographic sort; amendments
    skipped; line-at-a-time read; relation collapsed; substring FR match;
    exit-code collision; silent empty history; UTF-8 pin removed.
  - *Round 2 (8)* — catalog outranking the log; unknown branch removed;
    fragments swallowed; control chars unstripped; missing git pointer; missing
    retired banner; amendment divergence; missing fragment warning.
  - *Inline (1)* — the single-read invariant reverted to two reads.
  - *Round 3 (11)* — ADR table edited to the retracted value (the reviewer's own
    reproduction); a recovered run id dropped from the tables; wrong block count;
    coverage figure drift; commit-population drift; existence sentence printed
    unconditionally; sanitising reverted to summary-only; whitespace collapse
    removed; `OSError` swallowed; fragment counting removed; documented command
    deleted from the catalog.

  - *Round 4 (8)* — provenance skip-hatch restored; a deliberate no-op control
    (survived by design, proving the battery is not trivially green); mini-plan
    sum falsified; a round removed from the enumeration; retracted technical
    claim restored; reachability test stripped of its unconditional leg;
    documented command deleted from the catalog; superseded-measurement
    allowance widened until a stale figure reads as current.

  - *Round 5 (4)* — adjacent literals reintroduced into a display list; the
    fold truncating an over-long token; the two wrappers drifting apart; the
    provenance skip hatch restored.

  - *Round 6 (2)* — the display-literal detector reverted to the line-span
    heuristic (misses the single-line form); `_fold` breaking one character
    early.

  The previous figure said "28 across three rounds" while enumerating only two,
  which is the same unverifiable-published-number class as "six returned
  verbatim". The per-round counts are given so the total can be re-added.
- `no_recorded_changes` is fixture-driven on purpose: every requirement in this
  repo has events, so that branch has no live example — and a branch with no
  example is one nobody has watched run.
- The published counts (pairs vs distinct run ids) are pinned as DATA against the
  tables. A first draft published "six returned verbatim" against a table holding
  five, by subtracting distinct absent ids from a pair total; the suite was green
  throughout because nothing pointed at the arithmetic.
- The parity test's **first version skipped all seven cases** (relative imports,
  no parent package) — a green asserting nothing. Rewritten to subprocess
  isolation and given a guard test so it cannot go vacuous again.
