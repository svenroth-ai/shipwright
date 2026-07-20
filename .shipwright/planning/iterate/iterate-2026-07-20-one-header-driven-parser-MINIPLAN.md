# Mini-Plan — S4: one header-driven FR-table reader

- **Run ID:** iterate-2026-07-20-one-header-driven-parser
- **Campaign:** 2026-07-18-requirements-catalog (S4)
- **Mode:** change · **Spec Impact:** NONE · **Complexity:** medium

## Problem

Five independent parsers read the same `spec.md` FR table. They disagree on
**seven** axes (id strictness, column selection, column-map lifetime, priority
handling, escaped pipes, row recognition, fold-map skipping). Four documented
false verdicts (FV-1, FV-3, FV-4, FV-5) are consequences of that divergence, and
ADR-031's stated premise — "two known formats with stable column orders" — is
empirically false: there are five formats, and ADR-048 records a brownfield RTM
reporting "Traceability coverage 0%".

## Change

One reader, `shared/scripts/lib/fr_table_reader.py`, returning `FrTableRow`.
The five parsers keep their own return TYPES (they are different contracts) but
lose their parsing logic entirely — each becomes a projection of the shared row.

## Convergence decisions (each axis gets exactly one answer)

| # | Axis | Rule chosen | Why |
|---|---|---|---|
| C1 | FR-id strictness | strict `CANONICAL_FR_RE` — a FULL match of the trimmed cell against `^FR-\d{2}\.\d{2}$`, never a search or prefix | S3 derives the manifest namespace from the id's group digits; only the two-digit form makes that derivation total. Full-cell anchoring is what keeps `FR-01.01-extra` and prose mentions out |
| C2 | Column-map lifetime | set by a header row, persists across headings, replaced by the next header | `_requirement_parse`'s rule; group_i's reset-at-every-heading IS FV-5. Safe against capturing an unrelated later table because C1 requires a canonical id in the FIRST cell |
| C3 | Unrecognised priority | case-normalise, then coerce to `Must` | dropping a requirement over a typo is the same silent-loss class the campaign exists to remove; `Must` never downgrades scrutiny |
| C4 | An escaped pipe in a cell | split on UNESCAPED pipes only, then turn the two-character sequence backslash-pipe into a literal pipe in the value. Other backslashes are left exactly as written | `markdown_table.escape_cell` is the producer that writes that escape; splitting on every pipe breaks the round-trip and truncates the text. Not unescaping other backslashes keeps a Windows path in a hand-written cell intact |
| C5 | Row recognition | the stripped line starts with a pipe character; a missing closing pipe does not drop the row | majority (3/5); an anchored start-of-line pipe drops legitimately-indented GFM tables |
| C6 | Headerless fallback | body = `cells[1]`, priority = `cells[2]`, layers = `cells[3]` | majority; both writers always emit a header, so this path is a degraded mode, not a format |
| C7 | Fold-map lines | always skipped | load-bearing under C3: without it, coercion would resurrect every folded id as a live requirement |
| C8 | Minimum cell count | **none** — a canonical id in the first cell is sufficient, down to a one-cell `\| FR-01.01 \|` row | the id IS the declaration; `_requirement_parse`'s ≥3 floor silently dropped one. A text-less requirement surfaces in the RTM as a loud, actionable defect; a dropped one surfaces nowhere. (Wording corrected after external code review caught it saying "an id plus anything", which the code never did) |
| C9 | Removal sections | a `## Removed Requirements` heading (any level) sets `status="removed"` until a heading of the same or shallower level; rows are EMITTED with the status, never dropped by the reader | all five agreed on this already, but the deleted loops were semantic clones nothing enforced. Putting it in the reader's contract is what makes "keep them in sync" unnecessary. Callers that want live rows only filter on `status` — `read_active_fr_rows` |

## External plan review — dispositions

Both legs returned substantive feedback (Gemini 5 findings, GPT 12). Nothing was
waved through; each is `accepted-and-fixed` or `rejected-with-reason` below.

