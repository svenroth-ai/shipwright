# Iterate Spec: the review gate stops being bypassable

- **Run ID:** iterate-2026-07-27-review-gate-failclosed-fork
- **Type:** change
- **Complexity:** medium
- **Status:** in progress
- **Risk flags:** `touches_ci_supplychain` (`.github/workflows/**`)
- **Card:** `trg-c7e5835b` items (1) and (2) of five — PR A of two.
  PR B (items 3, 4, 5 + the `verify_sweep_delivery_surface.py` orphan) follows
  once this is merged. Supersedes the closed run
  `iterate-2026-07-25-pr-review-failclosed-fork`, whose design is carried here.
- **Implements:** FR-01.17 criteria (E)2, (E)3, (E)4, (E)5, (E)7

## Goal

Three ways a change currently reaches `main` with the required `PR Review`
check green and **no review having happened**:

1. **Too big.** The shipped template
   (`shared/templates/github-actions/claude-review.yml.template`) skips the
   review above 5000 diff lines, and the skipping step *succeeds*. It also
   swallows the reviewer's exit code (`|| true`) and returns normally when the
   output will not parse. Three fail-open paths, not one.
2. **From a fork.** GitHub withholds secrets from `pull_request` runs raised
   from a fork, so the reviewer cannot run. Both `pr-review.yml` files guard
   `decide` on `head.repo.full_name == github.repository`; on a fork PR `decide`
   is skipped, `review` is skipped via `needs:`, and **GitHub scores a skipped
   job as a successful required check**. Green, nothing reviewed.
3. **Waived on the very changes that most need it.** `skip-pr-review` waives
   review on any PR — including one that edits the checks themselves. FR-01.17
   (E)7: *"whoever unlocks a door is not the one who decides it may be
   unlocked."*

Both repos are **public with forking enabled**, so (2) is live exposure.

## Design decision: the required context moves to a commit status

The two-stage shape is given: stage 1 runs without credentials and saves the
change as an artifact; stage 2 fires on its completion, holds the credentials,
reads the artifact, and never executes the contributor's code.

The non-obvious half is **what satisfies the required `PR Review` check**.

| Option | Verdict |
|---|---|
| **A.** Keep the `review` job as the check; add a fork-only stage 2 posting a status also named `PR Review` | **Rejected.** The skipped job still emits a `skipped` check run under that name, which GitHub scores as success — the hole stays open — and two producers of one context is the ambiguity GitHub's docs warn against. |
| **B.** Leave forks red; a maintainer clears them with `skip-pr-review` | **Rejected as primary.** Forks would be *blocked*, not *reviewed*, and (E)7 is against widening that label's reach. Kept as the documented fallback when stage 2 is unavailable. |
| **C.** Stage 1 stops owning the context; **stage 2 posts `PR Review` as a commit status, for every PR** | **Chosen.** One path for fork and non-fork. Fail-closed *by construction*: if stage 2 never posts, the context is absent, and an absent required context is `pending`, which blocks — exactly FR-01.17 (E)2's "silence counts as not passing". No duplicate producers. The context name is preserved, so the ruleset needs no edit. |

**Accepted cost — one manual merge, once.** A `workflow_run` workflow only fires
from the default branch, so stage 2 does not exist for the PR introducing it and
nothing posts `PR Review` here. The `main-protection` ruleset grants
`RepositoryRole 5` (admin) `bypass_mode: always`, so the maintainer merges this
one by hand (operator confirmed, 2026-07-27). Every later PR is normal. A
two-PR landing was checked and does **not** avoid this — it relocates the same
gap.

## Acceptance Criteria

**The shipped template fails closed — all three paths** → FR-01.17 (E)2

- [ ] AC1. A diff over the size threshold makes the job **fail** (non-zero),
  not pass with a "skipping" message. (E)
- [ ] AC2. A reviewer that exits non-zero fails the job — the `|| true` that
  discards its exit code is gone. (E)
- [ ] AC3. Output that will not parse fails the job, instead of logging
  "No valid review output" and returning normally. (E)
- [ ] AC4. Each of AC1–AC3 names the deliberate override in its message, so a
  red gate is actionable.

**Fork changes are reviewed, never trusted** → FR-01.17 (E)4, (E)5

- [ ] AC5. Stage 1 runs on every PR including forks, holds **no secret**, and
  records the diff as an artifact — an **audit record**, never an input. (E)
- [ ] AC6. Stage 2 runs from the default branch and **never checks out or
  executes the contributor's code** — base repo checkout only. (E)
- [ ] AC7. Stage 2 takes the PR number and head SHA from the **trusted**
  `workflow_run` event, never from the artifact, so a forged artifact cannot
  redirect a verdict onto another PR. (E)
- [ ] AC7a. **Stage 2 trusts nothing stage 1 produced.** `pull_request` runs
  stage 1 from the PR head, so the contributor controls it. The tier decision
  and the reviewed diff are both derived in stage 2 from the API. A PR must not
  be able to declare itself exempt or nominate the code that gets reviewed. (E)
  *(Added after external review found both holes in the first draft — see the
  Confidence Calibration.)*
