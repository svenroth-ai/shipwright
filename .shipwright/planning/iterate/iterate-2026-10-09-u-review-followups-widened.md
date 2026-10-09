# Iterate Spec: u-review-followups-widened

- **Run ID:** iterate-2026-10-09-u-review-followups-widened
- **Type:** change
- **Complexity:** medium
- **Status:** built (autonomous)

## Goal
Close the review follow-ups the U0 / U3 / U4 / U10 ADRs left open as "accepted limits", so the review record, the small-run code-review trigger and the `unavailable` evidence say what they claim. A check of the last 25 commits (to #873) found none of them done; `_check_name` (crashed claim check reported under `CHECK_NAME`) was already in place and is not touched.

## Acceptance Criteria
- [x] `make_entry` takes `reason_code`; `record` and `close-missing` pass it instead of attaching it after construction.
- [x] Re-running a bare `--reason-code` record that lands on the marker-repair path writes the default disposition as the marker `reason`, not null.
- [x] `exemption_record` refuses an absolute path in ANY `::`-separated part of a scope, not only the first.
- [x] `append_iterate_entry` unpacks the validator tuple.
- [x] The F11.md PR-body template has a blank line before `Run-ID:`.
- [x] `stage-1-rejected` is a `review_not_run` code; the docs record a Stage-1 REJECT with it instead of `delegated-to-orchestrator`.
- [x] `record --force` on a marker-bound row needs `--marker-status` only when it could leave a `completed` marker behind; a skipped (`missing-keys` / `unavailable`) row is repairable in place.
- [x] The F5c entry carries a durable `risk_flags` list; a run with no `plan.json`, no `risk_recheck.json` and no list is UNKNOWN (fires), not "no flags"; a malformed list is unknown too.
- [x] A rebase-merged multi-commit PR already on the trunk is measured over all its `Run-ID:`-stamped commits, not by its last commit; other runs' commits are not counted.
- [x] `external_review.py` stamps every envelope with `capture: {run_id, at}`; the `unavailable` evidence rule refuses an envelope without this run's stamp.
- [x] `record` masks URLs and key/token shapes in the stderr capture that backs an `unavailable` row.

## Spec Impact
- **Classification:** none
- **NONE justification:** tightening and repairing existing finalization gates and their recorder (FR-01.11's behaviour is unchanged in kind: the review record still closes every pass, the trigger still keys on flags and diff size); no new user-observable capability and no requirement text changes.

## Out of Scope
- Cryptographic provenance of the capture (the stamp binds an envelope to a run; it does not stop a deliberate forgery).
- Secret shapes no pattern knows; masking of captures from a completed pass; adapter-side masking and an F11 re-check that a capture stayed masked (a re-run after a recorded row is a new attempt).
- Provenance of the failure (the stamp binds an envelope to a run, so an input typo still yields a stamped `unavailable` envelope); `risk_flags` stays self-reported.
- Counting `Run-ID`-less WIP commits of a rebase-merged PR.
- The webui consumer of `reason_code` (additive row key since U0).

## Design Notes
n/a (no UI).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `external_review.py` (`driver_record["capture"]`) | `lib/review_unavailable._stamp_problem` | JSON envelope field |
| F5c entry `risk_flags` (agent via `append_iterate_entry`) | `_cascade_trigger_inputs.recorded_risk_flags` | JSON list |
| `Run-ID:` commit trailer (F6) | `_cascade_trigger_inputs._run_commits` (`git log --grep`) | commit message |
| `review_capture_redact` (rewrites `*.stderr.txt`) | `review_unavailable.artifact_problem` | text, UTF-8 or UTF-16 BOM |

## Confidence Calibration
- **Boundaries touched:** the four above.
- **Empirical probes run:** real-git fixtures for the rebase-merged measure (3 commits 60+60+3 → 123 lines fires; a neighbour PR's 500-line commit is not counted; no trailer → tip alone); the CLI as a subprocess for the marker repair, `--force` relax, stage-1-rejected and the redaction; the real `external_review.main()` producing a stamped `_fail_envelope`; a UTF-16 stderr round trip.
- **Test Completeness Ledger:** see the F5c entry (`test_completeness`); 0 untested-testable.
- **Confidence-pattern check:** depth — the first full run of the shared root found the tightened gates failing every fixture that predates the new field, which is the intended tightening; the fixtures now write it. Breadth — every AC has a happy and an error-path test.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_review_followups_cli.py shared/tests/test_review_capture_redact.py shared/tests/test_cascade_trigger_durable_flags.py shared/tests/test_review_unavailable_capture.py -q -p no:cacheprovider`
- **Evidence path:** `.shipwright/runs/iterate-2026-10-09-u-review-followups-widened/surface_verification.json`
