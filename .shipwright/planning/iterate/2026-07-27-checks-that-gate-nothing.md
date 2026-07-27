# Iterate Spec: checks that run, report, and gate nothing

- **Run ID:** iterate-2026-07-27-checks-that-gate-nothing
- **Type:** change · **Complexity:** medium
- **Risk flags:** `touches_ci_supplychain` (`.github/workflows/**`) — confirmed
  against `risk_detectors`; `cross_component` and `touches_io_boundary` do NOT
  fire, so no integration-coverage and no boundary-probe obligation.
- **Card:** `trg-c7e5835b` items (3), (4), (5) + the unlisted third orphan.
  PR B of two; PR A (items 1–2) merged as #437.
- **Implements:** FR-01.17 (E)6

## Goal

Three checks that run, report a result, and hold nothing up — the card's theme.

## What shipped

### Item (5) + the third orphan — wired so they block

`scripts/verify_contract_surface.py` and `scripts/verify_sweep_delivery_surface.py`
were referenced by no workflow, no test and no doc. They ran nowhere. Both now run
in `ci.yml`'s `Python (lint + test)` job, which IS the required check — **verified
green locally first**, because wiring a red gate blocks every PR including the one
that wires it. Both are hermetic (no network, no clone; paths from `__file__`, not
cwd) and run after all setup steps, so the local green transfers.

**A gate the guard cannot see is half-wired.** `check_ci_gate_coverage.py` only
polices steps it recognises as gates, by command or by name — and these two run a
bespoke script, so it was blind to them. Proven: with a `continue-on-error: true`
planted on `Contract surface (gate)`, the guard exited **0**. `(gate)` is now a
name keyword, so the naming convention is load-bearing and the NEXT such step is
covered without editing a registry.

### Item (4) — the security verdict says what it covers

`security.yml` printed a bare `Critical findings: 0` and exited 0 while high
findings sat unmentioned. It now prints
`critical-gate PASS|FAIL — N critical (blocking), N high, N medium, N low`, writes
a severity table to the job summary, and emits a `::warning::` when it passes with
open highs. **The gate itself is unchanged** — blocking on critical alone is the
deliberate posture, and a test pins that this reporting fix did not move it.

### Item (3) — the comparison that did not exist

New pure `shared/scripts/lib/required_checks_drift.py` + producer
`shared/scripts/tools/check_required_checks.py`. Reports **both** directions:
`unenforced` (runs but gates nothing) and `phantom` (required but nothing produces
it). It runs as a **producer, not a CI gate** — the Actions token cannot read a
repo's protection configuration — and files one triage action-unit keyed on
`repo@branch` plus the exact divergence.

**On this repo it now reports exactly one genuine finding:** `Prepare review
request` (PR A's own stage 1) runs on every PR and blocks nothing. The operator
decides whether to require it or mark it advisory.

## What review changed

The build was green and looked finished. Everything below was found afterwards,
and each item is the same failure class the card is about — a check that reports
without holding anything up, or reports something untrue.

**F0 caught two defects the build had shipped:**

1. `POSTED_STATUS_CONTEXTS` gained `pr-review-run.yml`, an entry outside adopt's
   scope, and `test_automerge_readiness` went red. The map now has two consumers
   at different scopes; the dead-config guard was widened to "some consumer visits
   it" (a typo'd key still fails) and the Test-Update-Klausel is honoured in the
   same diff.
2. The job-summary write was unguarded under `set -e`, so **the security gate
   exited 1 on a clean scan** wherever `GITHUB_STEP_SUMMARY` is unset. The A5.8
   behavioral probe executes that body outside Actions and went red. A
   merge-blocking gate must never die for a cosmetic sink.

**External review round 1 → `block`.** Both models independently found the same
high-severity bug: a repo that requires **nothing** was treated as *unreadable* and
exited 2. That is the loudest case the producer exists to report, and it was blind
to it. Fixed by tracking readability separately from content; a `404` counts as an
answer only after the repo itself is proven readable (`resolve_default_branch`),
because a typo'd slug 404s on everything too. Also fixed: ruleset ref-scoping (now
via `repos/{repo}/rules/branches/{branch}`, the projection GitHub has already
evaluated for that ref — which also drops the admin-scope requirement) and `gh`
missing/hanging producing a traceback instead of the documented exit 2.

**External review round 2 → `ship-with-fixes`.** Four more, all fixed:

1. The severity breakdown counted only `findings.json` while the blocking total
   spans `findings.json` + `prompt_risks.json` — so it printed `0 high` with an
   open prompt-injection high. The understatement this item exists to remove,
   reintroduced one line below the fix.
2. `all_workflow_check_names` counted workflows that cannot run on a pull request.
   **This produced a false positive on this very repo:** the manual-only
   `grade-empirical.yml` was reported as drift. `workflow_report` already computes
   `dormant` and the code discarded it. Over-derivation mutes a producer exactly
   as surely as the under-derivation it replaced.
3. The reverse-drift test searched raw workflow text, so a verifier named in a
   comment would have satisfied it. It now parses steps and requires an executable
   `run:` line in a step that is not `continue-on-error`.
