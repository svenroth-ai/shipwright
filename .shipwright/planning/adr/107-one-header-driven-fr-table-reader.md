# ADR 107 — One header-driven FR-table reader; ADR-031 revised

- Run-ID: `iterate-2026-07-20-one-header-driven-parser`
- Campaign: `2026-07-18-requirements-catalog` — sub-iterate **S4**
- Revises: **ADR-031** (FR-table parser accepts 5-col adopt format + drift protection)
- Cites as falsifying evidence: **ADR-048** (brownfield RTM "Traceability coverage 0%")
- Triage closed: `trg-9532fa83` (FV-3 / FV-4 / FV-5)
- Mode: change · Spec Impact: **none** · Complexity: medium

## Context

Five parsers read the same `spec.md` FR table:

| # | Parser | Mode |
|---|---|---|
| 1 | `drift_parsers.parse_fr_table` | positional |
| 2 | `rtm.collect_requirements` | positional — regex byte-identical to #1; the surrounding removed-section loop a semantic clone nothing enforced |
| 3 | `_requirement_parse.parse_requirements` | header-driven, strict ids |
| 4 | `group_i._scan_one_spec` | header-driven, medium ids, `cells[0] == "id"` required |
| 5 | `_backfill_spec_parse.parse_frs` | header-driven, strict ids |

They disagreed on **seven** axes: id strictness (three tiers), column selection,
column-map lifetime, invalid priorities, escaped pipes, row recognition, and
fold-map skipping. Four documented false verdicts followed — FV-1 (a populated
spec parsing to zero rows makes traceability check T1 SKIP rather than FAIL),
FV-3 (the RTM displays the WRONG requirement text when a row is wider than its
header), FV-4 (Group I audits NOTHING when a header says `FR` instead of `ID`),
FV-5 (Group I drops every FR row under a later heading) — plus ADR-048's
brownfield RTM reporting "Traceability coverage 0%".

## Decision

**One reader**: `shared/scripts/lib/fr_table_reader.py`, with row mechanics in
the neutral leaf `shared/scripts/lib/_fr_table_cells.py`. All five call sites
project from it; none parses. Both positional regexes and both removed-section
loops are deleted. Each caller keeps only its own return TYPE — those are five
genuinely different public contracts with existing consumers, and converging the
type is S5/S6 work, not S4's.

### The seven convergence rules

| # | Axis | Rule | Why |
|---|---|---|---|
| C1 | Id strictness | `requirement_model.CANONICAL_FR_RE`, a FULL match of the trimmed cell | Manifest schema v3 (S3) derives a requirement's namespace from the id's group digits; only the two-digit form makes that derivation total. Full-cell anchoring keeps `FR-01.01-extra` and prose mentions out |
| C2 | Column-map lifetime | Set by a header row, survives headings, replaced by the next header | `_requirement_parse`'s rule. group_i's reset-at-every-heading IS FV-5. Safe against capturing an unrelated later table because C1 requires a canonical id in the FIRST cell |
| C3 | Unrecognised priority | Case-normalise, then coerce to `Must` | Dropping a requirement over a typo is the same silent-loss class this campaign exists to remove; `Must` never downgrades scrutiny |
| C4 | Escaped pipes | Split on unescaped pipes and unescape in ONE pass — the exact inverse of `markdown_table.escape_cell` | The producer writes that escape; a reader that splits on every pipe truncates the text. See "What the probe found" below |
| C5 | Row recognition | Stripped line starts with a pipe; a missing closing pipe does not drop the row | Majority (3/5); an anchored start-of-line pipe drops legitimately indented GFM tables |
| ~~C6~~ | Headerless fallback | **WITHDRAWN** (see round 2) — a row with no governing header is recorded, never emitted | Both external plan reviewers argued against it; the composition route below made it decisive |
| C7 | Fold-map lines | Always skipped | Load-bearing *because of* C3: without it, coercion would resurrect every folded alias id as a live requirement demanding coverage |
| C8 | Minimum row width | **RE-DECIDED** (see round 2) — a row must be wide enough to reach the Priority column its own header declares; narrower rows are recorded | First written as "no minimum". A text-less requirement is loud in the RTM and a dropped one is silent — but recording it keeps that property without admitting foreign rows |
| C9 | Removal sections | `## Removed Requirements` (any level) sets `status="removed"` until a same-or-shallower heading; rows are emitted with the status, never dropped by the reader | All five agreed already, but nothing enforced the clones. Putting it in the reader's contract makes "keep them in sync" unnecessary |
| C10 | Table governance | A requirement row must sit under a header naming a Priority column. A non-separator table row that names none INVALIDATES the map — we have left the requirements table | Round 2. What ends a requirements table is another TABLE, not a heading; this is width-independent, which a bound alone is not |

