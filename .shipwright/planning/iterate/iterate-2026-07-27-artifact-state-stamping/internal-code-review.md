# Internal code review — iterate-2026-07-27-artifact-state-stamping

Reviewer: `shipwright-build:code-reviewer` (opus), fresh context, reviewed against the
iterate spec's AC1–AC9. **Verdict: block** (two cheap blockers). 18 findings.

## What the reviewer confirmed holds

AC1 for the strip regex (no second `Source-State` regex in the tree); AC4's structural
claim (`collect_all` is the only non-test constructor of `ComplianceData` and reads both
fields off one `latest_work_event`; `latest_event_timestamp` is behaviour-identical for
every input, so the `events_log.latest_event_dt` parity test still passes); AC5 symmetric
and unable to eat body text or layout; AC6/7/8/9 properly pinned including
`utf-8-sig`/CRLF/array/corrupt and non-overwrite; and that `json.dumps(indent=2)+"\n"`
really does match `record_coverage_total.py`.

## Dispositions

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | baseline entry for `audit_staleness.py` understated the file by 10 lines → anti-ratchet would fail CI | **FIXED** — trimmed the file and reconciled all five baseline entries to measured counts; `anti_ratchet_check.py` now exits 0 |
| 2 | high | the new spec `(E)` criterion claimed the identifier is "never supplied by whoever wrote the record" — false for the test-results producer | **FIXED** — criterion reworded to what shipped; the code-resolved half (commit) and the declared half (run id) are now stated separately |
| 3 | med | `commit` bypassed `safe_run_id`; `commit="a clean"` forged a status token and `iterate-…-commit=deadbeef` parsed back AS a commit | **FIXED** — added `safe_commit()` used by `banner_line`/`to_block`/`from_block`; commit now parsed token-exact |
| 4 | med | `{run_id}` is an undefined placeholder in the test plugin and would be stamped verbatim | **FIXED** — both prompts now pass `$SHIPWRIGHT_RUN_ID` with an idempotent `:=` guard, and `safe_run_id` refuses `{`/`}` outright |
| 5 | med | the F5 stamp block sat *before* later whole-file writes that would drop `source_state` (the `coverage.total` loss, repeated) | **FIXED** — moved to the last step of `F5.md` with the reason stated |
| 6 | med | `_run_id_from_config` duplicates step 1 of `phase_quality._resolution.resolve_run_id` | **ACCEPTED IN PART** — not reused deliberately: that resolver's later steps fall back to a session id, which would fabricate a plausible-but-wrong run id and violate AC7. Documented at the call site |
| 7 | med | rationale duplicated across five-plus places (catalog **D**) | **FIXED** — module docstrings trimmed and pointed at the spec; `source_state.py` and `audit_staleness.py` both shrank |
| 8 | med | baseline bumps lack a bloat-exception ADR | **ACCEPTED IN PART** — four of five bumps eliminated by making the renderer change line-neutral or negative; the residual is `audit_staleness.py`, already `state="exception"`. Disclosed in the spec and the F3 decision drop |
| 9 | med | `F5.md` said "run it from the worktree" but the tool reads `--project-root`, so a main-root path silently stamps the wrong tree | **FIXED** — wording corrected, and the tool now warns when the declared run id disagrees with the record's own |
| 10 | low | `git status` prints repo-root-relative paths; the exclusion was computed against `--project-root`, so it silently missed in a subdirectory | **FIXED** — `_repo_relative()` re-expresses exclusions against `git rev-parse --show-toplevel` |
| 11 | low | at F5 `dirty` is `true` on essentially every run; the doc invited the opposite expectation | **FIXED** — disclosed in `F5.md` |
| 12 | low | the stdout line re-defined `[:12]` and `'(unknown)'` | **FIXED** — uses `SHORT_SHA_LEN` / `UNKNOWN_RUN` |
| 13 | low | `adr_id` also legitimately holds a real ADR reference, so a build-phase event rendered `run=ADR-055` | **FIXED** — `run_id_of()` returns `None` for an `ADR-\d+` value; tested |
| 14 | low | `getattr(data, "run_id", None)` on a field that always exists | **FIXED** — direct access |
| 15 | low | `"(no events)"` literal duplicated | **FIXED** — `NO_EVENTS` constant |
| 16 | low | `docs/hooks-and-pipeline.md` write matrix did not list the new writer | **FIXED** — row now names all three writers and their scopes |
| 17 | low | absolute import wedged into a relative-import block | **FIXED** — `from ._provenance import …` |
| 18 | low | "always, and only here" contradicted the agent, which also stamps | **FIXED** — both prompts reworded |

Reviewer's out-of-scope note, honoured: the absence of an enforcing gate
(`trg-12b4cf3f` / `trg-a1fd8125`) was correctly not reported. Its advisory — that the
wiring had not yet been exercised end-to-end — was acted on: the real producers were run
as empirical probes (see the spec's Confidence Calibration).
