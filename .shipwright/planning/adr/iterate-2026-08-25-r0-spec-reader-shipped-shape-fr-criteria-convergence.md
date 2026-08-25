# One shared FR-criteria reader, replacing three independent walks

**Campaign:** `req3-04-ac-identity-mono`, sub-iterate R0 (serial, wave 1 of 2).
**Spec:** `.shipwright/planning/iterate/campaigns/req3-04-ac-identity-mono/sub-iterates/R0-spec-reader-shipped-shape.md`
**Run-ID:** `iterate-2026-08-25-r0-spec-reader-shipped-shape` (campaign sub-iterate id `R0` — see the "Run-ID casing" note in Reflection for why this differs from the campaign's own display id)

## Context

Three readers in this repo each independently decided "does this FR heading
carry acceptance criteria, and what are they": `lib/spec_parser.py` (S5's
FR-coherence check, bold-label only — never knew the shape
`/shipwright-project`/`/shipwright-adopt` actually emit),
`tools/verifiers/_layer_coverage_ac.py` (the cross-layer fold gate, knew the
heading form since PR #459) and
`plugins/shipwright-compliance/scripts/audit/group_i_criteria.py` (I6, the
richest reader: two anchor forms, checkbox/`(E)`-marker stripping, placeholder
rejection, and an explicit "a table row is not an anchor" rule — its own
docstring already argued for this exact convergence). Measured before this run:
`parse_fr_headings` against this repo's own `.shipwright/planning/01-adopted/spec.md`
reported 20 of 20 FR headings with **zero** acceptance and **zero** description
— all false, 265 real `(E)` criteria present (WebUI repo: 37/37, same defect).

## Decision

Extract the richest reader's semantics into one shared parser,
`shared/scripts/lib/fr_criteria.py`: two anchor forms (`### FR-XX.YY —
Title` + bullets, `**FR-XX.YY: Name**` + `- [ ]`), checkbox/`(E)`-marker
stripping, placeholder rejection (`tbd/todo/tba/na/none/tbc`), continuation-line
joining, whitespace normalisation, and the explicit "a table row is never an
anchor" rule. All three callers now delegate — none keeps its own walk.
`spec_parser.parse_fr_headings` falls back to it (adjacency-gated: only a
bullet list starting immediately under the heading, no prose first) when the
bold-label extraction finds nothing. `compute_fr_coherence` additionally
exempts a heading whose id is ALSO a row of the file's own FR table (its
description lives in the table cell) — but only when that table cell is
**non-empty** (fixed post-review, see below).

## Consequences

**AC-4, catalog-scoped (operator decision, after Stage-1 review 2026-08-25).**
`compute_fr_coherence`, **restricted to `.shipwright/planning/01-adopted/spec.md`**:
`missing_description`, `missing_acceptance` and `missing_both` all now empty
(was 20/20 false on all three axes) — the catalog is fully resolved for the
first time. Repo-wide `report.ok` does **not** flip to `True`: one
pre-existing, unrelated ad-hoc planning doc
(`.shipwright/planning/iterate/2026-07-23-req3-phase2-FR-01.03-revisit-proposal.md`)
has an H1 heading shaped like `FR-01.03` with no label anywhere — this already
produced a `missing_both` entry on `origin/main` before this diff (verified by
running the pre-diff parser against it). Whether to accept that revisit
proposal (which would resolve the gap) is itself an open, separate operator
decision, not R0's to make — R0 only reports the gap honestly rather than
silently absorbing it into a "repo-wide `True`" claim it cannot support. The
original AC-4 was written repo-wide; the amended sub-iterate spec (post
Stage-1 review) narrows it explicitly to the catalog for exactly this reason —
this is a stated scope decision, not an unexplained one. `repo-wide
missing_both` went from 21 entries to this 1 pre-existing one. The three
affected records (`integration-tests/test_requirements_catalog_parsers.py`,
the migration guide, ADR-109) are updated in the same diff, matching the
exact instruction their prior versions embedded. `group_i_criteria.py`
shrank ~144→~83 lines; `_layer_coverage_ac.py` shrank ~198→~131;
`spec_parser.py` grew 350→348 (net, after trimming duplicated docstring
prose to stay within its grandfathered bloat-baseline `current`). The
label-form path is untouched — `test_spec_checks.py` is byte-identical to
`origin/main`.

## Rationale

