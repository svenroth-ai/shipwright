# Sub-Iterate A — Boundary Tests Foundation

> Part of campaign `iterate-skill-hardening`. Read
> `.shipwright/planning/iterate/campaigns/iterate-skill-hardening/campaign.md`
> for the campaign-level intent and the dog-food meta-directives.

## Context

iterate-2026-05-03-adopt-env-local-scaffold introduced two latent
producer-consumer bugs in `parse_env_file`:

1. Trailing `# comment` was not stripped (so `os.environ[KEY]` got
   `'sk-or-real        # description'` instead of `'sk-or-real'`)
2. UTF-8 BOM from Notepad-saved files prefixed the first key
   (`﻿KEY` instead of `KEY`)

Both bugs survived: 47 unit tests green, both Gemini and OpenAI external
reviews satisfied. Sven caught them by asking for an empirical
producer→file→consumer round-trip probe.

A's job: encode that lesson as a first-class concept in the iterate skill
so future iterates can't ship a producer/consumer pair without round-trip
proof — and so risk classification surfaces the boundary up-front.

## Scope

1. Risk taxonomy: add `touches_io_boundary` flag.
2. Phase: add **Boundary Probe** as an explicit sub-step in Build (TDD),
   gated by `touches_io_boundary`.
3. Reference doc: `references/boundary-probes.md` — the canonical edge-case
   list (BOM, CRLF, non-ASCII, export-prefix, inline-comment, empty
   values, `#` inside quoted values, plus the round-trip pattern itself).
4. Self-Review checklist: add a 7th item — *"Affected Boundaries explicitly
   identified? Producer/consumer pair tested round-trip if touched?"*
5. Round-trip-test pattern reference: `references/round-trip-tests.md`
   covers the duplicated-consumer drift hotspot pattern + the
   producer→file→consumer assert pattern.
6. Iterate spec template: gain "Affected Boundaries" + a placeholder
   "Confidence Calibration" header (B will fully populate the latter).
7. SKILL.md: ensure B1a parallel-sessions snippet remains discoverable;
   no logic change here, but verify it survives the Boundary Probe insert.

## Acceptance Criteria

- [ ] `RISK_TAXONOMY` in
      `plugins/shipwright-iterate/scripts/lib/classify_complexity.py`
      contains a `touches_io_boundary` entry. Patterns include
      `\.env`, `parse_env`, `\.json` config write/read keywords,
      `hooks\.json`, `settings\.json`, `dump`, `serialize`, `parse_`,
      `load_`, `write_`. `min_complexity = "small"`,
      `enforces = ["round_trip_test"]`.
- [ ] Self-detection helper: `is_io_boundary_change(changed_files)`
      returns True when any changed file path matches
      `(.env|hooks\.json|settings\.json|.*_config\.json|.*_state\.json)`
      OR when a Python source file contains both a
      writer-style call (regex `(json\.dump|yaml\.dump|\.write_text\()`)
      AND another file in the same diff contains the matching reader
      (`json\.load|yaml\.safe_load|\.read_text\(`). Path check covers
      90% of real cases; the AST-pair check covers the producer/consumer-
      lives-in-different-files case from the env iterate.
- [ ] `plugins/shipwright-iterate/skills/iterate/references/boundary-probes.md`
      exists and documents at minimum these 8 probe categories:
      UTF-8 BOM, CRLF line endings, non-ASCII values, POSIX
      `export KEY=value` prefix, inline `# comment`, `#` without
      leading whitespace inside a value, quoted values containing `#`,
      empty values (`KEY=`, `KEY=""`).
- [ ] `plugins/shipwright-iterate/skills/iterate/references/round-trip-tests.md`
      exists and documents:
      (a) the producer→file-on-disk→consumer pattern,
      (b) the duplicated-consumer drift-protection parametrized test
          pattern (when the same parser/serializer logic exists in N
          places),
      (c) when to apply (`touches_io_boundary` triggers it; user-edited
          formats also need the probes from boundary-probes.md).
