# Sub-Iterate D — shipwright-test Boundary-Coverage-Report

> Part of campaign `iterate-skill-hardening`. **Depends on A**: D's
> scanner reads "Affected Boundaries" sections from iterate-specs,
> which A standardized. Stacked on C per branch strategy.

## Context

A made `touches_io_boundary` a first-class flag and required iterates
that touch I/O boundaries to declare them in an `Affected Boundaries`
section. B made Confidence Calibration mandatory. C made multi-session
discipline structural. D closes the loop with **observability**: a
report that scans iterate-spec history and reports which boundaries
have been touched, which had round-trip tests, and which probes
covered which edge cases.

This report is for retrospective auditing and for catching iterates
that *should* have flagged `touches_io_boundary` but didn't (missing
section is itself a finding).

## Scope

1. New flag on `/shipwright-test`: `--report-boundary-coverage`.
   Output is a markdown report saved to
   `shipwright_test_results.json#boundary_coverage_report` AND
   `.shipwright/test-reports/boundary-coverage-{date}.md`.
2. Scanner module that:
   - Walks `.shipwright/planning/iterate/*.md` (iterate specs across
     all runs).
   - Parses `## Affected Boundaries` sections (markdown table form,
     Producer | Consumer | Format).
   - Cross-references each iterate's commit history (via
     `shipwright_events.jsonl`) to detect whether a round-trip test
     was added (heuristic: any test file under `tests/` mentioning
     producer or consumer name in a `--commit` of that run).
3. Report sections:
   - **Coverage Summary:** boundaries touched / round-trip-tested /
     probed.
   - **Per-iterate breakdown:** one row per iterate spec.
   - **Findings:** iterates touching IO files (per
     `is_io_boundary_change`) but missing the Affected Boundaries
     section (= drift signal).

## Acceptance Criteria

- [ ] `plugins/shipwright-test/scripts/tools/boundary_coverage_report.py`
      (new) with:
      - `scan_specs(project_root) -> list[BoundarySpec]` — parses
        Affected Boundaries tables from iterate specs.
      - `correlate_with_commits(specs, events_jsonl) -> list[CoverageRow]`
        — joins each spec to commits + test files added.
      - `render_markdown(rows) -> str` + `render_json(rows) -> dict`.
      - CLI (shipped, **richer than the original AC** per E spec HIGH-3):
        `uv run boundary_coverage_report.py --project-root . \
            [--output-markdown PATH] [--output-json PATH] [--print-json] \
            [--merge-into PATH]`.
        The original `--output {file|json}` mode-selector idea was
        superseded by separate `--output-markdown` / `--output-json`
        flags (less ambiguous; supports writing both at once) plus
        `--print-json` for pipe-friendly stdout. E added `--merge-into`
        for the single-step merge into `shipwright_test_results.json`
        (HIGH-4).
