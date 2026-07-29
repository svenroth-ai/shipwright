# Iterate Spec: main-self-heal

- **Run ID:** iterate-2026-07-28-main-self-heal
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

When the shared branch (`main`) goes red, an agent repairs it without being
asked. This iterate builds the three pieces that make that possible — **exact
attribution** (which commit broke it), a **diagnosis package** (one JSON with
everything the repair needs), and a **written procedure** at the two points
where an iterate already touches `main`. The agent is the fixer; this delivery
is the detector, the package, and the rules.

Source: `.shipwright/planning/iterate/HANDOVER-2026-07-29-main-selfheal-then-docs.md`
(PROMPT 1). It is the fuse before the switch: `strict_required_status_checks_policy`
is being turned off, which removes BEHIND entirely but lets two individually-green
changes break `main` together.

## Acceptance Criteria

- [ ] **AC-1 — exact attribution.** On `main`, CI verifies *every* commit and
      verifies them **in parallel**: the concurrency group is per-commit
      (`github.sha`) on `main` and per-ref elsewhere, and `cancel-in-progress` is
      false on `main` and true elsewhere (PRs keep cancelling, which saves
      minutes; a per-ref group with cancelling off would have queued main runs
      serially instead). Applied to `ci.yml` **and** `security.yml`, which carry
      the identical bug. Without this, "commit P green, commit C red ⇒ C is the
      first bad commit" does not hold and everything downstream is guesswork.
- [ ] **AC-2 — close the one coverage gap.** `bloat-check.yml` gains a
      `push: branches: [main]` trigger, so a file that crosses its size baseline
      only when two PRs combine is visible on `main`. Base-ref resolution is
      guarded: empty, all-zero or unresolvable yields an explicit "baseline
      unavailable" notice and an empty baseline, never a diff against an invalid
      revision. The PR-comment step stays `pull_request`-gated.
- [ ] **AC-3 — the diagnosis package.** `shared/scripts/tools/main_health.py`
      answers in ONE JSON: the state of each monitored workflow on `main`
      (counting only push-to-`main` runs, so a green PR run for the same commit
      cannot mask a red one); the **first bad commit** — the oldest red after the
      last green — alongside the latest red; the failing step and its reduced,
      redacted, explicitly-untrusted output; the candidate partners (the merges
      the bad commit was never tested against, resolved through the commit→PR
      association); and whether a repair is already in flight. **Fails
      honestly** — an unreadable source, an exhausted history window or a missing
      run reports `unknown` / `uncertain` with a named reason code, never
      `green`.
- [ ] **AC-4 — where the agent enters.** Two hooks in the iterate skill, both at
      points where an iterate already touches `main`: at iterate start (SKILL.md
      §B1a, right after the worktree is cut off `origin/main`) and before arming
      the merge (F11). The green path costs ONE API call.
- [ ] **AC-5 — the repair procedure.** `references/main-repair.md`: read the
      failure, read the bad commit and its candidate partners, fix the overlap,
      make the failing test pass then the full suite, ship a small `fix(main): …`
      PR linking the red run.
- [ ] **AC-6 — escalate, deliberately narrowly.** A card instead of a fix when
      the repair would **weaken the test suite** — enforced in CODE, and as a
      *gate*: `check_repair_safety.py` runs as a step of the required `CI` job
      for PRs that declare themselves repairs, comparing the parsed (AST)
      before/after of each changed test file over the merge-base diff. It blocks
      unambiguous coverage loss (assertions removed, a test function or file
      removed, `skip`/`xfail` newly applied) and *reports* a changed assertion
      expression without blocking, because updating a pinned count another PR
      legitimately changed is the commonest honest repair. Also a card when a
      finding-class workflow is red (a finding, not an overlap), or when more
      than a handful of commits are implicated, or two attempts already failed.
- [ ] **AC-7 — no duplicate repairs.** The repair PR IS the claim: one query
      names an existing open repair for that bad commit and the iterate simply
      proceeds. A claim is only recognised from a **non-fork** head branch — write
      access is the trust boundary, so a copied `Repairs-Commit:` trailer from a
      fork cannot suppress the repair loop. A claim that outlives its worker is
      reported `stale` (untouched past a threshold) so it can be taken over
      instead of wedging the mechanism, and closed-unmerged attempts are counted
      so "two attempts did not resolve it" is a fact rather than a hope.

