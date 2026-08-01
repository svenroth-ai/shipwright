# Mini-Plan — iterate-2026-08-01-campaign-diff-driven-risk-recheck

- **Run ID:** `iterate-2026-08-01-campaign-diff-driven-risk-recheck`
- **Intent:** CHANGE (Path B) · **Complexity:** medium · **Risk flags:** `cross_component`
- **Spec:** `.shipwright/planning/iterate/iterate-2026-08-01-campaign-diff-driven-risk-recheck.md`

## Problem (one paragraph)

The campaign `sub-iterate-runner` classifies complexity once, at Step 2, from the
sub-iterate spec *text*, before code exists. `classify()` is
`(message, sync_config_path, project_root)` and its risk detection is a regex sweep
over the message; the four diff-driven detectors in `risk_detectors.py` are imported
by `classify_complexity` but never called by `classify()`. The runner never reaches
Stage 2 (Repo Scout), which is the documented caller of those detectors. Result:
`cross_component`, `touches_ci_supplychain` and the file-pattern halves of
`touches_io_boundary` / `touches_build` cannot fire in campaign mode. Two different
failures follow — `check_ci_supplychain_ack` applies at every complexity and
RECOMPUTES from the diff, so a workflow-touching unit hard-fails its own F6-verify;
`check_integration_coverage` green-SKIPs below medium, so a hooks/churn-touching unit
records `small` and the gate reports green without evaluating.

## 1. Files to create / modify

| # | File | Type | Change |
|---|---|---|---|
| 1 | `plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py` | new | CLI over the 4 detectors; ~130 LOC (limit 300) |
| 2 | `plugins/shipwright-iterate/agents/sub-iterate-runner.md` | edit | Step 3.4; Step 3.5 trigger; F5c complexity note. **Hard ceiling 497 lines** |
| 3 | `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` | edit | Full Step 3.4 procedure + orchestrator handling of a CI-escalated unit (310/400) |
| 4 | `plugins/shipwright-iterate/agents/sub_iterate_runner_contract.schema.json` | edit | `success.risk_recheck`; widen `escalated` |
| 5 | `plugins/shipwright-iterate/scripts/lib/risk_detectors.py` | edit | Correct the "no in-repo production caller" docstring paragraph |
| 6 | `plugins/shipwright-iterate/skills/iterate/SKILL.md` | edit | §5b names Step 3.4 beside 3.5/3.7 |
| 7 | `plugins/shipwright-iterate/tests/test_diff_risk_recheck.py` | new | Unit tests, in-process (decision fn + git layer + `main()`) |
| 8 | `plugins/shipwright-iterate/tests/test_sub_iterate_runner_step_3_4.py` | new | Step 3.4 anchors + schema keys. **Revised during Stage 2:** originally an edit to `test_sub_iterate_runner_contract.py`, which is baseline-pinned at `current: 421`; growing it to 627 was an Anti-Ratchet violation, so the assertions moved here and the pinned file was restored byte-for-byte |
| 9 | `integration-tests/test_campaign_risk_recheck_integration.py` | new | Real-repo composition test (`category:"integration"`) |
| 10 | `shared/scripts/lib/autonomous_loop.py` + `shared/tests/test_autonomous_loop.py` | edit | Disposition O2: `failure_reason` fallback so an escalated unit's `reason` reaches the operator, scoped to non-complete (C9) |

## 2. Work breakdown (sequential)

1. **CLI module** (`diff_risk_recheck.py`). Pure decision function
   `recheck(changed_files, stage1_complexity, diff_loc) -> dict` + a thin `main()`
   that resolves the change set from `--base-ref` (see O1/G2 disposition: `git diff
   --numstat -z <base>` — base → **working tree** — unioned with `git ls-files
   --others --exclude-standard -z` for untracked files) or from `--changed-files`
   + `--diff-loc`. Escalation is decided in the pure function, not in `main()`.
   *Test:* unit tests call `recheck()` directly — flags, floor, ordering semantics,
   escalate-on-CI, empty list, Windows separators, quoted non-ASCII paths.
