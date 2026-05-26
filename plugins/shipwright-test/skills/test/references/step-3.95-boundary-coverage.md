# Step 3.95: Boundary Coverage Report (if --report-boundary-coverage)

**Condition:** Runs only when invoked with `--report-boundary-coverage`,
OR when `shipwright_test_config.json` sets `boundary_coverage.enabled: true`.

**Purpose:** Audit hook for Sub-Iterate A's `touches_io_boundary`
discipline (ADR-024). Scans `.shipwright/planning/iterate/**/*.md`
for `## Affected Boundaries` sections, correlates each spec with
commits in `shipwright_events.jsonl`, and emits a coverage report:

- **Coverage Summary**: boundaries touched / round-trip-tested / probed
- **Per-iterate breakdown**: one row per iterate spec
- **Drift Signals**: iterates whose commits or spec text touched
  IO-boundary files but did NOT declare an `## Affected Boundaries`
  section — the audit hook for catching skipped boundary declarations

**1. Run the report:**
```bash
uv run "{plugin_root}/scripts/tools/boundary_coverage_report.py" \
  --project-root "{project_root}" \
  --output-markdown ".shipwright/test-reports/boundary-coverage-{YYYY-MM-DD}.md" \
  --output-json ".shipwright/test-reports/boundary-coverage-{YYYY-MM-DD}.json"
```

**2. Merge into `shipwright_test_results.json`:**

After the report runs, embed the JSON output under
`shipwright_test_results.json#boundary_coverage_report` so downstream
compliance tooling can ingest it without re-scanning. Two equivalent
ways to do this (E spec HIGH-4 — pick one):

**Option A — single command** (preferred when you don't need a
standalone JSON artefact):

```bash
uv run "{plugin_root}/scripts/tools/boundary_coverage_report.py" \
  --project-root "{project_root}" \
  --output-markdown ".shipwright/test-reports/boundary-coverage-{YYYY-MM-DD}.md" \
  --merge-into "{project_root}/shipwright_test_results.json"
```

**Option B — two-step flow** (when you also want the standalone
`.shipwright/test-reports/*.json` artefact alongside the merge):

```bash
# (Step 1 above already wrote the standalone JSON.)
uv run "{plugin_root}/scripts/tools/merge_boundary_coverage.py" \
  --input ".shipwright/test-reports/boundary-coverage-{YYYY-MM-DD}.json" \
  --target "{project_root}/shipwright_test_results.json"
```

Both write atomically (`tmp.replace(target)`) and preserve any other
top-level keys already present in the target.

Resulting shape:

```json
{
  "boundary_coverage_report": {
    "summary": {
      "specs_scanned": 47,
      "specs_with_boundaries": 12,
      "total_boundaries": 31,
      "round_trip_tested": 18,
      "round_trip_unknown": 2,
      "drift_signals": 3
    },
    "rows": [...]
  }
}
```

The `round_trip_unknown` counter (E spec HIGH-5) tracks boundaries
where the matched commit's events lacked `changed_files`, so the
heuristic could not distinguish "no test added" from "we don't know".

**3. Non-blocking:** Drift signals produce WARNINGs in the test summary,
never hard-fail the pipeline. The drift signals are a discipline
indicator, not a correctness gate.

See `tools/boundary_coverage_report.py` source for parser semantics,
including the 8-probe coverage on the markdown table parser
(BOM, CRLF, non-ASCII, etc.) and the round-trip test heuristic.
