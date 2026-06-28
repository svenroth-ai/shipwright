# Iterate: cc1 — BP-1 FR-mapping (traced-% metric + behavior-aware verifier + backfill)

Campaign `2026-06-27-compliance-control-coverage`, sub-iterate `cc1`. Lane C, producer.

## Scope (the 5 ACs)

1. **AC-4** — Control-Grade `events_fr_tagged` credits *traced* changes (FR-linked OR satisfied no-FR), so the requirement-traceability dimension rises off the FR-tagging freeze cap. SSOT: `shared/scripts/lib/fr_classification.py`.
2. **AC-2** — the fail-closed FR-gate (`record_event._fr_or_change_type_gate_error`, at CLI AND finalize, intent-independent) blocks a behavior-affecting change (`spec_impact` add/modify/remove) with no FR — the no-FR branch is behavior-preserving only.
3. **AC-1** — dashboard `Recent changes traced to an FR` row makes the FR-tagging freeze visible (WARN on a relative drop OR a steady-zero floor).
4. **AC-3** — `group_d` D1 refined to all-time coverage (no spec-update watermark); 16 legacy-defect events backfilled via `event_amended`; D1 re-enabled in `audit_config.json`.
5. **AC-5** — `guide.md`, `F5b.md`, `hooks-and-pipeline.md`, `spec.md` updated.

## Decisions (user-confirmed before build)

- **Spec premise corrected:** **14 FRs (not 209)**, already 14/14 covered → coverage is not a lever; `tag_rate` (`events_fr_tagged`) is the only one. D1 was RED (watermark staleness), not green.
- **Q1 = Full credit → A:** crediting *satisfied no-FR* moves the public Control Grade B 87.2 → A 98.8 (→ 100.0 after legacy cleanup). The Spec handoff seam explicitly anticipates revisiting `events_fr_tagged`. Honesty counterweights: the dashboard freeze row + the grade detail "traced (FR-linked or classified no-FR)".
- **Q2 = Re-tag genuine + refine D1:** D1 → all-time coverage (the Spec rejects staleness-by-age); 4 behavior-affecting compliance events → FR-01.10; 12 framework infra/tooling defects → valid no-FR. **D4 left as its honest pre-existing fail (not masked).**
- **M3 (code-review) accepted trade-off:** the score can reach 1.0 from self-classification; the dashboard freeze row + grade detail are the transparency counterweight (the public grader plugin handles cold-repo classification separately). Not changing the repo-agnostic scorer for it.

## Confidence Calibration

- **Boundaries touched:** `shipwright_events.jsonl` serialization (WorkEvent gains `change_type`/`none_reason`/`spec_impact`; 17 `event_amended` corrections); the FR-gate (`record_event`/`finalize_iterate`); `audit_config.json`.
- **Empirical probes run:**
  - Live grade: B 87.2 → A 98.8 (credit) → A 100.0 (backfill); traceability dim 0.666 → 1.0.
  - Live D1: fail → pass; full detective audit `any_fail=False`.
  - Live D4: confirmed reverts to its honest pre-existing fail after the `evt-9a656b5f` clobber fix — backfill does NOT mask it.
  - Post-backfill: 211/211 work_completed events traced AND gate-valid (0 untraced, 0 gate-invalid).
  - Dashboard row: `WARN — FR-tagging dropped to 0% (last 30) vs 18% all-time`.
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | `is_traced`/`is_satisfied_no_fr`/`is_behavior_affecting` predicates | tested | `shared/tests/test_fr_classification.py` (incl. behavior-affecting-never-satisfied + gate-drift) |
  | Gate blocks behavior-affecting no-FR (CLI + finalize, intent-independent) | tested | `shared/tests/test_fr_gate_behavior_affecting.py` (6); finalize parity in `test_finalize_iterate.py` |
  | Gate accepts FR-linked / satisfied-no-FR, rejects unclassified | tested | `shared/tests/test_record_event.py::TestFrOrChangeTypeGate` |
  | WorkEvent classification fields round-trip (legacy + null tolerant) | tested | `test_workevent_null_coercion.py` (2 new) |
  | `count_traced` credits FR-linked AND satisfied no-FR | tested | `test_traceability.py::TestCountTraced` + live grade |
  | Dashboard freeze row WARNs on relative drop AND absolute zero | tested | `test_traceability.py::TestRenderTracedRow` (5) |
  | D1 all-time coverage (no watermark) | tested | `test_audit_groups_a_d.py::test_d1_coverage_persists_across_later_spec_update` + live |
  | D5 no-FR exemption excludes behavior-affecting | covered-by-existing-test | `is_satisfied_no_fr` unit test pins the carve-out; D5 delegates to it (live D5 pass) |
  | `audit_config` re-enables D1 (passes honestly) | tested | `test_audit_detector.py::test_framework_audit_config_disables_expected_checks` + live audit |
  | Backfill: all events traced + gate-valid; D4 not masked | tested | empirical probe (live: 0 untraced, 0 gate-invalid, D4 honest-fail, grade A 100) |
  | Docs (guide/F5b/hooks-and-pipeline/spec.md) | n/a | documentation, not a testable behavior |

  0 untested-testable behaviors.
- **Confidence-pattern check:** asymptote (depth) — full suites green: compliance 736, shared 3580+61+196, integration 169, plus targeted re-runs after each change. coverage (breadth) — all 5 ACs + every code-review finding (M1/M2/M4 fixed; M3 documented). integration composition — `cross_component=False` (verified via `risk_detectors`), so no mandatory integration test; the cross-plugin SSOT (`fr_classification`, shared by `record_event` and the compliance adapter via `load_shared_lib`) is exercised by both sides' tests + a live collector run.
