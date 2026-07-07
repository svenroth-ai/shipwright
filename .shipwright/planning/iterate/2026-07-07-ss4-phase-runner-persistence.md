# Iterate: SS4 — Phase-runner subagent + result contract + artifact persistence

- **run_id:** iterate-2026-07-07-ss4-phase-runner-persistence
- **Campaign:** 2026-07-07-single-session-pipeline (sub-iterate **SS4**)
- **Sub-iterate spec:** `.shipwright/planning/iterate/campaigns/2026-07-07-single-session-pipeline/sub-iterates/SS4-phase-runner-persistence.md`
- **Intent:** FEATURE + embedded BUG-FIX (section-writer persistence)
- **Complexity:** medium (safety-floored — the diff carries `cross_component`:
  edits `**/hooks/*.py` + pipeline machinery, which the F11 verifier
  `check_integration_coverage` recomputes from the diff and hard-gates)
- **Risk flags:** `cross_component`, `touches_io_boundary`
- **Spec Impact:** ADD (new phase-runner agent, reload helper) + MODIFY
  (section-writer persistence path, apply-guard). Behavior-changing → not SIMPLIFY.

## Problem

SS1–SS3 built the single-session pipeline (result contract, loop-state, the
in-conversation orchestrator loop + CLI). Two gaps remain for SS4:

1. **No phase-runner subagent exists.** The loop skill briefs the subagent
   *inline* and merely *asks* it to persist to disk — persistence is not
   guaranteed. `plugins/shipwright-run/agents/` is empty.
2. **The `section-writer` persistence bug (live /shipwright-plan).**
   `section-writer.md` declares `tools: Read, Grep, Glob` — **no Write tool** —
   so it cannot persist its own output. Persistence is delegated entirely to a
   `SubagentStop` hook (`write-section-on-stop.py`) that scrapes the subagent
   JSONL transcript, guesses the section name by regex, infers the planning dir
   from an env var, and writes the file. This is a ~5-link fragile chain; in the
   live run the hook **did not fire** → the section output was **lost** and had
   to be written by hand. Worse: when a subagent *does* write directly, the
   hook's failure-to-scrape path returns `decision: block`, which would **block
   the subagent** even though its job succeeded.

## Root cause (bug)

Persistence-via-transcript-scraping-in-a-Stop-hook is inherently unreliable: it
depends on hook registration + matcher semantics + transcript flush timing +
content-format heuristics + output-path inference. Any single link breaking =
**silent data loss** (the subagent "succeeded" but produced no file). The
robust design (already stated in `result_contract.py`) is: **the subagent owns
persistence** — it writes real outputs to DISK via its own Write tool and
returns only a compact result; the orchestrator reloads from disk + summaries,
never from transcripts.

## Approach (decisions confirmed with Sven)

- **Section-writer fix:** give it a **Write path** (add `Write, Edit`) + a
  direct-write instruction, AND **harden the hook to a genuine fallback** — if
  the section file already exists on disk, treat as success (never `block`).
  (Write-path + hook-as-fallback, belt-and-suspenders.)
- **Phase-runner subagent:** new `plugins/shipwright-run/agents/phase-runner.md`
  with a write path (`Read, Write, Edit, Bash, Grep, Glob`), generic-briefed
  per phase, that persists real outputs to disk and returns only the contract.
- **Orchestrator persistence GUARD (the enforcement):** `apply_phase_result`
  verifies every artifact an `ok:true` result claims actually exists on disk;
  a claim without a file is rejected fail-closed (`artifacts_missing`, no
  completion). This closes the whole *silent-loss* class at the loop level.
- **Reload from run_config + summaries:** new pure `single_session/
  orchestrator_context.py` rebuilds orchestrator state from `phase_tasks[].result`
  summaries (never transcripts), bounded by `MAX_SUMMARY_CHARS` (context-budget
  guard).

## Acceptance Criteria (from sub-iterate spec)

- [ ] AC1 — phase-runner persists artifacts reliably (fixture proof)
- [ ] AC2 — section-writer persistence bug root-caused + fixed + regression test
      (subagent has a write path; hook is a non-blocking fallback)
- [ ] AC3 — orchestrator reloads from run_config + summaries; context-budget guard test
- [ ] AC4 — structured result contract enforced (contract + on-disk artifact guard)

## Test plan

- `test_phase_runner_agent.py` — agent has write path + persistence discipline;
  fixture proof artifacts land on disk and the result validates.
- `test_orchestrator_context_reload.py` — reload from summaries; context-budget
  guard (O(N × MAX_SUMMARY_CHARS), transcript-free); artifact-existence verify.
- `test_section_writer_persistence.py` — section-writer declares Write + direct
  write; hook is a non-blocking fallback when the file already exists.
