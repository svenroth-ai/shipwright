# Iterate: hook block-channel (WP4) — security guards + artifact-drift gate

- **Run ID:** `iterate-2026-06-13-hook-block-channel`
- **Campaign:** `2026-06-10-audit-2-manual` · sub-iterate `a2-3`
- **Intent:** CHANGE (hook output-channel contract). Bug-fix flavor; root
  cause already established + Lens-B-traced by `Spec/audits/2026-06-10-deep-audit.md`
  (WP4), so the F-debug root-cause-first law is satisfied by the audit.
- **Complexity:** medium — floored by `cross_component` (edits
  `shared/scripts/hooks/check_artifact_drift.py`, a `**/hooks/*.py` file).
  The classifier's raw `large` + `touches_auth` + `touches_migrations` are
  message-keyword false positives (no auth file, no SQL migration touched —
  the "migrations" here are artifact-directory relocations).

## Problem

Claude Code hooks deliver their message on an event-specific channel:
- **PostToolUse + exit 2** → Claude reads **stderr**; stdout is discarded.
- **SessionStart** → Claude reads **stdout** (additionalContext, exit 0);
  it **cannot block** a session.

Two findings violate this:

1. **F-secrets (HIGH).** `check_secrets.sh` and the registered
   `plugins/shipwright-build/scripts/hooks/check_destructive_migration.sh`
   emit their block payload as JSON on **stdout** then `exit 2`. On exit 2
   the stdout JSON is discarded → the secret / destructive-migration warning
   never reaches the model. The safety net is silently inert.

2. **F2 (DECISION).** `check_artifact_drift.py` (SessionStart) + its
   `stale_artifact_detector.hook_main` claim a `migrated` **hard-gate**
   ("stops the session") via `{"success": false, ...}` on stdout + `exit 1`.
   SessionStart cannot block, and that JSON shape isn't read by the model →
   the documented gate is inert. All 4 migrations are `status:"migrated"`,
   so the path is reachable (a relocated legacy dir reappearing at root).

## Decision (F2) — user-approved: honest warn-only

SessionStart genuinely cannot block. Deliver the drift reason to the model
via the channel SessionStart **does** read — `additionalContext` on stdout,
`exit 0` (warn-only) — plus a stderr notice and the existing
`.shipwright/stale-folders.md` report. Correct the docstrings +
`docs/hooks-and-pipeline.md` from "hard-gate / stops the session" to
"warn-only; SessionStart cannot block." Rejected alternative: a new generic
UserPromptSubmit hard-gate hook across all 12 plugins — speculative
machinery + per-prompt scan cost for a rare drift (the existing
`phase_user_prompt_validate` is phase-task-scoped and cannot be reused).
YAGNI: add a real hard-gate when an incident proves warn-only insufficient.

## Changes (surgical — framework-internal hooks only, no product code)

| File | Change |
|---|---|
| `shared/scripts/hooks/check_secrets.sh` | block reason → stderr, exit 2; drop stdout JSON |
| `plugins/shipwright-build/scripts/hooks/check_destructive_migration.sh` | warning → stderr, exit 2; drop stdout JSON |
| `shared/scripts/lib/stale_artifact_detector.py` | `migrated` path → warn-only: SessionStart `additionalContext` on stdout + stderr notice + return 0; docstring |
| `shared/scripts/hooks/check_artifact_drift.py` | docstring (migrated → warn-only) |
| `docs/hooks-and-pipeline.md` | correct the two drift-gate claims |
| `shared/tests/test_hook_output_schema_compliance.py` | **AC:** new test asserting the reason lands on the channel the event reads (PostToolUse→stderr, SessionStart→stdout additionalContext) |
| `shared/tests/test_hooks.py` | flip check_secrets assertions stdout→stderr (codified the bug) |
| `shared/tests/test_stale_artifact_detector.py` | rewrite block test to the warn-only contract |

## Acceptance Criteria

- [x] The schema-compliance test layer asserts the block reason is delivered
      on the channel the event actually reads (new sibling
      `test_hook_block_channel.py` — sibling, not appended, because the
      schema-compliance file is anti-ratchet-capped).
- [x] F2 decision (honest warn-only) recorded in the iterate ADR; doc/code
      consistent (hooks-and-pipeline.md + artifact-migration-reference.md +
      4 relocation records + both docstrings).
- [x] Full F0 suite green; no new bloat crossing (anti-ratchet exit 0).

Status: implemented.

## Confidence Calibration
- **Boundaries touched:** Claude-Code hook output channels (PostToolUse
  exit-2 → stderr; SessionStart → stdout additionalContext). No `.env` /
  config / state IO boundary (path-based `is_io_boundary_change` = false).
- **Empirical probes run:** (1) diffed the two `check_destructive_migration.sh`
  copies — shared already stderr+unregistered, build is the registered
  stdout-bug copy; (2) confirmed `run_hook` in `test_hooks.py` targets the
  shared copy; (3) confirmed all 4 migrations `status:"migrated"` so the
  drift block path is reachable; (4) confirmed `CROSS_COMPONENT_FILE_PATTERNS`
  line `hooks/.+\.py$` matches `check_artifact_drift.py` → cross_component.
- **Test Completeness Ledger:** see `shipwright_test_results.json`
  `iterate_latest.test_completeness` (every behavior → tested / untestable).
- **Confidence-pattern check:** depth — channel asserted by subprocessing the
  real registered hook commands, not by reading source. breadth — both
  PostToolUse guards + the SessionStart gate covered. integration composition
  — the SessionStart-hook ⇄ detector channel test is the `category:"integration"`
  behavior for the `cross_component` flag (recomputed from the diff by the
  F11 `check_integration_coverage` verifier).