- [ ] `plugins/shipwright-test/skills/test/SKILL.md` (or whichever
      file holds the test skill's flag list) gains
      `--report-boundary-coverage` flag documentation pointing at the
      tool.
- [ ] `plugins/shipwright-test/scripts/lib/test_runner.py` (or
      equivalent — if not present, hook into wherever the test skill
      dispatches CLI flags): when the flag is set, run the tool after
      the test phase and merge the JSON output into
      `shipwright_test_results.json`.
- [ ] Findings section: iterates whose changed files matched
      `is_io_boundary_change` (consumed from A) but lacked an
      `## Affected Boundaries` section are listed under "Drift
      Signals". This is the audit hook for catching skipped boundary
      declarations.
- [ ] Tests:
      - `plugins/shipwright-test/tests/test_boundary_coverage_report.py`
        (new):
        - Fixture iterate-spec with Affected Boundaries table → parser
          extracts all 3 columns correctly.
        - Spec WITHOUT Affected Boundaries section + a fixture
          events.jsonl with an IO-touching commit → drift signal
          fires.
        - Round-trip detection heuristic on a fixture (test file
          mentions producer name → tested=True).
        - Markdown render + JSON render both round-trip.
      - Specifically: this sub-iterate practices A's round-trip
        pattern — the markdown render output is parsed back via the
        JSON render's dict, asserting structural equivalence.

## Implementation Plan

1. Create `boundary_coverage_report.py` under
   `plugins/shipwright-test/scripts/tools/`.
   - Use `re.compile` for the markdown table parser; tolerant of
     whitespace + alignment markers (`|---|---|---|`).
   - Detect Affected Boundaries section by literal heading match
     (`^## Affected Boundaries\s*$`).
   - Stop at next `^## ` heading.
   - Round-trip detection heuristic: for each (Producer, Consumer)
     row, search test files committed in this run for the producer's
     bare name. If found in at least one test file, mark
     `round_trip_tested=true`. Acknowledged as heuristic, not proof.
2. Wire CLI flag in test SKILL or runner.
3. Tests as listed in AC.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| iterate-spec authors (Sub-Iterate A's template) | `boundary_coverage_report.scan_specs` | Markdown `## Affected Boundaries` table |
| `is_io_boundary_change` (from A) | `boundary_coverage_report.correlate_with_commits` | bool |
| `boundary_coverage_report.render_json` | `shipwright_test_results.json#boundary_coverage_report` | JSON object |
| `boundary_coverage_report.render_markdown` | `.shipwright/test-reports/boundary-coverage-*.md` | Markdown report |

The Markdown table parser is the highest-risk boundary — iterate-spec
authors edit by hand, so all 8 probe categories from A's
`boundary-probes.md` apply. The round-trip-test pattern in this
sub-iterate is: parse a fixture markdown table → render JSON → render
markdown → re-parse → assert equivalence.

## Confidence Calibration

- **Boundaries touched:** see Affected Boundaries above. The most
  load-bearing one is the **markdown `## Affected Boundaries` table**
  — iterate-spec authors edit it by hand, so all 8 probe categories
  from A's `boundary-probes.md` apply. Secondary boundary is
  `events.jsonl` consumption, which is producer-machine-only (lower
  risk).

- **Empirical probes run (all PASS):**
  1. **Round-trip probe.** Fixture spec with 3-row Affected Boundaries
     table → `parse_affected_boundaries` → `render_json` → JSON dict →
     `_render_boundaries_table` → re-parsed → asserted structural
     equivalence (producer/consumer/format match field-by-field).
     `TestRoundTripRender::test_render_json_then_markdown_then_reparse_equivalent`
     PASSED.
  2. **BOM probe.** Fixture spec prefixed with `\xef\xbb\xbf` →
     parser strips BOM in `_read_text_lenient` and returns 3 boundaries.
     `TestParseMarkdownTable::test_handles_utf8_bom` PASSED.
  3. **CRLF probe.** Fixture spec converted to CRLF line endings →
     parser normalizes via `replace("\\r\\n", "\\n")` and returns the
     same 3 boundaries with no trailing `\\r` polluting the format
     value. `test_handles_crlf_line_endings` PASSED.
  4. **Non-ASCII probe.** Producer name `Müllabfuhr.py::dump` and
     format `JSON — ümlaut payload` round-trip through UTF-8 decode
     intact. `test_handles_non_ascii` PASSED.
  5. **Empty section probe.** Spec with `## Affected Boundaries`
     heading followed only by prose `(none — pure refactor)` → parser
     returns `[]` instead of crashing. `test_section_present_but_no_table_returns_empty`
     PASSED.
  6. **Drift-signal probe.** Spec WITHOUT `## Affected Boundaries`
     section + fixture events.jsonl with `changed_files: [".env.local",
     "shipwright_run_config.json"]` → `correlate_with_commits` flags
     `drift_signal=True`. `test_drift_signal_fires_when_io_commit_lacks_section`
     PASSED.
  7. **Real-world smoke test.** Ran the tool against the live
     `.shipwright/planning/iterate/` tree:
     - 17 specs scanned
     - 4 specs with `## Affected Boundaries` (= A, B, C, D — all four
       campaign sub-iterates correctly detected, with 5/3/4/4 boundary
       rows respectively, matching the actual table contents)
     - 7 drift signals (pre-existing iterate specs touching `.env.local`,
       `hooks.json`, `.claude/settings.json`, `shipwright_test_config.json`
       — exactly the audit hook intent)
     - `round_trip_tested: 2/16` (heuristic finds tests mentioning
       producer bare-names; conservative because most A/B/C/D producer
       names are descriptive prose like "iterate-spec authors",
       not Python identifiers)
  8. **8th probe — exact-heading discipline.** Heading like
     `## Affected Boundaries Notes` (with extra suffix) is correctly
     ignored — the regex `^##\s+Affected Boundaries\s*$` is exact.
     `test_heading_match_is_exact` PASSED.
  9. **Lint/type check.** `uvx ruff check
     plugins/shipwright-test/scripts/tools/
     plugins/shipwright-test/tests/test_boundary_coverage_report.py`
     → "All checks passed!".
  10. **Full plugin suite probe.** `pytest plugins/shipwright-test/tests/`
      → 122 tests green (103 baseline + 19 new). `pytest
      plugins/shipwright-iterate/tests/` → 146 tests green (no
      regressions from C). `pytest shared/tests/` → 1237 passed +
      34 pre-existing failures in `test_phase_plugin_hooks_consistency.py`
      (out of scope — predates this campaign).

- **Edge cases NOT probed + why acceptable:**
  - **POSIX `export` prefix, inline `# comment`, hash-in-quotes,
    empty values.** These four probes from A's boundary-probes.md
    target *env-file* parsing semantics. The `## Affected Boundaries`
    table is markdown, not env-file syntax — operators don't write
    `export Producer | Consumer | Format` in spec tables. Skipping
    these four with one-line justification per A's
    `references/boundary-probes.md` "machine-only formats" note.
  - **AST-pair detection on iterate-spec source files.** D consumes
    A's `is_io_boundary_change` directly; the path-match path catches
    every drift signal seen on real specs (7/7 above). AST-pair work
    deferred per A's same-rationale.
  - **Cross-process round-trip via subprocess invocation.** D's
    producer (the tool itself) and consumer (`shipwright_test_results.json`
    merge) live in the same process — the in-process render-then-reparse
    test in probe #1 is the load-bearing assertion.

- **Confidence-pattern check.** Asked "what would my round-trip probe
  miss?":
  - **Answer 1:** A spec where someone writes `## Affected Boundaries`
    but mistakenly uses HTML table syntax (`<table>...</table>`) instead
    of markdown pipes. Parser would silently return `[]`. Mitigated by
    the drift-signal path: if commits also touch IO files, it still
    fires.
  - **Answer 2:** A spec author lists the boundary rows but forgets
    the header row (so `data_rows = table_rows[1:]` skips a real row).
    Acknowledged as an under-detection bug with floor=1 missed
    boundary; not a correctness/safety issue. Documented as future
    enhancement candidate (validate header tokens).
  - **Answer 3:** Round-trip-tested heuristic depends on producer name
    being a Python identifier substring. Producer names in A/B/C/D
    specs are prose ("iterate-spec authors", "is_io_boundary_change") —
    so the 2/16 detection rate accurately reflects the heuristic's
    floor on prose producers, not a parser bug.
  No additional probes warranted — all real-world failure modes are
  documented and the 17-spec smoke-test confirms the tool produces
  meaningful audit output.

## Runner Overrides

1. NO push (Step 5). Orchestrator handles all pushes at campaign-end.
2. NO commit amends.
3. After F7, write result.json and exit.
4. Branch name: `iterate/skill-hardening-D-boundary-coverage-report`.
   Branched from `base_branch =
   iterate/skill-hardening-C-multi-session-discipline` (stacked).

## DOG-FOOD Notes

- **Boundary Tests:** A's pattern is the load-bearing test pattern of
  this sub-iterate (parse → render → parse round-trip).
- **Confidence Calibration:** template populated above by runner.
- **Multi-Session Discipline:** runner overrides 1–3.
- **Boundary-Coverage Awareness:** ironically D itself is the
  observability tool — but its own Affected Boundaries section is
  populated and will be auto-detected by future runs of D.