4. No tests covered the producer's host I/O or its exit codes — the two bugs above
   passed all 12 original tests. 17 added.

**CI's own PR-Review gate → `CHANGES_REQUESTED`,** on the pushed branch, after
everything above was green. `resolve_repo` used `url.rsplit("github.com", 1)[-1]`,
and `rsplit` on a string that does not contain the separator returns the WHOLE
string — so an SSH host alias (`gh:owner/repo`) or a GitHub Enterprise remote
became the "slug" and was handed to `gh api repos/<url>`. Now refused with a
message naming `--repo`. The same review also requires a maintainer to approve
the two `.github/workflows/**` files by hand; that is a human gate, not a defect.

## Spec Impact

- **Classification:** NONE — FR-01.17 and its (E) criteria are already on `main`
  (REQ-3 Phase 2). This implements (E)6 and touches no `spec.md`.
- **Justification:** the requirement and its acceptance criteria exist unchanged;
  this run supplies the enforcement (E)6 already promises. Traceability via the
  `@FR-01.17` tags on `shared/tests/test_required_checks_drift.py`,
  `test_checks_that_gate.py` and `test_check_required_checks_cli.py`.

## Confidence Calibration

- **Boundaries touched:** the CI trust boundary (`.github/workflows/ci.yml`,
  `security.yml`) and one shared registry whose consumer scope changed
  (`automerge_readiness.POSTED_STATUS_CONTEXTS`). `touches_io_boundary` did not
  fire — no `.env`, config or state file is in the diff — so no round-trip probe
  is owed. `cross_component` did not fire, so no integration-coverage behavior.

- **Empirical probes run:**
  - Planted `continue-on-error: true` on `Contract surface (gate)`: the shape test
    went red AND `check_ci_gate_coverage.py` exited 1. With the `(gate)` keyword
    removed it exited **0** — the guard was genuinely blind, not theoretically so.
  - Deleted the `high=` line from `security.yml`; renamed a gate step off-contract;
    dropped a real `scripts/verify_orphan_surface.py` into the tree: 5 tests red,
    each naming its own cause.
  - Extracted the `shipwright-critical-gate` step body and ran it over three
    fixture shapes: both scan outputs → `2 high, 2 medium, 1 low` (union correct);
    `prompt_risks.json` absent → `1 high, 0 medium, 1 low` + the degradation
    warning; a prompt-critical → `FAIL`, exit 1. The gate still blocks.
  - Ran the producer against the live repository at every stage. Before the
    dormancy fix it named two `unenforced` checks, one of which was a false
    positive; after, exactly one, and it is real.
  - Confirmed both newly-wired verifiers are hermetic (temp dirs and local git
    inits only; `_ROOT` from `__file__`) and that `ci.yml` checks out with
    `fetch-depth: 0`, so the local green is not an artifact of local state.

