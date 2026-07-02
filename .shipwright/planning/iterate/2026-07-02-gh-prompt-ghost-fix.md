# Iterate: Fix recurring gh-prompt triage ghost (mis-wired prompt-injection source)

- **Run ID:** iterate-2026-07-02-gh-prompt-ghost-fix
- **Type:** bug
- **Complexity:** small (classifier estimate; the cautious medium override was dropped after the
  diff landed — no risk flags materialized: no `json.load/dump` added, no auth/rls/migrations, not
  cross-component machinery. Isolated: consumer.py gating + a CI trigger line + tests/docs.)
- **Spec Impact:** MODIFY (behavior of the github_triage producer + security.yml triggers)

## Symptom
A long-fixed prompt-injection finding (ZWSP U+200B in a planning note, fixed in #300) keeps
re-surfacing as ever-new `gh-prompt:svenroth-ai/shipwright` triage items (trg-3efb7027,
trg-9812330d — both open). Manual dismisses did not stick.

## Root cause (three stacked defects — investigated 2026-07-02)

**A — mis-gating (`shared/scripts/github_triage/consumer.py`).** The prompt-injection source
only fires under `if cs_alerts is None:` (lines ~90/167/246). But prompt-injection findings are
NEVER uploaded to GitHub Code Scanning — `security.yml` uploads only OSS SARIF (semgrep/trivy);
`prompt_injection_scan.py` writes only `prompt_risks.json`. So the source is OFF when Code
Scanning is up (repo has 30 alerts ⇒ `cs_alerts` non-None) and ON only when a code-scanning
fetch fails. = signal loss (blind to prompt-injection when the repo is healthy). The gate was
inherited from the SAST artifact path, which needs it to avoid double-counting SARIF findings —
but prompt-injection can't double-count (never in SARIF).

**B — staleness (`.github/workflows/security.yml`).** The producer reads the latest MAIN
`security.yml` run artifact (`github_api.latest_security_workflow_run`, 14-day window). Triggers
= `pull_request` + weekly `schedule` (Mon 06:00 UTC) + `workflow_dispatch` — NO `push: [main]`.
So the main artifact refreshes only weekly; a fix merged between weekly scans is invisible for
up to 7 days.

**C — resolution can't land (main-tree-drift + orphan-status quarantine).** VERIFIED: the
appends trg-3efb7027 / trg-9812330d exist ONLY in the local main tree, never in `origin/main`
(fold commit 013f2d8a unpushed). Two dismisses of trg-3efb7027 (`by=webui` 01.07, `by=cli`
02.07) were quarantined as `orphan-status: no append anywhere in the combined triage log`
(`shared/scripts/lib/sweep_quarantine.py`): the sweep classifies against `origin-tracked ∪
outbox`, and the append never reached origin. This is the #169/#172/#303 delivery-gap family —
deep, high-blast-radius triage infra; NOT cleanly reducible to one sweep-local fix without a
dedicated reproduction.

## Invariant (non-negotiable)
No security signal lost, no live finding swallowed. Resolution may dismiss ONLY what provably no
longer reproduces in the HEAD-current CI artifact; keeps everything still present. After A the
prompt source fires reliably (even when Code Scanning is up) — coverage improves.

## Interaction: do A+B alone stop the recurrence?
YES for NEW ghosts. With A+B, current main (ZWSP fixed) → HEAD-current artifact has 0 prompt
findings → `prompt_unit=None` → no new append (recurrence stops) AND resolve_stale wants to
resolve the open items. But the EXISTING 2 items are origin-absent drift, so their resolve is
blocked by C. → The existing 2 need either C fixed or a landing main-tree reconcile.

## Scope decision (pending user approval)
- Option 1: A+B here + landing cleanup of the 2 items via reconcile; C as a dedicated
  reproduced follow-up. (recommended — controls blast radius, honors BUG root-cause law for C)
- Option 2: A+B+C all here (bigger, C needs clean reproduction first).

## Acceptance criteria
1. Prompt-injection source is evaluated regardless of `cs_alerts` (fires when Code Scanning up).
2. SAST artifact path stays gated on `cs_alerts is None` (no SARIF double-count).
3. `security.yml` scans main on every merge (`push: [main]`) so the artifact tracks HEAD.
4. A HEAD-clean prompt artifact auto-resolves an open gh-prompt item; a present finding keeps it.
5. The 2 stale items end up dismissed with a LANDING resolution (not re-quarantined).
6. Tests pin A (fires at cs_alerts non-None), the resolve/keep behavior, and (if in scope) C.
7. `docs/hooks-and-pipeline.md` + an ADR updated.

## Confidence Calibration
- **Boundaries touched:** github_triage producer/consumer; security.yml triggers; triage
  outbox sweep / quarantine; triage.jsonl I/O.
- **Empirical probes run:** (1) `gh api code-scanning/alerts` → 30 (cs_alerts non-None ⇒ prompt
  path currently dead). (2) unwrapped quarantine → 2 dismisses of trg-3efb7027 eaten. (3)
  worktree-tracked log ⇒ neither append in origin. (4) security.yml triggers ⇒ no push:main.
- **Test Completeness Ledger:** TBD at F5.
- **Confidence-pattern check:** TBD (integration composition for cross-component).
