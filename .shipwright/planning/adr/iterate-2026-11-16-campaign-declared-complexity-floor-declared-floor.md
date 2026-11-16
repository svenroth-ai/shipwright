# A campaign unit's declared complexity is a floor

Run: iterate-2026-11-16-campaign-declared-complexity-floor. Spec: `.shipwright/planning/iterate/2026-11-16-campaign-declared-complexity-floor.md`.

## Context

An operator declares each campaign unit `medium` in the brief. The sub-iterate-runner then classifies the unit twice, from the spec text (Stage 1) and from its diff (Step 3.4), and lands on `small` for ordinary 100-200 line changes. The plan, architecture and doubt reviews were closed not-applicable and ran only because the orchestrator asked (profile-architecture-rules campaign, units U1, U2, U4, U5, U6). Nothing machine-readable carried the declaration.

## Decision

The planner writes the declared tier into the unit spec as a `Complexity:` header line. Stage 1 (`classify_complexity.py --spec`) and the Step 3.4 re-check (`diff_risk_recheck.py --spec`) read it and take the higher of the declared and the derived tier. `risk_recheck.json` carries `declared_complexity` and the F11 gate `check_risk_recheck_recorded` fails a record whose effective tier is below it (the existing check already fails an F5c tier below the effective one). The planner rejects an unknown level and `large`; an unreadable `--spec` path or a mistyped level stops the run.

## Rejected

A runner-side `--complexity` override (nothing persists it, Step 3.4 and F11 cannot see it) and changing the size rules for every iterate (project-wide blast radius for a campaign-local gap). Re-deriving the tier from the spec at F11 stays out: the recheck record remains a transcription-integrity record.

## Known limits

A runner that omits `--spec` (for example from a stale plugin cache) records no declaration and F11 cannot tell that from an undeclared unit, so the plugin cache must be synced after merge before the next campaign dispatch. F5c `prior_source` does not name the declared floor, and declared-floored entries feed the history-prior median.