- **Test Completeness Ledger:** every behavior below is `tested` or carries a
  closed-vocabulary `reason_code`. Zero testable-but-untested.

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Both surface verifiers run in the required CI job | tested | `test_surface_verifier_runs_in_the_required_job` (2 params) |
  | 2 | Neither is loosened by `continue-on-error` / `\|\| true` | tested | `test_surface_verifier_is_a_hard_gate`; mutation-probed |
  | 3 | A gate step naming a missing script fails | tested | `test_gated_script_exists` |
  | 4 | A NEW `verify_*_surface.py` born unwired fails the build | tested | `test_every_surface_verifier_is_wired_to_some_workflow`; probed with a real orphan file |
  | 5 | Only executable `run:` lines count as wiring (not comments) | tested | `test_a_verifier_named_only_in_a_comment_is_still_an_orphan` |
  | 6 | The loose-gate guard classifies `(gate)` steps as gates | tested | `test_the_gate_guard_can_see_the_surface_gates`; probed by removing the keyword |
  | 7 | The security gate prints a labelled verdict, not a bare count | tested | `test_verdict_is_labelled_not_a_bare_count` |
  | 8 | Every severity is counted across BOTH scan outputs | tested | `test_every_severity_is_counted_across_both_scan_outputs` + 3-fixture behavioral probe |
  | 9 | The breakdown reaches the job summary | tested | `test_breakdown_reaches_the_job_summary` |
  | 10 | Reporting can never fail the gate (`GITHUB_STEP_SUMMARY` unset) | tested | `test_reporting_cannot_fail_the_gate` + A5.8 probe (19 tests) |
  | 11 | A PASS with open highs is annotated | tested | `test_passing_with_open_high_findings_is_said_out_loud` |
  | 12 | The gate still blocks on critical only | tested | `test_the_gate_itself_still_blocks_on_critical_only` + behavioral probe |
  | 13 | Drift is reported in both directions, and advisory suppresses | tested | `test_a_check_nobody_requires_is_unenforced`, `..._is_phantom`, `test_both_directions_are_reported_together`, `test_advisory_contexts_are_not_drift` |
  | 14 | Blank/whitespace names create no drift | tested | `test_whitespace_and_blanks_do_not_create_phantom_drift` |
  | 15 | The dedup key is stable and divergence-specific | tested | `test_dedup_key_is_stable_and_divergence_specific` |
  | 16 | Enumeration covers every workflow, not adopt's five | tested | `test_enumeration_covers_every_workflow_not_just_adopts_five` |
  | 17 | A workflow that cannot run on a PR is NOT derived | tested | `test_a_workflow_that_cannot_run_on_a_pr_is_not_derived`, `test_the_monorepos_manual_launch_gate_is_not_reported_as_drift` |
  | 18 | One unparseable workflow does not sink enumeration | tested | `test_enumeration_skips_an_unparseable_workflow` |
  | 19 | Empty derived never reads as in-sync | tested | `test_empty_derived_never_reads_as_in_sync`, `test_enumeration_survives_a_repo_with_no_workflows` |
  | 20 | `gh` missing / hanging is a controlled error, not a traceback | tested | `test_missing_gh_binary_is_a_controlled_error`, `test_gh_timeout_is_a_controlled_error`, `test_missing_gh_exits_2_without_a_traceback` |
  | 21 | HTTP status is recovered so 404 ≠ 403 | tested | `test_http_status_is_carried_off_stderr`, `test_a_failure_with_no_http_code_carries_no_status` |
  | 22 | A repo requiring nothing reads as empty, not unreadable | tested | `test_a_repo_that_requires_nothing_reads_as_empty_not_unreadable`, `test_empty_configured_set_makes_every_check_unenforced` |
  | 23 | Contexts come from rulesets AND classic protection, unioned | tested | `test_contexts_come_from_rulesets`, `test_classic_branch_protection_is_still_read`, `test_both_mechanisms_union` |
  | 24 | Neither source readable raises; one readable is enough | tested | `test_neither_mechanism_readable_raises`, `test_one_mechanism_unreadable_does_not_sink_the_other`, `test_unparseable_response_is_not_read_as_empty` |
  | 25 | The policy is read for the NAMED branch | tested | `test_the_policy_is_read_for_the_named_branch` |
  | 26 | An unreachable repo exits 2 before any policy lookup | tested | `test_unreachable_repo_exits_2_before_any_policy_lookup` |
  | 27 | In-sync exits 0 and files nothing; drift files exactly one item | tested | `test_in_sync_repo_exits_0_and_files_nothing`, `test_drift_files_one_item_keyed_on_repo_and_branch` |
  | 28 | The posted-status registry rejects a key no consumer visits | tested | `test_posted_status_contexts_name_known_workflows`; probed with typo'd keys |
  | 29 | A non-GitHub or malformed `origin` is refused, not guessed at | tested | `test_check_required_checks_io.py::test_a_non_github_remote_is_refused_not_guessed_at` (3 params) + `test_github_remotes_resolve_to_owner_name` (4 params) |
  | 30 | The live GitHub ruleset read returns this repo's real must-pass set | untestable | `reason_code: requires-external-nondeterministic-service` — the real API cannot be a hermetic test; exercised live at every stage instead, and every decision made on its response is covered by rows 22–27 |

- **Confidence-pattern check:**
  - *Asymptote (depth):* the last two review rounds returned findings of falling
    severity in the same region (producer I/O), and round 2's remaining items were
    two mediums and two lows. Round 1 changed the design; round 2 changed four
    lines and four tests. That is a converging, not a widening, surface.
  - *Coverage (breadth):* every claim in this diff has a test that was watched to
    fail. The one uncovered edge is declared in row 29 rather than left implicit.
  - *Integration composition:* `cross_component` does not fire (verified against
    `risk_detectors`), so no composition behavior is owed.

## Out of scope

- The webui (its own repo, its own PR — card `trg-9e6c0b66`).
- `shared/templates/github-actions/security.yml.template`. The adopt-shipped gate
  is a different, SARIF-based body with its own fixtures; giving it the same
  labelled verdict is a real follow-up, not a like-for-like edit.
- Requiring the one `unenforced` check: a ruleset change at the host, the
  operator's call, not a code change.
- Reusable-workflow (`workflow_call`) derivation. None exists in this repo; the
  external review's suggestion to label such cases "unverifiable" is noted rather
  than built (YAGNI).

## Follow-ups for the operator (carried over from the handover, still live)

1. **The one unenforced check.** `Prepare review request` runs on every PR and
   holds nothing up. **Before requiring any check, confirm it runs on every PR** —
   requiring one that does not blocks every PR forever, waiting on a result that
   never arrives. For `Prepare review request` that is confirmed. (`Empirical
   calibration (real OSS repos)` is NO LONGER reported: it is `workflow_dispatch`-
   only and the producer now excludes it correctly.)
2. **WebUI:** card `trg-9e6c0b66` in the webui repo — port the two-stage review and
   run the same check comparison. Design, rejected alternatives and PR A's external
   review findings are in shipwright#437.
3. **`ADVISORY_CONTEXTS` stays empty.** Do not pre-fill it. Pre-emptive silencing
   is exactly how a gate becomes decorative — the thing this card is about.
