# ADR — Mechanised checks for FR-01.02 (/shipwright-project) and FR-01.16 (elicitation)

Run ID: `iterate-2026-09-11-e2-checks-project-elicitation`
Campaign: `req3-06-enforcement-mono`, sub-iterate `e2-checks-project-elicitation`

## Context

The REQ-3 AC-evidence ledger named 9 `prompt-only (mechanisable)` lines
under FR-01.02 (`/shipwright-project`, 6) and FR-01.16 (guided elicitation,
3), excluding FR-01.16's 5 judgement lines (owned by sub-iterate e6). Per
campaign decision D7, no line may become an LLM-judgement gate — each
either gets a deterministic check + test, or is explicitly downgraded to
`prompt-only (judgement)` with a drift test and a stated reason (the
campaign's own abort condition).

## Decision

Built 4 new pure gate functions
(`shared/scripts/tools/verifiers/_project_gate_extras.py`) + their
filesystem-facing wiring (`_project_gate_wiring.py`), wired into
`project_checks.run_project_checks()` — the same dispatcher
`update-step --step project` already blocks on:

- **#4 + #15 merged, then #15 split** — `basis_forbids_assumed`: a
  QUALIFIED `assumed` cell (e.g. `assumed: nobody could answer`) is
  always banned — the settlement belongs in an acceptance criterion, not
  smuggled into the Basis cell. A BARE `assumed` cell is banned only when
  the row carries zero acceptance criteria (**#15's floor**) — `assumed`
  is legal per `fr-authoring.md` §4a but never bare, so the mechanical
  form obligation is "paired with a recorded criterion", not "absent
  altogether" (revised post-merge, see Stage-1 Spec-Review below; the
  original round shipped an outright ban copied from P4.2's grill-trace
  layer, which was stricter than the ledger's own decided ceiling).
  Whether the criterion actually NAMES the settlement, vs. an unrelated
  functional criterion vacuously satisfying the floor, has no
  deterministic "aboutness" oracle — split out as **#15b**, downgraded to
  judgement, drift-tested (same shape and rationale as #8/#8b and
  #10/#10b below). Skipped for `scope: "extension"` (added round 5
  review).
- **#5** — `criteria_free_of_implementation_detail`: reuses I1's own
  detector against every active FR's acceptance CRITERIA text, not just
  the Name column I1 already covered.
- **#8 split** — the floor (an ADR exists for the phase) was already
  enforced by pre-existing C4, just never cited; the link-back half (#8b)
  has no addressable schema field — downgraded to judgement, drift-tested.
- **#10 split** — the zero-row floor is enforced (`no_empty_split`); the
  topical-coherence half (#10b, added during round-3 review for
  consistency with #8/#8b and #3/#3b) has no "aboutness" oracle —
  downgraded to judgement, drift-tested against `split-heuristics.md`.
- **#11** — `starting_guidance_present`: CLAUDE.md + the three agent_docs
  files Step 7 writes must exist AND be non-empty; skipped for extension
  scope.
- **FR-01.16 C, #6** — cite P4.2's already-shipped `check_blank_dimension`
  / `check_greenfield_assumed` / `check_grill_trace_coverage` (campaign
  `req3-09-p4-grill-glossary`, merged one day before this run — the
  ledger's status cells simply hadn't caught up).
- **FR-01.16 #3 split** — the defined-anywhere half cites P4.2's
  `check_undefined_term`; the glossary-collision half (#3b) is reading
  comprehension — downgraded, drift-tested by P4.4's existing test.

## Consequences

9 lines closed (6 FR-01.02 + 3 FR-01.16); 4 judgement downgrades recorded
(#8b, #10b, #3b, and #15b added in the Stage-1 spec-review's second pass
below), each drift-tested, none gated. Live re-measurement (pre-#15b
split): 20 prompt-only/mechanisable, 24 prompt-only/judgement, 16
enforced-untested, 33 unimplemented, 76 enforced-tested. 67 new/updated
tests, all green; lint clean; no architecture-doc structural impact (new
verifier functions wired into an existing dispatcher, not a new
route/component/schema).

## External Plan Review Findings (Step 3.5, round 1)

Both GLM and OpenAI returned "revise" on the mini-plan. Dispositions:

| # | Finding (severity) | Disposition |
|---|---|---|
| 1 | Fixture `scope="extension"` may hollow out #11 coverage (medium×2) | accepted-and-fixed — dedicated new-gate tests already existed independent of the legacy fixtures |
| 2 | `criteria_free_of_implementation_detail` false-positive risk on real prose (medium) | rejected-with-reason — fires only once, at greenfield authoring, over freshly-written text in the same session; any FP is immediately visible/fixable, not a retroactive CI block |
| 3 | Verify C4 actually fires for #8's floor claim (low×2) | accepted-and-fixed — added `test_run_project_checks_detects_missing_c4_adr` |
| 4 | `basis_forbids_assumed` normalization / canonical parser reuse (medium×2) | rejected-with-reason — `fr_basis.classify()` already normalizes; all functions already use `fr_table_reader.read_active_fr_rows` (ADR-107's canonical reader) |
| 5 | Two-module pure/wiring split may be unnecessary (low) | rejected-with-reason — mirrors the established `plan_gate_extras.py`/`design_gate_extras.py` pattern, driven by the 300-LOC bloat-baseline guideline |
| 6 | Unreadable/missing split spec.md should fail loud, not pass vacuously (medium) | accepted-and-fixed — this became the seed of rounds 1-6's fail-loud hardening (see below) |

## External Code Review Findings (Step 3.7, rounds 1-7)

Both GLM and OpenAI ran against the growing diff 7 times; genuine findings
accepted-and-fixed each round, factually-incorrect findings
rejected-with-reason citing code/producer evidence. Summary (full
per-round feedback text: `code_review_output_round{1..7}.json` in this
run's iterate folder):

| Round | Genuine finding (severity) | Resolution |
|---|---|---|
| 1 | Filtered diff (`-- shared plugins`) produced a false HIGH ("FR-01.16 unaddressed") | not a code bug — re-ran with the full unrestricted diff; ledger file was always included |
| 1 | Orphan criteria blocks / scope-default defaults (medium) | rejected-with-reason — iteration is driven by active-row IDs only; `--scope` is a required, closed-vocabulary CLI arg (`write-project-config.py`), no third value exists |
| 2 | Directory enumeration mistakes `campaigns/`/`adr/`/`grill-traces/` for splits (high×2) | accepted-and-fixed — redesigned to enumerate from the project's own `splits` manifest, not raw directory listing |
| 2 | Declared split with no spec.md at all silently passed (medium) | accepted-and-fixed — same fail-loud reader now covers missing, not just unreadable |
| 3 | Malformed project config silently reads as "zero splits" (medium) | accepted-and-fixed |
| 3 | `assumed: <reason>` bypasses the ban (`fr_basis` reports it `malformed`, not `known`) (low) | accepted-and-fixed |
| 3 | Unvalidated split name can crash the validator (non-string/absolute/traversal) (medium) | accepted-and-fixed — `_is_safe_split_name`, cross-platform (POSIX+Windows) |
| 4 | `"splits"` a non-list scalar crashes iteration (medium) | accepted-and-fixed |
| 4 | Non-dict config crashes `.get("scope")` (medium) | accepted-and-fixed |
| 5 | `basis_forbids_assumed` (#4/#15) never scope-gated, unlike #11 (medium×2) | accepted-and-fixed — skipped for extension scope, matching #11's precedent |
| 5 | Falsy split names (`null`, `""`) filtered before being counted as "rejected" (medium) | accepted-and-fixed |
| 6 | Non-object config (`[]`, `null`) still silently read as "zero splits" in the SPLITS reader (the scope reader had already been fixed) (medium×2) | accepted-and-fixed — extracted shared `_read_project_scope` helper, fixed both readers identically |
| 6 | Windows drive-relative (`C:foo`) / root-relative (`\outside`) names bypass `_is_safe_split_name` (low+medium) | accepted-and-fixed |
| 7 | Mixed valid/invalid split-name manifest keeps the valid subset rather than failing on any invalid entry (medium) | rejected-with-reason — deliberate, documented design choice matching `no_empty_split`'s own per-split granularity; only total-unreadability fails loud |
| 7 | #15's settlement-oracle half unenforced for extension scope (medium) | rejected-with-reason — the #4/#15 merge decision (this ADR) explicitly never built a settlement oracle (no deterministic check exists); the merged mechanism's scope (greenfield) is #4's own stated scope, not a new gap |
| 7 | GLM round-7 verdict: **approve**, remaining items are refinements (low×4, non-blocking) | logged, not acted on this round (single-substring drift-test pins, `_read_spec_texts` triple-I/O, run_config/project_config split-source asymmetry) |

Round 7 closed the loop: GLM approved; the two remaining openai findings
are dispositioned above with cited evidence, not deferred.

## Self-Review (Step 3.6)

See `self_review_payload.json` in this run's iterate folder for the full
7-item checklist (all PASS). Item 7 (Affected Boundaries, ADR-024) ran a
live empirical round-trip probe against the REAL `/shipwright-project`
producer's acceptance-criteria format (bold `**FR-XX.YY: Name**` anchor +
`- [ ]` checkbox bullets, per `spec-generation.md` lines 175-330) — every
other test fixture in this diff used the also-supported but different
`### FR-xx.yy` + `- (E)` heading style, so this probe was necessary to
confirm the real producer shape round-trips correctly, not inferred from
reading `fr_criteria.py`'s docstring alone. Pinned as a permanent
regression test.

## Confidence Calibration (Step 3.8)

Fires because `touches_io_boundary` is set (diff-risk re-check). Boundary:
spec.md's FR table (Basis column + acceptance-criteria blocks) as written
by the real producer. One probe run (see Self-Review item 7): constructed
a spec.md snippet in the exact real-producer shape with a planted
file-path violation, called all three spec-text gates directly — all
fired correctly (assumed-Basis caught, planted violation caught inside
the bold-anchor block specifically, no false-empty-split). Zero findings
on the first probe — asymptote reached immediately, since the underlying
question (does `fr_criteria` support this anchor style) has a single
deterministic answer, not an iterative bug surface. No further boundary
probes were run this iterate (CLAUDE.md/agent_docs existence-checking and
the project-config JSON reads are plain file-existence/JSON-parse checks
with no format-ambiguity to probe).

## Stage-1 Spec-Review REJECT (post-merge with main, PR #729, round 1)

Stage-1 spec-reviewer REJECTed the shipped `basis_forbids_assumed`: an
outright ban on Basis=`assumed` is stricter than FR-01.02 #4's own
recorded ceiling ("only where the answer could not be obtained", not
"never"), and contradicts `fr-authoring.md` §4a, `requirement-elicitation.md`
§8's context-dependent availability table, and `spec-generation.md`'s
worked FR-01.05 example — all three keep greenfield `assumed` legal
when paired with a named settlement. Verified genuine (not fabricated)
by re-reading the three cited documents directly. Operator decision:
narrow the gate, not the docs — the docs are deliberate and mutually
consistent; a gate stricter than the decided ceiling is the defect.
Fixed by keeping the qualifier-smuggling ban (unconditional) and
replacing the bare-`assumed` outright ban with the form obligation the
docs actually state — presence of at least one acceptance criterion on
the row, not a judgement about the criterion's content (see the revised
`_project_gate_extras.basis_forbids_assumed` docstring for why a
mechanical check stops at presence, not aboutness).

## Stage-1 Spec-Review REJECT (round 2, re-run against the round-1 fix)

Re-verified genuine by re-reading `fr-authoring.md` §4a, `requirement-elicitation.md`
§8 and `spec-generation.md`'s worked FR-01.05 example directly (all three
explicitly require the settlement to be *named*, and the worked example
shows a distinct second criterion doing exactly that naming). Two
findings, both accepted:

1. **Unfaithful** — the round-1 fix checks criterion PRESENCE, never
   whether any criterion names a settlement; a bare `assumed` row with
   an unrelated functional criterion vacuously passes.
2. **Missing** — this campaign's own D7 rule was already applied twice in
   this identical diff for the exact same "buildable floor + unbuildable
   aboutness half" shape (#8/#8b, #10/#10b), but #15 was not split the
   same way, and no drift test pinned the "naming the settlement"
   language the ledger's own row #15 quotes.

Finding 1 restates the same unbuildable-oracle problem #10b's own text
already names ("no deterministic aboutness oracle exists, same rationale
as #4/#15's resolution") — building that oracle was ruled out by the
operator in round 1, consistent with this ADR's own Rejected Alternatives.
Finding 2 is the correct, actionable resolution the operator's round-1
instruction ("say so in the docstring and stop there") already implied at
the DOCSTRING level but the ledger did not yet reflect at the PROCESS
level: split into #15 (floor, enforced) + #15b (aboutness, judgement),
matching #8/#8b and #10/#10b exactly. No new test was needed — a
pre-existing drift suite, `shared/tests/test_requirement_granularity_and_basis.py`
(predates this sub-iterate, written for an earlier REQ-3 granularity
round), already pins the "never bare" / "what would settle it" /
"acceptance criterion" language across all three binding docs
(`test_every_basis_doc_sends_the_settlement_to_a_criterion`,
`test_every_surface_qualifies_assumed`) and the exact FR-01.05 worked
example the round-2 reviewer cited
(`test_worked_example_assumed_row_has_its_settlement_criterion`); #15b
cites all three rather than duplicating coverage.

## Stage-2 Code Review (round 3, PR #729, post spec-review-round-3 PASS)

Ran after Stage-1 spec-reviewer's round-3 PASS explicitly cleared Stage 2 to
proceed. Four findings, all verified genuine by reading the cited source
directly (`_project_gate_wiring.py`, `fr_basis.py`'s `classify()`,
`fr_criteria.py`'s docstring, the wiring test file's own docstrings):

| # | Finding (severity) | Disposition |
|---|---|---|
| 1 | `check_criteria_free_of_implementation_detail` (#5) and `check_no_empty_split` (#10) have no extension-scope skip, unlike `check_basis_forbids_assumed`/`check_starting_guidance_present` (medium) | deferred to triage `trg-9583d3a8` — the ledger's own #5/#10 text does not state "greenfield only" the way #4/#15/#11 do, so the correct treatment (extension-scope skip vs. touched-rows-only vs. a one-time rollout marker per the `check_binding_completeness` precedent, commit `c6bf0805c`) is a genuine design decision outside this round's scope, not a mechanical fix |
| 2 | `is_qualified_assumed`'s `verdict.value.startswith("assumed")` also matches an unrelated out-of-vocabulary typo with no word boundary (e.g. glued `assumedallowed`), which `fr_basis` classifies under its OTHER `malformed` branch ("not in the vocabulary") — not the qualifier-smuggling one (low) | accepted-and-fixed — switched to checking `verdict.note` (the field that textually names which malformed branch fired); added regression test `test_basis_forbids_assumed_ignores_an_unrelated_malformed_cell`. **Self-caught follow-on bug**, not part of the reviewer's finding: the fix's first pass checked `verdict.reason` instead of `verdict.note` — `BasisVerdict` is `(kind, value, reason="", note="")` and the descriptive text is populated into `note`, `reason` stays `""` on both `malformed` branches (it is populated only for `other`). Caught by re-running the affected tests before commit; corrected to `verdict.note` |
| 3 | `fr_criteria.py`'s docstring claim of "exactly two, both commented" `strict=False` callers is stale — this diff added two more without updating it (low) | accepted-and-fixed — docstring now enumerates all four callers; inline comments added at both new call sites in `_project_gate_extras.py` |
| 4 | A test docstring claimed "the other two gates" sharing `_read_spec_texts` got a missing/unreadable-spec regression test, but only `basis_forbids_assumed` actually did — `criteria_free_of_implementation_detail` never got one (low) | accepted-and-fixed — added `test_check_criteria_free_of_implementation_detail_skips_when_no_spec_yet` and `..._fails_loud_on_a_declared_but_missing_spec` |

## Rejected Alternatives

- A second, weaker "does this AC name a settlement" semantic oracle for
  #15 — no deterministic aboutness check exists; checking for the
  PRESENCE of an acceptance criterion on an `assumed` row (not its
  content) is the buildable ceiling a mechanical gate can honestly reach
  (see the Stage-1 Spec-Review REJECT above — the ADR's original
  resolution, an outright ban borrowed from P4.2's grill-trace layer,
  was reverted for being stricter than the ledger's own decided ceiling).
- Directory enumeration under `.shipwright/planning/` for split discovery
  — abandoned in round 2 after two independent reviewers found it cannot
  distinguish a real split from a reserved non-split dir; replaced with
  manifest-driven enumeration.
- Failing the whole manifest on ANY invalid split-name entry (openai
  round 7's suggestion) — rejected in favor of the existing per-split
  granularity (`no_empty_split`'s own model): keep the valid subset,
  fail loud only when nothing valid survives.