| Finding | Sev | Disposition |
|---|---|---|
| GPT-8 enumerate the import/execution modes; keep the reader a leaf | med | **accepted-and-fixed** — the highest-value finding. `test_fr_table_reader_load_styles.py` runs all four load styles in subprocesses, including the adversarial "compliance-local `lib` already bound, then load by file location", plus a leaf assertion |
| GPT-5 / Gemini-3 full-cell id validation, near-misses | high | **accepted-and-fixed** — 9 near-miss probes (`FR-01.01-extra`, backticked, embedded in text, padded) |
| GPT-3 / Gemini-2 a persisted column map could capture an unrelated later table | high | **accepted-and-fixed** — probe added. It cannot: C1 requires a canonical id in the FIRST cell, so an FR id in a Covers column is data, not a declaration. The plan failed to say the id match was anchored, which is why both reviewers saw the risk |
| GPT-6 the C4 unescape contract is stated ambiguously | med | **accepted-and-fixed** — wording corrected above (it was markdown pipe-escaping inside the table cell, not the code) + 6 escaping probes incl. trailing backslash and multiple escapes |
| GPT-2 `startswith("\|")` would match a literal backslash | high | **accepted-and-fixed (doc only)** — same markdown artifact; the code always read `startswith("\|")` as a bare pipe. Wording corrected |
| GPT-4 / Gemini-1 removal-section semantics must be in the shared contract | high | **accepted-and-fixed (doc)** — already implemented and covered by three tests; the plan never stated it, which is why both reviewers read step 2 as deleting the semantics. Now C9 |
| GPT-1 header alias precedence undefined | high | **rejected-with-reason** — implemented as `TITLE_COLS`/`NAME_COLS`/`PRIORITY_COLS`/`LAYERS_COLS` with documented precedence, one test per historical shape plus a reordered one. The plan under-specified it; the code does not |
| Gemini-4 thin rows could `IndexError` in the legacy projections | med | **rejected-with-reason** — no projection indexes positionally; `_pick` returns `""` out of range and priority coerces. Pinned by the C8 test |
| GPT-9 reader should return parse metadata (rejection counts/reasons) | med | **rejected-with-reason, triaged** — an accumulator nothing reads is dead surface, and making "present but unreadable" visible is S5's stated AC. Recorded as residual risk below |
| GPT-10 "projection" vs the AC "the other four are gone" | med | **rejected-with-reason** — the five entry points are five different PUBLIC types with existing callers; converging the type is S5/S6. GPT's actual concern — "do not retain five independently evolving traversal/state machines" — is met: every one is now a list comprehension with no state |
| **GPT-11 / Gemini-5 splitting `test_group_d_hardening.py` is scope creep** | low | **kept, dissent recorded** — two independent reviewers rated it unrelated to S4 and they are right in principle. The campaign brief instructs S4 to fix it (S3 left it at 332 lines, unbaselined, headed for a Group-H finding), and a separate commit is not available because the F11 verifier inspects a single commit. Surfaced to the orchestrator rather than silently overridden |
| GPT-12 parser abuse / dynamic import surface | low | **rejected-with-reason** — the only dynamic import takes hardcoded first-party module names, never header text; the scan is linear over bounded input |

## External code review — dispositions

**Gemini's code leg returned `feedback: null`** — an empty response, not a review.
The same degenerate result it produced on S2 and S3, so this is now three for three
on the code mode. Recorded in `degraded[]`; it is NOT counted as a passing review.
GPT-5.4 returned two findings.

| Finding | Sev | Disposition |
|---|---|---|
| `golden.json` is missing from the commit; blocks until regenerated | high | **rejected — false positive, verified empirically.** The diff sent for review deliberately EXCLUDED the 156 KB baseline to stay in budget, so the reviewer could not see it. Checked instead of asserted: `git show :…/golden.json` has the `--reason` stamped, all four FVs marked `flipped` with `flipped_in`, FV-2 still `frozen`, and `regen_golden.py --check` reports "golden.json is current". The exclusion was my error in preparing the review input, not a gap in the change |
| C8 as written ("an id plus anything") disagrees with the code, which accepts a one-cell row | low | **accepted-and-fixed** — a real doc/code inconsistency. Resolved in favour of the CODE, with the argument stated: a text-less requirement is loud in the RTM, a dropped one is silent. Wording corrected, and three probes now pin the one-cell case and its defaults so the behaviour is deliberate |

## The S3-inherited obligation: premise falsified, NOT implemented

S3 recorded that only `## Removed Requirements` sets `status="removed"` and that the
inline `**REMOVED** by` marker this repo uses "still parses as active", leaving S4 to
recognise both forms. **Investigated and rejected on evidence.** The repo's one marker
(`.shipwright/planning/01-adopted/spec.md:198`) sits inside the prose refinement section
headed `### FR-01.01 — /shipwright-run` and retires a *sub-behaviour* (the multi-session
execution mode), not the requirement. FR-01.01 is `/shipwright-run` itself, `Must`, with
an untouched and correct table row. Implementing the inherited reading would have dropped
the orchestrator from every live requirement set, RTM and coverage gate — a far worse
false verdict than the one it was meant to fix. `path-b-change.md` step REMOVE defines
exactly one removal form (move the row into a `### Removed Requirements` subsection), and
the marker is not an attempt at it. Pinned by a test so a later step cannot re-adopt it;
campaign SPEC §2.5 corrected.

