# Mini-Plan — coverage gates ask the diff, not the label

Run: `iterate-2026-08-01-coverage-gate-recompute-order` · CHANGE · medium

## Problem

Two F11 verifier gates stand down below `medium` complexity while their own
docstrings claim they cannot be dodged.

1. `shared/scripts/tools/verifiers/integration_coverage.py`
   `check_integration_coverage` reads the run's *recorded* complexity at `:68-69`
   and returns green `SKIPPED` at `:70-72` before reaching the diff recompute at
   `:76-80`. Its docstring `:63-65` advertises the recompute as the anti-dodge
   property. The recompute is real; the gate guarding it is keyed on a
   self-reported label.

2. `shared/scripts/tools/verifiers/layer_coverage.py` `_infra_result` at
   `:99-106` turns a missing `--commit`, an unresolvable base ref, a failed
   regeneration/collector load, and any verifier exception into a green SKIP when
   complexity is below medium — while `check_removal_coverage`'s docstring
   `:117-119` states it runs at ALL complexities.

Both are pre-existing. They matter now because PR #506 capped the fall-through
classification prior at `small`, so more runs sit in the band where both gates
stand down.

## Why the reversal is toward an existing decision

`ci_supplychain.py:168-170` already documents the opposite posture for the
sibling gate and names this one as the contrast: "Applies at EVERY complexity on
purpose (unlike the `cross_component` gate's medium+ floor) ... a complexity
floor would be the obvious way to dodge it." The repo holds two contradictory
recorded decisions; this run resolves it toward the later, better-evidenced one
and records the supersession (MUST-FIX 1, SHOULD-FIX 6).

## Reachability argument

`risk_taxonomy.cross_component` carries `min_complexity: "medium"`, so a
*detected* cross-component change is already forced to medium and the gate
fires. The below-medium band is reachable only when detection failed at
classification time but the F11 recompute succeeds — Stage 1 sees the message
only (the flag is diff-driven; Stage 1 has no diff), and the Stage-2 Quick Scout
detector step is prose the agent must remember to execute. The current order
makes the mechanical backstop depend on the non-mechanical step it backstops.

## Changes

### A. `integration_coverage.check_integration_coverage` — reorder

**Vocabulary.** `Severity.ERROR` is the *default* severity of `CheckResult`, so
`CheckResult(name, False, detail)` is already a blocking error; `format_report`
renders it as `FAIL` and `summarise` counts it in `errors`. "ERROR" and "FAIL"
below name the SAME outcome — a blocking `ok=False` result. The only other
outcomes are `severity=WARNING` (non-blocking unless `--strict`) and
`severity=SKIPPED`. Neither is used by this gate.

New order (each step's outcome):

1. **Tri-state git probe** — `work_tree` → continue; `not_git` → SKIP at every
   complexity; `git_error` → ERROR at every complexity. A binary
   `rev-parse --git-dir` rc check is NOT used: a broken git binary, a permission
   failure or corrupt repo metadata all return non-zero from inside a real
   repository, so reading any non-zero as "not a repo" would reintroduce exactly
   the fail-open class this change removes. `layer_coverage._git_context`
   already implements this distinction and documents why; it is promoted to
   `git_helpers.git_context()` and both gates call it (see B).
   A genuine non-git context stays a SKIP — an F11 run outside a repo has
   nothing to merge, and the CLI sandbox tests depend on it.
2. `commit = commit_hash or rev-parse HEAD`; still empty → ERROR.
3. `_iterate_changed_paths(...) is None` (diff unobtainable) → ERROR.
   `[]` is NOT `None` and still means "no net branch change" → continue to 4,
   which will find no hit and PASS.
4. No cross-component path in the diff → PASS (unchanged common case).
5. Only now read the iterate entry, for the ledger block AND the recorded
   complexity.
6. Ledger has a `category:"integration"` behavior → PASS.
7. Otherwise ERROR.

**Entry absent or malformed (step 5).** After the reorder the entry is read only
once applicability is established, so a missing or malformed entry must not
crash and must not excuse the finding:

- `find_entry_by_run_id` returning `None`, or a non-dict, yields an empty ledger
  block — the gate still ERRORs on a cross-component diff. Omitting the
  self-report must never be the cheap way out; that is the property the whole
  change defends.
- The recorded complexity is normalised defensively and used **only** as message
  content. The below-medium floor sentence (`cross_component` enforces
  `min_complexity: medium`) is appended **only when the complexity is known and
  is genuinely below medium**. An absent or unrecognised value produces the
  plain finding with no floor claim — asserting a floor violation we cannot
  substantiate would be the same species of overclaim this card is fixing.

The unreadable/corrupt `shipwright_test_results.json` branch (`:96-104`) keeps
its distinct failure message.

### B. `layer_coverage` — infra failures fail closed everywhere

**Call-site enumeration (done before editing).** `_infra_result` is
module-private with exactly 7 call sites, all inside `layer_coverage.py`:
3 direct in `check_removal_coverage` + 4 direct in `check_cross_layer_coverage`,
plus 1 shared via `_git_precheck`. Grep over the whole repo finds no other
importer, so no unreviewed caller inherits the stricter behaviour.

- `_git_context` is promoted to `git_helpers.git_context()` so
  `integration_coverage` can reuse the tri-state instead of re-deriving it.
  `_run_git` lives in `git_helpers` already, so the existing
  `monkeypatch.setattr(lc, "_run_git", ...)` in
  `test_git_subprocess_failure_errors_at_medium` must be retargeted to
  `git_helpers._run_git` — patching by module object, never by string, per
  ADR-045. Retargeting is required for the test to keep asserting its property;
  left alone it would keep passing while exercising nothing.
- `_infra_result` drops its `_is_enforcing` branch: always ERROR. Message no
  longer says "medium+".
- `check_removal_coverage`: move `_git_precheck` ABOVE the `not commit_hash`
  check. Load-bearing — in the current order `if not commit_hash` fires first,
  so making it unconditional would hard-fail every non-git project on a commit
  it was never going to have. This is a false-red the fix would otherwise
  introduce.
- `check_cross_layer_coverage`: UNCHANGED. Its medium+ early return at `:172-173`
  is a deliberate cost decision, not the verified loophole, so its
  `_infra_result` calls stay reachable only at medium+ where they already
  ERRORed. Scope confirmed with the operator.

Deliberate asymmetry: `integration_coverage` gains a HEAD fallback for a missing
`--commit`; `removal_coverage` does not. `removal_coverage` already ERRORed on a
missing commit at medium+ with no fallback (pinned by
`test_missing_commit_errors_at_medium_not_skip`), so adding one would change
medium+ behaviour — outside this card. `integration_coverage` currently SKIPs on
a missing commit at every complexity, so it needs the softer landing.

### C. Docstrings corrected in the same diff

`integration_coverage` (non-dodgeability claim), `layer_coverage` module header
`:18-23`, `_infra_result` `:99-106`, `check_removal_coverage` `:117-119`.

### D. Runtime prose

`plugins/shipwright-iterate/skills/iterate/SKILL.md` — Phase Matrix row
"Integration Coverage (cross-component)"; Step E sentence "the F11
integration-coverage verifier green-SKIPs below medium"; the `cross_component`
taxonomy row. `docs/hooks-and-pipeline.md:551` "requires, at medium+".
The agent executes the prose, so stale prose is a live defect.

### E. Tests (two roots, run separately — repo conftest refuses multi-root)

`shared/tests/test_check_integration_coverage.py`
- DELETE `test_skipped_at_small_complexity` (pins the reversed behaviour).
- ADD, **parameterized over all four complexities** (trivial/small/medium/large)
  so "at every complexity" is demonstrated rather than sampled: a
  cross-component diff without an integration behavior ERRORs.
- ADD the three-state diff contract explicitly:
  `None` → ERROR; `[]` → PASS (must not be conflated with `None`);
  matching paths → enforced.
- ADD the commit-resolution pair: absent `--commit` resolves `HEAD` and the gate
  still enforces; `HEAD` unresolvable → ERROR.
- ADD the git-context tri-state: `not_git` → SKIP; `git_error` → ERROR
  (the fail-open class GPT flagged).
- ADD entry robustness: no iterate entry at all, and a malformed entry, each
  still ERROR on a cross-component diff — and the message carries **no** floor
  claim when the complexity is unknown.
- ADD: a below-medium run's message DOES name the floor.
- Assert `severity` as well as `ok`/message on every one of these, so an
  ERROR silently becoming a WARNING or SKIP cannot pass.

`shared/tests/test_layer_coverage_hardening.py`
- REPLACE `test_missing_commit_skips_below_medium`: removal now ERRORs below
  medium; cross-layer still SKIPs (unchanged, and for a different reason —
  scope, not infra). Keeping both halves in one test is what makes the
  distinction visible.
- RETARGET `test_git_subprocess_failure_errors_at_medium`'s monkeypatch to
  `git_helpers._run_git` (see B).
- ADD: non-git below medium still SKIPs (the AC-6 false-red guard).
- ADD: git_error below medium now ERRORs (the AC-5 half that the non-git guard
  must not swallow).

Every new test gets a mutation check: flip production back, confirm red. The
parameterized and three-state tests are the ones most at risk of going vacuous,
so they are flipped individually, not as a block.

### F. ADR

Written with `shared/scripts/tools/write_decision_drop.py` keyed by `run_id`
(the F3 convention: drops land under `.shipwright/agent_docs/decision-drops/`
and are aggregated into `decision_log.md` with a sequential ADR-NNN at
`/shipwright-changelog` release time — an iterate must not edit `decision_log.md`
directly). Names MUST-FIX 1 and SHOULD-FIX 6 as superseded, with the
`ci_supplychain` contradiction as the evidence.

## External plan review — round 1 (GPT via openrouter; Gemini truncated)

Verdict `revise`. Dispositions:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | ERROR vs FAIL status mismatch between AC and plan | **Not a defect** — `Severity.ERROR` is `CheckResult`'s default and `format_report` renders it `FAIL`; the two words named one outcome. Prose unified (§A) since the ambiguity misled a reader. |
| 2 | med | `rev-parse --git-dir` non-zero conflates broken git with non-repo → green skip | **Accepted.** Tri-state `git_context()` promoted to `git_helpers` and used by both gates (§A.1, §B). |
| 3 | med | `_infra_result` may have unreviewed callers | **Verified, no change.** 7 call sites, all module-private; enumeration recorded in §B. |
| 4 | med | Missing/malformed complexity after the reorder | **Accepted** (§A, "Entry absent or malformed"). |
| 5 | med | Tests omit HEAD fallback, `None` vs `[]`, all-complexity proof | **Accepted** (§E). |
| 6 | low | ADR location/convention unspecified | **Verified, no change** — `write_decision_drop.py` keyed by run_id; now stated in §F. |

Gemini's reply was cut off at `finish_reason=length`; its one complete finding
(missing iterate entry after the reorder) duplicates #4 and is covered. A
truncated reply is recorded as degraded, not counted as an approval.

## External plan review — round 2

Verdict `revise`, but the direction is affirmed verbatim: *"the enforcement
direction and ordering are sound, and the plan correctly preserves the
intentional non-git SKIP and cross-layer scope."* Every remaining finding is an
explicitness / regression-test item, not a design change. All are folded into
the build below rather than into a third review round.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | med | `git_context()` extraction contract; other patch sites | **Accepted + verified.** Grep: `_git_context` has NO test patch sites (definition + one caller only), so promoting it is safe. `_git_precheck` stays in `layer_coverage`, so `test_layer_coverage_verdict.py:125`'s patch is unaffected. Only `test_layer_coverage_hardening.py:88`'s `_run_git` patch retargets. No cycle: `git_helpers` imports nothing from `layer_coverage`. A direct unit test for the helper is added. |
| 2 | high | How does `git_context()` separate `not_git` from `git_error`? | **Accepted.** Logic is preserved byte-for-byte from `_git_context`: rc==0 → `work_tree` iff stdout is `true`, else `not_git`; stderr matching "not a git repository"/"not a work tree" → `not_git`; anything else → `git_error`. `_run_git` already converts `OSError`/`ValueError`/`TimeoutExpired` into `(1, "", "")`, which lands in `git_error` — so exceptions and timeouts cannot escape unstructured. Tests added for the timeout/exception shape, not only the mocked non-repo one. |
| 3 | med | Boundary: corrupt results artifact vs malformed entry | **Accepted + verified at code.** `_read_iterates_dir` skips corrupt files and filters non-dicts, so `find_entry_by_run_id` returns `None` or a dict and never raises. Corrupt entry file → `None` → plain ERROR, no floor claim. Corrupt `shipwright_test_results.json` → the existing `:96-104` branch → its own distinct ERROR. Different paths, different messages, both blocking. Tested separately. |
| 4 | med | Positive paths must survive the reorder | **Accepted.** `test_ok_when_integration_behavior_present` and `test_ok_when_change_is_not_cross_component` are kept; ADD "non-matching path passes with NO iterate entry at all" — the case the reorder newly makes reachable. |
| 5 | med | An invalid explicitly-supplied commit | **Accepted.** Traces to `_branch_base_commit` → merge-base fails → `_commit_changed_paths` → `git show` rc!=0 → `None` → ERROR. Correct today; a test pins it rather than leaving it inferred. |
| 6 | low | `min_complexity` vs gate enforcement could re-create the ambiguity | **Accepted.** The taxonomy row states plainly that `min_complexity: medium` is the *classification escalation floor*, while integration coverage is *diff-enforced at every complexity* — the two are now independent. This is the exact ambiguity that produced the card. |
| 7 | low | Shell-injection surface on commit values | **Verified, no change.** `_run_git` calls `subprocess.run(["git", "-C", str(project_root), *args])` — argv list, no `shell=True`. The HEAD fallback uses the same path. |

Gemini truncated again (`finish_reason=length`); its visible tail affirms the
defensive entry handling. Recorded degraded both rounds — not counted as an
approval either time.

## Alternative considered and rejected

**Recompute first, but WARN below medium instead of FAIL.** Rejected on merit
(and by the operator at the approval gate): a green SKIP and an ignored WARN are
indistinguishable to whoever ships the change, so this relabels the loophole
rather than closing it. It also splits the gate into two enforcement postures
keyed on the very field the fix removes from the decision.

## Out of scope

- `check_cross_layer_coverage`'s medium+ scope gate (see B).
- `risk_taxonomy.cross_component.min_complexity` stays `medium` — it governs
  classification, not gate enforcement, and the two are now correctly separate.

## Risk

Runs that pass today start failing: a below-medium iterate touching
cross-component machinery without an integration behavior, and a below-medium
iterate whose removal-coverage regeneration fails. Both are the intended effect.
This run's own diff touches no cross-component path (verified: all four
diff-driven detectors return False on the anticipated file set), so it does not
gate itself.
