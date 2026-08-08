# Spec surrogate: iterate-2026-08-07-shared-op-predicates

Small-complexity SIMPLIFY iterates skip the full iterate-spec file (Phase Matrix:
"Iterate Spec — skip" below medium). This surrogate exists only so the external
plan-review tool (which compares a mini-plan against a spec) has real requirements to
check the plan against, rather than comparing the mini-plan to itself.

**Source of requirements:** triage card `trg-ca82a057` ("P2.19e [AUTO after P2.19a]
Merge the duplicated git-state predicates", IT-1 audit finding 29), which is this
run's launch payload verbatim.

## Requirements (acceptance criteria)

1. Eliminate the duplicated `_op_in_progress` / `_has_staged_changes` git-state
   predicates between `shared/scripts/lib/sweep_outbox.py` and
   `shared/scripts/lib/reconcile_triage.py` by delegating `sweep_outbox.py` to the
   already-extracted `shared/scripts/lib/main_tree_guards.py` (predecessor P2.19a,
   #588, already did the `reconcile_triage.py` side). ~34 LOC recovered.
2. `_CI_TRUTHY`/`_ci_active` needs **no work** — already unified via `lib.ci_env` at
   all four call sites (a correction to the original finding, confirmed 2026-08-05).
3. The `_op_in_progress`/`_has_staged_changes` extraction is mechanical: both
   predicates already take a `root: Path` parameter. The sweep checks the worktree;
   reconcile checks the main tree — that split must **not** change.
4. `reconcile_triage.py` additionally has `_is_detached`; `sweep_outbox.py` does not.
   This asymmetry must be **decided explicitly** (keep or align) with a stated reason
   when merging the duplicate predicates — not silently normalized either way.
5. This iterate is **behavior-preserving** — no functional change to either module's
   observable outcomes for any currently-tested path. Spec Impact = NONE.
6. Ordering: serial to P2.19a (both touch `reconcile_triage.py`) — P2.19a is merged
   (#588), so this run is unblocked.
7. Scope: this card only. `commit_event_followup.py`'s separate `has_staged_changes`
   copy and the `gitignore_selfheal.py`/`gitattributes_selfheal.py` inline copies are
   siblings of the same family but were never named in this card or the audit finding
   it derives from — out of scope unless the mini-plan gives an affirmative reason to
   pull them in.
