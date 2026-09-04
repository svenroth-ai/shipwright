# Iterate Spec: review-scratch-path

- **Run ID:** iterate-2026-09-03-review-scratch-path
- **Type:** bug
- **Complexity:** medium (escalated from Stage-1 `small` — see Complexity Escalation below)
- **Status:** implemented

## Goal
Fix a Windows-only bug in the code-review pipeline: a bash step writes the
diff to a bare `/tmp/shipwright-review-diff.txt` path, and a `uv run` Python
CLI reads it back via `--diff-file /tmp/shipwright-review-diff.txt`. On
Windows, Git-Bash (MSYS) and native Python resolve that literal string to two
different physical files, so the Python side silently reads a stale or
missing diff instead of erroring. Same pattern affects
`/tmp/campaign_units.json` in campaign-mode.md.

## Root Cause (F-debug Phase 4)
`/tmp/<name>` is not one location on Windows: Git-Bash mounts `/tmp` onto
`%TEMP%` (confirmed via `mount`: `.../AppData/Local/Temp on /tmp`), while a
bare leading `/` given to a native Windows Python process resolves against
the *current drive's root* (confirmed: `open('/tmp/x','w')` → `C:\tmp\x`) —
unrelated to `%TEMP%`. Both operations succeed with no error on either side,
so a write from bash and a read from `uv run` Python silently touch two
different files whenever the skill instructions hand a bare `/tmp/...`
string across that boundary.

- **Error text:** none — this is a silent-corruption bug, not a crash. The
  downstream symptom previously seen (memory `feedback_tmp_path_diverges_bash_vs_python`,
  2026-08-01) was a confusing schema error from `record_review_pass.py`
  ("payload has no 'review' key") caused by reading a stale file, not the
  real cause.
- **Reproduction (100%, this session):** `python -c "open('/tmp/x','w')..."`
  then Bash-tool `cat /tmp/x` → `No such file or directory`; `mount` shows
  Bash's `/tmp` → `%TEMP%`, disjoint from Python's drive-root resolution.
  Deterministic on any Windows host running Git-Bash + a native (non-MSYS)
  Python/`uv run` interpreter.
- **Recent changes:** not a regression from a recent Shipwright commit — this
  is a structural property of Windows + Git-Bash + native Python coexisting
  on one machine, present since `/tmp/shipwright-review-diff.txt` was first
  used as a bash→python handoff in the review-cascade skill instructions.
- **Boundary:** the write (`git diff HEAD > /tmp/...`, a Bash-tool `>`
  redirect) and the read (`uv run ... --diff-file /tmp/...`, a native Python
  `open()`) are two independent path resolutions of the same literal string
  — the boundary is exactly the tool switch from Bash to `uv run`.

## Acceptance Criteria
- [x] A shared helper (`shared/scripts/lib/review_scratch.py` +
      `shared/scripts/tools/review_scratch.py` CLI) resolves a run-scoped
      scratch path outside the repo tree and outside the OS's
      world-readable temp root (reuses `host_resource_lease.py`'s hardened
      private-root primitives), deterministically from `(run_id, name)` —
      revised from "resolve once into a shell var" after the internal plan
      review showed a Bash tool call is a fresh shell: each site
      independently re-invokes `resolve`, landing on the identical path.
- [x] `resolve(run_id, name)` returns
      `<private_shipwright_base>/review-scratch-v1/<run_id>/<name>`,
      validating both components and creating the parent dir if missing;
      `cleanup(run_id)` removes that run's subdirectory (validated,
      containment-checked before `rmtree`) and is a no-op if it does not
      exist. No self-healing sweep — see Architecture Review below; cleanup
      is explicit-only, and a leftover file in this private, ACL-hardened
      root is a non-problem.
