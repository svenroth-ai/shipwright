# Iterate Spec: escape markdown table cells

- **Run ID:** iterate-2026-05-20-escape-md-cells
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal

Stop the build dashboard and compliance reports from rendering broken markdown
tables when an event field (intent, description, FR list, commit subject …)
contains a literal `|` or newline. Empirically observed in the shipwright-webui
repo: a `description` containing `(local|tailscale|open)` shifted the
Recent-Changes row by three columns (Tests / Commit / FRs / Date all landed in
the wrong column). The bug is in the renderer, not in the upstream producer.

## Acceptance Criteria

- [ ] AC-1: A new `escape_cell()` helper lives at `shared/scripts/markdown_table.py`
      and converts `\` → `\\`, `|` → `\|`, `\r\n` / `\r` / `\n` → ` `.
      `None` → `""`, non-strings via `str(...)`.
- [ ] AC-2: All cells of the **Recent Changes** row in
      `shared/scripts/tools/update_build_dashboard.py::_generate_from_events`
      are wrapped in `escape_cell()`. Same for the **Build History** row.
- [ ] AC-3: Every event-derived cell in the markdown tables in
      `plugins/shipwright-compliance/scripts/lib/rtm_generator.py`,
      `test_evidence.py`, `change_history.py`, and `compliance_report.py`
      (External-Review-Evidence row — free-text `provider` and `reason`
      from review markers) is wrapped in `escape_cell()`. Constant labels
      (e.g. column headers, hard-coded status strings) are not wrapped —
      those can never contain a pipe.
- [ ] AC-4: A regression test in `shared/tests/test_build_dashboard_md_escaping.py`
      feeds the dashboard renderer a synthetic iterate event with
      `description = "A (x|y|z) B"` and asserts the Recent-Changes row, when
      split on **un-escaped** `|`, has exactly 6 data cells (i.e. 8 segments
      after split: empty-leading + 6 cells + empty-trailing).
      A second sub-test uses `intent` containing a newline and asserts the
      row stays on one physical line.
- [ ] AC-5: Unit tests in `shared/tests/test_markdown_table.py` cover the
      eight boundary categories applicable to a machine-only markdown
      producer (pipe, newline, CRLF, leading/trailing whitespace
      preservation, mixed pipe+backslash, multiple pipes, empty string,
      `None`, non-string scalar).

## Spec Impact

This is a behaviour-preserving bug fix to internal rendering. No FR is
created, modified, or removed. The dashboard and compliance reports
continue to describe the same data; only the markdown serialization
becomes robust against pipe/newline in field values.

- **Classification:** NONE
- **NONE justification:** Bug fix in the markdown rendering layer of
  `update_build_dashboard.py` and three compliance lib files. No
  user-visible behaviour change at the application/spec level — the
  dashboard and compliance reports already promise tabular rendering;
  this iterate restores that promise when the underlying data contains
  table-active characters. No FR row is added, modified, or removed.

## Out of Scope

- Refactoring the two pre-existing markdown escapers
  (`shared/scripts/lib/stale_artifact_detector.py::_escape_md`,
  `shared/scripts/tools/aggregate_triage.py::_escape_md`) to delegate to
  the new helper. They escape different character sets for different
  contexts (path-rendering vs bullet-rendering) and centralising them
  would be a separate cleanup iterate.
- Building a generic markdown table renderer. The 5-7 call sites we
  fix here remain f-string-style; only the per-cell escape is shared.
- Patching old already-rendered `build_dashboard.md` / compliance
  markdown files in target repos. The renderer is now-correct;
  re-running an iterate or compliance pass regenerates the files.

## Design Notes

n/a — no UI change.

## Affected Boundaries

Markdown is a producer/consumer-shaped format (this renderer produces;
the operator's eyes / GitHub markdown viewer consume). However: the
"consumer" here is human-readable rendering, not a downstream parser
shipwright owns. There is no shipwright code that re-parses the
generated `build_dashboard.md` or `traceability-matrix.md` into
structured data. The Affected Boundaries table is therefore narrow:

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `update_build_dashboard.py::_generate_from_events` | GitHub-flavored markdown viewer (browser + GitHub web UI) | markdown table |
| `rtm_generator.py::_verification_timeline` etc. | same | markdown table |
| `test_evidence.py::_test_progression` etc. | same | markdown table |
| `change_history.py::generate` (commit table) | same | markdown table |

`is_io_boundary_change()` does not fire — none of the IO-boundary file
patterns or producer/consumer keywords match a markdown-rendering diff.
Per `references/boundary-probes.md`, four of the eight probe categories
are N/A for a machine-only markdown producer (POSIX `export` prefix,
inline `# comment`, quoted `#`, BOM round-trip) — none of those apply
to a table-cell escape that targets only `|` / `\` / newlines.

## Confidence Calibration

- **Boundaries touched:** Markdown rendering layer in
  `update_build_dashboard.py` and three compliance lib files. The
  "consumer" is a human eye / GFM viewer — there is no shipwright-owned
  re-parser of the rendered markdown.
- **Empirical probes run:**
  1. **Pipe in `description`** (the original bug repro): synthetic
     event with `description="A (x|y|z) B"` → rendered row splits to
     exactly 6 data cells. PASS.
  2. **Newline in `description`**: `"first line\nsecond line"` → row
     stays single-line, both lines collapse to one cell. PASS.
  3. **Pipe in `intent`** (defence-in-depth — `intent` is normally an
     enum but the contract is "every cell escaped"): `"feat|hack"` →
     escaped, no shift. PASS.
  4. **Backslash interaction**: helper unit test
     `test_escape_cell_escapes_backslash_before_pipe` verifies `\` is
     doubled BEFORE `|` is escaped so an upstream `\\|` round-trips
     correctly. PASS.
  5. **CRLF (Windows producer)**: `\r\n` → space. Test
     `test_escape_cell_collapses_crlf_to_space`. PASS.
  6. **Bare CR**: `\r` → space. Old-style Mac line endings.
     `test_escape_cell_collapses_bare_cr_to_space`. PASS.
  7. **Cross-plugin import path**: compliance lib's sys.path
     bootstrap (`Path(__file__).resolve().parents[4]`) was verified by
     running the compliance test suite (33 tests in the three changed
     files; 320 in the whole compliance plugin). All pass.
  8. **End-to-end producer→file→re-parser round-trip**: the
     integration regression test materialises an event in
     `shipwright_events.jsonl`, runs the real
     `generate_dashboard(project_root)`, and re-parses the rendered
     row via `re.split(r"(?<!\\)\|", row)`. The split asserts
     8 segments (empty + 6 cells + empty). This is the canonical
     ADR-024 boundary-probe pattern applied to markdown.
- **Edge cases NOT probed + why acceptable:**
  - **POSIX `export` prefix, inline `# comment`, quoted `#`** (3 of
    the 8 categories in `references/boundary-probes.md`): N/A — the
    producer is machine-only Python f-strings, not a user-edited env
    or YAML file. ADR-031 codifies this exemption for machine-written
    markdown.
  - **BOM round-trip**: N/A — the renderer writes UTF-8 to disk via
    `(agent_docs / "build_dashboard.md").write_text(content, encoding="utf-8")`
    with no BOM, identical to current behaviour. This iterate touches
    cell content, not file encoding.
- **Confidence-pattern check:** No "are you confident?"-style
  question has fired in this run. The bug repro was driven by the
  user's empirical observation in the shipwright-webui repo; my
  fix is gated by 23 mechanical assertions (cell counts, character
  substitutions) rather than self-attestation. Asymptote heuristic
  satisfied — the last probe (cross-plugin import path) returned
  no finding AND all applicable categories are covered.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  `uv run --directory C:/01_Development/shipwright/.worktrees/escape-md-cells pytest shared/tests/test_markdown_table.py shared/tests/test_build_dashboard_md_escaping.py -v --color=no`
- **Evidence path:** stdout captured by `surface_verification.py` under
  `.shipwright/runs/iterate-2026-05-20-escape-md-cells/surface_verification.json`
