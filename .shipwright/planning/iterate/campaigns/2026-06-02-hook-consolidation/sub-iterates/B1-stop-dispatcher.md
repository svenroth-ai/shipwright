# B1 — Phase-aware Stop dispatcher (= trg-721b1765)

- **Type:** change (topology refactor)
- **Complexity:** medium → large (touches 11 hooks.json + back-compat)
- **Depends on:** B0
- **Triage:** this sub-iterate **is** the original `trg-721b1765`.

## Goal

Replace the 11× fan-out of `audit_phase_quality_on_stop.py` (and the
co-fanned universal Stop hooks) with **one phase-aware Stop dispatcher**
owned by `shipwright-iterate`, removing the shared Stop hooks from the
other 10 plugins' `hooks.json`.

Today 1 Stop event fires 11 identical phase-quality audits, 10 of which
audit phases that never ran in the session (e.g. adopt/deploy on this
framework monorepo — see the live SessionStart evidence in
`proposed-sessionstart-dedup-guard.md`).

## Acceptance Criteria

- [ ] **AC-1 (single audit).** One Stop event triggers **one**
      phase-quality audit, scoped via `resolve_engaged_phase` (B0) to the
      phase that actually ran.
- [ ] **AC-2 (fail-open).** `UNKNOWN` phase → audit runs (full set), never
      skipped. A wrong answer surfaces extra FAILs, never hides one.
- [ ] **AC-3 (universal Stop hooks run once).** `bloat_gate_on_stop`,
      `plugin_sync_reminder_on_stop`, `generate_handoff_on_stop` run
      exactly once per Stop (today 12×).
- [ ] **AC-4 (10 plugins de-registered).** The shared Stop hooks are
      removed from build, test, plan, design, project, security, deploy,
      changelog, compliance, adopt `hooks.json`. Plugin-local Stop hooks
      (`master_stop_check.py` project, `write_terminal_marker.py` build,
      `check_documentation.py` build, `iterate_stop_finalize.py`,
      `aggregate_triage_on_stop.py`) stay where they are.
- [ ] **AC-5 (consumer back-compat).** End-user projects on older cached
      plugins keep working (versioned migration / cache-sync note);
      removing hooks must not orphan their installs.
- [ ] **AC-6 (#126/#128 become defense-in-depth).** The `phase_is_engaged`
      FAIL→SKIP gates remain as a second safety net behind the dispatcher.
- [ ] **AC-7 (docs).** `docs/hooks-and-pipeline.md` hooks registry updated
      (handled jointly in B6 if stacked).

## Risk / care

- **Highest-stakes sub-iterate**: a routing bug here can hide a real
  quality FAIL. Bias every ambiguous branch toward running the audit.
- Recommend a `/shipwright-plan` pass before build (per the triage item's
  "plan-first, NOT a quick iterate" note).

## Tests

- Engaged=iterate → only iterate audited; adopt/deploy NOT audited.
- UNKNOWN → full audit runs.
- Universal Stop hooks fire exactly once.
- Regression: a deliberately-injected Tier-1 FAIL in the engaged phase is
  still surfaced after the topology change.