- [ ] `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md`
      gains a 7th Self-Review item:
      "Affected Boundaries: were producer and consumer of any changed
      serialized format identified, AND was a real round-trip probe
      run? See `references/round-trip-tests.md`."
- [ ] `plugins/shipwright-iterate/skills/iterate/SKILL.md`:
      - Risk taxonomy table gains the row.
      - Path A Step 6 (Build TDD) gains an explicit
        "Boundary Probe (when `touches_io_boundary` is set)" sub-step
        that points at both reference docs.
      - Phase Matrix (Section 6) gains a "Boundary Probe" row with
        cells: trivial=skip, small=if-flag, medium=if-flag, large=—.
      - Override Classes table: Boundary Probe is **Safety-enforced**
        (skippable only with explicit risk acknowledgment).
- [ ] Iterate spec template (the snippet inside Path A Step 1 of
      SKILL.md) carries an "Affected Boundaries" section AND an empty
      "Confidence Calibration" stub. Stub stays empty here; B fills it.
- [ ] Tests:
      - `plugins/shipwright-iterate/tests/test_classify_complexity.py`
        gains assertions for `touches_io_boundary` flag detection.
      - `plugins/shipwright-iterate/tests/test_boundary_detection.py`
        (new) covers `is_io_boundary_change` (path-match case +
        producer/consumer-AST-pair case + negative case).
      - `plugins/shipwright-iterate/tests/test_boundary_probes_doc.py`
        (new) asserts the reference doc enumerates all 8 probe
        categories by parsing markdown headings (drift-protection).
      - Existing test suites must remain green.

## Implementation Plan

### File-by-file changes

1. `plugins/shipwright-iterate/scripts/lib/classify_complexity.py`
   - Add `touches_io_boundary` entry to `RISK_TAXONOMY`.
   - Add `IO_BOUNDARY_FILE_PATTERNS` tuple.
   - Add helper `is_io_boundary_change(changed_files: list[str]) -> bool`.
   - For the AST-pair case: keep it path-match-only in this iterate
     unless time permits — note in a comment that AST-based detection
     is a future enhancement. The path-match alone covers all known
     real-world cases.

2. `plugins/shipwright-iterate/skills/iterate/references/boundary-probes.md` (NEW)
   - 8 sections, one per probe category.
   - Each section: rationale (why this probe matters), one-line
     example of the failing producer/consumer scenario, recommended
     pytest pattern.
   - Cross-reference to the env iterate's two latent bugs as motivating
     examples.

3. `plugins/shipwright-iterate/skills/iterate/references/round-trip-tests.md` (NEW)
   - Section 1: "Pattern — producer→file→consumer".
     - Skeleton pytest example.
     - Why "test the producer + test the consumer" misses the format
       mismatch.
   - Section 2: "Pattern — duplicated-consumer drift protection".
     - Reference the env iterate's lib-vs-validate_env divergence.
     - Skeleton parametrized test.
   - Section 3: "When to apply".
     - `touches_io_boundary` flag triggers; refer to phase matrix.

4. `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md`
   - Add 7th Self-Review item under "Self-Review Checklist".
   - Update the Output Format block to include the new line.

5. `plugins/shipwright-iterate/skills/iterate/SKILL.md`
   - Risk Taxonomy table: add the row.
   - Path A Step 6 (Build): add Boundary Probe sub-step.
   - Path B (CHANGE) and Path C (BUG): add a one-line cross-reference.
   - Phase Matrix Section 6: add Boundary Probe row.
   - Override Classes: add Boundary Probe under Safety-enforced.
   - Iterate Spec template inside Path A Step 1:
     append `## Affected Boundaries` section template +
     `## Confidence Calibration` empty stub.

