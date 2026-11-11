# Architecture Brief — U1 events open-file warning

**Change:** the drops event layout keeps one file per run in `shipwright_events.d/`; folding old ones runs automatically only at a release. A repo that does not release for a long time accumulates files silently.

**Options**
1. Do nothing; rely on the release-time fold.
2. A read-only advisory line (WARN) printed by the existing `main_health.py` tool at >= 150 open files, naming the manual fold command. No new mechanism, no exit-code effect, legacy layout silent.
3. Fold automatically at some trigger other than release (e.g. on every iterate start or when the count passes a limit).
4. Add a new blocking gate on the count.

Permanent additions of the recommended-by-default option 2: one small leaf module with a constant and a pure function; one extra stderr line.