`group_i_criteria.py`'s own docstring already argued this reader is the
correct one ("Reading the shape the producers actually write is the point");
building a fourth, independent fallback (the alternative considered) would
have made the divergence worse, not better. Direction (`verifiers/` and
`plugins/*/audit/` read `lib/`, never the reverse) mirrors the existing
`_layer_coverage_evidence.py` precedent exactly.

## Rejected alternatives

Renumber/rebuild a new parser per-caller (rejected: exactly the problem
being fixed — a fourth divergent reader). Change the label-form path to also
filter placeholders (rejected: out of scope per R0's own AC — the label form
must stay byte-identical, pinned by `test_spec_checks.py` being untouched).

## Complexity note — Step 2/3.4 discrepancy (honest record)

Step 2's message-keyword classifier returned `estimate: large` from the word
"migration" in this spec's prose (a doc filename
`docs/migrations/requirements-catalog-merge.md` and a quoted reference to a
**different**, past PR — "this is a migration PR with no baseline..."). This
is the documented classifier false-positive class (prose keyword match, not
diff-driven). Step 3.4's diff-driven re-check confirms: `diff_risk_flags: []`,
`complexity_floor: trivial` — the actual diff touches no migration, IO
boundary, build, CI-supplychain or cross-component path. Per the recheck's
one-way ratchet, `effective_complexity` is still reported as `large`
(stage1 never falls); this run adopted `large` for every gated step (F5c,
review cascade, confidence calibration) rather than silently downgrading it,
while recording the false-positive evidence here for anyone auditing the
`large` label later.

## External-Plan-Review-Findings (2026-08-25, `--mode iterate`, openai + deepseek via openrouter)

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | Plugin import path (`group_i_criteria` → `fr_criteria`) under-specified | accepted-and-fixed — implementation uses the established `load_shared_lib` (ADR-045) bootstrap already used by `drift_parsers`; verified by the full plugin test suite (95 passed) exercising the real audit entry point |
| 2 | openai + deepseek | medium | Cross-layer gate (`_layer_coverage_ac`) semantics change (placeholder filtering, `(E)` stripping) not explicitly tested | accepted-and-fixed — added `test_placeholder_only_criterion_digests_the_same_as_no_criteria`, `test_assertion_marker_is_stripped_before_digesting`, `test_a_real_criterion_still_digests_differently_from_a_placeholder` to `test_layer_coverage_criteria.py` |
| 3 | openai | medium | Shared-parser API shape ambiguous (document-level vs. section-level input) | rejected-with-reason — the actual implementation already has exactly this split: `criteria_for`/`iter_anchored_blocks` (whole-document, anchor search) vs. `leading_criteria` (pre-scoped body, adjacency-gated); reviewer saw only the plan text, not the code |
| 4 | openai | medium | Adjacency-rule edge cases (subheadings, code blocks) underspecified | rejected-with-reason — `leading_criteria` only accepts a bullet as the body's first non-blank line; any other content (a subheading, prose, a code fence) fails the bullet-regex match and returns `[]`, already covered by `test_parse_fr_headings_fallback_requires_adjacency` |
| 5 | deepseek | medium | Table-row exemption did not check the table cell's description was non-empty | accepted-and-fixed — `compute_fr_coherence` now filters `fr_table_reader.read_fr_rows` results to `row.text.strip()`; regression test `test_compute_fr_coherence_table_row_with_empty_cell_does_not_exempt` added |
| 6 | deepseek | medium | Large-file chunking could truncate heading/table discovery | rejected-with-reason — reviewer misread the spec's own file-reading note (about the AGENT's 2000-line `Read`-tool cap during investigation); the runtime parser reads the whole file via `Path.read_text()`, no chunking exists |
| 7 | deepseek | low | Placeholder handling inconsistent between labelled form and bullet fallback | accepted-and-documented, not fixed — R0's own AC requires the labelled-form path stay byte-identical (`test_spec_checks.py` untouched); harmonising placeholder handling there is out of scope for this run |
| 8 | openai | low | Triage-card location/schema unspecified | not applicable — card `trg-b85ebe2e` already exists (filed by the prior attempt of this same run) at `.shipwright/triage.outbox.jsonl` → swept into `.shipwright/triage.jsonl` |
| 9 | openai | low | Security: no external input channel; recommend markdown-robustness tests | accepted-and-documented — covered by the existing adjacency/placeholder test set; no new dependency or dynamic import introduced |

