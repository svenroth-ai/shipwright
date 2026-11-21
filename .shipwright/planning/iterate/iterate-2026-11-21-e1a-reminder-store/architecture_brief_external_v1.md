# Architecture Brief: operator reminders with context

## The problem
The operator wants to be reminded on a given day of a decision with its context (why, what was decided, what is open, which command to run), and one later call must be able to return everything due. Today nothing holds such reminders.

## What already exists here
- Triage store (`triage.jsonl`): append-only, tracked, has a snooze with a revisit date.
- `lib/file_lock.FileLock` and `lib/jsonl_records.read_jsonl_records` (tolerant reader).
- `lib/repo_root.resolve_main_repo_root`, used so worktree writes land in the main tree.
- `lib/main_health_diagnosis.py` holds a private credential-shape pattern list.
- The WebUI (separate repo) writes triage through its own TypeScript code.

## What would newly, permanently exist
A new git-ignored local file `.shipwright/reminders.jsonl` (append-only events folded on read), written only by one CLI (`reminder_cli.py`: add, list, show, done, snooze), and a text check that refuses secret-shaped reminder text. It stays correct through the single-writer rule and the shared lock.

## Options on the table
- **A:** A new append-only JSONL store plus CLI, reusing the lock and tolerant reader.
- **B:** Store reminders as triage items (parked with a revisit date) and extend triage fields.
- **C:** Do nothing; the operator keeps notes by hand.

## Constraints that are not negotiable
No secrets in reminder text; a part-2 consumer in another repo may only call the CLI.
