# Internal review cascade — iterate-2026-08-01-grade-snapshot-dirty-capture

`spec-reviewer` (Stage 1, hard gate) → `code-reviewer` (Stage 2) → `doubt-reviewer`
(Stage 3, advisory-must-address). All three spawned under the standing grant in
`CLAUDE.md`, all on `opus`, each against the merge-base diff.

**Outcome: 2 REJECT-blockers, 2 high, 3 medium, 9 low — all addressed.** Stage 1
rejected once and passed on re-review.

## Stage 1 — spec compliance: REJECT → APPROVE

| # | Finding | Disposition |
|---|---|---|
| 1 | AC4 said a malformed value "degrades to a fresh measurement"; the code returns the recorded unknown without re-measuring. Wording survived from the dropped JSON-store design, and the disputed case had **no test**. | **FIXED — code kept, AC rewritten.** The marker/value split is the behaviour worth having: re-measuring there is precisely how a producer's own writes would turn an honest unknown into a false `true`. AC4 now states the rule; two tests cover both branches. |
| 2 | The shipped `dirty` field definition said "when the run began" — wrong in the dominant case (an iterate is clean at run start and legitimately dirty at F5b) and contradicting the same document's rule 5. | **FIXED** — now "when the producer that measured it started, before it wrote anything", with the run-start reading explicitly disclaimed. |

Re-review verified every production blob was byte-identical to the already-verified
round, so no scope crept in with the fixes. Four non-blocking notes also taken: the
real `finalize_iterate.run()` ordering test, `"dirty"` added to the CLI refusal
parametrize, the `TestDefaultEnv` env leak, and the residual card (`trg-709828ad`).

## Stage 2 — code quality

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | **Anti-ratchet block**: `finalize_iterate.py` 568 > baseline 549. | **FIXED** — trimmed the duplicated rationale (the reason lives in the module docstring and the docs), then bumped the already-`exception` entry. |
| 2 | high | **Anti-ratchet block**: `record_event.py` 783 > baseline 769. | **FIXED** — same, comment compressed then entry bumped. |
| 3 | med | `resolve_churn_conflicts` writes **three** tracked MDs before spawning the regen and passed no run id — falsifying the measured inventory in the plan-review dispositions. | **FIXED** — captures at entry and forwards `run_id`. The inventory claim was wrong and is corrected rather than defended. |
| 4 | med | `test_child_process_inherits_the_capture` passed an explicit `env=` dict, so it proved only that a dict reaches a child — not the production mechanism. | **FIXED** — now uses the real `os.environ` with no `env=`, plus a negative control that fails if the child silently stopped measuring. |
| 5 | med | The capture's `except` in `update_compliance` was silent, though an unknown `dirty` is *omitted* and therefore invisible downstream forever. | **FIXED** — prints to stderr like its `finalize_iterate` sibling. |
| 6 | low | `_clear_env` in the new compliance test used bare `delenv`, which registers nothing to restore. | **FIXED** — `setenv`-then-`delenv`, and promoted to autouse. |
| 7 | low | Docstring overclaims: "at most once" (it is per *process tree*) and "nothing here raises" (the env writes are unwrapped). | **FIXED** — both qualified. |
| 8 | low | `commit.gpgsign` unset in one new git fixture, unlike its two siblings — the module would error out on a developer machine with global signing. | **FIXED** |
| 9 | low | `build_event` is no longer pure construction, so ADR-059's "pure construction" wording is now inaccurate. | **ACCEPTED, not amended.** The invariant ADR-059 actually protects — *no write before the gate* — still holds; no disk write happens. Amending a decision record for a wording nuance that changes no behaviour is not worth the churn. Noted here instead. |
| 10 | low | Dead `sys.path` guard, doubled `json.loads`, two side-effect-in-expression lambdas, one docstring claiming an empty `--run-id` makes the fallback unreachable (false — `''` is falsy). | **ALL FIXED** |
| 11 | low | `captured_dirty` has no production consumer and is one character from `capture_dirty`. | **KEPT.** It expresses "read without capturing", which is a real distinction the module's contract depends on, and removing it would push tests into internals. |
| 12 | low | The `shared/scripts` bootstrap is now duplicated three times in the plugin; no shared helper covers top-level shared modules. | **OUT OF SCOPE** — the reviewer agreed. Worth a card, not this diff. |

## Stage 3 — adversarial doubt (advisory-must-address)

The headline claim **survived**: the reviewer could construct no reachable sequence
that stamps a confident `dirty: false` on a tree holding genuine uncommitted source,
having traced every production caller and confirmed the env pair cannot propagate
back into the operator's shell.

| # | Sev | Doubt | Disposition |
|---|---|---|---|
| D1 | med | The capture was keyed to a **run**, never to a **tree** — so one process carrying one run id across two roots would answer for a tree it never measured. Already misfires in this repo's own suite, where several modules reuse one run id across per-test fixture repos. | **FIXED IN CODE** — new `SHIPWRIGHT_SOURCE_DIRTY_ROOT`; an inherited value is honoured only when the tree matches, and a mismatch re-measures (the conservative direction). Five tests, including same-run-different-tree. |
| D2 | med | The env write is process-global, and only the two new test modules cleaned up; six existing modules drive the capturing functions with no protection. | **FIXED** — autouse isolation fixtures in `shared/tests/conftest.py` and the compliance plugin's, so it is a property of the suite rather than of modules remembering. |
| D3 | med | Closing the amendment door does **not** make `dirty` unassertable — exporting the capture variables states it directly, more cheaply than the route just closed, while the surrounding docs are headed "no CLI route can assert it". | **FIXED IN DOCS + CODE COMMENT** — the paragraph now separates the three derived fields from the producer-supplied one and says plainly that `dirty` carries the same "not tamper-evidence" caveat as `grade`/`score`. |
| D4 | low | The new `sys.path` front-insert at `main()` entry was unscoped, widening a known shadowing hazard across every generator's import. | **FIXED** — scoped to the import and undone in a `finally`. |
| D5 | low | Spec and docstring said "uncommitted **source**" while the code counts any tracked modification. | **FIXED** — definitional uses now say "tracked changes"; the evidence sentences that literally measured *zero uncommitted source* are left, being precise as written. |
| D6 | low | How far back the value reaches is not recorded, so two snapshots' `dirty` values are not strictly comparable instants. | **ACCEPTED IN WRITING** — stated in `docs/hooks-and-pipeline.md` rule 5 rather than papered over. Carrying the capturer per event was judged not worth a wire-shape field for a bias that already points the conservative way. |