## External-Code-Review-Findings (2026-08-25, `--mode code`, openai via openrouter; deepseek unavailable that call)

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | high | `criteria_for`/`has_criteria` (I6, cross-layer gate) scan permissively (prose before bullets OK); only `leading_criteria` (S5's fallback) is adjacency-gated — reviewer read this as the three readers NOT converging | **REVERSED 2026-08-25** — originally rejected-with-reason as intentional group_i behaviour; the Stage-1 spec-reviewer (HARD-GATE) and a second external code review round independently rejected that disposition as not achieving AC-1's "one shared semantics" requirement. Fixed for real: `criteria_for`/`has_criteria` now default to the SAME adjacency gate `leading_criteria` uses (`strict=True`); the two real call sites that need the permissive scan (I6's `has_criteria`, the cross-layer gate's `criteria_digests`) pass an explicit, documented `strict=False`, each citing the pre-existing test that requires it (`test_legacy_bold_acceptance_label_still_counts`, `test_prose_outside_a_criterion_is_not_a_criterion_change`). See `lib.fr_criteria`'s module docstring, "One default semantics, one documented, tested opt-out" |
| 2 | medium | `leading_criteria` passed the WHOLE remaining body to `criteria_texts`, so a leading placeholder bullet + prose + a LATER unrelated bullet list would wrongly count as acceptance | accepted-and-fixed — real bug; `leading_criteria` now bounds to the contiguous leading run only; regression test `test_parse_fr_headings_fallback_leading_placeholder_does_not_reach_a_later_list` added |
| 3 | medium | Convergence test never calls `group_i_criteria.has_criteria` through its real module path | **REVERSED 2026-08-25** — originally rejected-with-reason citing ADR-044's test-root boundary; the Stage-1 spec-reviewer rejected that as a scope-question dodge (ADR-044 blocks a plain `import`, not a subprocess invocation). Added `integration-tests/test_fr_criteria_three_way_convergence.py`: I6's real `has_criteria` invoked as a subprocess (fresh `sys.modules`, no `scripts` package collision risk), alongside S5 and the cross-layer gate, on three inputs (shipped shape, prose-before-bullets, prose-between-two-lists) that actually distinguish adjacency behaviour |
| 4 | medium | Catalog pin (integration-tests) asserts `parse_fr_headings` only, not `compute_fr_coherence` (the actual S3/AC4 claim) | accepted-and-fixed — added `test_compute_fr_coherence_resolves_every_catalog_requirement`, scoped to the catalog's own entries (repo-wide `report.ok` is honestly NOT asserted, see the pre-existing-artifact note above); also corrected a now-stale comment in the same test file that claimed no other FR-shaped heading exists under `planning/iterate/` |

## Self-Review (Step 3.6)

1. **Spec Compliance** — pass. All ten R0 acceptance criteria checked against
   the actual implementation and real repo measurement; one caveat recorded
   above (repo-wide `report.ok` stays `False` due to one pre-existing,
   out-of-scope planning doc — the catalog-scoped claim, the one the AC
   actually measures against, is fully met).
2. **Error Handling** — pass. `fr_criteria` is pure/no-I/O; `compute_fr_coherence`
   already wrapped file reads in `except OSError: continue` before this diff,
   unchanged.
3. **Security Basics** — pass. No new input channel, no secrets, no dynamic
   import; `load_shared_lib` is the existing ADR-045-safe bootstrap.
4. **Test Quality** — pass. Convergence test pins all three readers on one
   input; adjacency/placeholder/table-exemption edge cases each have a
   dedicated unit test; the cross-layer gate's new delegated behaviour is now
   pinned (added post external-review).
5. **Performance Basics** — pass. No new I/O, no N+1; `fr_table_reader.read_fr_rows`
   was already called once per file by other consumers.
6. **Naming & Structure** — pass. `fr_criteria.py` follows the existing
   `shared/scripts/lib/` convention; `has_criteria`/`criteria_for`/`leading_criteria`
   names match the vocabulary the three callers already used.
7. **Affected Boundaries (ADR-024)** — pass. Producer = the markdown shapes
   `/shipwright-project`/`/shipwright-adopt` emit (unowned by this diff);
   consumer = the three readers, now unified. Round-trip probe: ran the real
   parser against this repo's own shipped `spec.md` (20/20 resolved) and the
   WebUI-shape equivalent test fixtures; see Confidence Calibration below.

## Confidence Calibration (Step 3.8 — effective complexity `large`)

Boundary: markdown FR-criteria shapes (bold-label / heading+bullets / bold-label+checkbox)
→ `fr_criteria`'s parser → three consumers. Probes run:

1. Real-repo probe: `parse_fr_headings` + `compute_fr_coherence` against this
   repo's actual `.shipwright/planning/01-adopted/spec.md` — found the
   catalog-scope claim holds (20/20) but surfaced the repo-wide `report.ok`
   caveat (documented above). **Finding.**
2. Fixed the finding (documented the caveat, verified pre-existing on
   `origin/main`) → re-probed: full plugin test suite (95 passed, `group_i`
   entry point), full targeted `shared/tests` slice (94 passed) — no new
   finding.
3. External plan review surfaced a real bug (table-row exemption not checking
   for an empty description cell) → fixed → added a pinning regression test →
   re-ran the full targeted slice (98 passed) — no finding.
4. External code review surfaced a second real bug (`leading_criteria` did not
   bound itself to the contiguous leading bullet run, so a leading placeholder
   plus a later, non-adjacent list could wrongly count) → fixed → added a
   regression test reproducing the exact reviewer scenario → re-ran the
   targeted slice (96 passed) and the catalog integration test (4 passed) —
   no finding.
5. Two consecutive no-finding probes after the last fix (targeted slice,
   `ruff check .`, `verify_local.py`, full plugin suite) — asymptote reached,
   boundary calibrated.

Edge cases not probed: a spec file exceeding the Python process's practical
memory limits (not a real constraint at this repo's scale — largest spec.md
here is well under 1MB); non-UTF-8 spec files (`read_text(..., errors="ignore")`
predates this diff, unchanged).

## Reflection — Run-ID casing (F3a)

This campaign's sub-iterate display id (`R0`) was handed to this run embedded
literally in the run_id: `iterate-2026-08-25-R0-spec-reader-shipped-shape`.
That string fails F5c's `append_iterate_entry.py` closed:
`RUN_ID_STRICT = r"^iterate-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$"` is
lowercase-only, with no `strict=False` path for a freshly-minted entry — and
three sibling regexes elsewhere in this repo (`lib/agent_doc_shape.py`,
`tools/verifiers/ci_supplychain.py`, `scripts/accepted_risks.py`) encode the
same lowercase-only rule, so this is a systemic convention, not one gate's
oversight. Discovered only at F5c, after F3/F4/the risk-recheck/the F5 ledger
had already been produced consistently under the uppercase string.

Resolved by renaming the run_id to `iterate-2026-08-25-r0-spec-reader-shipped-shape`
end-to-end (F3 decision-drop, F4 changelog-drop, risk_recheck.json's directory,
the F5 ledger, F5b's event, this ADR's own Run-ID line) rather than weakening
`RUN_ID_STRICT` — the regex is correct policy, the uppercase run_id was the
defect. Two artifacts could not be retroactively cleaned because they are
append-only logs, not regenerated views: `shipwright_events.jsonl` now carries
one stray `work_completed` event under the old uppercase run_id (harmless —
no check reads it, since every check queries by the corrected run_id), and
`.shipwright/compliance/performance/iterate-throughput.md` — itself generated
FROM that event log — carries one duplicate row for the same reason.

Filed as a Learnings pointer in `conventions.md` so a future campaign mints
sub-iterate run_ids pre-lowercased (`...-r0-...`), keeping the uppercase
display id only in campaign-facing metadata (branch/PR titles, the
`sub_iterate_id` field), never inside the run_id token itself.

## Post-Review Remediation — Stage-1 REJECT (2026-08-25)

PR #648 went through the orchestrator's delegated Stage-1 spec review
(`campaign-mode.md` 3f-bis) and was rejected on two points, both addressed
in this same commit:

**AC-4 scope.** Already covered above (Consequences) — the operator amended
R0's own spec to narrow AC-4 to the catalog explicitly; the ADR now cites
that amended wording rather than reading as an unexplained narrowing.

**The real bug (External-Code-Review-Findings #1 and #3, both reversed
above).** My own prior disposition — "intentional, pre-existing group_i
behaviour" — was a category error: a divergence being INTENTIONAL for one
caller (I6's legacy-label tolerance) does not make it ACCEPTABLE for AC-1's
literal requirement that all three readers agree on one shared default. The
fix does not remove I6's or the cross-layer gate's real, tested tolerance
(`test_legacy_bold_acceptance_label_still_counts`,
`test_prose_outside_a_criterion_is_not_a_criterion_change` both still pass,
unchanged) — it makes the tolerance an EXPLICIT, narrow, opt-in exception
(`strict=False`, two call sites, each with a comment naming the test it
preserves) instead of the silent default two of three readers used and one
did not. On every real, shipped spec (no prose before bullets) the two
defaults were always identical; only synthetic prose-before-bullets and
prose-between-two-lists inputs could ever tell them apart, and those are
now exactly what the new three-way convergence test exercises.

The second, related finding — "the convergence test never calls
`group_i_criteria.has_criteria` through its real module path" — was also
wrongly rejected the first time, citing ADR-044's test-root boundary as if
it forbade calling I6 at all. It forbids a plain `import` sharing this
process's `sys.modules`; it does not forbid a subprocess. This is the actual
lesson worth generalising: **a `rejected-with-reason` citing a real
constraint (ADR-044) is only a correct disposition if that constraint
actually blocks EVERY way of satisfying the finding, not just the first way
tried.** A subprocess crossing into `plugins/shipwright-compliance` was
already the established pattern one file over
(`integration-tests/test_compliance_enforcement.py::run_hook`); it should
have been reached before writing "rejected".

## Post-Review Remediation — Stage-2 code review, two MEDIUM findings (2026-08-25)

PR #648 passed Stage-1 re-review and Stage-2 code review (verdict: no
blocker), with two MEDIUM findings fixed in this same commit before merge
(the remaining medium and several lows were explicitly left for follow-up,
per the reviewer and the operator relaying it):

**Digest pooling (`_layer_coverage_ac.criteria_digests`).** Real correctness
risk, not cosmetic: it assigned `digests[fr_id] = sha256(...)` per anchored
block, last-write-wins. `iter_anchored_blocks`'s anchor surface (any heading
level, plus the bold form, plus a looser id shape) is materially wider than
the old, narrower `_FR_SECTION_RE` this replaced, making a doubly-anchored FR
id plausible in real specs, not just contrived ones. A later, empty block for
the same id would then silently overwrite an earlier, criteria-bearing one —
collapsing the digest to the empty-criteria value and making this HARD gate
report "no change" when there was one. Fixed by pooling: extract each
block's criteria list first (`fr_criteria.block_criteria(block,
strict=False)`, once per block — never concatenating raw lines across a
block boundary, which risked misreading a later block's leading indented
line as a continuation of an earlier block's still-open bullet), then
accumulate the resulting text lists per id before digesting once — the same
shape `fr_criteria.criteria_for` already uses. Regression test added:
`test_an_id_anchored_twice_pools_both_blocks_instead_of_last_write_wins`
(`shared/tests/test_layer_coverage_criteria.py`), asserting the pooled
digest differs from either single-block digest alone.

**I6 list-level assertion (three-way convergence test).** The shipped-shape
case only asserted `_group_i_has_criteria(...) is True` — a boolean that a
delegation regression silently changing I6's returned LIST (losing `(E)`-
stripping, a dropped placeholder rule, …) would still pass. Added
`_group_i_criteria_for`, the same subprocess bridge but returning I6's real
`criteria_for(..., strict=False)` list, and rewrote
`test_all_three_agree_on_the_shipped_shape` to assert list/digest-level
equality: I6's joined list equals S5's `heading.acceptance` exactly, and its
sha256 equals the cross-layer gate's `criteria_digests()` entry exactly —
not merely all-truthy or all-different-from-empty.

Neither fix changes this ADR's Consequences claims (catalog resolution
counts, `report.ok` caveat, line-count deltas) — both are internal
correctness fixes to the digest/list machinery those claims are read
through, not new behaviour. Full affected-suite re-run after both fixes:
`shared/tests/test_layer_coverage*.py` + `test_fr_criteria_convergence.py`
(101 passed), `integration-tests/test_fr_criteria_three_way_convergence.py`
(3 passed), `integration-tests/test_requirements_catalog_parsers.py`
(4 passed), and the compliance plugin's `group_i_criteria` suites (30
passed) — no regression.

Deferred (triage card filed, kind: improvement, referencing PR #648): the
cross-layer gate's two newly-widened, unlisted/untested block-termination
rules (a same-or-lower non-FR heading now ends a block; a criterion line
starting with `**FR-XX.YY` now truncates the block), and I6's own silently-
widened bullet semantics (ordered lists, placeholder+continuation) — both
flagged medium/low by the Stage-2 reviewer as safe to defer past this run.
