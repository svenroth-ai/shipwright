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
      - CLI:
        `uv run boundary_coverage_report.py --project-root . --output {file|json}`.
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

- **Boundaries touched:** see Affected Boundaries.
- **Empirical probes:** _to be filled by runner_
  - Round-trip: parse → render-json → render-md → parse → assert
    equivalence on fixture spec.
  - BOM probe: prepend `﻿` to fixture spec, parser must succeed.
  - CRLF probe: convert fixture to CRLF, parse must succeed.
  - Non-ASCII probe: producer/consumer names with umlauts in fixture.
  - Empty Affected Boundaries section probe: heading without table →
    parser returns empty list, not crash.
  - Drift-signal probe: spec with IO-touching commit but no Affected
    Boundaries section → drift signal fires.
- **Edge cases NOT probed + why:** _to be filled by runner_
- **Confidence-pattern check:** _to be filled by runner_

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
