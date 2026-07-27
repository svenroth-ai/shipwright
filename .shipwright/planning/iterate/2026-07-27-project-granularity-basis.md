# Iterate — requirement granularity guidance + the basis-template contradiction

> Run ID: `iterate-2026-07-27-project-granularity-basis`
> Type: CHANGE · Complexity: medium (classifier said `small`, overridden up)
> Campaign: REQ-3 Phase 2 · Anchor: `trg-a8110d84` · FR: `FR-01.02`

## 1. Problem

Per-plugin work unit from the FR-01.02 scenario pass. Two defects in
`/shipwright-project`, both about how a requirement is *written*:

**(1) Requirement granularity has no guidance and no check.**
`split-heuristics.md` says how big a *planning unit* should be — not too broad,
not too small, find natural boundaries. Nothing says how big a *single
requirement* should be, while the phase promises requirements "each one scoped
so it can be delivered on its own". This campaign is the evidence: one
requirement in this very catalogue carried a single acceptance criterion for an
entire phase and nobody noticed for months.

**(2) The templates contradict the basis rule.**
FR-01.02 forbids the `assumed` basis for a new project — with the person in the
conversation, unconfirmed means unasked. The phase's own generation template
seeds two of its four example rows with `Basis: assumed` and defines the value
as "nobody confirmed this — needs checking". A reader following the template
violates the criterion it is supposed to satisfy.

## 2. Decided rules (from the work unit — not re-litigated here)

- A capability that cannot be given acceptance criteria a single delivery would
  satisfy is **too broad and gets divided**. Being unable to enumerate what
  would settle it is the signal that it names several capabilities at once.
  The judgement stays human; the observable signal is **zero criteria**, and a
  warning on that is buildable.
- The `assumed` marking **stays available, but only together with what would
  settle it** — who to ask, or what to try. The ban targets silent assuming
  while someone is available to answer, not honest not-knowing.

## 3. Spec Impact: NONE (justified)

The two criteria this iterate implements are **already in the catalogue**,
authored by the REQ-3 Phase 2 content round (`28491e1c`) — see
`.shipwright/planning/01-adopted/spec.md` → `### FR-01.02`, the "cannot be given
acceptance criteria that a single delivery would satisfy" bullet and the
"what would settle it is named" clause of the basis bullet.

This run builds the guidance and the check those criteria call for. No
requirement text is added, modified or removed, so Spec Impact is `NONE`.
`FR-01.02`'s `Layers` cell stays `unit (inferred)` — promoting it to a bare
binding cell is a separate, known-landmine decision and is not in this scope.

## 4. Empirical probe — what the existing checks actually see

Run before designing anything, because the ledger's claim ("nothing anywhere
obliges a requirement to have criteria") had to be verified rather than trusted:

```
compute_fr_coherence(repo_root)  →  total_frs=19, missing_both=19, ok=False
parse_fr_headings('01-adopted/spec.md')[0]
    → FR-01.01  has_desc=False  has_accept=False  raw_body=2044 chars
```

**Finding.** `check_s5_fr_coherence` reports **19/19 FRs as missing both
description and acceptance** on a spec where every FR is fully elaborated —
FR-01.01 alone carries 2044 characters of criteria. `spec_parser` only
recognises `**Acceptance Criteria:**` bold labels; the converged shape that
`/shipwright-project` and `/shipwright-adopt` actually emit uses
`### FR-XX.YY — Title` headings with bare bullets. S5 is therefore blind to the
only shape the phase produces, and its signal here is 100% false.

Two consequences:
- I6 is **genuinely new**, not a duplicate of S5.
- S5's blindness is a **pre-existing defect in a different check** (the
  Phase-Quality spec category). Fixing it is out of scope for this work unit —
  filed as a triage follow-up rather than silently absorbed.

## 5. What gets built

### 5.1 Granularity guidance (docs)

`shared/fr-authoring.md` — the binding rulebook for all three authoring plugins
— gains **§3a "How big is one requirement?"**, sited directly after §3
(MINT-or-FOLD). §3 answers *does this deserve a row?*; §3a answers *is this row
one capability, or several wearing one name?*

`spec-generation.md` cites it, next to where it already cites §3, and
`split-heuristics.md` gains a pointer distinguishing the two granularities
(planning unit vs. requirement) so neither doc is read as governing the other.

### 5.2 The `assumed` contradiction (docs)

One wording, repeated in the three places that currently disagree:

| File | Today | After |
|---|---|---|
| `spec-generation.md` template rows | seeds bare `assumed` twice | seeds `interview`; the `assumed` form is shown once, qualified |
| `spec-generation.md` Basis table | "nobody confirmed this — needs checking" | + what would settle it must be named |
| `fr-authoring.md` §4a | same bare wording | same qualified wording |
| `requirement-elicitation.md` §8 | greenfield = flat **"No."** | qualified: silent `assumed` banned, honest gap allowed *with* what would settle it |

`/shipwright-adopt`'s use of `assumed` is untouched — brownfield legitimately
carries it, and §8 already scopes the rule by whether the person who knows is
reachable.

### 5.3 The check — Group I `I6`

`I6 — FR without acceptance criteria`, **advisory** (LOW, never `fail`), in the
detective-only requirement-hygiene group that already lints against
`fr-authoring.md`. Advisory is the decided posture: the work unit says
*"a warning … is buildable"*, and the judgement of whether a requirement is too
broad stays human.

Reads the **converged shape** — the one the phase actually emits:

- heading form `### FR-XX.YY — Title` followed by `-` / `*` bullets (adopt, and
  this repo's own catalogue);
- bold-label form `**FR-XX.YY: Name**` followed by `- [ ]` checkboxes (the
  `/shipwright-project` template).

A block whose only content is a `TBD` placeholder counts as **zero** criteria —
that is exactly the state seven rows sat in from May until this campaign.

### 5.4 Making room — a pure move

`group_i.py` is at 298 lines against the 300-line source cap, so I6 does not
fit. `FrRow` + the three scan functions move to a new `group_i_rows.py` and are
re-exported, following the sibling-module pattern the file already uses for
`group_i_detectors` and `group_i_scan`. Pure move, no logic change, so the
existing callers and tests are unaffected.

## 6. Alternative considered — and why not

**Fix S5 instead of adding I6.** Tempting: S5 already means to check this, and
one repaired check beats two overlapping ones.

Rejected. S5 lives in the Phase-Quality *preventive* verifier and asks a
different question (does each FR have a description **and** acceptance body).
Repairing its parser is a behaviour change to a gate that fires on every phase
transition in every project, and it would take this work unit from "add a
warning" to "rewrite a shared spec parser" — a scope the operator did not ask
for and could not review as one unit. The granularity rule this unit implements
is requirement-*authoring* hygiene, which is `fr-authoring.md`'s domain, and
Group I is that document's enforcement surface. S5's blindness is real and is
filed, not absorbed.

## 7. Affected Boundaries

- **Template ↔ parser (round-trip).** `spec-generation.md` and adopt's
  `artifact_writer` are the *producers* of the AC shape; `group_i_criteria` is a
  new *consumer*. A shape the templates emit that the parser cannot read is a
  false warning in every project — probed explicitly in §8.
- `shared/fr-authoring.md`, `shared/requirement-elicitation.md` — binding for
  `project`, `adopt`, `iterate` alike; wording drift between them is the exact
  defect this unit fixes, so a drift test pins them.
- Group I finding set — consumed by the compliance dashboard and `run_audit`'s
  exit code. I6 is advisory, so `any_fail` is unchanged.

## 8. Confidence Calibration

- **Boundaries touched:** see §7 — producer/consumer pair (spec templates →
  criteria parser), two shared binding docs, the Group I finding set.
- **Empirical probes run:**
  - `compute_fr_coherence` on the real repo → 19/19 false "missing" (§4). The
    reason I6 exists rather than a reuse of S5.
  - Bloat classification probe → `fr-authoring.md`,
    `requirement-elicitation.md`, `spec-generation.md` all classify `doc`
    (uncapped); only `group_i.py` carries the 300 cap, at 298. The reason for
    the §5.4 move.
  - Baseline probe → none of the four files has a `shipwright_bloat_baseline`
    entry, so no anti-ratchet hard gate applies.
  - Round-trip probe → the parser is run against the **literal** template block
    from `spec-generation.md` and the **literal** emission of adopt's
    `artifact_writer`, not against hand-written fixtures.
- **Test Completeness Ledger:** see §9.
- **Confidence-pattern check:** depth — the parser is tested against both real
  producers plus the repo's own 19-FR catalogue, not synthetic strings.
  Breadth — every shape branch (heading, bold-label, TBD placeholder, absent
  block, retired row) has a case. No `cross_component` machinery is touched, so
  no integration-composition behaviour is owed.

## 9. Test Completeness Ledger

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | Heading-form block with bullets → has criteria | `tested` | `test_group_i_criteria.py::test_heading_form_counts` |
| 2 | Bold-label form with `- [ ]` → has criteria | `tested` | `::test_bold_label_form_counts` |
| 3 | `TBD` placeholder block → zero criteria | `tested` | `::test_tbd_placeholder_is_no_criteria` |
| 4 | FR in table with no block anywhere → reported | `tested` | `::test_missing_block_reported` |
| 5 | FR table rows are not mistaken for AC anchors | `tested` | `::test_table_row_is_not_an_anchor` |
| 6 | I6 is advisory — never flips `any_fail` | `tested` | `test_audit_group_i_criteria.py::test_i6_never_fails` |
| 7 | I6 skips when the scan found no rows | `tested` | `::test_i6_skips_without_rows` |
| 8 | Retired rows are not reported as missing criteria | `tested` | `::test_retired_rows_excluded` |
| 9 | Round-trip: the `spec-generation.md` template parses | `tested` | `::test_project_template_round_trips` |
| 10 | Round-trip: adopt's emitted spec parses | `tested` | `::test_adopt_emission_round_trips` |
| 11 | Pure move keeps `group_i.scan_specs` / `scan_fr_rows` importable | `tested` | existing `test_audit_group_i*.py` (unchanged) |
| 12 | All six surfaces state the same `assumed` rule | `tested` | `test_requirement_granularity_and_basis.py::test_every_surface_qualifies_assumed` |
| 13 | `fr-authoring.md` §3a exists and is cited | `tested` | `::test_fr_authoring_carries_the_granularity_section`, `::test_granularity_rule_is_cited` |
| 14 | A heading merely *mentioning* an FR id is not its criteria block | `tested` | `test_group_i_criteria.py::test_heading_merely_mentioning_the_id_is_not_an_anchor` |
| 15 | The tightened anchor still admits every producer heading form | `tested` | `::test_anchor_accepts_the_shapes_producers_emit` |
| 16 | Each §8 situation row names the settlement, not just the prose above them | `tested` | `::test_every_situation_row_names_the_settlement` |
| 17 | The moved `_scan_one_spec` still resolves for the corpus registry | `tested` | `integration-tests/test_requirements_corpus_*` (registry pointer updated) |

Zero untested-testable behaviours. No `untestable` rows claimed.

## 9a. What the reviews changed — including where this spec was wrong

The external plan review (GPT-5.6 + Gemini 3.1 via OpenRouter) returned nine
accepted findings before any code was written; one — that a concrete syntax was
needed for "what would settle it" — led to the probe showing a qualified `Basis`
cell is **blocking-malformed** under audit `I5`, which is why the settlement
lands in an acceptance criterion instead. One finding was declined with reason
(a separate legacy-label branch; the general block rule already covers it, and a
test now pins that).

The external code review then found three more, two of which contradicted this
document:

1. **§5.4's claim that the pure move left "existing callers and tests
   unaffected" was false.** `integration-tests/requirements_corpus/registry.py`
   resolves `group_i._scan_one_spec` by module+attribute, and two suites assert
   the exact Group I check set. The integration suite was not among those run
   before the claim was made. The registry now points at the true module and
   the assertions know about I6.
2. **A real false-green defect.** The heading anchor matched *any* heading
   containing an FR id, so `### Notes for FR-01.01` plus any bullet would have
   suppressed the warning for a requirement with no criteria at all — the exact
   failure the check exists to prevent, in the check itself. The anchor now
   requires the id to *begin* the heading; a test reproduces the old behaviour.
3. **The brownfield row still disagreed** with the rule above it ("a work item
   to confirm it" names neither a person nor an experiment). Harmonised, with a
   per-row assertion rather than a document-wide phrase search.

**Self-review then widened the scope by three files.** Grepping for the old
gloss — rather than reasoning about which files *ought* to carry it — found the
rule still stated in its stale form in `shared/scripts/lib/fr_basis.py` (the
vocabulary module's own docstring), and in both iterate path references, which
instruct an author to type the cell. Correcting three documents and leaving
three copies contradicting them would have reproduced this work unit's own
defect. The drift guard now pins all six surfaces.

One piece of speculative tolerance was **removed** rather than kept: the anchor
briefly accepted an inline `<a id=…>` before the FR id. No producer emits that
(the catalogue puts the anchor on its own line, where it is simply skipped), so
it was untested generality guarding against nothing.

## 10. Out of scope (stated, not silently dropped)

- Repairing `check_s5_fr_coherence` — filed as triage (§4).
- Promoting `FR-01.02`'s `Layers` cell from `(inferred)` to binding.
- Making I6 blocking. The decided rule keeps the judgement human.
- Any change to how `/shipwright-adopt` chooses `assumed`.