## Steps

1. New `fr_table_reader.py` (neutral leaf, tri-modal sibling loader per ADR-045).
2. Delegate all five parsers; delete both `_FR_TABLE_RE` copies and the two
   semantic-clone removed-section loops.
3. Repurpose `test_fr_table_drift_protection.py` → boundary probes against the
   one reader (there is no longer a pair to keep in sync).
4. Flip FV-1/3/4/5 in `frozen_bugs.py` + the two corpus test modules, regenerate
   `golden.json` with `--reason`, **same commit**.
5. Revise ADR-031 with the falsification evidence.
6. Pay S3's debt: split `test_group_d_hardening.py` (332, unbaselined).

## Predicted golden movements (anything else is a defect)

FV-1 (`zero-row-parse` T1 SKIP→FAIL), FV-3 (`07-header-blind` text
`extra`→`ok`), FV-4 (`05-fixture-fr` group_i 0→1 row), FV-5 (`edge` group_i
gains FR-01.20), plus C1 (`edge` drift/rtm lose FR-1.1/FR-7/FR-001.001; group_i
loses FR-1.1/FR-001.001), C3+C5 (`malformed` drift/rtm gain the rows they used
to drop), C4 (`malformed` FR-01.08 cell text), C7 (no id resurrection).

## Self-Review

| # | Item | Verdict |
|---|---|---|
| 1 | Spec Compliance | **pass** — all eight ACs met: one reader, five shapes parse, column order not load-bearing, FV-1/3/4/5 flipped with `golden.json` + `frozen_bugs.py` in the same commit, `absent` still SKIPs, FV-2 still frozen, the drift-protection suite repurposed, ADR-031 revised with the falsification |
| 2 | Error Handling | **pass** — the reader raises nothing and returns `[]` for unparseable input; each caller keeps the exception behaviour it had (rtm still has no `try/except` on `read_text`, drift still swallows `OSError`), because reconciling those is S2b's, not S4's |
| 3 | Security Basics | **pass** — no auth/secret surface. The one dynamic import takes hardcoded first-party module names, never header text. The scan is a single linear pass, so the ReDoS class the old regex needed hand-hardening against is gone by construction |
| 4 | Test Quality | **pass** — 60 new assertions across three modules, every one derived from a behaviour the old parsers disagreed on. Two came from probes that FAILED first (doubled backslashes; the C8 wording/code gap) |
| 5 | Performance Basics | **pass** — one pass per line, one per row; the pathological-row timing guard is kept and passes |
| 6 | Naming & Structure | **pass** — every new file under 300 by splitting cohesive clusters, never by baselining. `drift_parsers` ratcheted 409 → 383 |
| 7 | **Affected Boundaries (ADR-024)** | **pass, with a fix** — the boundary is the `spec.md` FR table: producer `markdown_table.escape_cell` (+ `artifact_writer`), consumer this reader. A REAL round-trip probe was run and **failed 4 of 12 cases**; see Confidence Calibration |

## Confidence Calibration

Boundary: `spec.md` FR table. Producer `markdown_table.escape_cell`; consumer
`fr_table_reader`. Probes were run, not asserted.

