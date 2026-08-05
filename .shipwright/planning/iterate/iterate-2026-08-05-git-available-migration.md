# Iterate Spec: Migrate the remaining `_git_available` callers onto `git_context`

- **run_id:** `iterate-2026-08-05-git-available-migration`
- **status:** `implemented`
- **intent:** CHANGE
- **complexity:** medium
- **risk_flags:** none (Stage-1 keyword match flagged `touches_migrations` on the
  word "migration" in the card text; the real file-path detector requires
  `supabase/migrations/**`, which this diff never touches — confirmed false
  positive, not enforced)
- **source:** Stage-3 doubt review of `iterate-2026-08-01-fail-closed-reader-migration`;
  tracked as `trg-4183acd3`

## Problem

`git_helpers._git_available` is the binary `rc == 0` probe that `git_context`
was extracted to replace: a broken git binary, a `safe.directory` /
dubious-ownership refusal, a permission failure, or a wedged `index.lock` all
return non-zero from **inside** a real repository and are read as "git
unavailable" — indistinguishable from "not a git repository". Three consumers
(`ci_supplychain.py`, `integration_coverage.py`, `layer_coverage.py`) were
already migrated onto the tri-state `git_context` (`work_tree` / `not_git` /
`git_error`) across `iterate-2026-06-13-shc-git-helpers` →
`iterate-2026-08-01-coverage-gate-recompute-order` →
`iterate-2026-08-01-fail-closed-reader-migration`. `_git_available` itself was
never deleted, so it kept the old conflation live for every caller that had not
yet been migrated — most seriously `check_spec_impact_recorded`, an F11 ERROR
gate that green-SKIPs ("skipped (git unavailable — cannot inspect the
branch)") on an infrastructure fault instead of refusing.

## Scope (live callers as of this run — the finding named 5; PR #540 on
2026-08-03 added 2 more reproducing the identical shape)

| # | Call site | Gate kind | Current behavior on git fault | New behavior |
|---|---|---|---|---|
| 1 | `iterate_checks.py:949` (`check_spec_impact_recorded`) | F11 ERROR (feature/change) | green SKIP | refuse (ERROR) |
| 2 | `spec_checks.py:336` (S4 FR-preservation) | Tier-2 WARN-only, never FAILs | SKIP | SKIP (probe swapped, ceiling unchanged) |
| 3 | `spec_checks.py:611` (S9 README-freshness) | Tier-2 WARN-only | SKIP | SKIP (probe swapped) |
| 4 | `spec_checks.py:704` (S10 CLAUDE.md-sync) | Tier-2 WARN-only | SKIP | SKIP (probe swapped) |
| 5 | `_layer_coverage_regen.py:275` (`regenerate_base_head`) | internal helper; both current callers (`check_removal_coverage`, `check_cross_layer_coverage`) already gate on `git_context` via `_git_precheck` before calling it | returns `None` (caller ERRORs) | returns `None` (caller ERRORs) — same outcome, no longer routed through the binary probe |
| 6 | `test_results_evidence_check.py:40` (`check_test_results_evidence`) | F11 ERROR gate | green SKIP (folded into the "no commit" SKIP) | refuse (ERROR) when a commit *was* supplied and git faults; the no-commit SKIP is unchanged and untouched |
| 7 | `test_results_backfill_check.py:236` (`check_test_results_backfill`) | F11 ERROR gate | green SKIP (folded into the "no commit" SKIP) | refuse (ERROR) when a commit *was* supplied and git faults; the no-commit SKIP is unchanged and untouched |

**Also touched, docstring-only (flagged by the Stage-3 doubt review as missing
from this list — added here rather than left implicit):**
`ci_supplychain.py`'s `check_ci_supplychain_ack` docstring and
`integration_coverage.py`'s cross-component-gate docstring both named this
card (`trg-4183acd3`) as the still-outstanding remainder of the `_git_available`
family; both are updated to say it is closed, past tense, now that it is. No
logic, import, or branch changed in either file — confirmed by the code-review
and doubt-review passes, and by the unchanged `_CROSS_COMPONENT_PATTERNS`/
`_CI_SUPPLYCHAIN_PATTERNS` drift-pin tests staying green.

