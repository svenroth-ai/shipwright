# Iterate — the coverage gates ask the diff, not the label

**Run ID:** `iterate-2026-08-01-coverage-gate-recompute-order`
**Type:** CHANGE · **Complexity:** medium · **Risk flags:** none

Supersedes `trg-f872a6d7` (retitled into the phase scheme). Re-homed off the
IT-3 anchor, which closed as PR #498 two days before the card was filed and so
was carrying no owner. Pairs with P2.15.

---

## §0 — What the card claimed, and what the code says

Both claims were re-verified at code on 2026-08-01 before any edit.

**Claim 1 — `integration_coverage.py`.** `check_integration_coverage` reads the
run's *recorded* complexity at `:68-69` and returns a green `SKIPPED` at
`:70-72` when it is below `medium`. The recompute it advertises — the diff read
at `:76-80` — is never reached. Meanwhile `:63-65` states the gate "cannot be
dodged by omitting a self-report". **Confirmed.** The non-dodgeability is a
property of the *flag* (recomputed, not self-reported); it was never a property
of the *gate*, which is gated on a self-reported label sitting one field over.

**Claim 2 — `layer_coverage.py`.** `_infra_result` at `:99-106` converts a
missing `--commit`, an unresolvable base ref, a failed regeneration and a
verifier exception into a green SKIP whenever `_is_enforcing(complexity)` is
false. `check_removal_coverage`'s own docstring at `:117-119` says it "Runs at
ALL complexities (a removal is never trivial, SHOULD-FIX 6)". **Confirmed.**
Both statements are true at once only because "runs" and "can conclude
anything" were allowed to drift apart: below medium the check runs and then
declines to answer, in the colour of a pass.

**Why it matters now, not earlier.** Both are pre-existing. #506 capped the
fall-through classification prior at `small`, so materially more runs now sit
below `medium` — the exact band in which both gates stand down.

## §0.1 — The reversal is toward a decision this codebase already made

The card correctly flags that fixing this reverses a recorded decision: the
docstrings cite MUST-FIX 1 (infra gap ERRORs at medium+, SKIPs below) and
SHOULD-FIX 6. That reversal is not a new invention. `ci_supplychain.py:168-170`
already documents the opposite posture for the sibling gate, and names *this*
gate as the contrast:

> Applies at EVERY complexity on purpose (unlike the `cross_component` gate's
> medium+ floor): a one-line workflow edit is still a trust-boundary change, and
> a complexity floor would be the obvious way to dodge it.

So the repository holds two contradictory decisions about the same question.
This run resolves the contradiction in favour of the later, better-evidenced
one, and records the supersession rather than quietly editing the older text.

## §0.2 — The band where the gate is reachable is exactly the band that matters

`risk_taxonomy.cross_component` carries `min_complexity: "medium"`, so a
*detected* cross-component change is already forced to medium and the gate
fires. The below-medium band is therefore reachable only when **detection
failed at classification time but the F11 recompute succeeds** — i.e. Stage 1
saw the message only (`cross_component` is diff-driven and Stage 1 has no
diff), and the Stage-2 Quick Scout's diff-driven detector step, which is
*prose the agent must remember to execute*, did not run or did not catch it.

That is not a marginal case; it is the whole reason the recompute exists. The
current order makes the mechanical check depend on the outcome of the
non-mechanical one it was built to backstop.

---

## Acceptance Criteria

> **Vocabulary.** `Severity.ERROR` is the *default* severity of `CheckResult`,
> so `CheckResult(name, False, detail)` is already a blocking error;
> `format_report` renders it `FAIL` and `summarise` counts it in `errors`.
> "ERROR" and "FAIL" below name the SAME outcome. The distinct outcomes are
> `WARNING` (non-blocking unless `--strict`) and `SKIPPED`; neither gate uses
> them for these paths.

**AC-1 — the diff decides, at every complexity.** `check_integration_coverage`
evaluates the recomputed cross-component path set *before* the recorded
complexity. A diff touching no cross-component path passes at every complexity
(unchanged). A diff touching one, with no `category:"integration"` behavior in
the ledger, FAILS at trivial, small, medium and large alike.

**AC-2 — infra failures fail closed.** Inside a git repository: an absent
`--commit` resolves `HEAD`; an unresolvable `HEAD`, or an `_iterate_changed_paths`
result of `None` (diff unobtainable), is an ERROR at every complexity — never a
green SKIP. `[]` is not `None` and still means "this branch has no net change".

