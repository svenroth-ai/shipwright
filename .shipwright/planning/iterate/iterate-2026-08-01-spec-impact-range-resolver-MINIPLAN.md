# Mini-Plan — `iterate-2026-08-01-spec-impact-range-resolver`

Spec: `iterate-2026-08-01-spec-impact-range-resolver.md`. Intent BUG, complexity
medium (locked). Spec Impact NONE.

## Chosen approach

Convert the last single-commit consumer among the F11 gates to the shared range
resolver, keeping its existing anchor.

| Step | File | Change |
|---|---|---|
| 1 | `shared/tests/test_spec_impact_branch_range.py` (new) | RED — four behaviour tests + one call-site pin, built on the `git_origin_repo` / `make_worktree` fixtures that `test_derived_snapshot_gate.py` already uses for this exact shape |
| 2 | `shared/scripts/tools/verifiers/iterate_checks.py:51` | import `_iterate_changed_paths` alongside `_commit_changed_paths` |
| 3 | `shared/scripts/tools/verifiers/iterate_checks.py:955` | `_commit_changed_paths(project_root, event_commit)` → `_iterate_changed_paths(project_root, event_commit)` |
| 4 | same file, docstring + both return details | say *branch*, not *commit* (AC5) — the wording is what made the report unactionable |

`_commit_changed_paths` stays imported: `_iterate_changed_paths` is its caller, and
the module keeps no other user — but the symbol is re-exported through
`verify_iterate_finalization` and dropping it from the import list buys nothing.
*(Verified at build time: if nothing else in the module references it, it goes —
ruff F401 is a gating lint.)*

## Why not the tidier variant

Re-anchoring at `commit_hash` to match the siblings' call shape regresses
`test_spec_impact_resolves_event_by_run_id_in_multi_commit_iterate`. Full
reasoning + three further rejected alternatives in the spec.

## Blast radius

One call site. Five pre-existing tests exercise this gate
(`test_verify_iterate_finalization.py` ×9, `test_spec_impact_none_reason.py` ×2);
all must stay green **unmodified** — if one needs editing, the change is wrong, not
the test. In a remote-less fixture `_branch_base_commit` refuses an uncorroborated
base and returns `None`, so those tests keep taking the single-commit fallback.

## Revised after the review cascade

The plan above is what was built; four things were added by review and are not in it:

- **Stage 2 (high):** `iterate_checks.py` sat exactly at its anti-ratchet ceiling
  (1087), so the first draft's +33 lines of explanatory prose would have hard-blocked
  the commit. Rewritten to net zero.
- **Stage 2:** the detail wording, a surviving `is None` → `not changed` mutation,
  and `docs/guide.md` (which the plan missed; CLAUDE.md names it explicitly).
- **Stage 3 (high):** the widening is fail-OPEN for this gate where it is fail-safe
  for its four siblings. Accepted + pinned, not fixed — see the spec.
- **Stage 3:** the new test module had crossed 300 lines while the pre-commit hook
  stayed green (it cannot see files outside the baseline). Split in two.

## Verification

`shared/tests` root (full), then `shared/scripts/tests`, `shared/scripts/tools/tests`
and `integration-tests` — one pytest root per process (ADR-044). Lint with the
pinned `uvx ruff@0.15.15`.