## Spec Impact

- **Classification:** add
- **ADD** (new FR appended): FR-01.19 — Shared branch repairs itself
- **MODIFY** (existing FR changed): none
- **REMOVE** (FR retired): none
- **NONE justification:** n/a

**MINT-vs-FOLD gate (`shared/fr-authoring.md` §3).** MINT. The nearest existing
row, FR-01.17 ("Independent re-check on the code host"), guarantees that a
*proposed* change is re-checked **before it can merge**. This capability is about
what happens **after** the merge, on the shared branch itself: nobody had to be
told it went red, and the framework says which change broke it. That is not a
completion, polish, fix, extension or "Phase N of" FR-01.17 — it is a different
guarantee about a different moment. FR-01.11 (`/shipwright-iterate`) is about
scaling process to complexity, not about branch health.

**Layers: `unit (inferred)`, and the reason is a measurement, not a preference.**
The first draft declared the bare form, on the §4a reading that "the tests exist
in this same iterate". Driving the real traceability collector said otherwise:
`FR-01.19` comes back `coverage: {"unit": "MISSING"}`, `tests: {}`, and this
iterate's test files land in `untagged_tests` — the collector attributes **per
test function**, not per module docstring, so the module-level `@FR-01.19` tags
create no link. The precedent row FR-01.17 is itself `inferred_legacy` with no
links; the whole adopted catalogue is deliberately advisory, and
`integration-tests/test_fr_table_shape_convergence.py` guards exactly that: a
`Layers` cell without the literal `(inferred)` marker makes provenance
`explicit`, which routes a coverage gap from advisory to a hard, unbypassable
`sys.exit(1)`.

So the bare form would have asserted a machine-verifiable link that does not
exist, and hard-failed CI against a guaranteed gap. `(inferred)` is the accurate
standing of the cell. **This is not the same as saying the behaviour is
untested** — 129 tests cover it and the ledger below names them one by one; what
is absent is the *traceability link*, and the honest cell records that rather
than papering over it. Making the link real means per-function tagging plus
turning this into the only `explicit` row in an otherwise advisory catalogue —
a catalogue-wide policy change, deliberately out of scope here and recorded as
such.

## Out of Scope

- **A scheduled run** covering "no iterate is active" — a later three-liner once
  the procedure exists, explicitly deferred by the handover.
- **A fixer.** No code decides what the repair should be; the agent reads the
  package and fixes it. Automating the fix is the thing this design rejects.
- **Auto-revert.** Rejected upstream: it throws away good work on a flake or a
  mis-attribution, and it is outward-facing.
- **Turning off `strict_required_status_checks_policy`.** Authorised by the
  operator, but a repo-settings change, not a code change — it happens after this
  PR merges and is recorded in the run's artifacts, not in this diff.
- **A merge queue.** Deferred; see `2026-07-28-merge-queue-DEFERRED.md`.

## Design Notes

n/a — no UI surface. This is framework machinery (tools + skill prose + CI
workflow triggers).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `gh run list --json` (GitHub) | `lib/main_health.classify_runs` | JSON |
| `gh run view --log-failed` (GitHub) | `lib/main_health.reduce_failure_log` | text |
| `gh pr list --json` (GitHub) | `lib/main_health.match_repair_claim` | JSON |
| `git log --first-parent --format` | `tools/main_health._commit_series` | text |
| `git diff -U0` | `lib/assertion_weakening.detect_weakening` | unified diff |
| `tools/main_health.py` (stdout) | the repair agent / `references/main-repair.md` | JSON |

Every one of these is a **read** boundary whose producer is outside this repo
(GitHub, git). The risk is not round-trip drift but **misreading a payload
shape**, so the probes below drive real `gh`/`git` output rather than only
hand-written fixtures. `touches_io_boundary` did not fire (no `*_config.json`,
no `parse_env`/`json.dump` producer keyword) — the Boundary Probe sub-step is
therefore not enforced, but the empirical probes are run anyway because the whole
tool is a payload reader.

