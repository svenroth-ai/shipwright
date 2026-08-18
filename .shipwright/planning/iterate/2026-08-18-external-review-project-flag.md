# Iterate Spec: external-review-project-flag

- **Run ID:** iterate-2026-08-18-external-review-project-flag
- **Type:** bug
- **Complexity:** medium
- **Status:** implemented

## Goal
Every documented `uv run .../external_review.py` invocation must pass uv's
own `--project` flag pointed at `shipwright-plan` (the plugin that declares
the `openai` dependency the script imports), so the external review
cascade resolves that dependency reliably in any consumer project — not
only inside this monorepo, whose own root `pyproject.toml` happens to
declare `openai` too and therefore masked the bug.

## Acceptance Criteria
- [x] All 9 known `uv run .../external_review.py` call sites — 6 broken
  (5 in shipwright-iterate, 1 in shipwright-build) plus shipwright-plan's
  own 3 (already correct, confirmed unchanged) — pass `uv run --project`,
  and the script's own module-docstring usage example is updated to match
  (it was a 10th, undiffed, un-flagged mention of the same invocation).
- [x] `sub-iterate-runner.md`, which had no `plan_plugin_root` in scope,
  gets it threaded in as a new Input parameter (from the orchestrator,
  which resolves it the same way it resolves `plugin_root`) rather than a
  hardcoded/invented monorepo path.
- [x] A static regression test asserts `--project` on every call site's
  bash block — not a `uv run` execution, since that would pass in THIS
  repo today regardless of the bug (root `pyproject.toml` masks it).
- [x] Fix is empirically verified from a directory with NO
  `pyproject.toml` at all (the actual failure mode reported from
  leadwright, which has none) — plain `uv run` fails there,
  `uv run --project <plan_plugin_root>` succeeds.

## Spec Impact
- **Classification:** none
- **NONE justification:** This is a call-site bug in prose skill-instruction
  files (how Claude sessions are told to invoke a shared script), not a
  product-facing capability change to Shipwright's own FR spec. No FR is
  added, modified, or retired — the external review feature already exists
  and is already specified; this restores its documented dependency
  resolution in projects without a root `pyproject.toml` matching the
  monorepo's own.

## Out of Scope
- Removing the `google-genai` dependency from `shipwright-plan/pyproject.toml`
  (vestigial — the script only imports `openai`; a separate cleanup).
- Lightening `external_review.py`'s dependency to `httpx` instead of the
  `openai` SDK to sidestep this whole class of cross-plugin resolution bug.
