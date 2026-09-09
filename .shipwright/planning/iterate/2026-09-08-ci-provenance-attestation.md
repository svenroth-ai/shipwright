# Iterate Spec: CI Provenance Attestation for Promotion Evidence

- **run_id:** iterate-2026-09-08-ci-provenance-attestation
- **Campaign:** req3-04c-ac-identity-wave2, sub-iterate p3.4c
- **Status:** draft
- **Affected FRs:** FR-01.11 (AC-identity / evidence-ledger area, same FR as P3.1-P3.4)
- **Source sub-iterate spec:** `.shipwright/planning/iterate/campaigns/req3-04c-ac-identity-wave2/sub-iterates/p3.4c-ci-provenance-for-promotion-evidence.md`

## Problem

P3.5 (`promote-layers-per-fr`) needs to know, for a given commit, whether
that commit's `test-traceability.json` manifest was verified by a real
GitHub Actions CI run — not merely self-declared in a committed file. No such
fact currently exists anywhere: `ci_manifest_drift_check.py` already runs in
`ci.yml` on every push/PR and computes the answer (no drift = the committed
manifest matches what CI itself regenerated from real test output), but the
verdict is discarded at the end of the job. P3.5 spent ~8.5h and 12 external
review rounds re-discovering this same gap from different angles.

## Design history — three rounds, converging on a smaller design

**Round 1 (operator decision 2026-09-08):** artifact-based — CI uploads a
signed-by-nothing-but-GitHub-itself JSON record as a build artifact; a
consumer downloads and compares it. Rejected the heavier alternative
(GitHub native Sigstore/OIDC build attestations) as disproportionate for the
required property — see `## Alternative approaches (rejected)`.

**Round 2 (Internal Plan Review, opus-plan-reviewer):** found the artifact
design's digest could never reproduce (raw-byte hash vs. the drift check's
own structural comparison), the unforgeability claim had a real hole (a PR's
own `ci.yml` runs before review), and the predicate module's planned
location was the exact ADR-044/045 import trap this repo has already burned
itself on. All fixed in the design that then went to external review.