## Round 2 — the composition route (found in external code review)

C2, C3 and C8-as-first-written are each defensible and **composed into a
false-requirement route that was analysed nowhere**. Given a second, FR-id-keyed
table under a later heading:

```
| ID | Requirement | Priority |
| FR-01.01 | real requirement | Must |

## Coverage summary

| FR | Result |
| FR-01.01 | pass |
```

`## Coverage summary` is a heading, so the column map deliberately survived it
(C2 — the FV-5 fix). `| FR | Result |` names no Priority column, so the map was
not replaced either. `| FR-01.01 | pass |` then had a canonical id in `cells[0]`,
was emitted as a requirement with `text="pass"`, took a coerced `Must` (C3), and
survived at all only because C8 had removed the cell floor.

**All three guards that independently blocked this were removed by the same
change** — drift/rtm's positional `Must|Should|May` in data column 3,
`_requirement_parse`'s `len(cells) < 3` floor, and group_i's
reset-at-every-heading. Three redundant guards went at once and their shared duty
went with them; that is the general lesson, not the specific table.

**Blast radius:** `build_requirement_index` raises `DuplicateRequirementId` — a
hard manifest-build failure — naming the SAME file twice and telling the operator
to "renumber one of the two rows", which is unactionable when the second row is a
coverage table. Group I's I4 fails. The RTM renders FR-01.01 twice, one with the
text `"pass"`.

**Note the shape of the risk.** C7 protects the one FR-id-keyed table this repo
knows about (`## FR-Fold-Map`) **by name**, and C7's existence is itself proof
that such tables occur. Every other one was unprotected.

**Two mechanisms, because one is not enough.** A width bound alone fails the
three-column variant (`| FR | Result | Notes |`), and header-governance alone
fails the variant where the foreign table has no header row of its own and
inherits a stale map. Both are implemented; both are probed.

**The conflict, resolved explicitly rather than silently.** The width bound hits
C8's pinned `| FR-01.01 | ragged |` case in the `malformed` fixture. C8 is
therefore RE-DECIDED, not quietly overridden: its argument was "a text-less
requirement is loud in the RTM, a dropped one is silent", and the `invalid_ids`
accumulator preserves exactly that property — the row is still reported — while
"keep it as a REQUIREMENT" does not survive. The corpus cell moved with it.

**Consequence, stated not absorbed:** `malformed` now holds only ONE FR-01.01
row, so it no longer reaches Group I's I4 duplicate branch. That branch keeps
direct coverage in `test_audit_group_i.py::test_duplicate_fr_id_is_reported`, so
this is a documented reduction in corpus coverage, not an unguarded path.

**A regression the probes caught.** Withdrawing C6 broke the BOM probe: a UTF-8
BOM is not whitespace to `str.strip()`, so a BOM'd first line does not start with
`|`, its table header was invisible, and the whole first table had been surviving
only via the positional fallback. Fixed at the source (`content.lstrip("﻿")`)
rather than by weakening the probe.

## Why ADR-031's premise is falsified

ADR-031 rejected header-driven parsing as *"over-engineered for two known
formats with stable column orders"* and rejected consolidation as *"a bigger
structural change; deferred"*, relying on a drift-protection test to guard the
duplication meanwhile.

- **"Two known formats"** — there are five: greenfield template, greenfield
  example (no `Layers`), adopt 5-column on disk, adopt 6-column writer, and the
  traceability-fixture shape headed `FR`.
- **"Stable column orders"** — the live monorepo spec is already stale against
  its own generator (5 columns on disk, the writer emits 6).
- **The prediction lost twice in shipped artifacts** — ADR-048's 0% coverage,
  and FV-3's wrong requirement text in a published RTM.
- **The drift guard protected less than it looked** — it pinned the two
  REGEXES only. The removed-section loops around them were never covered, and
  the three header-driven parsers that grew up alongside were never in scope.
  A guard over 2 of 5 implementations, on 1 of 2 halves each, read as
  protection for 14 months.

## What the confidence-calibration probe found

The stated boundary is the `spec.md` FR table: producer
`markdown_table.escape_cell`, consumer this reader. A round-trip probe was run
through the **real producer** rather than hand-written escape fixtures. It
**failed 4 of 12 cases on the first run**.