- [ ] AC8. Stage 2 writes the verdict and its reasons **onto the PR** as a
  comment, and posts the `PR Review` commit status on the head SHA. (E)
- [ ] AC9. No second producer of the `PR Review` context — stage 1 has no job
  under that name. (E)

**The gate cannot exempt itself** → FR-01.17 (E)3, (E)7

- [ ] AC10. `skip-pr-review` no longer waives review on a PR touching
  `.github/workflows/**`, `.github/actions/**`, or the shipped workflow
  templates. Every other waiver path is unchanged. (E)
- [ ] AC11. The existing tier logic (`needs-review`, sensitive paths, external
  contributor) is preserved verbatim across the move.

**Cross-cutting**

- [ ] AC12. `shared/tests/test_workflow_token_permissions.py` passes: the new
  workflow is read-only at top level and only the posting job widens, to
  exactly `statuses: write` + `pull-requests: write` + `contents: read`.
- [ ] AC13. `docs/hooks-and-pipeline.md` (row E.15) and
  `AUTOMERGE_SETUP.md.template` describe the two-stage shape;
  `AUTOMERGE_SETUP.md.template` no longer calls the review "advisory".
- [ ] AC14. `ci_supplychain_ack` recorded (F11 recomputes the flag and fails
  closed without it).

## Spec Impact

- **Classification:** NONE
- **Justification:** FR-01.17 and its seven (E) criteria were authored by the
  REQ-3 Phase 2 content round and are already on `main`. This iterate
  *implements* five of them and mints nothing; no `spec.md` is touched. The new
  tests carry `@FR-01.17` tags, which is where the traceability is recorded.

## Out of Scope

- Card items (3), (4), (5) and the `verify_sweep_delivery_surface.py` orphan —
  **PR B**, off fresh `main` after this merges.
- The **webui** repo: same fork gap, its own iterate and PR. Its vendored
  reviewer already fails closed on size.
- Re-vendoring the webui's `pr_review.py` for `filter_generated_paths`.
- Changing the ruleset — the context name is preserved deliberately.
- The review model, prompt, or the quality of its findings. This is about
  *whether* a review runs.

## Design Notes

No UI. Deliverables: two workflow files here, two shipped templates, the
scaffolder + registry, tests, docs. Design Check Tier 2 (markdown).

**The three rules that keep stage 2 safe**, each pinned by a test —
`workflow_run` hands secrets and a writable token to a run whose input is
attacker-influenced:

1. never check out the PR head — base repo only;
2. the artifact is data — parsed as JSON, never sourced, never interpolated
   into a shell body;
3. identity (PR number, head SHA) comes from `github.event.workflow_run`, not
   from the artifact.

`workflow_run.pull_requests` is **empty for fork PRs** (documented GitHub
gotcha), so the PR number is resolved from the trusted head SHA via the API,
not read from that array or from the artifact.

## Affected Boundaries

Stage 1 writes an artifact that stage 2 reads — a serialized producer/consumer
pair introduced here. `touches_io_boundary` fires; a Boundary Probe +
round-trip test is required.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| stage 1 `prepare` job → `pr-review-request` artifact | stage 2 `workflow_run` job | JSON metadata + raw diff text |

## Confidence Calibration

- **Boundaries touched:** one — stage 1 writes `pr-review-request/{pr.diff,
  meta.json}`, stage 2 reads it. Plus a CLI boundary: stage 2 passes
  `--diff-file` to `pr_review.py`.

- **Empirical probes run:**
  - *Does a skipped job really satisfy a required check?* Confirmed against
    GitHub's own docs: successful states are `success`, `skipped`, `neutral`.
    This is the mechanism of the fork hole, not an inference.
  - *Are the required contexts actually named `PR Review`?* Read live from both
    repos' rulesets via `gh api`. Confirmed, in both. Neither uses classic
    branch protection — `main-protection` rulesets, `enforcement: active`.
  - *Can the introducing PR be merged at all?* `bypass_actors` =
    `RepositoryRole 5` (admin), `bypass_mode: always`. Yes, once, by the owner.
  - *Is the exposure real or theoretical?* `allow_forking: true`, `private:
    false` on both repos. Real.
  - *Does the derivation helper still name the right check?* It did NOT — it
    would have emitted `Prepare review request` and flagged stage 2 as dormant.
    Found by running it, fixed via `POSTED_STATUS_CONTEXTS`, pinned by a test.
  - *Did any existing test pin the defect?*
    `test_pr_review_workflow_shape.py::test_fork_pr_guard_present` **required
    the fork guard to exist** — the hole was under test. Rewritten.
  - *External review of the plan (OpenRouter, Gemini 3.1 Pro + GPT-5.6-terra,
    both succeeded, `degraded: false`).* **Both independently found a
    high-severity hole in my first draft**, and both were right:
    `pull_request` runs stage 1 **from the PR head**, so the contributor owns
    everything it emits. My stage 2 read `needs_review` from the artifact and
    waived the review when it said `false` — a PR could declare itself exempt
    and collect a green `PR Review` status, reintroducing exactly the
    self-exemption (E)7 forbids. The same trust bug applied to the diff: a
    forged artifact would get a benign diff reviewed while different code
    merged. **Fixed:** stage 2 now derives the tier from the API (labels,
    author, changed paths) in default-branch code and fetches the diff from the
    API; stage 1 carries no policy at all and its artifact is an audit record.
    Pinned by `test_stage2_never_reviews_the_artifact`,
    `test_stage1_carries_no_policy`, `test_tier_is_decided_here_from_api_data`.
    GPT additionally flagged that cross-run artifact download needs
    `actions: read`, which my permission set lacked — moot after the download
    was removed, but it was a correct catch.