| Probe | Result |
|---|---|
| 1 — producer round-trip, 12 pathological values through `escape_cell` → row → reader | **4 FAILURES.** `escape_cell` emits `\` → `\\` BEFORE `\|`, so undoing only the pipe returned every backslash doubled. Any Description holding a path or a regex came back wrong. Four of the five replaced parsers shared the defect and none had a round-trip test |
| — fix | Splitting and unescaping became ONE left-to-right pass in `_fr_table_cells.split_cells` — the exact inverse of the producer. It also closed a second defect found while writing it: a lookbehind for "pipe not preceded by a backslash" mis-reads `a\\\|` (escaped backslash, then a REAL separator) and silently merges two columns |
| 2 — same round-trip, re-run | 12/12 pass |
| 3 — column integrity: 144 combinations of 12 adversarial values across two cells, asserting the columns AFTER them stay intact | 144/144 pass, 0 failures |

**Asymptote reached** — two consecutive probes with no findings. Probes 1 and 3
are now permanent tests, not scratch scripts.

Not probed, and why that is acceptable: `artifact_writer`'s full table emission
(covered by its own suite, and the cell-level escape is the part this change
touches); non-UTF-8 spec files (`read_text` is the caller's, unchanged by S4).

## Round 2 — external code review (2 blocking, 3 fixes)

| Finding | Sev | Disposition |
|---|---|---|
| **B1 — C2+C8+C3 compose into a false-requirement route** | blocking | **accepted-and-fixed.** Reproduced first (both the 2- and 3-column variants), then fixed with TWO mechanisms because a width bound alone fails the 3-column case and header-governance alone fails the headerless case. **C6 WITHDRAWN**, **C8 RE-DECIDED**, new **C10** (table governance). The C8 conflict with the pinned `ragged` corpus cell was re-decided explicitly and the cell moved. Six probes in a new `test_fr_table_reader_boundaries.py`, including three guards ON the guards (FV-5, separator rows, non-canonical rows must not end a table). Full reasoning in ADR-107 |
| **B2 — C1's residual risk routed to an S5 AC that does not cover it** | blocking | **accepted-and-fixed.** Verified: S5's AC covers "no spec on disk" and "spec present, no recognised header"; the C1 route is neither — the spec is on disk and the header IS recognised, only the row ids fail. S5's AC amended to name the third state; anchors `trg-5f2037b7` + `trg-c9669d6a` filed in the TRACKED `.shipwright/triage.jsonl`, so "triaged" is verifiable in this diff rather than asserted |
| **F3 — the near-miss accumulator** | required | **accepted-and-fixed, and the ADR's stated rejection reason corrected.** The premise "an accumulator nothing reads is dead surface" was factually wrong: `invalid_layers` already threads this exact shape and `test_links` already publishes it. `invalid_ids` rides the same wire; the wrong justification is struck through in ADR-107 rather than deleted |
| **F4 — S5's Removed-Requirements miscount** | required | **accepted-and-fixed.** The 3 "occurrences" are prose mentions inside requirement bodies; `_HEADING_RE` needs `^#{1,6}\s` and cannot match them. There are ZERO such headings. Corrected in S5 with the original text struck through, noting the landmine was wrong in BOTH directions (SPEC §2.5's inline-marker claim was the other) |
| **C3 acknowledgement** | — | Recorded. Coercion is fail-LOUD (`group_d` maps `Must` to highest severity, the RTM files it under must-requirements). The residual — publishing an invented priority — is closed by the same accumulator as F3 |
| **`STILL_FROZEN` is a metadata guard** | record | Noted in `frozen_bugs.py`: it is derived from the `state` field, so it bites on a metadata regression only. The behavioural freeze is the three `test_fv2_*` assertions. S6 changes those FIRST |

**A regression the probes caught.** Withdrawing C6 broke the BOM probe — a UTF-8
BOM is not whitespace to `str.strip()`, so a BOM'd header line never registered
as a table row and the first table had been surviving on the positional fallback
alone. Fixed at the source, not by weakening the probe.

**New golden movement, and only one:** `malformed`/FR-01.01 `ragged` is no longer
a requirement in any parser (C8 re-decided) — recorded in `invalid_ids` instead.
Nothing else moved; C6's withdrawal moved zero cells because the corpus has no
headerless FR rows.

## Round 3 — anti-ratchet violations I introduced while fixing round 2

The round-2 fix ratcheted two baselined files (`test_links.py` 302→307,
`test_data_collector.py` 1253→1278). CI had passed on the previous commit, so
only the orchestrator running `anti_ratchet_check.py --worktree` surfaced it.
Both came from required work — the `invalid_ids` accumulator and its tests —
which does not make them exempt: an `exception` state with an ADR licenses a
file's existing size, never its growth.

Fixed by shrinking and splitting, **no `current` bumped, no exception ADR
written** (neither file supports the deep-module argument the template demands,
and I refused that argument for `drift_parsers` earlier this campaign):

- `test_data_collector.py` **1278 → 1029**; the four `TestCollectRequirements*`
  classes → `test_data_collector_requirements.py` (271). Cohesive, and exactly
  the surface S4 changed.
- `test_links.py` **307 → 279**; `build_requirement_nodes` + `_LAYER_ORDER` +
  `_cov_status` → `_test_links_requirements.py` (146 → 195), which already owns
  the requirement index. Duplicate omitted-when-empty comment folded away.

Gate: `"status": "ok"`, zero ratchets, zero new crossings. Splits preserved
every test — **102 before, 102 after**, measured both sides. `golden.json`
byte-identical: the split moved no cell.

## Residual risk (declared, not hidden)

C1 creates a NEW route to a zero-row parse: a spec using only non-canonical ids
parses to zero rows and T1 SKIPs again. FV-1's *trigger* is removed; the guard's
underlying conflation of "no spec" with "spec I could not read" is NOT fixed and
belongs to S5. Recorded in `frozen_bugs.py` and triaged.