`escape_cell` emits `\` → `\\` *before* it emits `|` → `\|`. A reader that
undoes only the pipe returns every backslash in the value doubled, so any
Description holding a path or a regex came back wrong. **Four of the five
parsers S4 replaced had this defect, and none had a round-trip test to reveal
it** — the hand-written fixtures had passed for months because they only ever
prove the reader agrees with the test author.

Writing the fix exposed a second defect: a `(?<!\\)\|` lookbehind mis-reads
`a\\\|` — an *escaped backslash* followed by a *real* separator — calls the
separator escaped, and silently merges two columns. Splitting and unescaping in
one left-to-right pass cannot make either mistake.

Probe 2 (same round-trip, re-run): 12/12. Probe 3 (column integrity, 144
combinations of adversarial values asserting the columns *after* them stay
intact): 144/144. Two consecutive clean probes — asymptote reached. Probes 1
and 3 are now permanent tests.

## The S3-inherited obligation: premise falsified, deliberately NOT implemented

S3 recorded that only the `## Removed Requirements` heading sets
`status="removed"`, that the inline `**REMOVED** by` marker this repo actually
uses "still parses as active", and left S4 to recognise both forms.

**Investigated and rejected on evidence.** The repo's single marker
(`.shipwright/planning/01-adopted/spec.md:198`) sits inside the prose refinement
section headed `### FR-01.01 — /shipwright-run` and retires a **sub-behaviour**
— the multi-session execution mode — not the requirement. FR-01.01 is
`/shipwright-run` itself, `Must`, with an untouched and correct table row.

Implementing the inherited reading would have dropped the orchestrator from
every live requirement set, RTM and coverage gate: a far worse false verdict
than the one it was meant to fix. There is no second removal form —
`path-b-change.md` step REMOVE defines exactly one (move the row into a
`### Removed Requirements` subsection with `status: deprecated`) and the marker
is not an attempt at it. No `### Removed Requirements` section exists in this
repo because nothing has been removed.

Pinned by
`test_fr_table_reader_contract.py::test_an_inline_removed_marker_does_not_retire_the_requirement`
so a later step cannot re-adopt the reading. Campaign SPEC §2.5 corrected.

## Consequences

- FV-1, FV-3, FV-4 and FV-5 flip. `golden.json` and `frozen_bugs.py` are
  updated **in this same commit** with a `--reason`; FV-2 stays frozen for S6;
  `absent` still SKIPs. Every moved golden cell is attributed to a named FV or
  convergence rule — see the mini-plan.
- A flipped frozen-bug entry is EDITED, never deleted: it keeps its mechanism
  and gains `state`, `flipped_in` and `now`, so the golden diff that moved those
  cells stays explained. Enforced by a test.
- `test_fr_table_drift_protection.py` retired; replaced by a contract suite, a
  probe suite and an import-style matrix (60 assertions).
- `drift_parsers` 409 → 383 lines; the bloat baseline is ratcheted DOWN.
- `test_group_d_hardening.py` (332 lines, unbaselined — left by S3 where CI's
  anti-ratchet cannot see it) split into two cohesive modules, not baselined.

## Round 3 — two anti-ratchet violations I introduced while fixing round 2

The round-2 fix commit ratcheted two baselined files, and CI had passed on the
PREVIOUS commit so nothing surfaced it until the orchestrator ran the gate:

| path | baseline | measured | state |
|---|---|---|---|
| `collectors/test_links.py` | 302 | 307 | grandfathered |
| `tests/test_data_collector.py` | 1253 | 1278 | exception, ADR-092 |

Both came from work that was *required* — the `invalid_ids` accumulator and its
tests. That does not make them exempt. **An `exception` state with an ADR
licenses a file's EXISTING size; it never licenses growing it.** Fixed by
shrinking and splitting, with no `current` bumped:

- **`test_data_collector.py` 1278 → 1029.** The four `TestCollectRequirements*`
  classes (247 lines) moved to `test_data_collector_requirements.py` (271). The
  seam is cohesive and is exactly the surface S4 changed: everything there
  answers "given a spec.md, which FR rows does the collector see, and what text
  does it take?", while the parent keeps configs, splits, sections, decisions,
  dependencies, SBOM/licence and event-log joins. Shaving 25 lines to squeak
  under would have been the dishonest fix on a file already at 1253.
