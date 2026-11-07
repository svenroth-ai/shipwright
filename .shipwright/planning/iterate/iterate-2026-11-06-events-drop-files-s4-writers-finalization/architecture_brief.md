# Architecture Brief: per-run event drop writers

Problem: parallel worktrees all append to one tracked shipwright_events.jsonl, so merges conflict and the churn resolver is needed.

Options
1. Keep the single file and keep resolving conflicts at merge time.
2. Per-run drop files under a folder, written by one shared writer module, behind a layout flag that defaults to the old file.
3. A database or service for events.

Smallest thing that would do: option 2 limited to the writers (readers already migrated), dormant until the flag flips.
