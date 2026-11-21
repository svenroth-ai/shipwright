# Architecture Brief: one "what is due" answer for reminders and parked triage entries

## The problem
A later consumer (the WebUI, in another repo) must show an alert and send mail from ONE call that returns everything due on a day: operator reminders AND parked triage entries whose revisit day has come.

## What already exists here
- A reminder store (`reminders.jsonl`, `lib/reminder_store.read_folded`), written only by `reminder_cli.py`.
- Triage resolves an expired park to open by derivation at read time (`triage.read_all_items`, field `revisitDue`).
- `lib/triage_defer.utc_date(now_utc())` is the one UTC "today" helper.
- A redaction helper in `lib/main_health_diagnosis.py`.

## What would newly, permanently exist
A read-only `due [--on D] [--json]` verb on the reminder CLI plus `lib/reminder_due.py`, returning a versioned JSON contract (`contractVersion` 1, fixed item field set) read by another repository.

## Options on the table
- **A:** One read-only verb that folds reminders, calls `triage.read_all_items` in process, and merges both into one fixed-shape list.
- **B:** The consumer calls the reminder CLI and the triage CLI separately and merges itself.
- **C:** Do nothing.

## Constraints that are not negotiable
Operator decisions (2026-11-21, already approved): parked triage entries are NOT copied into the reminder store; `due` merges both sources in one answer. No code may read `triage.jsonl` except through `read_all_items`. The output leaves the machine by mail, so triage text must be redacted at output time. The answer must not change triage behaviour (read only).
