# Iterate Spec: campaign-worktree-guard

- **Run ID:** iterate-2026-08-26-campaign-worktree-guard
- **Type:** bug
- **Complexity:** medium (cross_component: `campaign-mode.md` and
  `sub-iterate-runner.md` are both named in SKILL.md's `cross_component`
  file-pattern set — "campaign drain (`autonomous_loop`, `campaign_*`,
  `campaign-mode.md`)")
- **Status:** implemented
- **Trigger:** user report — "es sieht so aus als ob Subrunner in a campaign
  keinen worktree machen und dann ihr zeug direkt auf Main mergen" — confirmed
  live in two campaigns where a sub-iterate-runner mutated branches in the
  main repository checkout.

## Goal

A campaign sub-iterate-runner "works on the project directly (no worktree)"
by design — it reuses whatever directory the orchestrator hands it, rather
than calling `setup_iterate_worktree.py` itself. Nothing previously gave the
campaign orchestrator a worktree of its own to hand down, and nothing
verified the directory a runner received was actually isolated. Root-cause
both gaps and close them without requiring a worktree PER sub-iterate (the
interleaved-serial design shares one branch-hopping worktree across a
campaign's whole lifetime, by existing convention — `docs/hooks-and-pipeline.md`
already documented this for decision-drops before this fix).

## Acceptance Criteria

- [x] The campaign orchestrator gets one worktree, keyed to the campaign
  slug (not the session), created or resumed before anything else.
- [x] Every `sub-iterate-runner` spawn is preceded by a location check that
  STRICT-STOPs the loop rather than spawning into an unverified directory.
- [x] The runner itself independently refuses to touch git if its own
  `{project_root}` is not isolated (defense in depth — a spawned subagent's
  shell is not guaranteed to inherit the orchestrator's `cd`).
- [x] Every git command inside `sub-iterate-runner.md` is anchored to
  `{project_root}` (`git -C`), never bare — the actual mechanism by which a
  drifted cwd previously reached `main`.
- [x] The new check has no dependency on a Step-1 snapshot/`run_id` (a
  campaign sub-iterate never has one) and must never misread campaign step
  3h's own deliberate main-tree write as a leak.
- [x] `docs/hooks-and-pipeline.md` documents the new mechanism (CLAUDE.md
  rule: a between-phase-action change requires the same-diff update).

## Spec Impact

- **Classification:** none
- **NONE justification:** this is process/tooling enforcement inside the
  Shipwright framework itself (campaign orchestration), not a change to any
  target-project-facing requirement; there is no FR describing campaign
  worktree isolation for the framework's own behavior.

## Out of Scope

- Per-sub-iterate worktrees (rejected — the interleaved-serial design
  deliberately shares one worktree per campaign so shared-file/snapshot
  edits compose without a merge-theater drain; see `campaign-mode.md` →
  "Why interleaved-serial").
- Hardening the orchestrator's OWN git calls in 3f-bis/3g with `-C` — those
  run in the orchestrator's continuous session (cwd persists across its own
  sequential Bash calls, unlike a freshly spawned subagent), and the
  reported incident was specifically the *runner* landing in main, not the
  orchestrator.
- Rewriting the shared F0–F6 finalization reference docs (`F6.md`, etc.) to
  add `-C` throughout — they are correct as written for a standalone iterate
  (cwd IS the worktree there); the runner's own `cd "{project_root}"` at Step
  1.0 makes that assumption true for it too, without touching shared docs
  read by both flows.

## Root Cause

Two independent gaps, both structural:

1. **No campaign worktree existed to hand down.** `campaign-mode.md`'s
   Autonomous Campaign Loop never called `setup_iterate_worktree.py` under a
   campaign-scoped identity — it relied entirely on the orchestrating
   `/shipwright-iterate` session's own generic B1a worktree isolation, which
   is keyed to whatever slug that session happened to start with, not to the
   campaign. A resumed campaign session, or one that started at the bare repo
   root for any reason, had nothing campaign-specific to re-enter.