**AC-3 — the git probe is tri-state, not binary.** `work_tree` → proceed;
`not_git` → SKIP at every complexity; `git_error` (broken git binary, permission
failure, corrupt metadata, timeout) → ERROR at every complexity. A binary
"non-zero rc means not a repo" probe would green-SKIP a real infrastructure
fault from *inside* a repository — reintroducing the fail-open class this change
removes (external plan review, finding 2). The genuine non-git SKIP is not a
dodge: an F11 run outside a repo has nothing to merge, and it preserves the
sandbox contract the CLI tests rely on. `layer_coverage._git_context` already
draws this distinction and is promoted to `git_helpers.git_context()` so both
gates share one implementation.

**AC-4 — the failure names the floor violation.** When the gate fires on a run
recorded below `medium`, the message says so explicitly — the run is
under-classified against the `min_complexity: medium` the `cross_component`
flag enforces — rather than only asking for a test. An operator reading it
learns *two* things went wrong, which is the truth.

**AC-5 — `_infra_result` is fail-closed at every complexity.** A missing
`--commit`, an unresolvable base ref, a git subprocess failure, a failed
regeneration / collector load, or a verifier exception is an ERROR regardless
of recorded complexity.

**AC-6 — ordering preserves the non-git SKIP.** `check_removal_coverage` checks
the git *context* before it checks for a commit, so a non-git project SKIPs
rather than hard-failing on the missing commit it was never going to have. (In
the current order `if not commit_hash` precedes `_git_precheck`, which under
AC-5 alone would turn every non-git sandbox red — a false-red introduced by the
fix, caught before writing it.)

**AC-7 — `check_cross_layer_coverage` keeps its medium+ scope.** Its early
return at `:172-173` is a deliberate cost decision, not the verified loophole;
the card verified `_infra_result` and the *removal* docstring, not this. Its
`_infra_result` calls stay reachable only at medium+, where behaviour is
unchanged. Scope confirmed with the operator at the approval gate.

**AC-8 — the reversed claims are corrected in the same diff.** The docstrings
that asserted the old decision are rewritten, not left contradicting the code:
`integration_coverage.py` (the non-dodgeability claim), and `layer_coverage.py`
module header + `_infra_result` + `check_removal_coverage` (MUST-FIX 1 /
SHOULD-FIX 6).