- Fixing `--plugin-root "{plugin_root}"` in `sub-iterate-runner.md`'s two
  call sites pointing at shipwright-iterate's own root instead of
  shipwright-plan's — confirmed inert for `--mode iterate`/`--mode code`
  (only `--mode plan` prompt-loading consults it; verified against
  `external_review.py`'s own source, line 348).
- PEP 723 inline script metadata on `external_review.py` (`# /// script`
  block declaring `openai` directly) as a replacement for `--project` —
  a genuinely stronger alternative (uv resolves it regardless of cwd,
  fixing all 9 sites and removing the `plan_plugin_root` threading
  entirely), but a dependency-declaration-mechanism change to a shared
  script crosses more surface (and this file's own bloat baseline) than
  a prose fix; deferred alongside the httpx item above, not adopted here.
- `docs/guide.md:1516`'s `uv run shared/scripts/tools/probe_deepseek_zdr.py`
  mention has the same unflagged-`uv run` shape and the same script also
  imports `openai`, but it is a different script than the one this card
  named, and the doc's own invocations there are monorepo-relative
  (`shared/scripts/...`, not an absolute plugin path) — plausibly
  monorepo-only in practice. Left unaddressed; flagged for a follow-up
  card rather than silently expanding this one's scope.
- Quoting the ~11 other unquoted `--project {plugin_root}` sites in
  shipwright-plan that invoke scripts *other than* `external_review.py`
  (`check-context-decision.py`, `check-plan-gates.py`,
  `generate-batch-tasks.py`, `check-sections.py`,
  `setup-planning-session.py`, `mark-review-state.py`,
  `check-external-review-keys.py`) — a real latent bug on paths
  containing spaces, but a different, unrelated convention sweep. (The 3
  sites that *do* invoke `external_review.py` are this card's own scope
  and are now quoted — see External Plan Review below; this item was
  originally written to cover those 3 too, before that reversal.)

## Design Notes
n/a — no UI/mockup surface; this is a prompt/skill-instruction fix plus a
static regression test.

## Affected Boundaries
n/a — no serialized-format producer/consumer pair changes; the change is
which project context `uv run` resolves from, not a data format.

## Confidence Calibration
- **Boundaries touched:** none (see above).
- **Empirical probes run:**
  - Confirmed the actual call-site inventory by grep across all 3 plugins
    (found exactly 6 broken sites + 3 already-correct shipwright-plan
    sites, matching the card's corrected count).
  - Confirmed `--plugin-root` is used only for `--mode plan` prompt
    loading (`external_review.py:348`), so the pre-existing
    `--plugin-root "{plugin_root}"` mixup in `sub-iterate-runner.md` is
    inert for its `--mode iterate`/`--mode code` calls — left unchanged,
    out of scope.
  - Reproduced the failure from a scratch directory with **no**
    `pyproject.toml` at all: `uv run python -c "import openai"` →
    `ModuleNotFoundError`, exit 1 — the actual leadwright failure mode.
  - Confirmed the fix from the same no-`pyproject.toml` directory:
    `uv run --project "<plan_plugin_root>" python -c "import openai; print(openai.__version__)"`
    → `openai 2.30.0`, exit 0.
  - Confirmed `uv run --project "plugins/shipwright-plan" check-external-review-keys.py`
    resolves cleanly from this repo too (`available: true`).
  - Re-ran the no-`pyproject.toml` probe against the **installed plugin
    cache copy** (`~/.claude/plugins/cache/shipwright/shipwright-plan/0.3.1`,
    no pre-existing `.venv`), not just the monorepo copy — a consumer runs
    from the cache, not from `plugins/shipwright-plan`, and that copy's
    first-run `uv sync` is a genuinely different code path than a warm
    monorepo `.venv`. Two back-to-back invocations both succeeded (exit 0),
    confirming no first-run or reentrancy failure.
  - Repo-wide grep for every `uv run.*external_review\.py` line confirmed
    the 9-site inventory is exhaustive — no other live invocation exists
    outside the files already listed; the remaining mentions found are
    prose (SKILL.md summaries, `CHANGELOG.md`, `architecture_brief.md`),
    none inside a `uv run` line.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Every `external_review.py` invocation block anywhere under `plugins/`+`shared/` carries `--project` (repo-wide scan, not a fixed allowlist) | tested | `shared/tests/test_external_review_project_flag.py::test_external_review_calls_pass_project_flag` — PASSED |
  | 2 | The scan finds exactly the known 9 invocation blocks — neither silently missing a site nor silently passing vacuously on 0 matches | tested | same test — `EXPECTED_TOTAL_BLOCKS == 9` sanity assertion, verified failing pre-fix |
  | 3 | `uv run --project <plan_plugin_root>` resolves `openai` from a directory with no `pyproject.toml` (the actual consumer-project failure mode), against BOTH the monorepo copy and the installed plugin-cache copy | tested | manual probes above, `openai 2.30.0`, exit 0 both times — not unit-testable without shelling `uv`, and the mechanism (`uv run --project`) is uv's own contract, not this repo's code |
  | 4 | Plain `uv run` (no `--project`) fails from the same no-`pyproject.toml` directory, confirming the bug is real outside this monorepo | tested | manual probe above, `ModuleNotFoundError`, exit 1 |
  | 5 | `sub-iterate-runner.md` declares `plan_plugin_root` as an Input parameter (consumer side of the new contract) | tested | `test_sub_iterate_runner_declares_plan_plugin_root_input` — PASSED |
  | 6 | `campaign-mode.md`'s runner spawn actually names `plan_plugin_root` in the brief (producer side — the consumer-side declaration alone would be undocumented-parameter theater) | tested | `test_campaign_mode_threads_plan_plugin_root_into_runner_spawn` — PASSED |
  | 7 | `sub-iterate-runner.md`'s existing contract tests still pass after adding the Input parameter (no drift) | tested | `plugins/shipwright-iterate/tests/test_sub_iterate_runner_contract.py` — 37/37 PASSED |
  | 8 | The canonical `uv run --project` failure-handling note ("not a completed review, record `not_run`") exists in iteration-reviews.md, so every other call site's pointer to it resolves to something real | tested | `test_canonical_failure_handling_note_exists` — PASSED |
  | 9 | `external_review.py`'s own module docstring usage example also shows `uv run --project` — a 10th, undiffed mention outside the *.md scan (a `.py` file, prose `<...>` placeholder, not caught by the markdown-only walk) | tested | `test_external_review_docstring_shows_project_flag` — PASSED |
- **Confidence-pattern check:** Asymptote — the "is `--plugin-root` also
  broken?" question was probed empirically against the script source
  rather than assumed; it resolved to "no, inert for these modes," so no
  further probe needed there. Coverage — every AC above has a `tested`
  row; 0 untested-testable.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `cd shared/tests && uv run pytest test_external_review_project_flag.py -v`,
  plus the manual `uv run --project` probes recorded in Confidence
  Calibration (both the monorepo and the installed plugin-cache copy, each
  from a directory with no `pyproject.toml`).
- **Evidence path:** pytest output above (5 test functions, all PASSED);
  probe transcripts inline in this spec.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Diagnosis, fix shape, and reproduce-then-fix probe design
  are correct; the run promoted `{plan_plugin_root}` from inert to
  load-bearing without a resolution rule, a failure branch, or a
  producer-side test.
- **Findings:**
  1. (high) `{plan_plugin_root}` undefined resolution + no failure branch
     — **fix**: added the canonical resolution + failure-handling note to
     `iteration-reviews.md`, pointed to from every other call site;
     extended `sub-iterate-runner.md`'s Branch B to cover a `uv run`
     failure the same way as `missing_keys`.
  2. (medium) No handling for `uv run` itself failing — **fix**: folded
     into finding 1's fix (same note covers both).
  3. (medium) Producer side (`campaign-mode.md` brief) untested —
     **fix**: added `test_sub_iterate_runner_declares_plan_plugin_root_input`
     + `test_campaign_mode_threads_plan_plugin_root_into_runner_spawn`.
  4. (medium) Fixed-file allowlist test inverts the guard — **fix**:
     rewrote as a repo-wide scan of `plugins/`+`shared/` with a total-count
     sanity assertion, confirmed (by grep) to add no false positives from
     the ~15 historical/prose mentions elsewhere in the repo.
  5. (medium) PEP 723 inline script metadata is a stronger alternative —
     **disclose**: recorded in Out of Scope with the reason (crosses more
     surface than this prose fix; deferred alongside the httpx item).
  6. (medium) Probes only ran against the monorepo copy, not an installed
     plugin-cache dir — **fix**: re-ran both probes against
     `~/.claude/plugins/cache/shipwright/shipwright-plan/0.3.1`, confirmed
     working including a from-cold first invocation.
  7. (low) `docs/guide.md:1516` same bug class, different script,
     unaddressed — **disclose**: recorded in Out of Scope, flagged as a
     follow-up card rather than silently expanding this one.
  8. (low) Quoting asymmetry on shipwright-plan's 3 pre-existing sites —
     **originally declined** (for this diff) as part of a broader
     repo-wide unquoted-`{plugin_root}` convention (14 sites across 7
     shipwright-plan files, most for unrelated scripts). **Reversed to
     fix** after the External Plan Review below (see) — both external
     reviewers independently raised the identical point, arguing these 3
     are exactly the invocations this diff already targets, not an
     unrelated sweep. Now quoted; the other ~11 unrelated-script sites
     remain a genuinely separate follow-up.
  9. (low) `check-external-review-keys.py` inconsistently lacks
     `--project` next to a call that now has it — **decline**: verified
     that script imports only stdlib + `external_review_config` (also
     stdlib-only), so it structurally needs no `--project`; the asymmetry
     is correct, not a defect. No action.
  10. (low) Verification/Spec Impact under-claim the evidence gathered;
     no CHANGELOG drop planned — **fix**: Verification reclassified
     `none` → `cli` with the probe evidence above; F4 (mandatory at every
     complexity) will add the CHANGELOG drop during finalization.
- **Known limitations:** none beyond the declined items 8-9 above (each
  has its own stated reason, not a disclosed gap).
- **Status:** 8 fixed, 2 declined (with reason), 0 unaddressed.

## External Plan Review (Branch A, `--mode iterate`)
- **Ran:** yes (retrofitted after implementation — see Architecture
  Review's Known Limitation below; ideally runs during planning)
- **Verdicts:** deepseek=approve · openai=revise
- **Findings and dispositions:**
  1. (medium/openai) Quoting asymmetry on the 3 pre-existing
     `shipwright-plan` `external_review.py` sites — **fix**: quoted (see
     Internal Plan Review finding 8, reversed above); test regex now
     requires quotes on all 9 sites, not just the 6 newly-touched ones.
  2. (medium/openai, low/deepseek) `plan_plugin_root` producer coverage
     only tested for `campaign-mode.md` — **verified, no fix needed**:
     grepped the whole repo for `subagent_type="shipwright-iterate:
     sub-iterate-runner"` (the only way this subagent is spawned via the
     Agent/Task tool); `campaign-mode.md`'s step 3c is the sole hit. The
     other mention (SKILL.md's "hand-run sub-iterate" flag) runs the
     iterate skill directly as a session, not as a Task-spawned subagent,
     so it resolves `plan_plugin_root` ambiently like any standalone
     session resolves `plugin_root`/`shared_root` — no threading gap.
  3. (medium/openai) Cross-plugin documentation pointer from
     `shipwright-build`'s `code-review.md` to `shipwright-iterate`'s
     `iteration-reviews.md` — **already fixed** before this call ran (see
     code-reviewer's Stage 2 finding: `code-review.md` carries a
     self-contained inline note, not a cross-plugin pointer). Stale by
     the time this reviewer read the plan text.
  4. (medium/openai, medium/deepseek) `--project` value check must be
     context-sensitive (`{plugin_root}` only inside shipwright-plan,
     `{plan_plugin_root}` elsewhere), not "any recognized placeholder" —
     **already implemented** this way in `_invocation_defect`; the
     reviewers were reading the plan's prose description, which under-
     stated how the test actually discriminates by file path.
  5. (low/deepseek) Manual probes only ran `python -c "import openai"`,
     not the actual `external_review.py` script — **fix**: re-ran
     `uv run --project <target> .../external_review.py --help` from a
     scratch directory with no `pyproject.toml`, against both the
     monorepo copy and the installed plugin-cache copy; both exit 0.
  6. (low/deepseek) `REPO_ROOT` must derive from `Path(__file__)`, not
     `Path.cwd()`, or running from `shared/tests` would scan the wrong
     tree — **already implemented** this way (`Path(__file__).resolve()
     .parents[2]`); non-issue.
  7. (low/deepseek) The unquoted-`{plugin_root}` exception must not
     become a general allowance for *new* unquoted sites — **fix**: same
     as finding 1; quoting is now required (not optional) by the regex
     for every targeted site.
- **Status:** 3 fixed for real (1, 5, 7 — folding to the same underlying
  changes), 2 verified-already-correct (3, 4), 1 verified-not-a-gap (2),
  0 declined.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-18-external-review-project-flag/architecture_brief.md`
- **Verdicts:** deepseek=reject · openai=reject
- **Smallest thing that would do (per reviewers):** PEP 723 inline script
  metadata (`# /// script` block declaring `openai`) directly on
  `external_review.py`, replacing all 9 call-site `--project` edits, the
  `plan_plugin_root` threading into `sub-iterate-runner.md`, and the
  repo-wide regression scan with one dependency declaration colocated with
  the script.
- **Findings:** both reviewers, independently and via the bias-avoiding
  brief (no rejection rationale shown), converged on the same
  simpler-alternative finding (openai: medium; deepseek: high) — the
  `--project`/`plan_plugin_root` approach creates a permanent cross-plugin
  data-flow contract and a maintained call-site inventory to solve a
  problem PEP 723 solves in one file, with no caller-side changes at all.
- **Reconciliation — declined, with reason (this run):** This exact
  alternative was already surfaced and explicitly deferred **before** this
  run began — the initiating bug card named PEP 723 by name and this
  spec's Out of Scope recorded it as "a genuinely stronger alternative...
  but a dependency-declaration-mechanism change to a shared script crosses
  more surface (and this file's own bloat baseline) than a prose fix;
  deferred alongside the httpx item, not adopted here." Internal Plan
  Review (finding 5, above) independently raised the identical point and
  it was disclosed, not declined blind. The Architecture Review pass ran
  out of its intended sequence in this run — retrofitted after
  implementation, spec-review (4 rounds), Internal Plan Review, code
  review, and the full test suite were already complete, rather than
  during planning where a `reject` is meant to be seen "while the code
  does not yet exist." Rearchitecting now would restart the whole cascade
  on a materially different, larger-surface fix. **Decision: keep the
  implemented `--project`/`plan_plugin_root` fix as-is; do not rework.**
  PEP 723 remains a real, independently-corroborated future improvement —
  flagged for the user's attention in the F12 summary and left as a
  candidate follow-up card, not silently dropped. **Known limitation of
  this run:** the Architecture Review call should have run during
  planning, before Step 6; running it this late defeated its "ask before
  building" purpose. Noted so a future run does not repeat the ordering
  mistake.