- **Test Completeness Ledger:** every behaviour this diff introduces, each
  `tested` (with evidence) or `untestable` (closed-vocabulary reason code).
  0 testable-but-untested.

  | # | Behaviour | Disposition | Evidence / reason |
  |---|---|---|---|
  | 1 | Oversize diff fails instead of skipping | `tested` | `test_oversize_diff_fails_instead_of_skipping` |
  | 2 | Reviewer exit code never discarded | `tested` | `test_reviewer_exit_code_is_never_discarded` (comment-stripped) |
  | 3 | Unparseable output fails closed | `tested` | `test_unparseable_review_output_fails_closed` |
  | 4 | Stage 1 holds no secret | `tested` | `test_stage1_holds_no_secret`, `TestStage1::test_holds_no_secret` |
  | 5 | Stage 1 not fork-guarded | `tested` | `test_stage1_is_not_fork_guarded`, `TestStage1::test_fork_guard_absent` (parses `if:`, not prose) |
  | 6 | Stage 1 uploads the artifact | `tested` | `test_stage1_uploads_the_request_artifact` |
  | 7 | Stage 1 owns no `PR Review` context | `tested` | `test_stage1_owns_no_pr_review_context` |
  | 8 | Stage 2 triggered by `workflow_run` | `tested` | `test_stage2_is_triggered_by_workflow_run`, `test_stage2_is_chained_to_stage1` |
  | 9 | Stage 2 never checks out PR head | `tested` | `test_stage2_never_checks_out_contributor_code` |
  | 10 | Stage 2 takes identity from trusted event | `tested` | `test_stage2_takes_identity_from_the_trusted_event` |
  | 11 | Stage 2 posts verdict + status | `tested` | `test_stage2_posts_the_verdict_onto_the_change`, `test_posts_the_required_context_as_a_status` |
  | 12 | Token permissions least-privilege | `tested` | `test_pr_review_stage1_holds_no_write_scope`, `test_pr_review_run_only_posting_job_widens` |
  | 13 | Artifact path agrees across stages | `tested` | `test_artifact_path_round_trips_between_the_stages` |
  | 14 | `--diff-file` exists on the reviewer | `tested` | `test_reviewer_accepts_the_diff_file_flag` |
  | 15 | Diff content round-trips | `tested` | `test_diff_file_content_round_trips` |
  | 16 | Waiver cannot cover a change to the checks | `tested` | `test_waiver_cannot_cover_a_change_to_the_checks` (×2) |
  | 17 | Tier logic preserved across the move | `tested` | `TestStage1::test_skip_label_rule` / `needs_review` / `sensitive_paths` / `external_author` |
  | 18 | Adopt scaffolds BOTH stages | `tested` | `test_stage2_lands_too`, `test_stage2_existing_file_preserved` |
  | 19 | Derivation names the posted status, not a job | `tested` | `test_required_check_names_match_deployed_workflows` (3 profiles), `test_posted_status_contexts_name_known_workflows` |
  | 20 | Stage 2 actually runs on a real fork PR end-to-end | `untestable` | `requires-external-nondeterministic-service` — needs a real fork PR against GitHub with live secrets; no local harness can produce a `workflow_run` event with a populated artifact. **First live fork PR is the proof**; until then the gate fails closed, which is the safe direction. |

- **Confidence-pattern check:**
  - *Asymptote (depth).* The three stage-2 hardening rules are each pinned by a
    test that reads parsed structure, not prose — after two of my own tests
    false-failed on their own explanatory comments, every text assertion was
    moved to `_shell_code` / `_job_conditions` / `if:`-parsing.
  - *Coverage (breadth).* Both the monorepo pair and the shipped template pair
    are parametrised through the same invariants, so the shipped one can no
    longer be weaker than ours — which is the whole complaint on the card.
  - *Integration composition.* `cross_component` does not fire (no merge/churn
    resolver, hooks, phase validator, or campaign machinery in the diff), so no
    `category:"integration"` behaviour is required. Row 19 nonetheless composes
    the scaffolder → deployed-workflow → derivation chain across 3 profiles.
  - **Known gap, stated plainly:** row 20. Everything here proves the workflows'
    *shape*; nothing proves GitHub executes them as designed. The failure mode
    if I am wrong is a blocked PR, not an unreviewed merge.

## Verification (medium+)

- Full suite at F0, plus the new `@FR-01.17` tests.
- F0.5: the artifact round-trip is the executable surface — authored **and run**.
- `uvx ruff@0.15.15 check .`; YAML parse assertions on both workflows.
