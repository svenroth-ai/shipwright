# Spec context: lock-primitive-tail

No formal iterate spec exists (small complexity skips it per the phase
matrix). This file stands in as the `--spec-file` input for external plan
review — it is the triage-card description this run bundles, unmodified.

## Bundled work items

**trg-6d8fbc10 (P2.19i)** bundles trg-db1de213 + trg-2e961fee, both follow-ups
from the merged iterate-2026-08-06-write-lock-primitives (P2.19d,
trg-dc013d82 — PR #580, merged).

### (1) Retry predicate vs the measured Windows code (was trg-db1de213)

Measured empirically during P2.19d, not inferred: a byte-range lock on a
read target makes CPython raise an errno-only `PermissionError` with
`winerror` None (not any Windows error code), so `atomic_write.py`'s retry
predicate — which compares only `winerror` against a fixed set — never
matches and the read fails through instantly instead of retrying within the
read budget. Deliberately deferred by P2.19d to its own run because it is
the read side of a decision (fail fast vs. stall a genuinely denied read for
the full budget) that deserved its own reasoning.

### (2) Third copy of the lock mechanics (was trg-2e961fee)

P2.19d fixed the identical unbounded/non-reentrant wait-loop defect in TWO
copies (`file_lock.file_lock` function and `file_lock.FileLock` class, now
unified on one shared bounded+reentrant loop). A THIRD literal copy of the
same pattern exists in `plugins/shipwright-run/scripts/lib/
phase_task_lifecycle.py`'s `_PhaseTasksLock` — out of scope for P2.19d
(explicitly scoped to two files). Repair path: delegate to the now-fixed
shared class instead of maintaining a fourth variant.

See the mini-plan
(`iterate-2026-08-07-lock-primitive-tail-miniplan.md`) for the implementation
and `.shipwright/triage.jsonl` entry `trg-6d8fbc10` for the original card
text (German original with the exact measurements).