- [x] The 4 affected skill/agent files that still cross the bash/Python
      boundary with a file (`code-review.md`, `code-review-protocol.md`,
      `iteration-reviews.md`, `sub-iterate-runner.md`) resolve the scratch
      path independently at each write/read site (never a shell variable
      across separate Bash tool calls) and `cleanup` is called exactly once,
      as the true final step of each flow (success and failure path). On the
      build side that is `code-review.md`'s 6c step, not
      `code-review-protocol.md`'s Step 6b — a doubt-reviewer (Stage 3)
      finding this run caught 6b's own doc originally also calling `cleanup`,
      which would have deleted the diff file 6c still needed to reuse;
      fixed by making `code-review.md` the sole cleanup owner for the build
      flow. `campaign-mode.md`'s
      `campaign_units.json` handoff instead switched to a direct pipe
      (`campaign_progress.py list-units | autonomous_loop.py init
      --units-from -`) — no scratch file, no `review_scratch.py` call, per
      the Architecture Review reconciliation below.
- [x] `docs/guide.md`'s description of `/tmp/shipwright-review-diff.txt`
      is updated to describe the resolved-path mechanism.
- [x] A guard test fails CI if any `plugins/*/skills+agents/**/*.md` or
      `shared/prompts/**/*.md` file contains a bare `/tmp/` path literal
      again (confirmed RED before the doc edits, GREEN after).
- [ ] Post-merge: `bash scripts/update-marketplace.sh` +
      `uv run scripts/check_plugin_cache_sync.py --strict` (needs `main`
      fast-forwarded to the merged commit — cannot run pre-merge).

## Spec Impact
- **Classification:** none
- **NONE justification:** this is an internal fix to the code-review
  pipeline's own file-handoff mechanism (skill instructions + a shared
  script), not a user-visible capability described in any FR. No `spec.md`
  row documents `/tmp/shipwright-review-diff.txt` as a contract.

## Out of Scope
- Not fixing the general Bash-tool-vs-native-Python `/tmp` divergence itself
  (that is Claude Code / Anthropic's harness behavior, not something this
  repo's code can change) — only Shipwright's own hardcoded uses of it.
- Not sweeping every `/tmp/` reference repo-wide (tests using `/tmp/...` as
  an inert mock path string, e.g. `test_deliver_pr*.py`, are unaffected —
  they never cross a real bash/python boundary).

## Design Notes
n/a — no UI, no target-app design surface. This is a framework-internal
pipeline fix.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| Bash `git diff HEAD > "$(review_scratch.py resolve --run-id {id} --name shipwright-review-diff.txt)"` (code-review.md, code-review-protocol.md, iteration-reviews.md, sub-iterate-runner.md) | `uv run external_review.py --diff-file "$(review_scratch.py resolve --run-id {id} --name shipwright-review-diff.txt)"` (Python, independent re-invocation — deterministic, so identical) | plain-text diff file — `{id}` is `{run_id}` in the iterate-side docs (iteration-reviews.md, sub-iterate-runner.md), which already bind it, and `{SHIPWRIGHT_SESSION_ID}` in the build-side docs (code-review.md, code-review-protocol.md), which have no `run_id` concept of their own — a Stage-2 code-reviewer finding (this run) caught the original text using the unbound `{run_id}` on the build side |
| `review_scratch.py resolve` stdout (Python, prints the resolved path) | Bash command substitution `"$(...)"` at the call site | plain-text absolute path string |
| `uv run campaign_progress.py list-units` stdout (Python, campaign-mode.md) | `uv run autonomous_loop.py init --units-from -` stdin, same shell pipe (Python) | JSON, no file, no `review_scratch.py` call — see Architecture Review below |

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** The diagnosis was correct but the original mechanism (resolve
  once into a shell variable, reuse for write+read) does not work — a Bash
  tool call is a fresh shell, and the write/read sites are separate calls in
  3 of the 5 files. Also: unvalidated `rmtree` input, a two-root test runner
  command `pytest` refuses, and a reinvented (less safe) temp-dir helper
  when the repo already has a hardened one.
- **Findings:**
  - [high/architecture] shell-var-across-bash-calls is broken → **fixed**:
    inline `$(review_scratch.py resolve ...)` independently at every write
    and read site (deterministic, so safe to recompute).
  - [high/security] unvalidated `run_id`/`name` → `rmtree` → **fixed**:
    strict regex validation + parent-containment assertion + reparse-point
    rejection before any delete.
  - [high/completeness] two-root pytest command (`shared/scripts/tests` +
    `shared/tests`) → **fixed**: both test files live under
    `shared/scripts/tools/tests/` (one root, matches the tools/ convention).
  - [medium/security] reinvented insecure temp dir → **fixed**: reuses
    `host_resource_lease.py`'s hardened private-root primitives (extracted
    into `_private_shipwright_base()`) instead of `tempfile.gettempdir()` +
    `os.makedirs`.
  - [medium/architecture] cleanup unenforceable via prose alone → **fixed**:
    `resolve()` also runs a best-effort sweep of stale (>24h) run
    directories, so a skipped explicit cleanup self-heals.
  - [medium/completeness] guard test too narrow + self-colliding on its own
    remediation prose → **fixed**: scoped to `plugins/*/skills+agents` +
    `shared/prompts`, and the regex excludes the `/tmp/...` (three literal
    dots) illustrative shorthand this fix's own prose uses.
  - [medium/completeness] missing marketplace-sync / hooks-doc / changelog
    follow-through → **disclosed** for hooks-and-pipeline.md (this change
    touches no hook, phase, validator, or startup read — the artifact-write
    matrix is unaffected since the diff file was never a tracked artifact);
    **fixed** for marketplace-sync (tracked as a post-merge AC below, since
    `check_plugin_cache_sync.py --strict` needs `main` fast-forwarded first);
    changelog drop is F4's normal job, not a plan gap.
  - [medium/completeness] subprocess test invisible to diff-coverage →
    **fixed**: in-process unit tests cover `resolve`/`cleanup`/validation/
    sweep directly; exactly one thin subprocess test remains as the
    cross-process contract pin.
  - [medium/architecture] concurrency run-scoping unspecified → **fixed**:
    every call site keys off the innermost run's own id (`{run_id}` per
    sub-iterate, `{slug}` for campaign init) — already the existing
    convention in `sub-iterate-runner.md`, not a new design; disjointness
    is unit-tested.
  - [low/architecture] `tempfile.gettempdir()` env-drift between resolve
    and cleanup → **disclosed**: `_private_shipwright_base()` already fails
    closed (raises) on an untrusted `TMPDIR`/`TEMP`/`TMP` override rather
    than silently diverging — a stronger mitigation than recording the
    resolved root, so no extra override flag was added.
  - [low/security] f-string-into-shell in the proposed test → **fixed**:
    list-form `subprocess.run`, no `shell=True`, throughout.
  - [low/completeness] no space-in-path test → **fixed**: added.
  - [low/performance] extra `uv run` cold starts / `--project` risk →
    **fixed**: `review_scratch.py` is stdlib-only, documented in its module
    docstring, no `--project` needed.
