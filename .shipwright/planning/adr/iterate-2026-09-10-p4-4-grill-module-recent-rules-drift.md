# Pin Sec.0/Sec.4/Sec.5's most recent rules against drift

## Context

`shared/requirement-elicitation.md`'s three newest rules had no drift test:
Sec.0 ("The order — do it in this sequence", the section BEFORE Sec.1, whose
own text calls itself "load-bearing") was entirely absent from
`REQUIRED_SECTIONS`, so it could be deleted whole without any test turning
red; the Sec.5 minimum-two-scenarios rule (FR-01.16 AC05) and the Sec.4
glossary cross-check trigger (FR-01.16 AC04) had section headings pinned by
`REQUIRED_SECTIONS`/`test_module_retains_cited_sections` but not their rule
sentences, so a reword that gutted either rule while keeping the heading
would pass silently — the same gap `test_module_pins_the_load_bearing_rules_by_sentence`
already closed for two other Sec.0/Sec.8 rules.

## Decision

Appended `"## 0. The order — do it in this sequence"` to the END of
`REQUIRED_SECTIONS` in `shared/tests/test_requirement_elicitation_refs.py`
(per the card's own instruction — not inserted at position 0; the existing
12 entries keep their order and position) and added three new pinning tests
mirroring `test_module_pins_the_load_bearing_rules_by_sentence`'s style —
one per rule, each asserting the rule's own sentence (not just its heading)
is `in body`:

- `test_module_pins_the_execution_order_rule_by_sentence` — pins `"the order
  is load-bearing"` (Sec.0).
- `test_module_pins_the_minimum_two_scenarios_rule_by_sentence` — pins `"The
  minimum is two per requirement, put to the person"` (Sec.5, FR-01.16 AC05).
- `test_module_pins_the_glossary_cross_check_trigger_by_sentence` — pins
  `"Trigger: every time a term is captured, check it against the terms
  already there"` (Sec.4, FR-01.16 AC04).

## Consequences

Deleting or rewording any one of the three sentences now turns exactly its
own new test red (verified manually, see "AC5 spot-check" below); the other
35 pre-existing tests across the two sibling files are unaffected. No
production code, schema, or architecture surface changed — test-only drift
protection.

## Rationale

Matching the existing `test_module_pins_the_load_bearing_rules_by_sentence`
style (one assertion per rule sentence, in a dedicated test function with a
docstring explaining what failure mode it closes) keeps the file consistent
rather than growing a second pinning idiom. The Sec.4 trigger sentence
soft-wraps across a markdown source line
(`...already\n  there.**`); rather than inventing a new normalization
helper, the fix inlines `" ".join(body.split())` — collapsing all
whitespace runs (including the line-wrap) to single spaces before the
substring check — the smallest fix that makes the wrapped phrase
contiguous, confined to the one assertion that actually needs it.

## Rejected alternatives

- Inserting the new `REQUIRED_SECTIONS` entry at position 0 (matching the
  document's own Sec.0-before-Sec.1 ordering) — rejected per the card's
  explicit instruction to append at the END, so the existing 12 entries'
  order and position stay untouched (a smaller, more reviewable diff than a
  list reorder).
- A generic whitespace-normalizing helper function for the whole file —
  rejected as premature: only the Sec.4 trigger sentence actually wraps in
  the raw file (verified by reading `shared/requirement-elicitation.md`
  directly); the other two sentences the P4.4 card names are each on a
  single source line, so a shared helper would be an abstraction with a
  single call site.

## AC5 spot-check (red/green, manual — not shipped as an automated meta-test)

Performed against the real, tracked `shared/requirement-elicitation.md`
(temporarily edited via `git checkout --` to restore, confirmed clean before
and after each probe — no scratch-copy indirection needed since the file was
already at a known-clean git state):

1. Removed `"the order is load-bearing"` from Sec.0 → ran
   `pytest -k test_module_pins_the_execution_order_rule_by_sentence` → FAILED
   (only that test). Restored via `git checkout --`, confirmed clean.
2. Removed `"The minimum is two per requirement, put to the person"` from
   Sec.5 (replaced with an unrelated sentence) → ran
   `pytest -k test_module_pins_the_minimum_two_scenarios_rule_by_sentence` →
   FAILED (only that test). Restored, confirmed clean.
3. Removed the Sec.4 trigger sentence's key clause (replaced the
   `"Trigger: ..."` bullet with unrelated prose) → ran
   `pytest -k test_module_pins_the_glossary_cross_check_trigger_by_sentence`
   → FAILED (only that test). Restored, confirmed clean.