2. **Nothing verified isolation before or during a spawn.** The F0/F11
   leak-guard (`check_iterate_isolation.py`) exists but is unusable here: it
   requires a Step-1 snapshot keyed by `run_id`, and a campaign sub-iterate
   mints its own `run_id` (loop step 3b) but never calls
   `setup_iterate_worktree.py` for it — the snapshot would never exist, so
   the guard would hard-fail every sub-iterate closed for a reason unrelated
   to isolation. It also diffs the main tree for *any* new dirty path, which
   would misreport campaign step 3h's own deliberate main-tree write (the
   live-board `status.json`) as a leak. Compounding this,
   `sub-iterate-runner.md`'s own git commands were all bare (`git checkout
   -b`, `git push`, …) — safe only if the runner subagent's shell happens to
   start inside `{project_root}`, which is not guaranteed for a freshly
   spawned subagent.

## Fix

1. **`references/campaign-worktree.md` (new).** ONE worktree per campaign
   slug (`.worktrees/campaign-<slug>` on `iterate/campaign-<slug>`), set up
   or resumed at Autonomous Campaign Loop step 0 via the existing
   `setup_iterate_worktree.py` (its already-idempotent "already inside a
   worktree" branch handles the ensure-pointer-and-snapshot half). Documents
   the spawn guard and the runner's own defense-in-depth check.
2. **`lib.worktree_location.worktree_location_error`** (new module, split
   from `worktree_isolation.py` — that file was already at its bloat-baseline
   ceiling) +
   **`checks/check_worktree_location.py`** (new script) — a location-only
   isolation check: is `{project_root}` a worktree under
   `<main_root>/.worktrees/`, yes or no. Deliberately NOT the fuller
   `check_iterate_isolation.py`: no snapshot, no `run_id`, never diffs the
   main tree, so it is usable by a campaign sub-iterate (which has neither)
   and cannot misfire on step 3h's write.
3. **`campaign-mode.md`** — step 0 (worktree setup, before anything else)
   and step 3c (spawn guard, immediately before every spawn) both point at
   the new reference file; both are load-bearing STOP points, not advisory.
4. **`sub-iterate-runner.md`** — Step 1.0 runs the same check against its
   own `{project_root}` before touching git (refuses with
   `reason_code:"not_isolated"` on failure); every git command in the doc
   changed from bare to `git -C "{project_root}"`.
5. **`docs/hooks-and-pipeline.md`** — new "Campaign Worktree (2026-08-26)"
   paragraph after B1b, per CLAUDE.md's same-diff rule for a between-phase-
   action change.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `setup_iterate_worktree.py` (unchanged — reused, not modified) | `campaign-mode.md` step 0 (orchestrator) | worktree dir + JSON stdout |
| `worktree_location_error` / `check_worktree_location.py` (new) | `campaign-mode.md` step 3c (orchestrator, before every spawn) AND `sub-iterate-runner.md` Step 1.0 (runner, on itself) | exit code + `--json` payload |

## Confidence Calibration

- **Boundaries touched:** both rows above — the campaign orchestrator →
  runner `project_root` handoff, and the new check script's own CLI/exit
  contract.
- **Empirical probes run:**
  - Ran `worktree_location_error` against a real linked git worktree (via the
    `git_origin_repo` fixture) — round-trip, not a mock: empty string.
  - Ran it against the bare main repo of the SAME fixture — non-empty error
    naming `.worktrees/`, reproducing the exact incident shape (a runner
    handed the main checkout).
  - Ran it against an isolated worktree with a main-tree write made
    AFTERWARD (simulating campaign step 3h) — still empty, confirming no
    snapshot-diff false-positive (the reason `check_iterate_isolation.py`
    itself is unusable here).
  - Ran `check_worktree_location.py` as a real subprocess (matching how
    `campaign-mode.md` and `sub-iterate-runner.md` actually invoke it)
    against an isolated worktree that has NO Step-1 snapshot at all —
    green, confirming it does not inherit `check_iterate_isolation.py`'s
    snapshot dependency.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `worktree_location_error` returns `""` for an isolated worktree | tested | `test_worktree_location_error.py::test_worktree_location_error_empty_for_isolated_worktree` PASSED |
  | 2 | `worktree_location_error` flags the bare main repo checkout | tested | `test_worktree_location_error.py::test_worktree_location_error_flags_main_repo` PASSED |
  | 3 | a main-tree write after isolation never flips the verdict (no snapshot diff) | tested | `test_worktree_location_error.py::test_worktree_location_error_never_diffs_the_main_tree` PASSED |
  | 4 | `check_worktree_location.py` CLI allows an isolated worktree | tested | `test_check_worktree_location.py::test_allows_isolated_worktree` PASSED |
  | 5 | `check_worktree_location.py` CLI blocks the main repo checkout | tested | `test_check_worktree_location.py::test_blocks_the_main_repo_checkout` PASSED |
  | 6 (integration) | the CLI needs no Step-1 snapshot — real subprocess against a real freshly-created worktree with no snapshot file at all | tested | `test_check_worktree_location.py::test_does_not_require_a_run_id_snapshot` PASSED (real `git worktree add`, real subprocess invocation of the shipped script — the same call shape `campaign-mode.md`/`sub-iterate-runner.md` use, not a mocked import) |
  | 7 | existing `worktree_isolation.py` / `check_iterate_isolation.py` behavior unbroken by the new function | tested | `test_worktree_isolation_lib.py` (26/26) + `test_check_iterate_isolation.py` full suite PASSED |
  | 8 | `sub-iterate-runner.md` prose/doc-shape meta-tests still pass with every bare `git` command replaced by `git -C` | tested | `plugins/shipwright-iterate/tests/` full suite (948 passed, 1 skipped) — includes `test_sub_iterate_runner_contract.py`, `test_sub_iterate_runner_finalization.py`, `test_sub_iterate_runner_step_3_4.py`, `test_campaign_review_contract_prose.py` |
  | 9 | new/edited reference files stay within their runtime-prompt LOC ceilings (campaign-mode.md ≤400, sub-iterate-runner.md ≤497 per the ADR-119 exception, campaign-worktree.md well under 400) | tested | `test_skill_references_link.py::test_every_new_reference_under_loc_budget` + `test_sub_iterate_runner_step_3_4.py::test_runner_doc_within_bloat_ceiling` PASSED |

  0 untested-testable.

## Doubt Review (Stage 3, cross_component trigger)

Raised 4 doubts (2 high, 1 medium, 1 low):

- **cwd-persistence-across-Bash-calls (high) — rebutted.** Step 1.0's single
  `cd "{project_root}"` was doubted as unverified for the F4/F6 finalization
  prose that runs many separate Bash-tool calls later. Resolved by the Bash
  tool's own documented contract — cwd persists across every later command in
  the same session — not by a code change.
- **No cross-session lock on the shared campaign worktree (high) — deferred.**
  Two orchestrator sessions resuming the same slug can race
  `git checkout -b` in the one shared directory; nothing in this fix (or the
  existing `file_lock`, which only covers `loop_state.json`) prevents it.
  Real, but a pre-existing class of risk this fix does not invent — a
  standalone iterate's own resume path has never had a session lock either.
  Documented in `campaign-worktree.md`'s "Known limitations" section, filed
  as follow-up `trg-16bec646`.
- **Location-only guard, not identity (medium) — deferred.** A mis-threaded
  `project_root` pointing at a different, still-isolated worktree would pass
  unchanged. Out of scope: the reported incident was "landed on `main`",
  which this closes completely. Documented, filed as `trg-50bd22a1`.
- **bash/Python main-root computation duplication, submodule edge case (low)
  — accepted.** Shipwright's own monorepo is not a submodule deployment, so
  the divergent fallback path is unreachable here.

- **Confidence-pattern check:** asymptote — first pass, no prior "are you
  confident?" moment to re-probe; two rounds of probe-then-shrink were
  needed to fit the LOC ceilings without losing the safety-critical content
  (extracting rationale into the new `campaign-worktree.md` reference rather
  than deleting it), and the final probe (test suite green at the exact
  ceiling) found no further issue, so the boundary is calibrated. Coverage —
  every ledger row is `tested`, 0 `untestable`, count (9) exceeds the AC
  count (6). Integration composition (row 6, `cross_component` fired): a
  real subprocess invocation of the shipped CLI against a real git worktree,
  not a unit-level import/mock.