**Round 3 (External LLM Review, plan-mode then architecture-mode) — this is
the FINAL design.** Plan-mode review (both `glm` and `openai`, verdict
`revise`) found the artifact design still conflated "GitHub has no record"
with "the check itself failed" (breaking the CLI's exit-code contract), plus
a `default_branch()` cwd-dependency bug and other fixable issues.
Architecture-mode review (`openai` approve, `glm` revise) then found
something more fundamental: **the entire artifact/digest layer is redundant.**
A workflow run's `head_sha` already pins it to one exact commit, and a commit
has exactly one committed manifest (commits are content-addressed — the
manifest at commit X cannot differ across two askings). So "was the manifest
at commit X verified" reduces to "did a qualifying CI run at head_sha=X
report the drift check as clean" — a fact GitHub already records as a
**step conclusion**, queryable via the Jobs API, with no new artifact, no
digest function, and no upload step needed at all.

**Adopted.** This is a strict simplification (same unforgeability property,
same trust-boundary filter, far less new surface) and directly answers the
proportionality concern raised with the operator before Round 1 — see
`## Architecture Review` below for the full disposition.

## Design (final)

**CI side (`ci.yml`) — one new step, and it cannot fail.** The existing
"Check traceability manifest against a fresh regeneration" step gets
`id: manifest_drift` and one added line, `echo "code=$code" >>
"$GITHUB_OUTPUT"`, placed immediately after the existing `code=$?` capture —
on every exit path, including the `exit "$code"` branch. Its own body,
branching, and exit-code contract (0/1/2) are otherwise **unchanged**. A new
step, `if: steps.manifest_drift.outputs.code == '0'`, `run: echo "manifest
verified clean"` — a pure affirmation with no fallible logic, so it needs no
`continue-on-error` (it cannot fail; when the `if:` is false it is recorded
as `skipped`, not `failure`). Its own step **conclusion** is now an
externally-queryable, unambiguous signal: `success` if and only if the drift
check found no drift; `skipped` for drift-found (1) or hard-error (2); and
(for a hard error, which is NOT wrapped in `continue-on-error` and therefore
still fails the job exactly as today) the job stops before this step is
reached at all — preserving `ci_manifest_drift_check.py`'s documented "the
caller must never swallow exit 2" contract byte-for-byte.

**Consumer side — a predicate, no downloads.** `resolve_ci_verification()`
reads NOTHING from the local tree; the CLI convenience wrapper's only local
read is `git -C <project_root> rev-parse` for input validation (see below),
never a manifest file:
1. `owner, repo = github_api.owner_repo(project_root)`; the module's own
   literal `gh api repos/{owner}/{repo}` call resolves the default branch
   (NOT `github_api.default_branch()`, which is cwd-dependent — see
   `## Internal Plan Review` finding 4 / External Review finding 4, same
   bug class `owner_repo()` was already fixed to avoid).
2. `gh api repos/{owner}/{repo}/actions/workflows/ci.yml/runs?head_sha=
   {commit}&status=success&per_page=100` (repo interpolated literally, never
   `gh`'s cwd-based placeholder). `per_page=100` (the API maximum) is a
   documented, deliberate bound, not full pagination — see
   `## Known limitations`.
3. **Trust boundary:** keep only runs whose OWN API-reported `event ==
   "push"` AND `head_branch == <default branch>` AND `conclusion ==
   "success"`. Read from GitHub's run object, never from anything
   self-reported. This is what delivers the unforgeability property.
4. For EVERY qualifying run (not just the newest — a later job-level failure
   or an in-flight rerun must not hide an earlier genuine pass): `gh api
   repos/{owner}/{repo}/actions/runs/{run_id}/jobs`, find the step named
   `PROVENANCE_STEP_NAME` (a module-level constant — the ONE place the name
   is spelled, `ci.yml`'s step name is pinned against it by test), and check
   `conclusion == "success"`.
5. Any qualifying run's step conclusion is `success` → **verified**. No
   qualifying run's step conclusion is `success`, but at least one
   qualifying run exists (drift check ran and reported drift, or the
   provenance step's own conclusion could not be read as a plain `success`)
   → **not_verified**. No qualifying run at all → **no_record**. The query
   itself could not complete or was DETECTABLY TRUNCATED (`gh`/`git`
   missing, timeout, malformed response, an invalid `commit`/`workflow_file`,
   or `total_count` exceeding the fetched runs page — Stage-3 doubt review:
   an undetected truncation is newest-first, so the truncated tail is the
   OLDEST runs, exactly where an older confirming run would live, and would
   otherwise misreport as `not_verified`) → **error** — distinct from
   `no_record`, because "GitHub definitively has no matching run" and "the
   check could not be performed" are different facts (External Review, both
   `glm` and `openai`, independently: the first two design rounds conflated
   these, which broke the CLI's own exit-code contract). **`commit` must be
   exactly 40 hex chars** (Stage-3 doubt review: GitHub's `head_sha` filter
   is an exact match, so an accepted-but-unexpanded 7-39 char abbreviation
   would silently under-match into a false `no_record`; the predicate itself
   enforces this, not only the CLI wrapper that expands shorter refs via
   `git rev-parse` before calling it).

**Scope of `verified` — structural only.** `ci_manifest_drift_check.py`'s
exit code (what the new step's `if:` reads) is computed from
`compare_traceability_manifest.structural_diff()`, which strips
`tests`/`coverage`/`acs` from every requirement before comparing —
`execution_report()`, which covers exactly those fields, is report-only and
never gates (a standing, deliberate advisory-only decision this predicate
does not and must not change; P3.4c's own mandate forbids making the drift
check blocking). So `verified` means "a real CI run confirmed the committed
manifest's FR/AC/test-ID structure was not fabricated or hand-edited" — it
does **not** independently confirm the recorded test pass/fail status or
coverage numbers are accurate (Stage-3 doubt review, high severity: those
are exactly the fields P3.5's per-FR promotion reads). Disclosed, not fixed
here — closing that gap would mean either making the drift check blocking
(explicitly forbidden by this sub-iterate's mandate) or a separate,
larger mechanism; a future P3.5 resumption must read this section before
treating `verified` as proof of anything execution-tier.

**Unforgeability property.** Only a `push`-triggered, `conclusion=success`
run on the repository's default branch is ever accepted — checked against
the API's OWN run object (`event`, `head_branch`, `conclusion`), never
anything self-reported. A `push` run executes the WORKFLOW FILE OF THE
COMMIT BEING PUSHED, not an earlier version (Stage-3 doubt review: the
original wording — "a run of the `ci.yml` that already existed on `main`
before the commit landed" — was factually wrong about how GitHub Actions
resolves a push-triggered workflow; corrected here). A `pull_request`-triggered
run (whose OWN, possibly attacker-modified `ci.yml` runs before any human
review) is never accepted, however its step conclusions read — but a
malicious `ci.yml` edit that itself reaches `main` via a reviewed merge
WOULD forge every `verified` result thereafter, which is why the real
barrier is the review gate on that merge, not "the workflow predates the
commit." **Who would have to be compromised to fake a `verified` result:**
someone would need to get a commit (a `ci.yml` change or otherwise) onto the
default branch — gated by this repo's `touches_ci_supplychain` mandatory-review
**POSTURE, a Shipwright-side agent convention, not a GitHub branch-protection
technical control** (Stage-3 doubt review: the original sentence read as if
this were mechanically enforced; it is not) — or control of GitHub's own
Actions/API infrastructure, or the ability to repoint the CALLER's own git
checkout's `origin` remote to a different, attacker-controlled repository
(`owner_repo()` reads `git remote get-url origin`, local and mutable), or
control of the `gh`/`git` binary or environment this process resolves (a
repo-wide trust assumption every script that shells out to `gh`/`git`
already makes — disclosed, not fixed here; hardening it is a repo-wide
project out of this sub-iterate's scope). This predicate is trustworthy only
when run from a checkout and environment the caller itself controls (true
for every real caller — a freshly-fetched CI or iterate worktree). A
tree-local *content* write alone is insufficient.

**Module placement — flat, not under `lib/`.** `github_api.py` is
importable only with `shared/scripts` flat on `sys.path` (bare `from
security_findings import ...` inside it); no module under `shared/scripts/
lib/` imports it today, and this repo has already burned itself on exactly
this ADR-044/045 collision class multiple times. `shared/scripts/
ci_provenance.py` lives FLAT, a peer of `github_api.py`, importing it the
same way `github_workflow_api.py` already does.

## Known limitations

- **Push-only.** A commit that only ever ran in a `pull_request`-triggered
  CI run never gets a `verified` result for that exact SHA. Intentional — a
  direct restatement of the unforgeability property, and matches P3.5's real
  question ("was the commit actually on `main` verified").
- **`per_page=100`, not full pagination.** A single commit accumulating over
  100 workflow runs is not a realistic shape for this repo's trigger set.
  If it ever changes, the fix is adding `--paginate` to one call site.
- **Not a durable ledger.** GitHub's own run/job history is subject to
  retention limits outside this design's control; `resolve_ci_verification`
  is a promotion-time check, not permanent evidence storage. P3.5 is its
  only intended consumer (Architecture Review, `glm`, low severity —
  disclosed, not fixed: stating the consumption window here IS the fix).
- **The jobs query reads only the latest run ATTEMPT.** GitHub's Jobs API
  defaults to `filter=latest`; if a run is manually re-run after already
  qualifying, and the rerun's own provenance step does not confirm (e.g. a
  flaky regeneration), the earlier attempt's genuine confirmation is not
  consulted — the AC9 "an in-flight rerun must not hide an earlier genuine
  pass" reasoning is applied across RUNS, not across ATTEMPTS within one run
  (Stage-3 doubt review, medium — disclosed, not fixed: requires querying
  `/attempts/{n}/jobs` per candidate, more surface than this predicate's
  size justifies for a scenario that requires someone to manually re-run an
  already-successful run).
- **A step or default-branch rename retroactively un-verifies history.**
  `PROVENANCE_STEP_NAME` and `default_branch` are both compared against
  GitHub's immutable historical run records; a rename changes what today's
  code looks for, but not what past runs recorded, so every commit verified
  before the rename becomes `not_verified`/`no_record` even though nothing
  about those commits changed (Stage-3 doubt review, low). Treat both as
  effectively append-only in practice.
- **`verified` covers structural agreement only, not execution-tier fields**
  (test pass/fail status, coverage) — see `## Design (final)`'s "Scope of
  `verified`" paragraph above (Stage-3 doubt review, high).
- **This predicate trusts the ambient `gh`/`git` resolution and environment**
  of the process running it, like every other script in this repo that
  shells out to them — see `## Design (final)`'s unforgeability paragraph
  above (Stage-3 doubt review, medium).

## Alternative approaches (rejected)

- **GitHub native Artifact Attestations** (Sigstore/OIDC build provenance).
  Rejected in Round 1: new workflow permissions, a `gh attestation verify`
  dependency with no precedent in this codebase, materially more surface
  than needed for the same property. Reconfirmed in Round 3 — the
  step-conclusion design is smaller still.
- **A build artifact carrying a structural-digest record** (this iterate's
  own Round 1/2 design). Superseded in Round 3: redundant once `head_sha`
  is accepted as already pinning the commit-to-manifest binding — see
  `## Design history`.

## Files to create/modify

1. `.github/workflows/ci.yml` (edit) — `id: manifest_drift` + one output
   line on the existing step (unchanged body/branching otherwise); one new
   step (`if: steps.manifest_drift.outputs.code == '0'`, no fallible logic).
2. `shared/scripts/ci_provenance.py` (new, **flat**, peer of `github_api.py`
   — NOT under `lib/`) — `PROVENANCE_STEP_NAME` constant,
   `resolve_ci_verification(commit, *, project_root, workflow_file="ci.yml")
   -> CIVerification(status, detail, run_id=None)`, `status` in `{verified,
   not_verified, no_record, error}`. Validates `commit` against
   `^[0-9a-f]{40}$` (exactly 40 — GitHub's `head_sha` filter is an exact
   match; Stage-3 doubt review) and `workflow_file` against a bare
   `*.yml`/`*.yaml` filename before any call. Own small `_gh_api(path, *,
   cwd)` helper in this file — does not extend or grow `github_api.py`/
   `security_findings.py` (both at/near their bloat ceiling).
3. `shared/scripts/tools/ci_provenance_check.py` (new) — CLI: `verify
   --commit <ref> [--project-root .]`. Expands `--commit` to a full 40-char
   SHA via `git -C <project_root> rev-parse --verify` (accepts anything git
   can resolve — a full/abbreviated SHA, `HEAD`, a tag) before calling the
   predicate; a ref git cannot resolve is `error`, exit 2. Prints one JSON
   line, maps status → exit code (0 verified / 3 not_verified / 4 no_record
   / 2 error).
4. Tests: `shared/tests/test_ci_provenance.py` (predicate unit tests via the
   `gh`-subprocess seam, monkeypatched at the module-object level per
   ADR-045 convention), `shared/scripts/tools/tests/
   test_ci_provenance_check.py` (CLI contract, including one real-subprocess
   invocation — Internal Review's "mask" warning about `shared/tests`'s
   conftest applies here too), a CI-YAML-shape test pinning the new step's
   `if:`, the output-line placement, and the step-name match against
   `PROVENANCE_STEP_NAME`.
5. `.shipwright/agent_docs/decision_log.md` — new ADR (written as a
   run_id-keyed decision-drop at F3, not appended directly from the iterate)
   naming the unforgeability property in one sentence (AC7) and the Round-3
   simplification.

## Acceptance Criteria (assertion-shaped)

- **AC2-agent:** `resolve_ci_verification(commit, project_root=...)` returns
  `status="verified"` when a mocked qualifying run's (push, default branch,
  conclusion=success) Jobs-API response shows `PROVENANCE_STEP_NAME` with
  `conclusion="success"`; `status="not_verified"` when a qualifying run
  exists but no qualifying run's step conclusion is `"success"`;
  `status="no_record"` when no qualifying run exists at all; `status=
  "error"` when the query cannot complete (mocked `gh` failure, or an
  invalid `--commit`) — four distinct, never-conflated outcomes.
- **AC8-agent (the actual forgery test):** `gh` mocked to return ONE run for
  `head_sha=commit` whose Jobs-API response shows the provenance step as
  `"success"`, but whose run metadata has `event="pull_request"` (or
  `head_branch` ≠ default branch, or `conclusion="failure"`) —
  `resolve_ci_verification()` returns `no_record`, never `verified`.
- **AC9-agent (multi-run search):** `gh` mocked to return TWO qualifying
  runs for the same `head_sha` — the newest's Jobs-API response has the
  provenance step `"skipped"` (drift found on a later rerun), the older's
  has it `"success"` — `resolve_ci_verification()` returns `verified`,
  proving the search does not stop at the first qualifying run.
- **AC4-agent:** `ci.yml`'s new step has `if:` gated on
  `steps.manifest_drift.outputs.code == '0'`; a YAML-shape test asserts the
  literal condition string (not `always()`, not unconditional), that the
  `echo ... >> "$GITHUB_OUTPUT"` line exists on every exit path of the
  drift-check step, and that the new step's `name:` literal matches
  `ci_provenance.PROVENANCE_STEP_NAME` imported from the Python source.
- **AC5-agent:** `ci_manifest_drift_check.py`'s own exit-code contract
  (0/1/2) and its existing branching are unchanged, with exactly one
  narrowly-scoped `echo` line added — a semantic-preservation test, not
  byte-identity. The new step has no fallible logic (a bare `echo`), so it
  needs no `continue-on-error` and genuinely adds no new failure condition —
  the ORIGINAL Round-1 claim, now actually true because the design shrank.
- **AC6-agent:** a commit with no qualifying run at all — `status=
  "no_record"` — is reported by the CLI with exit code 4, never a crash,
  never `status="verified"`. An invalid `--commit` or a `gh`/`git` transport
  failure is reported as `status="error"`, exit code 2 — distinct from
  `no_record`.
- **AC7 (doc-only, no runtime assertion):** the ADR states, in one sentence,
  who would have to be compromised to fake a `verified` result. **OPEN as of
  this diff** (External code review, glm/openai, both medium — flagged
  correctly): no decision-drop exists yet under this diff's changed paths.
  By design, not an oversight — the spec's own "Files to create/modify" item
  5 states the ADR is "written as a run_id-keyed decision-drop at F3, not
  appended directly from the iterate." This note is the tracked deferral
  glm asked for: AC7 is NOT satisfied until F3 runs and the decision-drop
  lands with the settled sentence from `## Design (final)`'s unforgeability
  paragraph above.

## Verification (medium+)

- **Surface:** none (no `dev_url`, no UI) — CLI + library only.
  `surface_verification.justification`: "pure CLI/library predicate, no web
  surface; verified via unit + CLI-contract tests against a mocked `gh`."
- **Runner (two invocations — one root per pytest process, CLAUDE.md):**
  `uv run pytest shared/tests/test_ci_provenance.py
  shared/tests/test_ci_provenance_hardening.py
  shared/tests/test_ci_provenance_gh_api.py
  shared/tests/test_ci_yml_provenance_step_shape.py -v` (one invocation, one
  root — `shared/tests`; the `test_ci_provenance*`/`test_ci_yml_*` split
  across four files is a 300-line-guideline split of the SAME test root, not
  separate roots, so they run together)
  and separately
  `uv run pytest shared/scripts/tools/tests/test_ci_provenance_check.py -v`
  (External code review, glm: the original two-invocation list predated the
  guideline-driven splits and omitted three of the five resulting files,
  which would have let the repo's actual verification runner skip the AC4/AC5
  shape assertions entirely).

## Confidence Calibration
- **Boundaries touched:** `.github/workflows/ci.yml` (CI trust boundary,
  `touches_ci_supplychain`); a new GitHub-API-facing predicate (network
  boundary, mocked in tests, never called against the real API in this
  repo's own test suite). `touches_io_boundary` recomputed **False** from the
  diff (no serialized local-file format is produced or consumed — the whole
  point of this predicate is that it never reads/writes a local file), so
  the 8-category boundary-probe checklist does not apply; the phase itself
  still runs (mandatory at medium+ regardless).
- **Empirical probes run (asymptote heuristic):** the five-stage review
  cascade above (Internal Plan Review → External plan review → Architecture
  Review → Stage 1/2/3 internal cascade → External code review) already ran
  eight probe/fix rounds and found a real, fixed defect in nearly every one —
  the strongest form of "probe found something" this heuristic asks for. Two
  additional, fresh probes were run at Step 7.5 itself, specifically to
  reach the "last probe found nothing" exhaustion condition on a dimension
  the review cascade had not directly exercised (the raw `_gh_api`
  transport-failure boundary):
  1. **Probe: does a genuinely missing `gh` binary degrade gracefully?**
     (`FileNotFoundError`, an `OSError` subclass, is distinct from the
     mocked non-zero-`returncode`/bad-JSON paths already tested — none of
     those exercise the actual `except (OSError, ...)` branch with a real
     exception type Python raises for a missing executable.) **Result: no
     finding** — `_gh_api` returns `None` as designed. Locked in as a
     permanent test, `test_gh_api_returns_none_when_gh_binary_is_missing`.
  2. **Probe: is the truncation-detection boundary (`total_count` exactly
     equal to the fetched page length) off-by-one?** **Result: no
     finding** — `total_count > len(...)` correctly treats the equal case as
     "not truncated," verified by direct execution (not just by reading the
     comparison operator).
  Per the decision rule (`confidence-anti-patterns.md`): condition 1 (last
  probe found nothing) — met, both probes above. Condition 2 (all applicable
  `boundary-probes.md` categories run) — n/a, `touches_io_boundary` is
  False. Condition 3 (drift-protection for N>1 consumers) — n/a, single
  intended consumer (P3.5) per `## Known limitations`. Condition 4 (no
  yes-then-bug this run) — met for these two Step-7.5 probes specifically;
  the review cascade's own many yes-then-bug cycles are already closed
  (fixed or disclosed) above, which is what makes this phase's remaining
  surface small enough for two probes to reach exhaustion.
- **Test Completeness Ledger:** every testable behavior introduced by this
  diff is `tested`; none are `untestable`.
  | Behavior | AC | Disposition | Evidence |
  |---|---|---|---|
  | verified: qualifying run confirms | AC2 | tested | `test_verified_when_qualifying_run_confirms_clean_manifest` |
  | not_verified: qualifying run never confirms | AC2 | tested | `test_not_verified_when_qualifying_run_never_confirms` |
  | not_verified: step absent from every job | AC2 | tested | `test_not_verified_when_provenance_step_is_absent_from_run` |
  | no_record: no run matches head_sha | AC2 | tested | `test_no_record_when_no_run_matches_head_sha` |
  | no_record: only pull_request runs exist (forgery) | AC8 | tested | `test_no_record_when_only_pull_request_runs_exist` |
  | no_record: run on a non-default branch | AC8 | tested | `test_no_record_when_run_is_on_a_non_default_branch` |
  | no_record: run conclusion not success | AC8 | tested | `test_no_record_when_run_conclusion_is_not_success` |
  | no_record: local file forgery never consulted | AC3 | tested | `test_local_file_forgery_is_never_consulted` |
  | error: invalid commit shape | AC2/AC6 | tested | `test_error_on_invalid_commit_shape` |
  | error: abbreviated (non-40-char) commit | AC2/AC6 | tested | `test_error_on_abbreviated_commit_never_falls_through_to_no_record` |
  | error: uppercase commit normalized, not rejected | — | tested | `test_uppercase_commit_is_accepted_via_lowercase_normalization` |
  | error: invalid workflow_file | — | tested | `test_error_on_invalid_workflow_file` |
  | error: owner/repo unresolvable | AC2 | tested | `test_error_when_owner_repo_unresolvable` |
  | error: gh transport fails (runs query) | AC2/AC6 | tested | `test_error_when_gh_transport_fails` |
  | error: jobs query fails for a qualifying run | AC2 | tested | `test_error_when_jobs_query_fails_for_a_qualifying_run` |
  | error: jobs response has malformed step shape | AC2 | tested | `test_error_when_jobs_response_has_malformed_step_shape` |
  | error: runs response truncated (total_count) | AC2 | tested | `test_error_when_runs_response_is_truncated` |
  | error: gh binary missing (FileNotFoundError) | AC2 | tested | `test_gh_api_returns_none_when_gh_binary_is_missing` |
  | verified: search continues past a non-confirming newer run | AC9 | tested | `test_verified_searches_past_a_non_confirming_newer_run` |
  | runs query bound to the exact commit | AC9 | tested | `test_runs_query_is_bound_to_this_exact_commit` |
  | verified: confirming step in a matrixed run's second job | — | tested | `test_verified_when_confirming_step_is_in_a_second_job_of_a_matrixed_run` |
  | malformed job doesn't hide a confirming job | — | tested | `test_malformed_job_does_not_hide_a_confirming_job` |
  | `_gh_api` argv/cwd/timeout construction | — | tested | `test_gh_api_real_subprocess_argv_and_cwd` |
  | `_gh_api` non-zero exit / bad JSON | — | tested | `test_gh_api_returns_none_on_nonzero_exit_and_bad_json` |
  | `_gh_api` cwd pinned to project_root, not process cwd | — | tested | `test_gh_api_passes_project_root_as_cwd_not_process_cwd` |
  | CLI: status→exit-code map (0/3/4/2) | AC6 | tested | `test_verified_maps_to_exit_0` / `_not_verified_maps_to_exit_3` / `_no_record_maps_to_exit_4` / `_error_maps_to_exit_2_distinct_from_no_record` |
  | CLI: real subprocess starts cleanly, invalid ref → exit 2 | AC6 | tested | `test_real_subprocess_invocation_starts_cleanly` |
  | CLI: `git rev-parse` expands `HEAD` to a full SHA (real git) | — | tested | `test_resolve_full_sha_expands_head_via_real_git` |
  | CLI: unresolvable ref → `None` | — | tested | `test_resolve_full_sha_returns_none_for_unresolvable_ref` |
  | CLI: unresolvable `--commit` → exit 2 without calling the predicate | — | tested | `test_unresolvable_commit_maps_to_cli_exit_2` |
  | ci.yml: `$GITHUB_OUTPUT` line precedes every exit path | AC5 | tested | `test_drift_check_step_emits_code_output_before_any_exit` |
  | ci.yml: `set +e` precedes the capture precedes the output line | AC5 | tested | `test_drift_check_set_plus_e_precedes_the_capture_and_output_line` |
  | ci.yml: provenance step `if:` matches, name matches the constant | AC4 | tested | `test_provenance_step_name_matches_the_python_constant` |
  | ci.yml: provenance step has no fallible logic (exact body) | AC5 | tested | `test_provenance_step_has_no_fallible_logic` |
  | ci.yml: drift-check 0/1/2 contract otherwise unchanged | AC5 | tested | `test_drift_check_exit_code_contract_unchanged` |
- **Confidence-pattern check:** no "are you confident?" yes-then-bug cycle
  occurred at Step 7.5 itself (both fresh probes found nothing on the first
  try) — but this is read as the SIGNAL that the earlier five-stage cascade
  already did the work this phase exists to force, not as evidence this
  phase was unnecessary. Discipline followed: every reviewer-found defect
  across all five stages was fixed or explicitly disclosed with reasoning in
  this spec (never silently dropped), and the two Step-7.5 probes targeted a
  genuinely under-exercised dimension rather than re-confirming already-
  covered ground.

## CI-supplychain acknowledgment

This iterate touches `.github/workflows/ci.yml`. Per the standing posture
(`ci_manifest_drift_check` stays advisory — AC4's design note,
iterate-2026-08-26-r1b-ci-manifest-regen-gate, reconfirmed sibling-repo
#449): `ci_manifest_drift_check.py`'s own step, body, and exit-code contract
are unchanged except one narrowly-scoped output-emission line. The one new
step is a bare `echo` with no fallible logic — it adds no new failure
condition to `ci.yml` at all (this claim, made and then retracted as
imprecise during Round 1/2 of this design, is now literally true because the
final design has no artifact-upload or writer-script step left to fail).
Recorded via `record_ci_supplychain_ack.py` before F11.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Round-1 (artifact-based) trust architecture was right in
  shape but had three load-bearing defects that would have shipped green
  (every test mocked `gh`): the digest could never reproduce between CI and
  consumer, the unforgeability claim had a real hole (a PR's own `ci.yml`
  runs before review), and the predicate module's planned location was the
  exact ADR-044/045 import trap this repo has already burned itself on. Plus
  an illegal multi-root pytest command in the spec's own verification
  runner. All fixed in Round 2; the artifact/digest layer itself was later
  found unnecessary by Architecture Review (Round 3) and removed — see
  `## Design history`.
- **Findings:** 17 total — 6 high, 6 medium, 4 low, 1 accept-as-is. Full
  detail in the review record (`record_review_pass.py show`,
  `plan_internal`... — payload is metadata-only per protocol; findings text
  lived here in Round-2 history, now superseded by the Round-3 design which
  moots several of them (digest reproducibility, artifact retention
  conflation, artifact re-run 409, artifact-name single-source-of-truth all
  no longer apply — there is no artifact).
- **Known limitations:** superseded — see `## Known limitations` above
  (current, Round-3 design).
- **Status:** 15 fixed in Round 2, 2 disclosed; several subsequently mooted
  by the Round-3 simplification.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-08-ci-provenance-attestation/architecture_brief.md`
- **Verdicts:** glm=revise · openai=approve
- **Smallest thing that would do (per reviewers):** `glm` — read the drift
  check's own step conclusion via the GitHub Actions Jobs API instead of
  publishing a new artifact; drop the writer script, the digest function,
  the upload step, and the artifact-name cross-file contract entirely.
  `openai` — approved the artifact design as proposed, no findings.
- **Findings:** `glm` (high, simpler-alternative): the artifact channel is a
  redundant binding — `head_sha` already pins run→commit→manifest, so a
  digest match adds nothing an exact-commit query didn't already have.
  `glm` (medium, proportionality): four new files + two workflow steps + an
  ADR + a cross-file name contract is a large permanent surface for one
  boolean about a commit that GitHub's own run history already encodes.
  `glm` (low, existence): the evidence is non-durable regardless of shape
  (both artifacts and run/job history expire); name P3.5 as the only
  consumer so nobody later treats `verified` as a permanent record.
  `openai`: no findings, approved as proposed.
- **Reconciliation:** Adopted `glm`'s simplification in full — see
  `## Design history` and `## Design (final)` above. This is not a rejection
  of `openai`'s approval (the Round-2 artifact design WAS sound and
  sufficient); it is accepting a strictly smaller design that delivers the
  identical property, which is a strict improvement, not a disagreement to
  reconcile away. `openai`'s low-severity "existence" framing is folded into
  `## Known limitations`.

## Code Review (Stage 1 spec-reviewer → Stage 2 code-reviewer)

- **Stage 1 (spec-compliance, HARD-GATE) — round 1: REJECT.** `_provenance_step_conclusion`
  collapsed "the jobs-API query itself failed" and "the step is absent" into
  the same bare `None`, so a transient `gh` failure on a qualifying run fell
  through to `not_verified` (a definite negative) instead of `error` — the
  exact four-outcome conflation this design exists to prevent, just one level
  deeper than the bug Internal Plan Review already caught once. **Fixed:**
  added a `_JOBS_QUERY_FAILED` sentinel, checked before the `"success"`
  comparison; added a regression test
  (`test_error_when_jobs_query_fails_for_a_qualifying_run`). Also corrected a
  stray wrong ADR path in the spec/mini-plan (`.shipwright/planning/adr/…` →
  the real `.shipwright/agent_docs/decision_log.md`). **Round 2: PASS**, no
  remaining citations.
- **Stage 2 (code quality) — PASS with findings, no blocking high.** 12
  findings (2 medium, 10 low). Fixed:
  - *(medium, security)* the unforgeability sentence overclaimed — it did not
    account for the caller's own git checkout `origin` remote being
    repointed to an attacker-controlled repository (`owner_repo()` reads
    local, mutable `git remote get-url`). Amended the one-sentence claim
    (module docstring + `## Design (final)` above) to name this explicitly
    rather than silently trust it.
  - *(medium, correctness)* the spec's own design text promised the CLI's
    "one local read is `git -C <project_root> rev-parse` for input
    validation," but this was never implemented — an abbreviated (7-39 char)
    `--commit` silently resolved to a false `no_record` because GitHub's
    `head_sha` filter requires an exact 40-char match. **Fixed:** implemented
    the promised `git rev-parse --verify --quiet <commit>^{commit}` expansion
    in `ci_provenance_check.py` (the CLI's one local read; the predicate
    itself still reads nothing from the tree), with new tests covering both
    the real-git expansion and the unresolvable-ref → exit 2 path.
  - *(medium, test coverage)* the query string binding `head_sha={commit}`
    was asserted nowhere — a fake dispatch keyed only on path prefix would
    stay green even if that binding were silently dropped. **Fixed:**
    `_install_gh_api` now refuses to answer unless the query string actually
    pins `head_sha` to the commit under test, plus an explicit
    `test_runs_query_is_bound_to_this_exact_commit` test.
  - *(low, correctness — same conflation class as Stage 1)* a malformed
    `run["id"]`, and a jobs-query failure on ANY candidate run (not just the
    newest), both used to short-circuit to a result without exhausting the
    remaining qualifying runs. **Fixed:** both now continue the search
    (mirroring AC9's own "an in-flight rerun must not hide an earlier genuine
    pass" reasoning) and only report `error` after every candidate is
    exhausted with no `verified` match.
  - *(low, correctness)* `_provenance_step_conclusion` returned only the
    first job's matching step, which would misreport if `python-checks` is
    ever run as an OS matrix (this repo's own `*-checks` convention).
    **Fixed:** now scans all jobs, preferring `success` if any job's step
    confirmed it.
  - *(low, security)* `_COMMIT_RE` used a `$`-anchored `match`, which accepts
    a trailing newline. **Fixed:** `fullmatch` on an unanchored pattern.
  - *(low, test coverage)* `_gh_api`'s own subprocess construction (argv,
    cwd, timeout) and its non-zero-exit/bad-JSON failure paths had zero
    direct coverage — every other test monkeypatches past it. **Fixed:**
    added direct tests (now in the split-out `test_ci_provenance_gh_api.py`,
    see below), plus a "step absent" test
    (`test_not_verified_when_provenance_step_is_absent_from_run`) and a
    multi-job matrix test.
  - *(low, readability)* type annotation cleanup, sentinel moved to the
    module's constants block, CLI test helper return-type annotation.
    **Fixed** while already touching these lines.
  - **Disclosed, not fixed** *(low, performance)*: no aggregate wall-clock
    budget across the multi-run search (worst case ~100 candidate runs ×
    30s timeout). Accepted — a realistic commit matches 1-3 runs at most
    (the `head_sha` filter is exact), and this is the same
    documented-limitation shape as `## Known limitations`'s `per_page=100`
    entry, not a live problem worth added complexity for.
  - **Disclosed, not fixed** *(low, test quality)*:
    `test_local_file_forgery_is_never_consulted` cannot fail independently
    of the adjacent no-run-matches test. Accepted as intentional
    documentation of AC3 alongside the stronger, already-present
    `_gh_api`-mocking tests that make "never reads a local file" true by
    construction (there is no file-read call in the module at all).
- **File-count note:** the fix round added two new test files
  (`shared/tests/test_ci_provenance_gh_api.py`, `..._hardening.py` — both
  split out of `test_ci_provenance.py` once it repeatedly crossed the
  300-line guideline) beyond `## Files to create/modify`'s original list —
  same predicate, same test root, no new production surface.

## Doubt Review (Stage 3, mandatory for this unit)

Fresh-context, disprove-biased, per the sub-iterate spec's explicit
requirement (P3.5's own record shows `doubt: not_run`, and this is exactly
the pass that would have caught that unit's original defect early). 10
doubts raised: 2 high, 5 medium, 3 low. The API-side trust filter itself
could not be disproven — no PR-branch-only action was found to produce a
qualifying run object. Every doubt below is either fixed in this diff or
disclosed with reasoning; none required rejecting the design.

- **(high) Scope overclaim — `verified` was read as covering execution-tier
  fields (tests/coverage) it does not cover.** Fixed by precise, honest
  wording, not by code: added the "Scope of `verified` — structural only"
  paragraph to `## Design (final)` and the module docstring, plus a Known
  Limitations bullet. Cannot be fixed by making the drift check blocking —
  that is explicitly forbidden by this sub-iterate's own mandate — so
  correcting the claim IS the fix, same pattern as the External Review
  "existence" disclosure above.
- **(high) The predicate's own commit regex still accepted a 7-39 char
  abbreviation** that GitHub's exact `head_sha` match turns into a false
  `no_record`; Stage 2's fix only reached the CLI wrapper, not the library
  function P3.5 calls directly. **Fixed:** `_COMMIT_RE` now requires exactly
  40 hex chars; the predicate returns `error` for anything shorter. New test:
  `test_error_on_abbreviated_commit_never_falls_through_to_no_record`.
- **(medium) Jobs-endpoint pagination default (30) unhandled** for an
  OS-matrixed run with many jobs. **Fixed:** added `per_page=100` to the
  jobs-endpoint query, matching the runs-endpoint's own documented bound.
- **(medium) Runs-list truncation silently downgraded to a false
  `not_verified`**, with `total_count` ignored. **Fixed:** `_qualifying_runs`
  now compares `total_count` to the fetched page and returns `error` (via
  `None`) on a detected truncation. New test:
  `test_error_when_runs_response_is_truncated`.
- **(medium) The compromise-route enumeration omitted the `gh`/`git` binary
  and its environment**, reachable via a plain working-tree file on Windows.
  **Disclosed, not fixed:** amended the unforgeability sentence and added a
  Known Limitations bullet naming this as a repo-wide trust assumption every
  script that shells out to `gh`/`git` already makes; hardening it
  (resolving and pinning an absolute, non-tree-relative binary path) is a
  repo-wide project out of this sub-iterate's scope, not this module's to
  solve alone.
- **(medium) "A run of the `ci.yml` that already existed on `main` before
  the commit landed" was factually wrong** about how GitHub Actions resolves
  a push-triggered workflow (it runs the pushed commit's OWN `ci.yml`), and
  left ambiguous whether `touches_ci_supplychain`'s mandatory review is a
  GitHub-enforced control or a Shipwright-side posture (it is the latter).
  **Fixed:** rewrote the unforgeability paragraph in both the module
  docstring and `## Design (final)` to state the real mechanism and be
  explicit about posture vs. enforcement.
- **(low) `workflow_file` unvalidated** while `commit` was validated,
  despite both landing in the same request path. **Fixed:** added
  `_WORKFLOW_FILE_RE`, validated alongside `commit`. New test:
  `test_error_on_invalid_workflow_file`.
- **(low) A step-name or default-branch rename retroactively un-verifies
  history**, since GitHub's historical run records are immutable but the
  comparison target is resolved today. **Disclosed, not fixed:** added a
  Known Limitations bullet; both are effectively append-only in practice, and
  no design this size can rewrite GitHub's own history.
- **(low) "Prefer `success` if any job confirms" is the permissive, not
  conservative, reading** under an OS matrix. **Disclosed, not fixed** (this
  IS the intended behavior — structural drift is expected to be
  platform-independent by the comparator's own premise): documented the
  rationale explicitly in `_provenance_step_conclusion`'s docstring instead
  of leaving it implicit.
- **(low) AC7's ADR sentence had not been settled before F3 would copy it.**
  Addressed by this very review round — the sentence is now settled (see the
  unforgeability paragraph above) before the F3 decision-drop is written.
- **Disclosed, not fixed** *(medium, shape only — not independently
  severity-rated by the reviewer)*: the jobs query's default `filter=latest`
  means a manually re-run attempt can hide an earlier attempt's genuine
  confirmation; see the matching Known Limitations bullet. Requires
  per-attempt querying to close, more surface than this predicate's size
  justifies for a scenario requiring a manual re-run of an already-successful
  run.

## External Code Review (glm + openai)

Both `revise`, no contradiction (`glm`=revise, `openai`=revise, agree within
one step). 8 findings total (4 unique-per-provider plus overlap on the
AC7/ADR gap and the shape test's `set +e` omission).

- **(medium, both providers) AC7's ADR is absent from the diff.** Disclosed
  by design already (see the `## Acceptance Criteria` AC7 bullet's new "OPEN
  as of this diff" note above) — not fixed here, tracked instead so it
  cannot be silently marked satisfied before F3.
- **(medium, openai) Schema-malformed Jobs API entries (`steps` not a list)
  were silently read as "step absent," not `error`.** **Fixed:**
  `_provenance_step_conclusion` now tracks a `malformed` flag and returns
  `_JOBS_QUERY_FAILED` when nothing confirmed AND at least one job entry was
  malformed (a confirming job elsewhere still wins — permissive-on-success is
  unchanged). New tests:
  `test_error_when_jobs_response_has_malformed_step_shape`,
  `test_malformed_job_does_not_hide_a_confirming_job`.
- **(medium, glm) The shape test didn't pin the `set +e` guard** that makes
  the `$GITHUB_OUTPUT` capture reachable at all — a future edit removing it
  would silently starve `outputs.code` (every drift-found commit would
  degrade to a false `not_verified`) while the existing test stayed green.
  **Fixed:** new test
  `test_drift_check_set_plus_e_precedes_the_capture_and_output_line` pins
  `set +e` before `code=$?` before the output echo.
- **(medium, glm) The spec's Verification runner listed 2 invocations but 5
  test files exist** (three added across the two 300-line-guideline splits).
  **Fixed:** `## Verification (medium+)` above now lists all four
  `shared/tests` files as one invocation (same root) plus the CLI test root,
  and the exact command was run to confirm it passes.
- **(medium, openai) The provenance step's shape test only asserted
  `startswith("echo ")`,** which `echo ...; false` would also satisfy.
  **Fixed:** tightened to an exact string match of the step's `run:` body.
- **(low, glm) `code-review.json` recorded `_run_cli`'s type-annotation fix
  as `accepted-and-fixed`, but the edit was never actually applied** — a
  genuine accuracy bug in the review record, caught by a fresh external
  pass re-checking the record against the diff. **Fixed:** applied the
  annotation now (`-> tuple[int, dict]`); this section documents the
  correction so the record stays trustworthy rather than silently amending
  history.
- **(low, glm) An uppercase 40-char SHA was rejected as `error`.** Legal git
  input, only reachable via direct library use (the CLI's `rev-parse`
  normalizes). **Fixed:** `resolve_ci_verification` lowercases `commit`
  before validation. New test:
  `test_uppercase_commit_is_accepted_via_lowercase_normalization`.
- **(low, glm) `owner_repo()`'s failure mode was assumed, not verified** —
  raised as a doubt that an uncaught exception there could crash
  `resolve_ci_verification` outside its documented exit-code contract.
  **Reasoned rebuttal, not fixed:** read `github_api.py:178-197` directly —
  `_git_remote_origin` catches `OSError`/`SubprocessError` internally and
  `owner_repo` never raises; its own docstring states this. The doubt does
  not hold against the actual source.
- **(low, openai) A missing/invalid `total_count` is accepted as "not
  truncated."** **Disclosed, not fixed:** `total_count` is a guaranteed
  field of GitHub's List-workflow-runs response schema; requiring and
  validating it defensively adds fragility (a synthetic or future-API
  response omitting it would wrongly `error`) without a realistic failure
  mode it guards against — disproportionate for this predicate's size, same
  judgment already applied elsewhere in this review round.
- **(low, glm, not independently actioned) `Path(project_root)` raises on a
  non-str/Path argument.** Out of scope: `project_root`'s type contract
  (`Path | str`) is a caller obligation, not a transport failure this
  predicate's `error` status is meant to catch — consistent with how the
  rest of this module and its siblings treat type-contract violations.