Full suite (38 tests across `test_requirement_elicitation_refs.py` +
`test_requirement_elicitation_discovery.py`) re-run after each restore
confirmed all-green before proceeding — each probe's failure was isolated to
its own new test, never a neighbour.

## Self-Review

1. **Spec Compliance** — pass. All 3 sub-iterate ACs met: `REQUIRED_SECTIONS`
   gains the Sec.0 heading at the end (order/position of the existing 12
   unchanged); the three new pinning tests exist, pin the exact wording
   quoted in the spec's "Verified today" section, and were independently
   red/green spot-checked (AC5, documented above); all pre-existing
   assertions across both sibling test files still pass.
2. **Error Handling** — N/A. Test-only change reading a fixed repo-relative
   path already read by every pre-existing test in the file; no new failure
   mode introduced.
3. **Security Basics** — pass (N/A-adjacent). No user input, no secrets, no
   new I/O boundary — reads the same local Markdown file the file's other
   ten tests already read.
4. **Test Quality** — pass. Each new test targets exactly one rule sentence,
   independently spot-check-verified to fail in isolation when (and only
   when) its own sentence is removed; docstrings state the failure mode each
   closes, matching the file's existing convention.
5. **Performance Basics** — pass. One additional `MODULE.read_text()` call
   per new test (already the file's existing pattern); no loops, no N+1, no
   new I/O boundary.
6. **Naming & Structure** — pass. Function names
   (`test_module_pins_the_execution_order_rule_by_sentence`,
   `..._minimum_two_scenarios_rule_by_sentence`,
   `..._glossary_cross_check_trigger_by_sentence`) state exactly which rule
   each pins, mirroring `test_module_pins_the_load_bearing_rules_by_sentence`.
   File stays at 248 lines, well under the 300-LOC bloat-baseline cap (sibling
   `test_requirement_elicitation_discovery.py` unchanged at 276 lines).
7. **Affected Boundaries (ADR-024)** — N/A, justified. No serialized-format
   producer/consumer boundary is touched — this reads Markdown prose that is
   not a wire format between two components (same justification P4.3's ADR
   gave for the sibling file); nothing writes `requirement-elicitation.md`
   programmatically and nothing downstream deserializes these tests' output
   beyond `pytest`'s own pass/fail.

## Confidence Calibration

Not triggered — Step 3.4's diff-driven risk re-check reported
`effective_complexity: "small"` (not upgraded from Stage-1's `small`),
`risk_flags: []` (no `touches_io_boundary`), so neither calibration trigger
condition holds. Self-Review (above) is the only review this run's
complexity requires.

## External-Plan-Review / External-Code-Review — not triggered

Step 3.4's diff-driven risk re-check: `stage1_complexity: "small"`,
`effective_complexity: "small"` (not upgraded), `risk_flags: []`,
`diff_loc: 59` (< 100), `plan_review_required: false`. None of Step 3.5's or
Step 3.7's trigger conditions (medium+, any canonical risk flag, diff > 100
LOC) hold, so both the external plan review (3.5) and the full code-review
cascade (3.7 — internal spec/code/doubt delegation AND the external LLM code
review) are skipped per those steps' own stated skip conditions, not
delegated. Recorded in `result.json` as `reviews.plan:
skipped_complexity_below_threshold`, `reviews.code:
skipped_diff_below_threshold`, `reviews.external_code:
skipped_diff_below_threshold`. Self-Review remains the only review pass this
run's size and risk profile requires.

## F2 — no structural impact

No new route, component, schema, service, write-surface, read-surface, or
convention. A test-only drift-protection addition to an existing test file;
`architecture.md` is unchanged.

## F3a — reflection

Confirmed the P4.3 ADR's own reflection (continuing-campaign-branch
`diff_risk_recheck.py --base-ref` staleness) before running Step 3.4: `git
diff --stat HEAD origin/main` was empty (content-identical), so `--base-ref
HEAD` (the tool's own documented default when omitted) was the correct,
already-safe choice here — no repeat of the inflated-diff symptom P4.3 hit.
Nothing new to add to `conventions.md` this run; the existing entry already
covers this campaign's shared-branch shape.

## Campaign-mode note

Built in campaign mode (interleaved-serial, shared branch), final
sub-iterate of `req3-09-p4-grill-glossary` (P4.1-P4.3 already merged).
Because Step 3.7's own trigger conditions did not hold for this diff (small
complexity, no risk flags, 59 LOC), the internal spec/code/doubt cascade and
the external code review were both genuinely skipped rather than delegated —
see "External-Plan-Review / External-Code-Review — not triggered" above.
