# Iterate Spec — Serial integrate_main merge for campaign / parallel iterates (Auto-merge churn fix, Option A)

- **Run ID:** iterate-2026-06-12-automerge-serial-integrate
- **Intent:** CHANGE (modify the auto-merge / branch-refresh behavior of F11 + campaign mode)
- **Complexity:** medium (plan-locked; classifier estimated `small`/history)
- **Governing plan:** `Spec/automerge-churn-serial-integrate-plan.md` (Decision = Option A)
- **Origin:** campaign `2026-06-10-audit-1-auto` (#199–#206) surfaced the auto-merge churn cascade.

## Problem (restated)

GitHub auto-merge (armed in F11 since PR #197) does a **server-side 3-way merge**
and never runs `integrate_main` / `resolve_churn_conflicts` — the
regenerate-at-merge resolver. For a single, current iterate that is fine. For
**parallel** iterate branches (an `--autonomous` campaign or concurrent
iterates), each branch carries its own regenerated derived snapshots
(`.shipwright/compliance/*.md`, `.shipwright/agent_docs/*.md`,
`shipwright_test_results.json`). As branches merge serially, every still-open
branch goes **DIRTY** (auto-merge stalls on the snapshot conflict) or merges
**stale** (Group-E staleness), because the regen step never runs server-side.
`events.jsonl` + `triage.jsonl` are `merge=union` and are NOT affected.

## Decision — Option A

Do the merge through the existing resolver (`integrate_main`), **serialized**,
for any context where iterate branches can be stale (campaigns / concurrency).
Keep GitHub auto-merge ONLY for the common single-iterate case where the branch
is current at merge time. Host-agnostic, reuses `integrate_main` + churn
resolver, changes no artifact model, softens no gate (`audit_staleness` stays).

## Spec Impact

MODIFY — changes the behavior of an existing phase (F11) and an existing mode
(campaign autonomous loop). No new FR; this is process/orchestration. No
`spec.md` FR delta.

## Affected Boundaries

- `shared/scripts/tools/ensure_current.py` **CLI/return-dict JSON contract** —
  new tool returning `{status, action, behind, integrated, steps}` that F11 +
  campaign prose parse (producer/consumer boundary → round-trip tested).
  **Decision (deviation from the first-draft spec):** implemented as a SEPARATE
  thin wrapper over `integrate_main.integrate`, NOT as an `integrate_main
  --ensure-current` flag, so `integrate_main.py` stays byte-identical and neither
  file crosses the 300-LOC bloat guideline (plan AC: "no new bloat crossing").
  No existing caller expected `integrate_main --ensure-current` — this is a NEW
  capability — so the wrapper breaks nothing.
- **Env var** `SHIPWRIGHT_ITERATE_AUTOMERGE` (default `1`/on) — when `0`, F11
  defers the auto-merge arm so the campaign serial drain owns the merge.
- Runtime-prompt prose: `references/F11.md`, `references/campaign-mode.md`,
  `SKILL.md` F11 index row, `docs/hooks-and-pipeline.md`.

## Approach

1. **Primitive — `shared/scripts/tools/ensure_current.py` (new module).**
   fetch (once) → resolve `origin/<default>` → compute `behind = HEAD..ref`
   commit count → if `behind == 0` return `already-current` (no-op, no commits);
   else delegate to `integrate_main.integrate(do_fetch=False)` (merge → churn
   reconcile → regenerate snapshots → commit follow-up) and report `integrated`
   (derived from a HEAD before/after comparison, not step-name strings). Own
   `main()` CLI mirroring integrate_main's exit-code mapping. `integrate()`
   already no-ops when up-to-date, so this softens no gate.

2. **F11 single-iterate behind-guard** (`references/F11.md`). After the
   leak-guard and BEFORE push/`gh pr create`, run `integrate_main --ensure-current`.
   On a non-churn (source) conflict it exits non-zero → STOP (hard safety gate).
   Then push (ships any integrate commits), create the PR, arm auto-merge from a
   current, already-regenerated tree.

3. **F11 env-gated arm** (`references/F11.md`). Gate the existing arm on
   `SHIPWRIGHT_ITERATE_AUTOMERGE` — `=0` defers (campaign drain owns it). The
   `iterate/*` `case` guard + `||` fail-soft are preserved unchanged.

4. **Campaign serial drain** (`references/campaign-mode.md`). The orchestrator
   spawns sub-iterate-runners with `SHIPWRIGHT_ITERATE_AUTOMERGE=0` (their F11
   brings the branch current + pushes but does NOT arm). After the build loop, a
   new **Serial Merge Drain** phase merges the sub-iterate PRs one at a time:
   `integrate_main --ensure-current` on each branch against the now-advanced
   `origin/main` → push if integrated → merge → wait for merge → next.

5. **Docs** (`docs/hooks-and-pipeline.md`). Record that auto-merge is unsafe for
   parallel sub-iterate PRs touching derived snapshots; the serial
   `integrate_main` drain is the contract.

## Acceptance Criteria (from plan)

- [ ] `ensure_current` no-ops on a current branch (no new commit); integrates +
      regenerates on a behind branch (test).
- [ ] Single-iterate auto-merge arm path unchanged: arm line + flags + `iterate/*`
      guard + fail-soft preserved (regression test).
- [ ] F11 `behind`-guard present before the arm (drift test).
- [ ] F11 arm respects `SHIPWRIGHT_ITERATE_AUTOMERGE=0` campaign-defer (drift test).
- [ ] campaign-mode.md documents the serial `integrate_main` drain + the defer
      env var (drift test).
- [ ] Host-agnostic regeneration (uses `integrate_main`/git, no GitHub-only API).
      Full F0 suite green; no new bloat crossing.

## Confidence Calibration
- **Boundaries touched:** `tools/ensure_current.py` JSON result
  (`status`/`action`/`behind`/`integrated`/`steps`); env var
  `SHIPWRIGHT_ITERATE_AUTOMERGE` (F11 read; campaign export); F11 + campaign +
  SKILL index + docs prose. `integrate_main.py` left byte-identical (zero diff).
- **Empirical probes run:**
  - `test_ensure_current_noop_when_current` — current branch ⇒ `action=already-current`,
    `integrated=False`, `behind=0`, HEAD unchanged, integrate NEVER reached
    (monkeypatch raises if regen runs). Confirms the common single-iterate path is
    a pure no-op.
  - `test_ensure_current_integrates_when_behind` — origin/main advanced on a churn
    MD ⇒ merge + `regenerated-followup` commit, branch advances, `action=integrated`,
    `behind>=1`. The JSON contract keys round-trip.
  - `test_ensure_current_blocks_on_source_conflict` — non-churn (`app.py`) conflict
    ⇒ `status=blocked`, `integrated=False`, regen NOT run, tree restored (hard gate).
  - `test_ensure_current_cli` — `ensure_current.py` prints the already-current
    contract JSON + exits 0.
  - F11/campaign drift greps (`test_f11_automerge_arm`, `test_campaign_serial_drain`)
    pin: guard before arm, env-gated arm, campaign defer env + serial drain via
    `ensure_current.py`. 17 shared + 379 iterate tests green; ruff clean.
- **Test Completeness Ledger:** table below — every behavior `tested`, 0 untested-testable.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the three integrate outcomes (noop / integrate+regen /
    blocked) are each driven through the REAL `integrate_main.integrate` against a
    real bare-origin + linked worktree (only `regenerate_tracked_snapshots` is
    faked, as the existing integrate tests do), so the guard's delegation,
    behind-count, and contract mapping are exercised end-to-end, not mocked.
  - *Coverage (breadth):* both surfaces are covered — single-iterate (functional +
    F11 drift) and campaign (drift). The one path NOT executed live is the
    agent-driven serial drain loop itself (prose), which is drift-pinned, not
    unit-runnable (no Task tool in tests); flagged below as `covered-by-existing-test`
    at the prose layer + verified by the campaign drift assertions.

### Test Completeness Ledger
| Behavior | Disposition | Evidence / reason_code |
|---|---|---|
| ensure_current no-ops when branch current | tested | test_ensure_current_noop_when_current |
| ensure_current integrates + regenerates when behind | tested | test_ensure_current_integrates_when_behind |
| ensure_current blocks on non-churn source conflict | tested | test_ensure_current_blocks_on_source_conflict |
| ensure_current JSON contract keys (action/integrated/behind) | tested | asserted in the three tests above (round-trip) |
| F11 refresh-if-behind guard present before arm | tested | test_f11_has_refresh_if_behind_guard |
| F11 arm respects campaign-defer env var | tested | test_f11_arm_respects_campaign_defer |
| F11 arm line/flags/iterate-guard/fail-soft preserved | tested | existing test_f11_automerge_arm.py (regression) |
| campaign-mode documents serial integrate_main drain + defer | tested | test_campaign_serial_drain.py |
| SKILL F11 index advertises guard | tested | test_skill_index_line_advertises_arm (extended) |
