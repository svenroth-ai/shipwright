# Iterate: Compliance-artifact rendering fixes

- **Run ID:** iterate-2026-06-16-compliance-rendering-fixes
- **Intent:** CHANGE (bug fixes to compliance-report rendering)
- **Spec Impact:** NONE (no FR/spec behavior change; corrects how existing
  artifacts render existing event data)
- **Complexity:** medium
- **Affected FR:** FR-01.10 (audit-ready compliance documentation)

## Problem

Four rendering defects in the auto-generated compliance artifacts (reported by
the maintainer; present in both the monorepo and the adopted `shipwright-webui`
repo, which share the same cached compliance generators):

1. **Type column shows free-text.** The Traceability-Matrix *Verification
   Timeline* and the Build-Dashboard *Recent Changes* table render the raw
   event `intent`. 7 monorepo events (and 2 webui events) leaked a *description*
   into `intent` (the real class lived in `change_type`), so a 100-char sentence
   lands in the Type cell. Adopted repos also seed `intent` from git
   conventional-commit types (`fix`/`docs`/`merge`/…).
2. **False FAILs.** Test-Evidence *Test Progression* and the RTM per-FR *Status*
   treat `total − passed` as failures. Every such event is a merged iterate
   (green-at-merge by the Iron Law), so the gap is **skipped** tests, not
   failures. With no `shipwright_known_failures.json`, `baseline=0` and every
   skip-gap false-FAILs (26 in the monorepo, 1 in webui).
3. **Dashboard missing links.** The *Compliance Artifacts* table omits
   `audit-report.md` (and the activity/build dashboard).
4. **WebUI parity.** Same cached generators → same defects; the WebUI artifacts
   need regenerating after the source fix + cache-sync.

## Approach

- New shared `shared/scripts/event_classification.py :: normalize_intent()` —
  collapses any non-token `intent` (free-text description, or empty) to a clean
  default; canonical-aliases `feat`→`feature`, `fix`→`bug`; keeps other single
  short tokens. Imported by both Type-column producers (RTM + build dashboard).
- Skip-aware PASS: in `_test_progression` (test_evidence) and the RTM per-FR
  status, a completed-work `passed<total` gap renders skip-aware PASS / COVERED
  (never FAIL). The `baseline_failure_count` plumbing (public contract) is
  **kept**; only the final FAIL branch changes. Real open regressions still
  surface via the existing triage-deep-link override.
- `compliance_report.py`: add `audit-report.md` (+ activity dashboard) rows to
  the Compliance Artifacts table, conditional on file existence.
- Regenerate monorepo artifacts; after cache-sync, regenerate webui artifacts
  (separate webui PR).

## Affected Boundaries

- Compliance report generators (read `shipwright_events.jsonl`,
  `shipwright_test_results.json`; write `.shipwright/compliance/*.md`,
  `.shipwright/agent_docs/build_dashboard.md`). No event wire-format change, no
  config/state schema change. `intent`/`change_type` vocab is read-only here.

## Confidence Calibration

- **Boundaries touched:** compliance report rendering (RTM, Test Evidence,
  Dashboard, Build Dashboard); no event/config/state schema changes.
- **Empirical probes run:**
  - Enumerated all malformed-`intent` events: monorepo 8 (7 free-text + 1
    `fix`), webui 63 (2 free-text + conventional-commit types). Confirms the
    normalize_intent input space.
  - Confirmed `shipwright_known_failures.json` absent → `baseline=0` → all 26
    monorepo Test-Progression FAILs are skip-gaps on merged work.
  - Cross-tab of `intent` × `change_type` on well-formed events confirms the two
    fields are orthogonal (e.g. `intent=change`, `change_type=tooling`).
  - Confirmed both Type-column sites read `intent`; the Build-Dashboard FRs
    fallback to `change_type` is intentional (left unchanged).
- **Test Completeness Ledger:**

  | Behavior | Disposition |
  |---|---|
  | `normalize_intent` keeps canonical tokens (feature/change/bug) | tested (test_event_classification) |
  | `normalize_intent` aliases feat→feature, fix→bug | tested (test_event_classification) |
  | `normalize_intent` keeps other single tokens (docs/test/merge) | tested (test_event_classification) |
  | `normalize_intent` collapses free-text / empty → default | tested (test_event_classification) |
  | RTM Verification Timeline Type uses normalize_intent | tested (test_rtm_generator) |
  | Build Dashboard Recent-Changes Type uses normalize_intent | tested (test_build_dashboard) |
  | Test-Progression skip-gap → skip-aware PASS (not FAIL) | tested (test_test_evidence) |
  | RTM per-FR skip-gap → COVERED (not FAIL) | tested (test_rtm_generator) |
  | `PASS (baseline)` path preserved when known_failures present | tested (test_test_evidence) |
  | Dashboard Compliance Artifacts table includes audit-report.md | tested (test_compliance_report) |
  | Monorepo artifacts regenerate clean | untestable (covered-by-existing-test: F0 suite + manual regen verify) |
  | WebUI artifacts regenerate clean | untestable (requires-external-nondeterministic-service: separate repo/PR, verified by inspection) |

- **Confidence-pattern check:** depth — each render-site change has a direct
  unit test asserting the new token/status; breadth — both Type-column sites and
  both FAIL sites are covered; no `cross_component` machinery touched, so no
  integration-composition behavior required.