6. Tests
   - `plugins/shipwright-iterate/tests/test_classify_complexity.py`:
     extend with `test_touches_io_boundary_flag_detection` and
     `test_touches_io_boundary_min_complexity`.
   - `plugins/shipwright-iterate/tests/test_boundary_detection.py`
     (new): cover `is_io_boundary_change`.
   - `plugins/shipwright-iterate/tests/test_boundary_probes_doc.py`
     (new): markdown drift-protection.

## Affected Boundaries

This sub-iterate produces several serialized/structured artifacts that
other code reads — manually populated since Sub-Iterate D's scanner
isn't online yet.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `classify_complexity.py::classify` (`risk_flags` list) | `SKILL.md` Section "Repo Scout" + iterate spec template | JSON `risk_flags[]` |
| `classify_complexity.py::is_io_boundary_change` | sub-iterate-runner brief (in B/C/D and beyond) | bool return value |
| `references/boundary-probes.md` (markdown headings) | `tests/test_boundary_probes_doc.py` (drift-protection parser) | Markdown structure |
| `references/round-trip-tests.md` (markdown headings) | iterate runners reading the doc when flag fires | Markdown structure |
| `iteration-reviews.md` 7th Self-Review item | Build runners outputting the Self-Review block | Plain-text checklist line |

The most important boundary here is the **classify_complexity.py JSON
output ↔ SKILL.md Repo Scout consumer** — the new `touches_io_boundary`
risk flag is a string that must match exactly between the producer's
emit-site and the consumer's match-site. The `tests/test_classify_*`
suite is the round-trip test for that boundary.

For the markdown reference docs, the round-trip is structural rather
than character-exact: a drift-protection test parses the headings and
asserts the canonical 8 probe categories appear. Loose enough to allow
prose edits, strict enough to catch accidental category drops.

## Confidence Calibration

(B fills in this section as a real phase. Until then, runner manually
populates before F0:)

- **Boundaries touched:** see "Affected Boundaries" above.
- **Empirical probes run:** _to be filled by runner_
  (at minimum: re-run `classify_complexity.py` end-to-end against a
  fixture path containing each `IO_BOUNDARY_FILE_PATTERN` and assert
  the flag fires).
- **Edge cases NOT probed + why acceptable:** _to be filled by runner_
  (likely candidates: AST-pair detection — explicitly deferred per
  Implementation Plan; cross-platform CRLF in markdown reference docs —
  not load-bearing because docs are markdown, not parsed as data).
- **Confidence-pattern check:** before declaring confident, ask
  "what would my round-trip probe miss?" and run one more probe if
  any answer is non-trivial.

## Runner Overrides

These override the sub-iterate-runner contract
(`plugins/shipwright-iterate/agents/sub-iterate-runner.md`) for this
campaign:

1. **DO NOT execute Step 5 (push to origin).** Stop after F7. The
   campaign orchestrator (parent session) handles all pushes at
   campaign-end with explicit user authorization. This is per the
   parallel-session source-of-truth rule and the campaign brief.
2. **DO NOT amend prior commits.** Each sub-iterate produces exactly
   one functional commit on its own branch (plus the F7 housekeeping
   commit if your finalize sequence requires it).
3. **After F7, write `.shipwright/runs/{loop_id}/{sub_iterate_id}/result.json`
   per the contract** and exit. The orchestrator picks it up.
4. **Branch name:** `iterate/skill-hardening-A-boundary-tests-foundation`.
   Branched from the orchestrator-supplied `base_branch` if set, else
   from current HEAD (which the orchestrator left at
   `iterate/skill-hardening`).

## DOG-FOOD Notes

This sub-iterate practices the very rules it builds:

- **Boundary Tests:** "Affected Boundaries" section above is populated;
  round-trip test for the `risk_flags[]` boundary is in
  `test_classify_complexity.py` extension; markdown drift-protection
  is in `test_boundary_probes_doc.py`.
- **Confidence Calibration:** stub above; runner must fill in before F0.
- **Multi-Session Discipline:** runner overrides 1–3 above.
- **Boundary-Coverage Awareness:** "Affected Boundaries" table is the
  manual data point that D's scanner will later consume.
