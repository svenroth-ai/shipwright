---
campaign: 2026-06-02-hook-consolidation
branch_strategy: stacked
status: draft
created: 2026-06-02
expands_triage: trg-721b1765
---

# Campaign: 2026-06-02-hook-consolidation

## Intent

Collapse the cross-plugin **hook fan-out** into **phase-aware dispatcher
hooks owned by `shipwright-iterate`** (the only always-present plugin),
removing the shared hooks from the other 11 plugins' `hooks.json`.

This expands `trg-721b1765` from "*phase-quality **Stop** hook fans out
×11*" to the full, systemic problem: Claude Code fires **all** registered
hooks of an event type with **no active-plugin filter**, so every shared
script registered in N plugins runs N× per event — 10+ of those doing
redundant work (or, on Stop, auditing phases that never ran).

The **gist**: build one **fail-open phase resolver** ("which phase
actually ran / is active?") *once* and reuse it across Start, Stop,
Prompt, and PostTool dispatchers — instead of re-inventing it in four
unrelated iterates. That shared core is precisely why this is a campaign,
not a single iterate.

### Observed fan-out (the evidence)

| Event | Shared script | Plugins | Fan-out | Sub-iterate |
|---|---|---|---|---|
| SessionStart | `capture_session_id.py` (emits the Phase-Quality block) | 12/12 | **12×** | B2 |
| SessionStart | `check_artifact_drift.py` | 12/12 | 12× | B2 |
| SessionStart | `session_start_using_shipwright.py` | 12/12 | 12× | B2 |
| SessionStart | `phase_session_start.py` | 9/12 | 9× | B2 |
| UserPromptSubmit | `phase_user_prompt_validate.py` | 9/12 | 9× | B3 |
| PostToolUse(Write\|Edit) | `check_file_size.py` | 12/12 | 12× | B4 |
| PostToolUse(Write\|Edit) | `mark_plugin_edit.py` | 12/12 | 12× | B4 |
| Stop | `audit_phase_quality_on_stop.py` | 11/12 | **11×** | B1 |
| Stop | `generate_handoff_on_stop.py` | 12/12 | 12× | B1 |
| Stop | `bloat_gate_on_stop.py` | 12/12 | 12× | B1 |
| Stop | `plugin_sync_reminder_on_stop.py` | 12/12 | 12× | B1 |
| PreToolUse | `validate_command.sh` (build) | **1/12** | 1× | B5* |
| PreToolUse | `check_rtm_coverage.py` (compliance) | **1/12** | 1× | B5* |
| PreToolUse | `check_security_scan.py` (compliance) | **1/12** | 1× | B5* |

\* **PreToolUse is a different problem.** These hooks are **plugin-local**
(each registered in exactly one plugin) → there is **no** "11 redundant
copies" duplication. But the same no-active-plugin-filter means they
**fire cross-phase** (compliance's RTM/security gates run on every Bash
call during a build/iterate session). That is contamination, not
duplication, on the **hot path** (before every tool call). Treat
separately, measurement-gated, lowest priority — do **not** lump it with
the duplicate-fan-out cases.

## Architecture (target state)

- ONE dispatcher per event type, registered **only** in
  `shipwright-iterate/hooks/hooks.json`.
- Each dispatcher resolves the engaged phase via a shared **fail-open
  resolver** (latest event / `current_step` / `phase_history`) and runs
  only that phase's relevant sub-hooks; universal sub-hooks (bloat gate,
  plugin-sync reminder, file-size, drift) run once.
- **Fail-open invariant:** a wrong/"unknown" phase answer must run MORE
  checks, never FEWER — it must never hide a real Tier-1 FAIL. The
  #126/#128 engagement gates (`phase_is_engaged` FAIL→SKIP) become pure
  defense-in-depth behind the dispatcher.
- **Consumer back-compat:** end-user projects install the cached plugins;
  removing hooks from 11 `hooks.json` must not break their installs.
  Versioned migration + a fallback so an old cache still functions.

## Sub-Iterates

| ID | Slug | Title | Depends on | Status |
|---|---|---|---|---|
| B0 | phase-resolver-contract | Fail-open "which phase ran/active" resolver + contract + tests (shared core) | — | pending |
| B1 | stop-dispatcher | Phase-aware Stop dispatcher in iterate; remove Stop fan-out from 10 plugins (**= trg-721b1765**) | B0 | pending |
| B2 | sessionstart-dispatcher | Phase-aware SessionStart dispatcher; collapse `capture_session_id`/drift/using-shipwright/phase-start fan-out (supersedes the `proposed-sessionstart-dedup-guard` interim) | B0 | pending |
| B3 | userpromptsubmit-dispatcher | Collapse `phase_user_prompt_validate.py` ×9 to one phase-aware prompt validator | B0 | pending |
| B4 | posttooluse-dispatcher | Collapse `check_file_size.py` + `mark_plugin_edit.py` ×12 to one PostToolUse(Write\|Edit) hook | B0 | pending |
| B5 | pretooluse-crossphase | **Measurement-gated.** Quantify cross-phase PreToolUse firing; only then decide phase-scoping vs. leave-as-is (hot-path latency budget) | B0 | pending |
| B6 | docs-and-tests | Update `docs/hooks-and-pipeline.md` hooks registry + cross-plugin fan-out regression test; cache-sync + back-compat verification | B1–B5 | pending |

## Sequencing rationale

- **B0 first** — the resolver is the shared dependency of B1–B4. Build and
  harden it once (fail-open, tested) before any topology change.
- **B1 next (highest value, = the original triage item)** — Stop is where
  the wrong-phase audits are most damaging (FAIL must never be hidden).
- **B2** — removes the *visible* SessionStart spam (the 11× block we see
  live). If `proposed-sessionstart-dedup-guard` already shipped the
  interim, B2 replaces the guard with the real topology fix and drops the
  now-redundant guard code.
- **B3, B4** — mechanical once B0 + the B1/B2 pattern exist.
- **B5** — only if measurement shows the compliance PreToolUse gates
  actually cost something in non-compliance sessions.
- **B6** — docs + regression guard so the fan-out can't silently return.

## Out of scope

- Behavioural changes to *what* any individual check asserts — this is a
  routing/topology refactor, not a check-logic change.
- The `proposed-sbom-triage-cluster-collapse` style producer reshaping
  (unrelated).
