# Iterate spec: claims-hardening follow-ups (iterate-2026-10-08-claims-hardening-followups)

Type: change. Complexity: medium. Follow-up to campaign `2026-10-07-finalization-claims-hardening` units U5 and U6 (their accepted limits). Spec impact: NONE (finalization-gate hardening; no requirement text changes).

## Acceptance criteria
- AC1: No no-FR `change_type` label covers a requirement catalog (`.shipwright/planning/<split>/spec.md`); an iterate's own `iterate/<run>/spec.md` stays bookkeeping.
- AC2: `finalize_iterate`'s idempotent re-run that supplies claims is judged by the requirement gates before the recorded id is returned; a re-run with no claims (Stop-hook repair) still returns the recorded id.
- AC3: A stacked campaign unit's event may carry `stack_base_ref`; the change_type diff then starts at that parent unit branch. The ref must be an `iterate/*` ancestor of HEAD that sits on the trunk and is not the unit's own branch; otherwise the gate refuses.
- AC4: Surface-evidence freshness counts a hand-resolved conflict inside a first-parent trunk-merge commit as a branch write, and the staging guard dates a deleted file (removing commit date, or surviving parent directory mtime when uncommitted).

## Out of scope
Per-project label overrides; deriving the stack base from campaign loop state; re-checking the label at F11.

## Internal Architecture Review
Verdict: build (1), (2), (4) as specified. For (3) the reviewer preferred staying fail-closed (option C) unless stacked-unit refusals cost real work; the operator card for this run explicitly asks for (3) ("make it measure the unit"), so it is built as the stated-and-validated field (option A), not derived (B). Reconciliation: the old-git path is fail-closed with a distinct message (done); directory-mtime dating errs toward refusing (documented). Not taken: pinning `stack_base_ref` to a SHA and requiring the NEAREST `iterate/*` ancestor. A caller who names a nearer ancestor of their own making shrinks their own diff; recorded as an accepted limit (the name is runner-stated, bounded by the iterate/*, ancestor, on-trunk and not-own-branch checks).
