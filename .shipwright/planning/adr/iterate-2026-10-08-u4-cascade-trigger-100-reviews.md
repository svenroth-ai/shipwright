# Small-iterate code-review trigger, one diff-size rule (campaign unit U4)

Campaign `2026-10-07-finalization-claims-hardening`, unit U4. New F11 claim check `verifiers/cascade_trigger.py` (inputs in `verifiers/_cascade_trigger_inputs.py`), registered in `CLAIM_CHECKS`; the diff-size rule moves to `shared/scripts/lib/review_diff_threshold.py` and the iterate plugin loads it by path (`scripts/lib/review_threshold_bridge.py`), re-exported by `diff_risk_recheck.py`.

## The counting rule (defined once)

Added + removed lines against the merge-base with the trunk, `git diff --numstat --no-renames`, untracked files counted whole before the commit, **strictly more than 100** (exactly 100 does not trigger). Not counted: `.shipwright/`, `CHANGELOG-unreleased.d/`, `shipwright_events.jsonl`, `shipwright_test_results.json`. F3-F5c write those after the trigger is decided, and without the exclusion almost every small iterate measures over 100 at F11. The old doc formula `git diff HEAD~1 | wc -l` counted headers and context lines and saw only the last commit.

## Unknown is triggered, never quiet

When F11 cannot measure the diff (no trustworthy trunk base: a remote without the trunk ref, a trunk named `develop`, a shallow clone; a merge commit on the trunk) or a risk-flag source is unreadable (corrupt or foreign `plan.json`, foreign or malformed `risk_recheck.json`), the run counts as triggered with reason `diff size unknown: <why>` / `risk flags unknown: <why>`, and the review record decides. `code` completed with evidence, or `not_run` with an accepted code, passes; anything else fails and the message names the repair for the input as well as for the row. A repo with no remote at all and one local `main`/`master` (greenfield) trusts that lone merge-base. Only a git failure on the work tree itself fails outright. A triggered `code` row accepts an allowlist: `unavailable`, `delegated-to-orchestrator`, `user-opt-out`; `missing-keys` and `config-disabled` describe the external leg and are refused.

## Accepted limits (no code change)

1. A run labelled `trivial` skips this gate by design (the spec scopes it to `small`), so the complexity label is the trigger's weakest point.
2. `.shipwright/` is excluded from the count wholesale, not file by file.
3. Base resolution differs: Step 3.4 uses one `base_ref` (its fork point), F11 the narrowest merge-base of several trunk names. The counting rule is shared; the base is not.
4. When `base == head` the tip commit alone is measured, which assumes squash-merged PRs.
5. `delegated-to-orchestrator` is not proven to come from a campaign context; the gate takes the code at its word.
6. Self-reported flags other than `cross_component` and the CI paths are not recomputed. Recomputing the path-based detectors (e.g. auth, migrations) from the diff is a follow-up.

## Architecture Review

External, `--mode architecture` over `architecture_brief.md`: GLM **approve**, GPT **approve**. GLM (low): extending the medium+ floor down to small (option B) would make review mandatory for every small change; keep the conditional trigger. **Accepted** - option A taken.

## External-Plan-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GLM medium | Rename records raise and would crash the gate | rejected-with-reason: both consumers pass `--no-renames`, so a move is delete + add; the raise only guards a caller that turned detection on. `measure_diff` turns it into a reported error, never a crash. Test: a pure move counts both sides (400 lines) |
| GLM medium | Exclusion list may miss other bookkeeping (risk_recheck.json, plan files) | rejected-with-reason: both live under `.shipwright/`, which is excluded as a prefix |
| GLM medium | Fail-closed on an unresolvable base can break legacy runs | rejected-with-reason: only `small` runs with no recorded or recomputed flag reach it, and an unmeasured diff must not certify "<= 100"; the message names the repair |
| GLM low | Sweep other mentions of the old formula | accepted-and-fixed: `sub-iterate-runner.md` Step 3.7 and `iteration-reviews.md` rewritten; `campaign-step-3-5-plan-review.md` already defers to Step 3.4's value |
| GLM low | Bridge hard-depends on `shared/` | rejected-with-reason: the plugin cache carries `shared/` (same walk-up as `campaign_progress.py`); the ImportError names the missing file; a fallback copy would be a second definition |
| GLM low | Precedence between plan flags and recheck flags | rejected-with-reason: union, by design (one-way ratchet, as Step 3.4) - documented in the inputs module |
| GLM low | `diff-below-threshold` is self-attested | accepted (already in plan): refused whenever the trigger fired |
| GPT medium | `not_applicable` widens the contract | accepted-and-fixed: refused when triggered, test added |
| GPT medium | Excluding all of `.shipwright/` drops planning inputs | rejected-with-reason: `.shipwright/` holds artifacts Shipwright produces (CLAUDE.md), not code under review; path detection still sees every path, only the count filters |
| GPT medium | Missing vs malformed risk inputs | accepted-and-fixed: absence is legal (standalone without `--run-id`, legacy); corrupt plan and foreign/malformed risk_recheck fail closed; tests for both |
| GPT medium | Renamed-and-edited files | accepted-and-fixed: one invocation (`--no-renames`) for both consumers, rename test added |