- **Known limitations:** none beyond the two `disclosed` items above.
- **Status:** 12 fixed, 2 disclosed, 0 declined

## Confidence Calibration
- **Boundaries touched:** the three producer/consumer pairs in "Affected
  Boundaries" above.
- **Empirical probes run:**
  - Reproduced the root-cause divergence live (this session, pre-fix):
    Python `open('/tmp/x','w')` → `C:\tmp\x`; Bash-tool `cat /tmp/x` on the
    same nominal path → `No such file or directory` (`mount` showed Bash's
    `/tmp` → `%TEMP%`, disjoint from Python's drive-root resolution).
  - `shared/scripts/tools/tests/test_review_scratch.py` — 20 in-process
    unit tests (determinism, disjointness, round-trip, cleanup x2, 8 unsafe
    `run_id` rejections, 5 unsafe-`name` rejections, unsafe-`run_id` cleanup
    rejection, space-in-path) + 1 cross-process contract test spawning two
    independent `uv run` processes and asserting they resolve the identical
    path and share written content — all PASSED.
  - `shared/scripts/tools/tests/test_review_scratch_guard.py` — 2 tests;
    confirmed RED before the 5 skill-doc edits (caught all 11 pre-fix
    `/tmp/` literals), GREEN after — PASSED.
  - Re-ran the pre-existing `host_resource_lease`/`_host_resource_locking`/
    `_windows_acl` suite (43 passed, 8 skipped — platform/privilege gated)
    to confirm the `_private_shipwright_base()` extraction is
    behavior-preserving.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `resolve(run_id, name)` is deterministic (same input → same path) | tested | `test_resolve_is_deterministic` PASSED |
  | 2 | `resolve` is disjoint across distinct run_ids | tested | `test_resolve_disjoint_across_run_ids` PASSED |
  | 3 | A file written at the resolved path is readable back at it | tested | `test_resolve_round_trips_content` PASSED |
  | 4 | `cleanup(run_id)` removes the run's scratch directory | tested | `test_cleanup_removes_run_directory` PASSED |
  | 5 | `cleanup` on a never-created run_id is a no-op | tested | `test_cleanup_on_missing_run_id_is_a_noop` PASSED |
  | 6 | Unsafe `run_id` values are rejected (traversal, empty, separators, overlong) | tested | `test_resolve_rejects_unsafe_run_id` x8 PASSED |
  | 7 | Unsafe `name` values are rejected | tested | `test_resolve_rejects_unsafe_name` x5 PASSED |
  | 8 | `cleanup` rejects an unsafe `run_id` before touching disk | tested | `test_cleanup_rejects_unsafe_run_id` PASSED |
  | 9 | A temp root containing a space in its path still works | tested | `test_resolve_survives_a_space_in_the_temp_root` PASSED |
  | 10 | Two independent processes resolving the same `(run_id, name)` land on the identical path and see each other's writes (the actual regression pin) | tested | `test_cli_resolve_is_stable_and_content_survives_across_two_processes` PASSED |
  | 11 | No skill/agent doc contains a bare `/tmp/` path literal | tested | `test_no_bare_tmp_path_literal_in_review_pipeline_docs` PASSED (was RED pre-fix) |
  | 12 | The guard's own glob scope is non-empty (doesn't silently pass on nothing) | tested | `test_scanned_globs_actually_match_something` PASSED |
  | 13 | `_private_shipwright_base()` extraction preserves `host_resource_lease`'s existing behavior | tested | 43 passed / 8 skipped, pre-existing suite, unmodified assertions |
  | 14 | The Windows-specific bash-vs-Python divergence itself (Git-Bash `/tmp`→`%TEMP%` vs. Python `/tmp`→drive-root) | untestable | `requires-external-nondeterministic-service` — CI runs Linux, where this specific divergence cannot occur; pinned instead via the platform-agnostic contract test (#10) plus the live manual reproduction recorded above |
  | 15 | `campaign_progress.py list-units`'s JSON output, piped through stdin, composes correctly with `autonomous_loop.py init --units-from -` (the `cross_component` Integration Coverage for the post-Architecture-Review pipe) | tested | `shared/tests/test_campaign_units_stdin_pipe_integration.py::test_list_units_piped_into_init_composes` PASSED — real subprocess pipe, two units, asserts `state["units"]` ids match |
  | 16 | The pre-existing serial-strategy `cmd_next`/`cmd_record` composition still passes after the `_load_units_from`/`cmd_init` stdin change | tested | `shared/tests/test_campaign_serial_composition_integration.py::test_serial_subiterate_composes_on_prior_merge` PASSED (file-path `--units-from` path, unaffected by the additive stdin branch) |

- **Confidence-pattern check:** asymptote — the internal plan review already
  surfaced a genuine "yes, confident" → high-severity-finding cycle once
  (the original shell-var design), and the Architecture Review surfaced a
  second one (the self-healing sweep, "confident" it was a good idea, was
  dropped once both external reviewers converged on it being disproportionate
  complexity for a non-problem); every fixable finding across both cycles was
  addressed and re-verified via the test suite above, no "confident" claim
  went unchecked twice. Coverage — all 16 ledger rows are
  `tested`/`untestable` with 0 untested-testable.

## External Plan Review (GLM + OpenAI, via OpenRouter — Codex CLI unauthenticated, fell back)
- **Verdicts:** glm=approve, openai=revise (no contradiction — within one
  step, `contradiction.requires_resolution: false`)
- **Root cause of the split:** both reviewers were handed the mini-plan file,
  which at review time still described the ORIGINAL (shell-var,
  `tempfile.gettempdir()`, unvalidated `rmtree`) design that the Internal
  Plan Review above had already superseded before this call ran — the
  mini-plan was never synced after that revision. openai's 3 "high" findings
  and glm's finding #1 (medium) are the same root issue read two ways: a
  stale planning artifact, not a defect in the shipped code or docs (which
  glm partly cross-checked against the Confidence Calibration evidence and
  scored `approve` despite the same staleness).
- **Findings:**
  - [high, openai] shell-var handoff still described → **fixed**: mini-plan
    now carries a superseded-banner pointing to this section as
    authoritative; the implementation never used a cross-call shell var.
  - [high, openai] `tempfile.gettempdir()` insecure base described →
    **fixed**: same — mini-plan staleness; implementation already reuses
    the hardened `host_resource_lease.py` private root.
  - [high, openai] unvalidated `rmtree`/`ignore_errors=True` described →
    **fixed**: same — mini-plan staleness; implementation already validates
    + containment-checks before any delete, no `ignore_errors`.
  - [medium, openai] stale-sweep not in mini-plan → **fixed**: mini-plan
    banner + corrected file table now point at the actual (swept) design.
  - [medium, openai] guard test placement/scope stale in mini-plan →
    **fixed**: mini-plan file table corrected to the actual single-root
    path + scope.
  - [medium, openai] integration-test fallback (`bash -c` interpolation)
    described → **disclosed**: that fallback was never implemented; the
    shipped test is one thin list-form-`subprocess.run` contract test, no
    shell interpolation. Mini-plan step 3's stale prose is covered by the
    superseded banner rather than being rewritten line-by-line.
  - [medium, glm] mini-plan stale vs. spec → **fixed** (see above).
  - [medium, glm] iterate spec's Verification runner command still named
    the pre-fix two-root path → **fixed**: corrected to
    `shared/scripts/tools/tests/{test_review_scratch,test_review_scratch_guard}.py`.
  - [low, glm] failure mode shifts from silent-stale-read to loud-fail at
    the resolve step → **disclosed**: correct direction (fail-closed), and
    the reasoning is already recorded in this spec's Root Cause section;
    not repeated in the skill docs to avoid pushing already-line-capped
    files (`sub-iterate-runner.md` is at its exact 497-line ADR-119 ceiling)
    over budget for a restatement.
  - [low, glm] CWD assumption for invoking `review_scratch.py` unpinned in
    the boundary table's schematic example → **disclosed**: the actual 5
    skill-doc edits all use the same `"{shared_root}/scripts/tools/..."`
    template already used for `external_review.py` in the same docs, so
    this is a spec-table simplification, not an implementation gap.
  - [low, glm] `resolve()`'s sweep is a surprising side effect for its name
    → **fixed**: documented in the module docstring.
  - [low, glm] guard failure message should point at the sanctioned
    alternative → **no_change_needed**: already does
    ("Use shared/scripts/tools/review_scratch.py resolve instead").
  - [low/informational, glm] post-merge marketplace-sync AC → **disclosed**:
    already tracked as an open AC, ordering already correct.
- **Status:** 8 fixed, 5 disclosed, 1 no_change_needed, 0 declined. No
  finding named an actual defect in the shipped code, docs, or tests — all
  resolved to the mini-plan/spec sync gap, now closed.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-03-review-scratch-path/architecture_brief.md`
  — 4 options laid out without a stated preference: A (shared resolver both
  sites call independently, as shipped), B (Python consumers accept
  `--run-id`/`--name` or generate the data in-process, no path string ever
  crosses the bash/Python boundary), C (in-repo gitignored scratch dir), D
  (do nothing).
- **Verdicts:** openai=revise (medium), glm=revise (high) — no contradiction,
  both prefer Option B over the shipped Option A.
- **Smallest thing that would do (per reviewers):** both reviewers pointed at
  the same two boundaries as avoidable: `external_review.py` could run
  `git diff HEAD` itself instead of reading a handed-off file, and
  `autonomous_loop.py init` could take the campaign units list via stdin
  pipe or import instead of a scratch file — both producer and consumer are
  same-shell Python CLIs already, so B costs nothing there. Both also flagged
  the stale-run sweep inside `resolve()` as disproportionate: a destructive,
  age-guessed `rmtree` side effect of path *resolution*, buying only the
  absence of small leftover files in an already-private, ACL-hardened
  per-user directory.
- **Findings:**
  - [high/simpler-alternative, glm] Option A standardizes the boundary
    crossing instead of eliminating it; both handoffs in the boundary table
    are Python-reachable without a shared file.
  - [medium/simpler-alternative, openai] the repo-wide `/tmp/` guard
    forecloses legitimate bash-only or single-runtime `/tmp` uses outside
    the 5 review/campaign docs it was scoped to.
  - [medium/proportionality, glm] the stale-sweep patches a mechanism
    (unenforceable prose cleanup) with another mechanism (a destructive,
    age-guessed `rmtree`) rather than removing the need for cleanup.
  - [low/existence, glm] the `/tmp/` guard tripwires the one literal that
    bit, not the class (a `$TMPDIR/x` or drive-root path in future prose
    passes silently) — accepted as a known, narrow limitation; not worth a
    broader detector for a single historical incident.
- **Reconciliation (user-approved, "Teilweise übernehmen"):**
  - **Adopted Option B** for the `campaign_units.json` boundary:
    `campaign-mode.md` now pipes `campaign_progress.py list-units` directly
    into `autonomous_loop.py init --units-from -` (stdin sentinel). No
    scratch file, no `review_scratch.py` call for this boundary at all —
    the AC and Affected Boundaries table above reflect this.
  - **Kept Option A** for the 4 diff-file boundaries, against the
    reviewers' recommendation, for a reason specific to this pipeline that
    the openai/glm brief did not have visibility into: the external review
    cascade (Branch A/B/C) must see the *same frozen diff snapshot* the
    internal `code-reviewer` subagent already reviewed. If
    `external_review.py` ran `git diff HEAD` itself, it would run *after*
    the internal reviewer's auto-fixes have already landed on disk, showing
    a different (smaller, already-remediated) diff than what was actually
    reviewed internally — silently breaking the cascade's "does the
    external reviewer see what the internal one saw" invariant. A
    file-based snapshot, resolved deterministically by both the bash writer
    and the Python reader, is the smallest thing that preserves that
    invariant; `git diff HEAD` re-run in-process is not equivalent to it.
  - **Dropped the stale-run sweep** entirely, per both reviewers' alignment
    that it was disproportionate: `_sweep_stale` and `_STALE_SECONDS`
    removed from `review_scratch.py`; `resolve()` is now pure path
    resolution with no side effect. Cleanup stays explicit-only via the
    `cleanup()` calls already at the end of each flow (success and failure
    path) — a skipped cleanup leaves an inert file in a private,
    ACL-hardened, per-user directory, which is a non-problem, not a target
    for garbage collection.
  - The repo-wide-guard finding was **re-opened and fixed** during the
    Stage-3 `doubt-reviewer` pass, correcting this bullet's original,
    inaccurate rebuttal. The reconciliation above claimed the guard's glob
    (`plugins/*/skills/**`, `plugins/*/agents/**`, `shared/prompts/**`) was
    "scoped to the 5 originally-affected doc trees, not repo-wide" — that
    was factually wrong: those three globs match 217 files across every
    plugin's skills+agents trees (203 + 11 + 3), not 5. `doubt-reviewer`
    demonstrated a live false-positive risk from the guard's own regex
    (`/tmp/` as an unanchored substring match): `/var/tmp/cache` — a
    legitimate, unrelated path — trips it. Fixed by tightening the regex to
    `(?<![\w/])/tmp/(?!\.\.\.)`, requiring `/tmp/` to be the ROOT of an
    absolute path (as every real instance of this bug's pattern always is)
    rather than a substring of a longer, unrelated path — closing the false
    positive while keeping the guard's breadth (every skill/agent doc,
    future ones included) intact, since narrowing to a fixed file list
    would defeat the guard's whole purpose of catching a *future* doc that
    reintroduces this exact bash/Python handoff pattern.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run pytest shared/scripts/tools/tests/test_review_scratch.py shared/scripts/tools/tests/test_review_scratch_guard.py -v`
  (one test root) and, separately (a different root — the repo's
  one-root-per-invocation rule),
  `uv run pytest shared/tests/test_campaign_units_stdin_pipe_integration.py shared/tests/test_campaign_serial_composition_integration.py -v`.
- **Evidence path:** `shipwright_test_results.json.iterate_latest.surface_verification`