**AC-9 — runtime prose matches.** `SKILL.md` Phase Matrix row, `SKILL.md` Step E
("the F11 integration-coverage verifier green-SKIPs below medium"), the
`cross_component` taxonomy row, and `docs/hooks-and-pipeline.md` ("requires, at
medium+") are updated in the same diff. The agent executes the prose, so stale
prose is a live defect, not documentation debt.

**AC-10 — the supersession is recorded.** An ADR decision drop names MUST-FIX 1
and SHOULD-FIX 6 as superseded and states why, so the next reader finds the
reversal rather than re-deriving it. Written via `write_decision_drop.py` keyed
by `run_id` (an iterate must not edit `decision_log.md` directly).

**AC-11 — a missing or malformed iterate entry does not excuse the finding.**
Because the entry is now read *after* applicability is established, `None` or a
non-dict entry must (a) not raise, (b) still ERROR on a cross-component diff —
omitting the self-report must never be the cheap way out — and (c) produce a
message with **no** floor claim. The floor sentence is appended only when the
recorded complexity is known *and* genuinely below medium; asserting a floor
violation the gate cannot substantiate would be the same species of overclaim
this card exists to fix.

## Spec Impact

**NONE.** This changes F11 verifier enforcement behaviour inside the framework;
no functional requirement in `.shipwright/planning/*/spec.md` describes verifier
complexity gating, and no FR row or acceptance criterion changes. Justification
recorded at F5b.

## Affected Boundaries

- **git diff → gate decision** (`_iterate_changed_paths`): the tri-state
  `None` / `[]` / paths contract is now load-bearing for `integration_coverage`
  in the failing direction, where it previously only skipped.
- **iterate entry store → gate** (`find_entry_by_run_id`): the recorded
  `complexity` stops being a control-flow gate and becomes message content only.
- **F11 orchestrator → CLI exit code**: two gates gain reachable ERROR states in
  complexity bands that could not previously block.

## Confidence Calibration

- **Boundaries touched:** (1) git diff → gate decision — `_iterate_changed_paths`'
  `None` / `[]` / paths tri-state is now load-bearing for `integration_coverage` in
  the *failing* direction, where it previously only skipped; (2) iterate entry store
  → gate — the recorded `complexity` moved from control flow to message content, and
  the read is now absorbed against a raising reader; (3) shared
  `shipwright_test_results.json` → gate — the fallback is now attributed via
  `read_iterate_latest`, where it was previously read raw; (4) F11 orchestrator →
  CLI exit code — two gates gained reachable ERROR states in complexity bands that
  could not previously block.

- **Empirical probes run:**
  - *Four mutation probes on the core change.* Restoring the early complexity gate →
    caught by 15 tests. Restoring `_infra_result`'s below-medium SKIP → 4. Making
    `git_context` a binary probe → 6. **Reverting the `_git_precheck` ordering →
    caught by ZERO**: every existing non-git test supplied a fake sha, so it reached
    the precheck regardless of order.
    `test_non_git_project_with_no_commit_skips_rather_than_erroring` was written to
    close that and confirmed red against the reverted order before the probe was
    undone.
  - *Two mutation probes on review fixes.* Removing the per-run-entry preference →
    the de-vacuumed `test_derived_snapshots` test fails (it passed vacuously before
    the fix). Stubbing the ledger attribution back to `current` → 2 tests fail.
    Removing the `_read_entry` absorption → the non-UTF-8 test fails with exactly the
    `UnicodeDecodeError` the external reviewer predicted.
  - *Diff-driven risk detectors run on the FINAL file list* (not the anticipated
    one): `cross_component`, `ci_supplychain`, `io_boundary`, `touches_build` all
    False. This change is therefore not itself subject to the gate it edits.
  - *Stage-1 keyword falsified.* The `medium` estimate came from the substring
    `integration` inside the filename `integration_coverage.py`; discarded as
    non-evidence and re-derived from the Stage-2 scout.
  - *Python 3.11 as well as local 3.12*, because CI pins 3.11.
  - *Call-site enumeration* before editing `_infra_result`: 7 sites, all
    module-private, no external importer.

- **Test Completeness Ledger:** 35 behaviours, all `tested`, 0 untestable, 0
  testable-but-untested. Against 11 acceptance criteria. Full table in
  `shipwright_test_results.json` → `iterate_latest.test_completeness` and in this
  run's F5c entry.

  | # | Behaviour | Evidence |
  |---|---|---|
  | 1-5 | `git_context` classifies work tree / definitive non-git / **localized** non-git / localized failure *inside* a repo / synthesized failure | `test_check_integration_coverage_infra.py` (5 tests) |
  | 6-7 | integration gate enforces, and is satisfied, at **all four** complexities | 2 tests × 4 params |
  | 8-14 | non-git SKIP · git-fault ERROR ×4 · HEAD fallback · HEAD unresolvable · diff `None` ERROR · diff `[]` PASS · invalid commit ERROR | `..._infra.py` |
  | 15-17 | floor note only when substantiable (12 cases) · named below medium · absent at medium/large | `test_check_integration_coverage.py` |
  | 18-20 | absent entry · non-UTF-8 entry absorbed · non-dict entry | `test_check_integration_coverage.py` |
  | 21-25 | per-run entry preferred · **foreign ledger refused** · own shared-file ledger accepted · corrupt results distinct · the cheap remedy actually clears the gate below medium | `..._ledger.py` + `test_derived_snapshots.py` |
  | 26-28 | removal: infra ERROR ×4 · non-git+no-commit SKIP ×4 (ordering guard) · git fault ×4 | `test_layer_coverage_hardening.py` |
  | 29-30 | cross-layer keeps medium+ scope · keeps its original probe order | `test_layer_coverage_hardening.py` |
  | 31 | Phase Matrix row gated at every tier (cell-parsing, not substring) | `test_cross_component_prose.py` |

- **Confidence-pattern check:**
  - **Depth (asymptote):** six mutation probes; the fifth and sixth were prompted by
    review findings rather than by my own suspicion, and one of the first four found
    a genuinely unpinned guard. Returns had not flattened — the probes kept finding
    things, which is why the review cascade was worth its cost here.
  - **Breadth (coverage):** 35 behaviours over 11 ACs; every new branch has a test on
    both sides (SKIP *and* ERROR, `None` *and* `[]`, floor-claimed *and*
    floor-absent, foreign ledger *and* own ledger).
  - **Composition (integration):** `cross_component` is **False** on this diff (all
    four detectors verified on the final file list), so no `category:"integration"`
    behaviour is *required*. Several are nonetheless integration-shaped — behaviours
    21-25 drive the gate end-to-end through a real git worktree, the F5c entry store
    and the shared results file together — and are marked `category:"integration"`
    honestly rather than to satisfy a gate that does not apply.
  - **Known residue, owned:** two deferrals filed as `trg-20cc9ec8`
    (`check_ci_supplychain_ack` still uses the binary git probe) and `trg-06216b9f`
    (`iterate_entry` readers do not catch `UnicodeDecodeError`). Both are recorded in
    code comments *and* on the board — the doubt reviewer caught that an earlier
    draft claimed they were filed when they were not.