Per-call-site judgement (why #2-4 stay SKIP while #1/#6/#7 become ERROR): S4/S9/S10
are declared "Tier-2, WARN-only" in `spec_checks.py`'s own module docstring, and
`test_spec_checks.py::test_s10...` already pins that S10 never returns
`STATUS_FAIL`. There is no ERROR severity available to escalate into without
inventing one outside that module's contract, so the fix is a probe swap only
(clearer SKIP wording, same outcome). #1/#6/#7 are `Severity.ERROR`-default F11
canon gates — the exact class this migration exists to close.

Then delete `_git_available` from `git_helpers.py` and its now-obsolete direct
unit test in `test_git_helpers.py`.

**Not in scope:** the `changed is None` ("BLIND") branch inside
`check_spec_impact_recorded` — that is `_iterate_changed_paths`'s own signal for
an unresolvable merge-base on a *healthy* work tree, unrelated to
`_git_available`, and already correctly a SKIP by that function's contract.
`test_layer_coverage_*.py`'s locally-defined `_git_available()` test helpers
(environment-availability check for `pytest.mark.skipif`) are unrelated
functions that happen to share a name with the production helper — confirmed
by reading them; not touched.

## Acceptance Criteria

- [x] **AC-1-agent:** `check_spec_impact_recorded` classifies via
  `git_helpers.git_context`: SKIP on `not_git`, refuse (`ok=False`,
  non-skipped) on anything else, exactly like `check_ci_supplychain_ack`.
- [x] **AC-2-agent:** S4/S9/S10 classify via `git_context` and keep their SKIP
  outcome on both `not_git` and `git_error` (Tier-2 ceiling), with a message
  that no longer claims "git unavailable" when git in fact ran and refused.
- [x] **AC-3-agent:** `regenerate_base_head` classifies via `git_context`
  instead of `_git_available`; both existing callers' behavior is unchanged
  (proven by the existing `layer_coverage` test suite staying green).
- [x] **AC-4-agent:** `check_test_results_evidence` and
  `check_test_results_backfill` check `commit_hash` **before** classifying
  `git_context`, so the pre-existing "no `--commit`" SKIP is reached and
  returned first, unconditionally, with `git_context` never even called in
  that case. Only once a commit *was* supplied does `git_context` run: SKIP on
  `not_git` (still a stand-down, matching `check_ci_supplychain_ack`'s own
  `not_git` SKIP), refuse only on `git_error`/anything else. (External plan
  review flagged the ordering as under-specified in prose; the code was
  already correct — this AC now states the order explicitly.)
- [x] **AC-5-agent:** `git_helpers._git_available` is deleted; grep for the
  literal call form `_git_available(` returns zero hits in production code
  anywhere in the repo. This is deliberately narrower than a bare string grep
  for `_git_available`: the three `test_layer_coverage_*.py` files carry
  their own LOCAL, differently-sourced `_git_available()` test helpers (an
  environment `git --version` availability check for `pytest.mark.skipif`,
  unrelated to `git_helpers`) that are explicitly out of scope and are not
  expected to disappear. (External plan review flagged this scoping as
  ambiguous in the AC's original one-line phrasing.)
- [x] **AC-6-agent:** New infra tests mirror
  `shared/tests/test_check_ci_supplychain_infra.py`'s shape (not-a-repo skips;
  a git fault at every applicable tier errors/skips per its class; an
  unrecognised `git_context` value fails closed; a localized non-repo message
  still skips) for `check_spec_impact_recorded`,
  `check_test_results_evidence`, and `check_test_results_backfill`.

## Verification (medium+)

- **surface:** `none` — pure backend verifier-library change; no `dev_url`,
  no UI, no build artifacts. Justification recorded per F0.5.
- **runner:** `uv run pytest shared/tests -k "git_helpers or spec_checks or iterate_checks or layer_coverage or test_results" -v`
  (targeted), then the full `shared/tests` root for the suite requirement.
- **full suite:** `uv run shared/scripts/tools/run_test_suite.py --project-root . --run-id iterate-2026-08-05-git-available-migration`

## Spec Impact

`NONE` — this is an internal correctness fix to the framework's own F11
verifier gates. No adopted-project functional requirement describes
`git_helpers._git_available`'s conflation; nothing in `.shipwright/agent_docs/spec.md`
references it.

## Confidence Calibration

- **Boundaries touched:** `git_helpers.py` (probe deletion), 4 F11/Tier-2
  verifier modules that call it (`iterate_checks.py`, `spec_checks.py`,
  `_layer_coverage_regen.py`, `test_results_evidence_check.py` +
  `test_results_backfill_check.py`), plus their test files.
- **Empirical probes run:** grepped every `_git_available(` call site across
  `shared/scripts` (7 found, not the 5 the finding named — confirmed via `git
  log` that PR #540, merged 2026-08-03, added 2 after the finding was written
  on 2026-08-01) and every reference to the bare string `_git_available`
  including test files, to rule out a missed caller or a stale docstring
  mention masquerading as a live reference. Confirmed the blocking dependency
  (P2.22 / `iterate-2026-08-01-fail-closed-reader-migration`, #526) is merged
  to `origin/main` via `git merge-base --is-ancestor`. Read the full settled
  pattern in `ci_supplychain.py` and `integration_coverage.py` (`git_context`
  → SKIP on `not_git`, refuse on anything else) and the reference test file
  named in the card, `test_check_ci_supplychain_infra.py`, in full.
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | `check_spec_impact_recorded` refuses (not SKIP) on a git fault inside a repo | tested | `test_check_spec_impact_recorded_infra.py` |
  | `check_spec_impact_recorded` still SKIPs outside a repo | tested | same file |
  | `check_test_results_evidence` refuses on a git fault when a commit was supplied | tested | `test_check_test_results_infra.py` |
  | `check_test_results_evidence` still SKIPs when no commit is supplied (git healthy) | tested | same file |
  | `check_test_results_backfill` mirrors the same split | tested | same file |
  | S4/S9/S10 keep SKIP on both `not_git` and `git_error`, message no longer claims unconditional unavailability | tested | `test_spec_checks.py` additions |
  | `regenerate_base_head` behavior unchanged for both existing callers | tested | pre-existing `test_layer_coverage_*` suite (regression, not new) |
  | `_git_available` has no remaining reference anywhere in the repo | tested | `grep -R _git_available` returns zero hits outside `git log`/CHANGELOG history |
- **Confidence-pattern check:** asymptote — each of the 7 call sites was read
  in full, not sampled, before deciding its severity; the two undocumented
  sites were found by re-deriving the grep rather than trusting the card's
  count. Coverage breadth — every severity class present in the call-site set
  (F11 ERROR, Tier-2 WARN-only, internal-helper-already-gated) has at least one
  representative fixed and tested. No `cross_component` integration behavior
  applies (confirmed against `_CROSS_COMPONENT_PATTERNS` — none of the touched
  files match).
