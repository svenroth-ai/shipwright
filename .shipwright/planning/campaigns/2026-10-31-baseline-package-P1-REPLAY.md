# Baseline package P1 - affected_acs replay

Command: `uv run shared/scripts/tools/affected_acs_replay.py --project-root . --window 100 --git`

The window is the last 100 iterate events (one PR can carry several).

| Count | Value |
|---|---|
| window | 100 |
| required (runtime-touching, scoped intent) | 83 |
| declared | 1 |
| missing | 82 |
| unknown_paths (no path list, git could not supply one) | 1 |
| conclusive | false |

Reading: the field is new, so almost every past runtime-touching iterate lacks it. The check therefore reports a missing declaration as an advisory WARNING and never blocks. The measurement is inconclusive because one event has no readable path list.
