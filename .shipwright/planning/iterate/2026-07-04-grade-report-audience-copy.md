# Iterate: grade report — audience-facing copy redesign

- **Run ID:** iterate-2026-07-04-grade-report-audience-copy
- **Intent:** CHANGE · **Complexity:** medium
- **Follows:** shipwright-grade G3 (#315) + CTA follow-up (#317).

## Spec Impact
**NONE** (framework/grader tooling — same FR-gate class as G1–G3). This is a
render-only overlay + copy change to the `shipwright-grade` HTML report; the
scoring engine, the view-model, and the terminal/markdown/json renderers are
untouched. No existing framework FR is touched.

## Why
The report is a **public marketing instrument** for non-experts (people with
AI-built repos, not compliance engineers). The old cards spoke compliance-ese
("not measurable — needs per-change behavior-impact (BP-2)"), so the audience
"understood nothing" and bounced. Goal: read the report → understand what's
missing and what improves → adopt + take the Masterclass.

## What changed
- New `lib/report_copy.py` — a per-dimension plain-language copy layer (plain
  question · one-line "what this checks" · concrete-scenario "why it matters" ·
  honest "With Shipwright" line · "backed by"). Trusted static data, keyed by
  the engine dimension key.
- New `lib/_html_dom.py` — the escape-by-default `el`/`_Raw`/`_text` builder
  EXTRACTED unchanged (keeps the security seam in one auditable module + keeps
  `html_report.py` ≤300 LOC).
- `lib/html_report.py` — `_dim_card` rewritten: plain question + visible
  one-liner + (measured → "In your repo: <detail>" | n/a → jargon-free reframe)
  + expandable native `<details>` "Why it matters" that ALSO surfaces the
  open-standard anchor + provenance (spec requirement — kept, just off the
  face). `_cta()` → two next-step cards (Understand → Masterclass, Fix → adopt),
  both linking svenroth.ai/shipwright. Funnel panel reworded ("What your repo is
  missing").
- Honesty guardrails: every "With Shipwright" claim states the ENFORCED
  mechanism, never perfection (verified against Shipwright's own live A-grade
  dashboard). Reconciliation "flags … until re-proven" (not "won't let through");
  test-health carries a coverage-depth honest limit; traceability "linked to a
  requirement OR explicitly classified"; size "no unchecked growth".

## Confidence Calibration
- **Boundaries touched:** HTML output boundary (unchanged security model — still
  escape-only, now with 2 static trusted CTA links). The engine `detail` (repo-
  derived) is still escaped; jargon suppression for n/a dims drops the *detail*
  string from render, not the escaping of any shown field.
- **Empirical probes run:**
  - Rendered the report for a real git repo; a parser confirmed **balanced tags,
    0 script/img/iframe/form, all hrefs = the CTA constant, 7 `<details>` all
    closed** (deterministic).
  - Honesty audit vs Shipwright's OWN live dashboard (A/99, all 7 dims measured
    incl. reconciliation 0/5) — each "With Shipwright" claim maps to an enforced
    mechanism; caveats (traceability no-FR share, test-health = pass/fail not
    coverage, size = net-growth) folded into the copy.
- **Test Completeness Ledger:** all behaviors testable ⇒ tested; 0
  untested-testable (machine block in `shipwright_test_results.json`).
- **Confidence-pattern check:** *depth* — the security seam is unchanged
  (extracted, byte-identical) + parser-based inertness; the honesty hedges + the
  "every engine dim has copy" fallback are pinned by `TestCopyIntegrity`.
  *breadth* — 271 tests green; ruff clean; all modules ≤300 LOC. *integration* —
  N/A (pure renderer; no cross-component machinery).