- **`test_links.py` 307 → 279.** `build_requirement_nodes` (plus `_LAYER_ORDER`
  and `_cov_status`, which only it uses) moved into
  `_test_links_requirements.py` (146 → 195). That module already owns the
  requirement INDEX, so shaping a requirement's manifest NODE belongs beside it;
  `test_links` keeps tag collection, fold resolution and assembly. The one test
  importing `_cov_status` follows it to its new home. The `invalid_ids` comment
  was also folded into the adjacent `fold_map` comment, which stated the same
  omitted-when-empty churn rule twice.

**No bloat-exception ADR was written.** The template demands a deep-module
argument, and neither file has one available: a test module and a collector are
not Ousterhout deep modules whose interface is small relative to their
implementation. I refused that argument for `drift_parsers` earlier this
campaign and the same refusal applies here.

Verified: `anti_ratchet_check.py --worktree` reports `"status": "ok"`, zero
ratchets, zero new crossings. Both splits preserved every test exactly — 102
before, 102 after, measured by running the affected files at the pre-split
commit and again after.

## Residual risk — declared, not hidden

C1 opens a **new** route to a zero-row parse: a spec using only non-canonical
ids parses to zero rows and T1 SKIPs again. C10 adds a second such route (a
requirements table with no Priority-bearing header). S4 removed FV-1's
**trigger**, not its **guard** — `check_t1_all_spec_frs_mapped` still cannot
distinguish "no spec" from "spec I could not read".

**CORRECTED in round 2.** This ADR, the mini-plan and `frozen_bugs.py` all
routed the mitigation to S5's acceptance criterion, which read *"`_column_map`
distinguishes 'no spec on disk' from 'spec present, no recognised header'"*.
**That AC does not cover the C1 route.** There the spec IS on disk and the
header IS recognised — `_header_map` fires on any row naming a Priority column —
and only the row ids fail. S5 would have shipped, satisfied its own AC, and left
the route open: a declared safety net pointed at the wrong hole, for the
campaign's own §6.1 catastrophic risk. S5's AC has been amended to name the
third state explicitly ("spec present, header recognised, no row id matches the
canonical form"), and triage anchor `trg-5f2037b7` filed against the tracked
log so the "triaged" half is verifiable rather than asserted.

What makes these routes DIAGNOSABLE in the meantime is the `invalid_ids`
accumulator: every declined row is recorded with a reason and published on the
manifest, so a zero-row parse can be told apart from an empty repo by looking.

## Rejected alternatives

- **Keep the duplication behind the drift-protection test** — that plan held
  for 14 months and covered 2 of 5 implementations on 1 of 2 halves each.
- **Migrate all callers to one return type** — five genuinely different public
  contracts; converging the shape is S5/S6.
- **Treat the inline `**REMOVED**` marker as a row tombstone** — falsified
  above; would delete a live `Must` requirement.
- ~~**A reader-side parse-metadata accumulator for diagnosability** (raised in
  external plan review) — an accumulator nothing reads is dead surface, and the
  visibility work is S5's AC.~~

  **REVERSED in round 2, and the stated reason was factually wrong — recorded
  rather than quietly edited out.** `_requirement_parse.parse_requirements`
  already threaded exactly this shape via `invalid_layers`, and
  `collectors/test_links.py` already published it on the manifest. A reader for
  an `invalid_ids` accumulator therefore existed *before* the objection was
  written; "nothing reads it" was not true. It rides the same wire for ~8 lines.

  The need is concrete, not hypothetical: `generate_adoption_artifacts` emits
  `f"FR-01.{i:02d}"` with **no cap on `i`** (same in `feature_inferrer`), so an
  adopted repo with more than 99 detected routes emits `FR-01.100` — accepted by
  the pre-S4 loose regex, declined by the canonical tier, and until now dropped
  in silence with no N→0 detector anywhere downstream (`traceability_checks`
  SKIPs, Group I skips all four checks, and `_group_d_traceability` on an empty
  manifest returns **pass** with the literal claim "every active FR is covered at
  its required layers"). Generator cap filed as `trg-c9669d6a`.

  The accumulator also closes the one residual harm of C3: the RTM can publish a
  coerced `Must` the author never wrote, and now something records that it was
  invented.

- ~~**Drop the headerless fallback entirely** (raised by both external
  reviewers) — it would convert a degraded read into a silent zero-row parse,
  the exact failure class being removed.~~

  **REVERSED in round 2 — the reviewers were right.** The objection assumed the
  drop would be *silent*; with the accumulator it is not, which removes the only
  argument for keeping it. And the fallback was itself half of the composition
  route: a stale column map plus a positional guess is what let a headerless
  foreign table yield requirements. Both writers always emit a header, so this
  was a degraded mode rather than a format.
