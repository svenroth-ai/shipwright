# Sub-Iterate B — Confidence Calibration Phase

> Part of campaign `iterate-skill-hardening`. **Depends on Sub-Iterate A**:
> the iterate spec template gains a "Confidence Calibration" stub in A;
> B replaces the stub with a real phase + reference doc.

## Context

Confidence collapses without empirical anchor. On
iterate-2026-05-03-adopt-env-local-scaffold, the answer to
*"are you confident?"* was twice "yes" — and both times a probe
afterwards found a real bug. Three rounds of *"are you confident?"
→ probe → bug"* established the asymptote: the area is not exhausted
until at least one probe finds nothing. B encodes this calibration
heuristic so future iterates ask the calibration question structurally
rather than ad-hoc.

## Scope

1. **New phase: Confidence Calibration**, inserted between Self-Review
   (Path A Step 7) and F0 Fresh Verification Gate.
2. Reference doc `references/confidence-anti-patterns.md` documents:
   - The "are you confident?" anti-pattern (asking the question and
     accepting the answer without testing it).
   - The asymptote heuristic (2 probes finding bugs → at least one more;
     3 probes with no findings → exhausted).
   - The link to `boundary-probes.md` for the probe checklist.
3. SKILL.md update: phase matrix, lifecycle, iterate spec template fully
   filled in (replacing A's stub).
4. Phase complexity gating: Confidence Calibration is **mandatory at
   medium+** AND **mandatory whenever `touches_io_boundary` is set**
   (regardless of complexity). Trivial/small without flag may skip.

## Acceptance Criteria

- [ ] `plugins/shipwright-iterate/skills/iterate/references/confidence-anti-patterns.md`
      exists and documents at minimum:
      - "Are you confident?" anti-pattern definition + counter-pattern
        ("instead of asking, run a probe").
      - Asymptote heuristic with a worked example from the env iterate.
      - Link to `boundary-probes.md`.
      - Decision rule: when to stop probing.
- [ ] `plugins/shipwright-iterate/skills/iterate/SKILL.md` Path A:
      - New "Step 7.5: Confidence Calibration" between Step 7
        (Self-Review) and Step 8 (Full Code Review).
        Step body: 4 questions the runner must answer in the
        iterate-spec's Confidence Calibration section before F0.
      - Phase Matrix Section 6 gains a "Confidence Calibration" row.
        Cells: trivial=skip, small=if-flag, medium=always,
        large=always. Where "if-flag" = touches_io_boundary set.
      - Override Classes: Confidence Calibration is **Mandatory at
        medium+, Safety-enforced at small with `touches_io_boundary`,
        Advisory otherwise.**
- [ ] Iterate spec template (Path A Step 1 inside SKILL.md): the
      Confidence Calibration stub left by A is replaced with the full
      template:
      ```
      ## Confidence Calibration
      - **Boundaries touched:** {list from Affected Boundaries}
      - **Empirical probes run:** {one-line per probe + finding}
      - **Edge cases NOT probed + why acceptable:** {list}
      - **Confidence-pattern check:**
        - Has any "are you confident?"-style question already produced
          "yes" + a subsequent finding in this run? If yes, add one more
          probe before F0.
      ```
- [ ] Path B (CHANGE) and Path C (BUG): one-line cross-reference to
      Step 7.5 in SKILL.md (so the new phase is reachable from all
      paths).
- [ ] Tests:
      - `plugins/shipwright-iterate/tests/test_confidence_anti_patterns_doc.py`
        (new): drift-protection parses the markdown headings of
        `confidence-anti-patterns.md` to assert the asymptote heuristic
        and "are you confident?" sections are present.
      - `plugins/shipwright-iterate/tests/test_skill_phase_matrix.py`:
        if such a test exists, extend; if not, add one that parses
        SKILL.md's Phase Matrix table and asserts both
        "Confidence Calibration" and "Boundary Probe" (from A) appear
        as rows.

## Implementation Plan

1. Create `references/confidence-anti-patterns.md` (~200 lines).
   Sections:
   - 1: The "are you confident?" anti-pattern.
   - 2: Asymptote heuristic with worked env-iterate example.
   - 3: Decision rule — when to stop probing.
   - 4: Cross-references (boundary-probes.md, round-trip-tests.md).

2. Edit `SKILL.md`:
   - Insert "Step 7.5: Confidence Calibration" inside Path A.
     Body: the 4-question template the runner must populate.
   - Update Phase Matrix Section 6: add row.
   - Update Override Classes table.
   - Replace A's stub in the Path A Step 1 template with the full
     template (the AC above).

3. Path B + Path C: one-line cross-reference each. Keep terse.

4. Tests as listed in AC.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `references/confidence-anti-patterns.md` headings | `tests/test_confidence_anti_patterns_doc.py` (drift parser) | Markdown structure |
| `SKILL.md` Phase Matrix table | `tests/test_skill_phase_matrix.py` (drift parser) | Markdown table |
| Iterate spec template inside SKILL.md | every iterate runner reading the spec template | Plain text |

## Confidence Calibration

- **Boundaries touched:** see "Affected Boundaries" above.
- **Empirical probes:** _to be filled by runner_
  - Re-render the iterate spec template in a fixture, assert that the
    Confidence Calibration section now has all 4 fields by name.
  - Parse SKILL.md's Phase Matrix and assert the Confidence Calibration
    row exists with the right cells.
- **Edge cases NOT probed + why acceptable:** _to be filled by runner_
  - Cross-platform line endings in the markdown reference doc — not
    load-bearing.
- **Confidence-pattern check:** _to be filled by runner_
  Specifically: has any "are you confident?" question received a "yes"
  in this sub-iterate followed by a real finding? If yes, run one more
  probe before F0.

## Runner Overrides

Same as A:

1. NO push to origin (Step 5 of runner contract). Orchestrator handles
   all pushes at campaign-end with explicit user authorization.
2. NO commit amends.
3. After F7, write result.json and exit.
4. Branch name: `iterate/skill-hardening-B-confidence-calibration`.
   Branched from `base_branch =
   iterate/skill-hardening-A-boundary-tests-foundation` (per stacked
   strategy — orchestrator passes this to the runner).

## DOG-FOOD Notes

- **Boundary Tests:** A's flag and reference docs are now consumed by
  this sub-iterate's tests — the round-trip is markdown-structure-via-
  drift-protection.
- **Confidence Calibration:** this sub-iterate's own spec carries the
  template that B itself produces. The runner must populate before F0
  (recursive but valid: B builds the template, B uses the template).
- **Multi-Session Discipline:** runner overrides 1–3.
- **Boundary-Coverage Awareness:** Affected Boundaries table populated.
