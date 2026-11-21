# Reminder store: a separate local event log with one CLI writer

Run: `iterate-2026-11-21-e1a-reminder-store` (campaign `reminders-core`, unit E1a). Spec bookkeeping: new FR `FR-01.22` (the tests need an FR tag and the infra catalog is not usable in the same merge); an operator utility store with no phase output, requirement source is the campaign brief.

## Decision
A new append-only `.shipwright/reminders.jsonl` (git-ignored, resolved at the MAIN root), written only by `tools/reminder_cli.py`, reusing `FileLock` and the tolerant JSONL reader, with a secret check (`lib/reminder_secrets.py`) built on the one public `contains_secret()` promoted in `lib/main_health_diagnosis.py`.

## Architecture Review

External (`external_review.py --mode architecture`), verbatim verdicts:
- glm: **approve**. "Option A is the right shape"; low note: document which store a dated follow-up belongs in (reminder = operator-facing with context; triage = automated finding).
- openai: **reject**. "A separate reminder event store duplicates the existing ability to hold contextual work until a revisit date"; recommends Option B (extend triage with reminder context fields plus a thin CLI adapter).

Disposition of the openai reject: **rejected with reason: operator decision 4/5 + lock hazard, facts absent from the reviewer brief.** The campaign brief records the operator's decisions (2026-11-21): parked triage entries are NOT copied into the reminder store (`due` merges both sources at read time), and the store is a separate git-ignored local file (triage.jsonl is git-tracked). The WebUI writes triage through its own TypeScript implementation (`proper-lockfile`) that does not coordinate with the Python `FileLock`, so adding fields to triage items would add a cross-writer hazard and change the `triage list --json` contract. Option B was therefore already considered and rejected by the operator. The first brief the external reviewers saw (`architecture_brief_external_v1.md`) did not carry those facts; the internal reviewer's brief (`architecture_brief.md`) does. The runner halted first, per contract, and resumed on the orchestrator's instruction.

Documentation note from glm adopted: the docs row states reminders are operator-requested only; triage remains the home of automated findings.

## Rejected alternatives
B: reminders as triage items (operator decision 4/5, lock hazard). C: do nothing (the operator needs dated context).

## Confidence Calibration
Boundary: reminder_cli (producer) to `reminders.jsonl` to `read_folded` (consumer), human-editable file. Probes run: 5 (round trip, UTF-8 BOM + CRLF rewrite, non-ASCII on a cp1252 console, blank lines, unterminated tail followed by an append). One finding: non-ASCII titles crashed the CLI on a legacy console codepage; fixed (UTF-8 stdout/stderr) and pinned by a test. Two further probes (blank lines, unterminated tail) found nothing: asymptote reached. A leading BOM is reported as one damaged fragment but the reminder survives. Not probed: concurrent writers on a network share (accepted, local store).

## Self-review note
`add --why` is required on the CLI (the library accepts none): a deliberate stricter choice, real context is the point of a reminder. The command-flag secret rules suggested by the plan reviewer were removed after a Stage-1 reject: the brief scopes the check to the one pattern set plus URL credentials.