## Self-Review

1. Spec Compliance - pass: small + (risk flag or > 100 lines) requires `code` completed with evidence or `not_run` + closed code; constant in `shared/scripts/lib`, re-exported; one counting definition, stated in Step 3.7.
2. Error Handling - pass: unknown diff, no trustworthy base, merge commit on trunk, corrupt/foreign artifacts count as triggered (the record decides); a git failure on the work tree fails.
3. Security Basics - pass: argument-array git calls, run_id path-safety checked first, no secrets.
4. Test Quality - pass: real git repos, boundary 100/101, removed lines, rename, multi-commit branch, exclusion, recomputed flag, code vocabulary, evidence bar.
5. Performance Basics - pass: a few bounded git calls, small runs only.
6. Naming & Structure - pass: own modules, registered once; `iterate_checks.py` untouched; capped files not grown (305, 510).
7. Affected Boundaries - pass: consumers of `<run_id>.plan.json` and `risk_recheck.json` probed against this run's real producer output.
8. Test Hygiene Probe - pass: no findings.

## External-Code-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT high / GLM medium | No trustworthy base measured only the tip commit | accepted-and-fixed: no base is now unknown (fail closed unless flagged); multi-commit and missing-base tests added |
| GLM high | A merge commit already on the trunk measured as ~0 lines | accepted-and-fixed: unknown; test added |
| GPT medium | NUL-separated paths with a newline were split | accepted-and-fixed: NUL input split on NUL only; test added |
| GLM medium | Empty commit falls back to HEAD | rejected-with-reason: F11 always passes `--commit`; same fallback as `check_integration_coverage` |
| GLM low | Import-time dependency of `diff_change_set` on the bridge | rejected-with-reason: as the plan finding above |
| GLM low | Recomputed flags ran over uncounted paths | accepted-and-fixed: detectors run over counted paths only |

## Internal-Review-Findings (code-reviewer, doubt-reviewer)

| Finding | Disposition |
|---|---|
| An unmeasurable diff failed before the review record was read, so a reviewed run could not clear it | accepted-and-fixed: unknown is triggered and the record decides; greenfield trusts its lone local trunk; tests on real repos for each shape |
| Denylist for the triggered `code` row let `missing-keys` / `config-disabled` pass | accepted-and-fixed: allowlist `ACCEPTED_CODES`; parametrized refusals |
| `complexity` compared without trimming | accepted-and-fixed: `.strip().lower()` |
| `plan.json` read without the recheck reader's hardening | accepted-and-fixed: symlink / non-regular file refused, foreign `run_id` refused |
| "Diff under 100 lines" contradicted the `> 100` boundary | accepted-and-fixed: "at most 100 changed lines" throughout `iteration-reviews.md` |
| Tests inherited the caller's git environment | accepted-and-fixed: `GIT_DIR`-family variables dropped, `commit.gpgsign=false` |
| Two numstat parsers | accepted-and-fixed: `diff_change_set.parse_numstat_z` delegates to the shared one through the bridge |
| `_is_merge` read a git failure as "is a merge" | accepted-and-fixed: the two are reported separately |
| Trivial label, `.shipwright/` exclusion, base resolution, tip-only on trunk, unproven delegation, self-reported flags | accepted as limits; see "Accepted limits" above |

## Confidence Calibration

Effective complexity `small`, no `touches_io_boundary`: not required. Probe run anyway on the two read boundaries: `recorded_risk_flags` on this run's real `plan.json` (classify_complexity) and `risk_recheck.json` (diff_risk_recheck) returned `['touches_auth']`; `measure_diff` on this worktree's HEAD found the base `b7e09d35` and 0 counted lines (one `.shipwright/` path). Not probed: a plugin-cache install without `shared/` (ImportError by design).