- Update loop/CLI/integration fixtures to write claimed artifacts (guard).
- Integration (`cross_component` coverage): full CLI loop with on-disk artifacts
  passes the guard; a claimed-but-missing artifact is rejected `artifacts_missing`.

## Confidence Calibration
- **Boundaries touched:** `touches_io_boundary` — reads `shipwright_run_config.json`
  (orchestrator_context, read-only), reads a subagent JSONL transcript + reads/writes
  section `.md` files (write-section-on-stop hook), reads/writes artifacts via the
  loop's on-disk guard. `cross_component` — edits `**/hooks/*.py` + orchestrator
  loop (pipeline machinery) + agent defs.
- **Empirical probes run:**
  - Reload a config with a 1 MB spurious `transcript` field on each task →
    `summaryCharBudget == 3 × MAX_SUMMARY_CHARS`, transcript never read (probe: `test_context_budget_is_bounded_by_summary_ceiling`).
  - Apply an `ok:true` result claiming `artifacts/project.md` NOT on disk →
    rejected `artifacts_missing`, task stays `in_progress`, run `in_progress`
    (probe: `test_apply_rejects_missing_artifact_before_lifecycle` + integration `test_claimed_but_unwritten_artifact_is_rejected`).
  - Run the SubagentStop hook with a pre-existing section file + a
    confirmation-only transcript → no-op, no clobber, exit 0 (probe: `test_hook_noop_when_section_file_exists`).
  - Run the hook with env unset + an inferred dir outside the project tree →
    refuses to write (probe: `test_hook_refuses_salvage_write_to_untrusted_inferred_dir`).
  - `single-session-reload` CLI on a fresh single_session config → `{ok:true, context:{...}}`, exit 0 (probe: `test_reload_exit0_returns_context`).
- **Test Completeness Ledger:** every behavior below is `tested`; the only
  `untestable` row is the live LLM subagent write (enforced by the on-disk guard,
  which IS tested). See the machine-readable block in `shipwright_test_results.json`
  → `iterate_latest.test_completeness`.

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | phase-runner agent has a write path | tested | test_phase_runner_has_write_path |
  | phase-runner brief = disk-persist, not hook | tested | test_phase_runner_briefs_disk_persistence_not_hook |
  | claimed-but-unwritten artifact caught (guard) | tested | test_apply_rejects_missing_artifact_before_lifecycle |
  | artifact-on-disk → apply proceeds | tested | test_apply_accepts_when_claimed_artifact_on_disk |
  | ok=False skips artifact guard | tested | test_apply_failure_result_skips_artifact_guard |
  | stale apply → stale_version (not artifacts_missing) | tested | test_apply_stale_version_reports_stale_not_artifacts_missing |
  | reload from compact summaries, transcript-blind | tested | test_phase_summaries_never_carry_transcript, test_context_budget_is_bounded_by_summary_ceiling |
  | reload read-only + None on no/corrupt/v1 config | tested | test_reload_does_not_mutate_config, test_reload_none_on_corrupt_config, test_reload_none_on_non_v2_schema |
  | summary ceiling enforced at write-time | tested | test_context_budget_ceiling_enforced_at_write_time |
  | single-session-reload CLI + routing | tested | test_reload_exit0_returns_context, test_reload_exit1_on_no_config, test_cli_main_routes_single_session_reload |
  | section-writer write path + direct-write brief | tested | test_section_writer_declares_write_path, test_section_writer_instructs_direct_write |
  | hook no-op on existing file (no clobber/block) | tested | test_hook_noop_when_section_file_exists |
  | hook salvage (file missing, env set) | tested | test_hook_salvages_when_file_missing |
  | hook refuses untrusted inferred write dir | tested | test_hook_refuses_salvage_write_to_untrusted_inferred_dir |
  | hook refuses non-section-document salvage | tested | test_hook_refuses_salvage_of_non_section_document |
  | hook never blocks (bad payload / no path / empty) | tested | test_hook_never_blocks_* (3) |
  | components compose end-to-end (`cross_component`) | tested (integration) | integration-tests TestPersistenceGuardCrossComponent |
  | live LLM subagent actually writes its files | untestable (`requires-external-nondeterministic-service`) | enforced fail-closed by the tested on-disk guard |
- **Confidence-pattern check:** depth — probed the guard, reload, and hook at
  their boundaries (real files/config on disk, not mocks). breadth — 4 ACs each
  with happy + error paths; run 282 / plan 57 / integration 3 green.
  **integration composition** — `cross_component` machinery (hook + loop +
  contract) proven to compose by a `category:"integration"` behavior
  (TestPersistenceGuardCrossComponent), which the F11 `check_integration_coverage`
  verifier recomputes from the diff and requires.