## Confidence Calibration

- **Boundaries touched:** the six read-boundaries listed under Affected
  Boundaries — all of them payloads produced *outside* this repository.

- **Empirical probes run** (four; each drove the real producer, not a fixture):

  1. **`gh run list --json` field shapes.** Ran the real query against this
     repository. Every field the predicate depends on came back exactly as the
     fixtures assume — `event: "push"`, `headBranch: "main"`, `workflowName:
     "CI"` / `"Security Scan"` / `"CodeQL"`, `conclusion: "success"`,
     `status: "completed"`. **Finding:** confirmed; no fixture drift.
  2. **The whole tool against the real repository.** **Finding — a real bug,
     invisible to the fixtures:** `main_advanced_during_check` fired on a
     perfectly quiet branch. `gh run list` reaches much further back than the
     25-commit window, so "this SHA is not in the walked series" was true of
     every ordinary older commit. Fixed to key on the *newest* selected run
     (runs come back newest-first, so only that one can prove the branch moved),
     and pinned by `test_runs_for_commits_merely_OLDER_than_the_window_are_not_main_moving`.
     A second, quieter finding from the same run: `saturated` was being turned
     into `run_history_truncated` whenever *any* commit had runs, rather than
     when coverage stopped short of the window end — two different refusals with
     two different fixes, now distinguished.
  3. **`check_repair_safety.py` against this iterate's own diff.** Real git
     plumbing, 11 files examined, `verdict: clear`. **Finding:** the CLI's
     `--name-status --find-renames` parsing and base-tree reads work against a
     real working tree.
  4. **Does the gate actually bite?** A throwaway repository, one weakening per
     run, driving the real CLI: assertion dropped, test deleted, `skip` added,
     file deleted — all `exit 2 / blocked`; the *honest* repair (a pinned count
     updated) `exit 0 / review`. **Finding:** the refusal is real end-to-end,
     and the commonest correct repair is not blocked by it. Promoted from a
     throwaway probe to a permanent test (`test_repair_gate_bites.py`) because a
     detector tested only on hand-written inputs proves nothing about the
     plumbing in front of it.