2. **Schema** (#4). Add `risk_recheck` to `success.properties`; add `reason_code`
   + `ci_paths` to `escalated` and widen `detected_complexity`. Both branches are
   `additionalProperties:false`, so this must precede any result carrying the field.
   *Test:* extend the contract test's schema assertions; validate a sample of each
   branch with `jsonschema`.
3. **Runner contract** (#2). Compact Step 3.4 (command, floor-merge rule,
   escalation rule, F5c note), Step 3.5 trigger line, pointer to campaign-mode.md.
   Compress equivalent verbosity elsewhere to hold ≤497 lines.
   *Test:* contract-anchor tests (Step 3.4 heading, label, escalation vocabulary,
   the 100-LOC phrase now present for 3.5), plus a line-count assertion.
4. **Reference** (#3) + **SKILL §5b** (#6) + **docstring correction** (#5).
   *Test:* existing §5b drift test; a new assertion that campaign-mode.md documents
   the escalated-unit path.
5. **Integration test** (#9). Real temp git repo, CLI run as a real subprocess.
   Fixtures split per the O5 disposition:
   - **hooks-only** (`plugins/x/hooks/hooks.json`), left **UNCOMMITTED** in the
     working tree — proves both the success path (floor `medium`, no escalation)
     and the O1/G2 fix in one case. Asserts the floor equals the complexity
     `check_integration_coverage` needs to stop SKIPping, pinning the two SSoTs.
   - **workflow-only** (`.github/workflows/ci.yml`) — proves escalation: exit 3,
     `reason_code`, populated `ci_paths`.
   - **untracked new hook** — proves a file that appears in no `git diff` is seen.

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

None. Two JSON contracts change shape (result.json schema; the CLI's stdout, which
is new surface).

## 5. Test strategy

- **Unit, in-process:** `recheck()` decision function. In-process on purpose —
  subprocess-only tests measure 0% to the diff-coverage gate (<80% patch coverage
  blocks).
- **Contract/drift:** anchors in `sub-iterate-runner.md`, schema keys, §5b mention,
  and the ≤497-line ceiling.
- **Integration (`category:"integration"`, mandatory here):** real temp git repo,
  real subprocess, proving CLI + detectors + complexity floor + verifier expectation
  compose. Required because `cross_component` enforces `integration_coverage` and
  `check_integration_coverage` is non-dodgeable.
- **E2E (F0.5):** `surface = none` with justification — this change has no runnable
  app surface; its executable surface *is* the test suite. The CLI is exercised as a
  real subprocess in #9, which is the honest equivalent.
- **Full test suite** (enforced by `cross_component`), one pytest root per process.

## 6. Alternative approach (rejected)

**Add `--changed-files` to `classify_complexity.py` and have the runner re-run Step 2
after Build.** Rejected for four reasons: (a) it makes `classify()` two-phase, and
the same run would then contribute twice to the `prior_source: history` median that
#506 introduced; (b) it re-grows the module a prior iterate deliberately shrank by
extracting `risk_detectors.py`; (c) complexity classification has no vocabulary for
"stop and escalate", which AC4 requires; (d) it would put the escalation decision
inside the function every standalone iterate also calls at Step E, widening blast
radius far beyond campaign mode. A separate single-purpose CLI keeps `classify()` a
pure Stage-1 function and mirrors the Repo Scout step that already exists
(`iteration-planning.md` Quick Scout step 3).

---

## External-Plan-Review-Findings (openrouter → openai + gemini, verdict `revise`)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| O1 / G2 | **high** | `git diff <base>...HEAD` only sees *committed* history. Build leaves changes in the working tree (F6 is the commit), so the re-check would see nothing and silently pass — reproducing the exact failure it fixes. | **accepted-and-fixed.** Change-set = `git diff --numstat -z <base>` (base → **working tree**: committed + staged + unstaged) ∪ `git ls-files --others --exclude-standard -z` (untracked — a *new* hook file appears in no diff). Integration case asserts an **uncommitted** file still fires. |
| O2 | **high** | Orchestrator consumer of `escalated` not identified or tested. | **accepted-and-fixed.** Verified: `escalated` ∈ `VALID_STATUSES` (`autonomous_loop.py:30`), accepted by `_validate_result` (:257), whole result persisted (:328), any non-`complete` → exit 3 → STRICT-STOP (:341); `campaign_progress.py:151` counts it distinctly. **Real defect found:** `:324` sets `failure_reason` from `result["error"]` only, but an escalated result carries `reason` — the *why* is dropped from the operator view. Fixed with a fallback + consumer-level test. |
| O3 | med | Exit-code/JSON protocol underspecified; `set -e` could kill the runner before `result.json`. | **accepted-and-fixed.** Stable protocol: valid JSON **always** on stdout; `0` = continue, `3` = valid CI escalation, any other non-zero = operational failure. Step 3.4 captures stdout **and** status, validates JSON, and only an exit-3-with-valid-JSON becomes an escalated result. |
| O4 / G1 | med/**high** | `diff_loc` has no source — `--name-only` carries no counts. | **accepted-and-fixed.** `--numstat` supplies added+deleted in the same pass; binary files (`-`) count 0. `--changed-files` requires explicit `--diff-loc` (default 0), documented as such. |
| O5 | med | A combined CI+hooks fixture escalates before F5c, so it cannot prove AC3. | **accepted-and-fixed.** Fixtures split: **hooks-only** exercises the success path and floor `medium`; **workflow-only** exercises escalation. |
| O6 | med | `max(stage-1, floor)` on complexity *strings* is wrong. | **accepted-and-fixed.** Import canonical `COMPLEXITY_ORDER` from `complexity_vocabulary` (SSoT); validate the Stage-1 value and error on an unknown one. |
| O7 / G4 | med/low | git invocation robustness: newlines in filenames, leading-`-` paths, `shell=True`. | **accepted-and-fixed.** Argument array (never a shell), `-z` NUL-delimited output, `--` before pathspecs, `--end-of-options` guard on refs. |
| O8 | med | `additionalProperties:false` + optional field ⇒ a result stays valid while silently omitting the mechanism. | **PARTIALLY accepted.** Escalated-variant fields (`reason_code`, non-empty `ci_paths`) made **required** via a conditional — new vocabulary, no historical artifacts to break. Making `success.risk_recheck` **required** is **rejected-with-reason**: the same schema deliberately keeps `reviews` and `finalization` optional *"for backwards-compat with historical result.json files"*; requiring it would invalidate every pre-change artifact and contradict the precedent in the same file. Execution enforcement belongs in the runner contract and 3f-bis, not in a schema that must still validate history. |
| O9 | low | Normalization/dedup consistency across flags, paths and counts. | **accepted-and-fixed.** One canonical normalized set drives detection; original paths retained for reporting. |
| G3 | med | "Compress equivalent verbosity elsewhere" delegates blind pruning. | **accepted-and-fixed.** Named target: the **Step 3.5 Branch A/B/C bodies** and the **Step 3.7 item-1 delegation paragraph** — the two most verbose blocks — preserving every drift-tested phrase (`Branch A/B/C`, `External Plan Review`, `Code Review Cascade`, `external_review.py`, `--mode code`, `100 lines`/`100 LOC`). A line-count assertion pins ≤497. |

**Design note added by the review:** `campaign-mode.md:182-191` shows the orchestrator's
3f-bis **already** computes its trigger from the diff *because* "the runner … has no
Stage-2 Repo Scout, so diff-driven flags … are structurally never set for it". The gap is
already recognised and already remedied at one site; this change extends the same remedy
to the steps that run **inside** the runner, where the orchestrator cannot reach.

---

## Internal-Code-Review-Findings (Stage 1 `spec-reviewer` PASS → Stage 2 `code-reviewer`)

**Stage 1 verdict: PASS.** All AC1–AC8 verified against the tree, all
"accepted-and-fixed" dispositions delivered, O8's rejected half factually correct,
no scope creep. Four non-gating observations; #21 (an undelivered test promise) and
#22 (an overstated docstring) were fixed before Stage 2 ran.

**Stage 2 findings — all accepted and fixed:**

| # | Sev | Finding | Fix |
|---|---|---|---|
| C1 | **high** | **Regression introduced by this change.** `plan_review_required` was computed from the CLI's four diff-driven flags only, but seven canonical flags (`touches_auth`, `touches_rls`, `touches_middleware`, `touches_migrations`, `touches_billing`, `touches_shared_infra`, `touches_public_api`) have no diff-driven detector. A spec saying "fix the login redirect" → Stage 1 sets `touches_auth`, estimate `small`; diff touches only a page component. The OLD rule RAN the plan review; the new one SKIPPED it — narrowing the gate AC5 exists to widen. | `--stage1-flags` added and UNIONED into `risk_flags` (never replaced); floors still come from diff flags alone since Stage 1 already applied its own. Contract passes `{step_2_risk_flags}`. Tests: `test_stage1_flags_are_unioned_not_replaced`, `test_stage1_and_diff_flags_both_survive`. |
| C2 | **high** | **Rename blind spot.** `git diff --numstat` has rename detection ON by default and reports only the NEW path, so moving `.github/workflows/security.yml` → `security.yml.disabled` raised no CI flag: an autonomous unit could disable a security workflow. Empirically confirmed — with detection on git emits the single combined path `.github/workflows/{security.yml => security.yml.disabled}`, which fails the `\.ya?ml$` anchor. | `--no-renames` added, so a move is a delete + an add and the old path is seen. The rename branch of `parse_numstat_z` is deleted and the parser now RAISES on a rename-shaped record, pinning the coupling. Real-repo test: `test_moving_a_workflow_out_of_the_trust_boundary_still_escalates`. |
| C3 | **high** | The <80% diff-coverage gate would likely BLOCK the PR: `_git`, `collect_change_set` and `main` (~27 of ~83 new statements) were exercised only via subprocess, which measures 0%. The documented process contract was therefore untested. | 14 in-process tests added, monkeypatching `_git` **by module object** (ADR-045, never the `"lib.X"` string): union, merge-base preference, fallback, both raise paths, and the `(exit code, stdout JSON)` pair for exits 0 / 2 / 3. |
| C4 | med | Base ref resolved to the ref's TIP, not the fork point. A concurrent `origin/main` advance mid-Build would make upstream files read as this unit's — an unrelated upstream workflow edit would STRICT-STOP the campaign citing `ci_paths` it never touched. | `resolve_base()` uses `git merge-base HEAD <ref>`, falling back to the ref only when there is no common ancestor. |
| C5 | med | `git ls-files --others` failure was silently swallowed — fail-OPEN on the leg that exists to see brand-new hook files, reproducing the original silent stand-down through the fix. | Raises `RuntimeError`. Test: `test_untracked_failure_raises_instead_of_silently_dropping`. |
| C6 | med | O9 was not actually delivered: `_dedupe` returned originals and detection ran on them, while only two of four detectors self-normalise — a quoted non-ASCII path would leave `cross_component` down. | Renamed `normalized_paths()`; ONE normalized set now drives detection, counting and reporting. |
| C7 | med | Step 3.4 passed `--base-ref "{base_branch}"` unconditionally, but `base_branch` is NULL for the first stacked sub-iterate → exit 2; and the step gave no instruction for a non-0/non-3 exit, so a runner could read "not 3" and continue on Step 2's stale estimate. | `--base-ref` defaults to `HEAD` (correct: nothing is committed until F6). Contract item 3 now says any other non-zero → `status:"failed"`, never continue. Tests pin both. |
| C8 | low | Rename fixture was not a shape git emits, so the test passed for the wrong reason. | Replaced by the raises-test above; the real shape is now what is asserted. |
| C9 | low | The `failure_reason` fallback could stamp a reason onto a GREEN unit, since `_validate_result` does not apply the schema. | Scoped to non-complete. Test: `test_complete_result_never_gains_a_failure_reason`. |
| C10 | low | `campaign-mode.md` claimed `failure_reason` reaches "the board", but no in-repo consumer reads it. | Reworded to the verifiable claim (it lands in `loop_state.json`). |
| C11 | low | `Detector` typed as `object`; one assertion (`max(["small","medium"])`) tested a Python builtin, not the module. | `Callable[[list[str]], bool]` alias; tautological assertion removed. |
| C12 | low | `ls-files` paths are cwd-relative while diff paths are repo-root-relative. | `--full-name` added. |

**Bloat consequences handled in the same pass.** `test_sub_iterate_runner_contract.py`
is baseline-pinned at `current: 421`; the new assertions had grown it to 627, which is
an Anti-Ratchet violation (audit H3, HIGH). They were moved to a new
`test_sub_iterate_runner_step_3_4.py` (240 lines) and the pinned file restored
byte-for-byte. `diff_risk_recheck.py` was trimmed from 343 to exactly 300 so it does not
become a NEW crossing requiring an allowlist entry (audit H1).