- **Test Completeness Ledger** — 129 tests, one row per behaviour this diff
  introduces. **Every AC is enforced by something that goes red**; no row is
  closed by prose alone.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | AC-1 · `main` runs are never cancelled, on both workflows | tested | `test_main_attribution_workflows::test_main_runs_are_never_cancelled[ci.yml, security.yml]` (parsed YAML) |
  | 2 | AC-1 · `main` runs get a per-commit group so they do not queue | tested | `…::test_main_runs_get_their_own_group_so_they_do_not_queue[ci.yml, security.yml]` |
  | 3 | AC-2 · bloat check runs on merges, still comments only on PRs | tested | `…::test_bloat_check_runs_on_merges_to_main`, `…::test_bloat_check_still_only_comments_on_pull_requests` |
  | 4 | AC-2 · base ref guarded against empty / all-zero / unresolvable | tested | `…::test_bloat_check_guards_every_shape_its_base_ref_can_take` |
  | 5 | AC-3 · a green PR run cannot mask a red push-to-`main` run | tested | `test_main_health::test_pr_run_for_the_same_sha_never_masks_the_main_run` |
  | 6 | AC-3 · conclusion mapping incl. `cancelled` ≠ pass | tested | `test_main_health` (4 cases) |
  | 7 | AC-3 · only the overlap class decides health | tested | `test_main_health::test_a_red_finding_class_workflow_does_not_make_the_commit_red` |
  | 8 | AC-3 · first bad = oldest red after the anchor; latest red reported too | tested | `test_main_health_attribution::test_first_bad_is_the_oldest_red_and_latest_red_is_reported_separately` |
  | 9 | AC-3 · gaps downgrade confidence; three refusals have distinct reason codes | tested | `test_main_health_attribution` (6 cases) |
  | 10 | AC-3 · unknown is never green, whatever failed | tested | `test_main_health_tool` (4 cases: gh, git, no runs, running) |
  | 11 | AC-3 · a broken diagnosis call does not cost the verdict | tested | `test_main_health_tool::test_a_broken_diagnosis_call_degrades_without_losing_the_verdict` |
  | 12 | AC-3 · failing step from structured data; excerpt reduced, capped, redacted, labelled untrusted | tested | `test_main_health_diagnosis` (9 cases) + `test_main_health_tool::test_a_missing_log_does_not_hide_the_failing_step` |
  | 13 | AC-3 · a commit SHA is not redacted as if it were a secret | tested | `test_main_health_diagnosis::test_a_commit_sha_is_not_mistaken_for_a_secret` |
  | 14 | AC-3 · `main` advanced is detected; older commits do not false-positive | tested | `test_main_health` (2 cases — #2 above is why the second exists) |
  | 15 | AC-3 · the monitored policy and the real YAML agree, both directions | tested | `test_main_attribution_workflows` (3 cases incl. the reverse sweep) |
  | 16 | AC-4 · the start hook sits between cutting the worktree and loading context | tested | `test_main_repair_hooks::test_the_start_hook_runs_right_after_the_worktree_is_cut` |
  | 17 | AC-4 · the F11 hook runs *before* the arm | tested | `…::test_the_f11_hook_runs_before_the_merge_is_armed` |
  | 18 | AC-4 · both hooks say unknown is never green | tested | `…::test_unknown_is_never_treated_as_green_at_either_hook` |
  | 19 | AC-4 · the green path costs exactly one API call | tested | `test_main_health_tool::test_the_green_path_costs_exactly_one_api_call` |
  | 20 | AC-5 · the procedure carries every repair step and is within budget | tested | `test_main_repair_hooks` (3 cases) |
  | 21 | AC-6 · every unambiguous coverage loss is blocked (7 classes) | tested | `test_assertion_weakening` (11 cases) |
  | 22 | AC-6 · the fences that would make it unusable hold | tested | `test_assertion_weakening` (5 fence cases) |
  | 23 | AC-6 · a changed expectation is reported, never blocked | tested | `test_assertion_weakening` (3 cases) |
  | 24 | AC-6 · **the gate bites through real git**, and the honest repair passes | tested | `test_repair_gate_bites` (6 cases, real repositories) |
  | 25 | AC-6 · the CI step blocks, keys on the shared grammar, and runs the checker from the BASE revision | tested | `test_main_attribution_workflows` (4 cases) |
  | 26 | AC-6 · escalation classes and idempotency keys | tested | `test_main_health_diagnosis` (4 cases) |
  | 27 | AC-7 · claim matching: branch, fork rejected, prefix, stale, failed attempts | tested | `test_main_health_diagnosis` (8 cases) |
  | 28 | AC-7 · **the claim is atomic** — two simultaneous repairers, one wins | tested | `test_repair_claim_is_atomic::test_only_one_of_two_simultaneous_repairers_can_claim` (real remote) |
  | 29 | AC-7 · the loser can read who holds it; a released claim lets the next through | tested | `test_repair_claim_is_atomic` (3 further cases) |
  | 30 | An agent actually *obeys* the two hooks at runtime | untestable | `covered-by-existing-test` — the hooks are skill prose, and no test can compel a model to follow prose. What IS testable is that the prose exists, is correctly placed and says the right thing (rows 16–19), which is the same guarantee every other skill step has. |
  | 31 | The GitHub-side behaviour of the CI gate step on a live PR | untestable | `requires-external-nondeterministic-service` — the step's *decision* is row 24 (real git) and its *wiring* is row 25 (parsed YAML); only Actions' own dispatch is unreachable locally. |

  **Addendum after the two external CODE-review rounds** (mini-plan §10). Seven
  defects were fixed; each brought its own row, and three of them are cases
  where a *test agreed with the code because both were wrong* — the ledger above
  counted them as covered when they were not.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 32 | A detected `main_advanced_during_check` downgrades the status instead of only annotating it | tested | `test_main_health::test_a_detected_race_downgrades_the_answer_it_does_not_just_annotate_it` |
  | 33 | A red finding-class workflow yields `escalate` (exit 5), a passing one leaves `green` alone | tested | `test_main_health` (2 cases — the first replaces an assertion that had pinned the defect) |
  | 34 | A repaired red further back is history; a red under a still-running tip is not | tested | `test_main_health_attribution` (2 cases) |
  | 35 | **A same-SHA claim push is NOT a lock** — the falsification the create-ref choice rests on | tested | `test_repair_claim_is_atomic::test_pushing_the_claim_branch_before_working_is_NOT_a_lock` (real remote) |
  | 36 | A push only rejects once histories diverged — i.e. it protects the agent that no longer needs protecting | tested | `test_repair_claim_is_atomic` |
  | 37 | A branch-only claim reports staleness `None` (unknown), and `True` once its pull requests are closed | tested | `test_main_health_diagnosis` (2 cases) |
  | 38 | A rename out of test collection blocks | tested | `test_assertion_weakening::test_renaming_a_test_out_of_collection_blocks` |
  | 39 | The repair is based on `origin/<default>`, and releasing deletes the ref as well as the PR | tested | `test_main_repair_hooks` (2 cases) |
  | 40 | GitHub's create-ref returns *422 Reference already exists* for a duplicate claim | untestable | `requires-external-nondeterministic-service` — a host property, not a git one. Mocking it would assert only what the mock was told; the git-side half is row 35. |

- **Confidence-pattern check.**
  *Asymptote (depth):* yes, twice, and the second time is the instructive one.
  After the fixtures went green the answer to "does it work?" was **yes** — and
  probe #2 found a real false positive on a quiet branch. A further probe (#4)
  found nothing, which read like the honest place to stop. It was not: two
  independent external rounds on the finished diff then found **seven** more
  defects, three of them in behaviours this very ledger had already marked
  `tested`. The lesson is written down rather than smoothed over — a green suite
  authored by the same person who wrote the code measures agreement, not
  correctness, and only an independent reader breaks that symmetry. It is also
  why the operator's "ask both twice" was worth the tokens: round 2 found three
  defects round 1 did not.
  *Coverage (breadth):* 31 rows, 29 `tested`, 2 `untestable` with structural
  reasons, **0 untested-but-testable.** The one gap this audit found — AC-7's
  atomicity claim was asserted in prose and enforced nowhere — was closed with a
  real-remote test before this section was written, not explained away.
  *Composition:* `cross_component` does not fire (no merge/churn resolver, no
  `hooks.json`, no phase validator, no campaign machinery in the diff), so no
  integration-coverage row is owed; re-verified from the actual diff at F11.

## Degraded condition — the local F0 full-suite run

**`shared/tests` was never completed in one local process, and that is stated
here rather than implied by a green tick elsewhere.**

Every run of it — three attempts, including one deliberately detached from the
session so it would outlive a session death — was terminated by the environment
at 79 %, then 94 %, then 94 % again. The Windows event log records no crash for
any of them; the process simply goes away. The same fault killed this session
repeatedly (memory pressure, a duplicated WebUI server and the pty idle-reaper
were each investigated and each **falsified** — recorded so the next run does
not pay for it again).

**What this does and does not mean.** In every attempt the suite reached 94 %
with **zero failing tests**. So the evidence points at an environment fault, not
at a regression. Locally green and complete: `integration-tests` (422),
`shared/scripts/tests`, `shared/scripts/tools/tests`, the `shipwright-iterate`
plugin suite (521), and all 123 tests this iterate adds. What is unverified
locally is the remainder of `shared/tests` — which CI runs on this pull request
as a **Required Check**, and which is the authoritative gate either way.

Recorded in `iterate_latest.degraded[]`. If CI reddens on a `shared/tests` file
this iterate did not touch, that is the missing 6 % speaking, and it is a
finding rather than a surprise.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run shared/scripts/tools/main_health.py --project-root . --json`
  driven against the REAL repository and the REAL `gh` CLI, plus
  `uv run shared/scripts/tools/check_repair_safety.py --project-root . --base HEAD`
- **Evidence path:** `.shipwright/runs/iterate-2026-07-28-main-self-heal/f05-surface/`
- **Justification (only if surface=none):** n/a
