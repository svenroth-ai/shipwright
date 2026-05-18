# Iterate Spec: End-to-End Verification Gate (F0.5)

- **Run ID:** iterate-2026-05-06-e2e-verification-gate
- **Type:** feature
- **Complexity:** medium (autonomous, plan-driven)
- **Status:** in_progress
- **Source plan:** `C:\Users\you\.claude\plans\ich-m-chte-am-iterate-polished-puffin.md` (approved)

## Goal

Add a single normative end-to-end verification gate (F0.5) to the iterate skill,
between F0 and F1, that verifies user-erlebbare surfaces were empirically driven
through a running stack — with schema-enforced evidence in
`shipwright_test_results.json` and a fail-closed audit in
`verify_iterate_finalization.py`. Closes the gap behind the 2026-04 webui
regression where backend-only diffs dodged file-path-gated browser verify.

## Acceptance Criteria

- [ ] AC-1: SKILL.md has a new `### F0.5: End-to-End Verification Gate` section
      between F0 and F1, describing surface taxonomy (web/cli/api/none),
      runner protocol, evidence schema, and four fail-closed conditions.
- [ ] AC-2: `shared/scripts/surface_verification.py` orchestrator exists,
      supports `--surface web|cli|api|none`, runs the matching runner,
      enforces `tests_run > 0` for non-none surfaces, writes evidence to
      `.shipwright/runs/{run_id}/surface_verification.json`, exits non-zero
      on each fail-closed condition.
- [ ] AC-3: `shared/scripts/tools/verifiers/iterate_checks.py` exposes
      `check_surface_verification(project_root, run_id) -> CheckResult`
      registered in `run_all_checks`, severity ERROR. Returns skipped at
      trivial/small complexity. Tests in
      `shared/tests/test_verify_iterate_finalization.py` cover the four
      fail-closed conditions plus the medium+ skip.
- [ ] AC-4: SKILL.md Phase Matrix row "E2E Update" renamed to
      "E2E Verification (author + execute)" with semantics
      `if feature+UI | if feature+UI or touches_io_boundary | always | —`.
      Step 9 toned to "early signal — see F0.5". Step 11 split into 11a
      (Author Spec) + 11b (Execute Spec). Iterate-spec template adds
      `## Verification (medium+)` section. F-Step ordering invariant
      (line 965) names F0.5.
- [ ] AC-5: `references/iteration-planning.md` gains an "Acceptance Criteria —
      Verification Shape (medium+)" subsection covering assertion-shape
      + agent/user AC pairing. `references/design-and-testing.md` is
      restructured into "End-to-End Verification — Authoring" +
      "End-to-End Verification — Execution" with per-surface runners and
      banners on Browser Verify / Smoke Test marking them early-signal.
- [ ] AC-6: `.shipwright/agent_docs/conventions.md` learning bullet appended.
- [ ] AC-7: `docs/hooks-and-pipeline.md` "Browser Verify Gate Semantics"
      section updated to cover F0.5. `docs/guide.md` Chapter 8 Override
      Classes table moves E2E Verification from Advisory → Mandatory at
      medium+. Finalization sequence in guide gets step 0.5.
      `plugins/shipwright-test/agents/browser-fixer.md` description
      adds shipwright-iterate as caller.

## Affected FRs

n/a — this is a meta-iterate on the iterate skill itself; no project-FR mapping.

## Out of Scope

- Skill-Iterate-Fixture-Project (deferred; skill iterates use `surface: cli`
  with `pytest plugins/<plugin>/tests/` until then).
- Behavior-Surface auto-detection (matrix=`always` at medium+ subsumes detection).
- `/shipwright-test` as Live-Smoke-Owner (dependency-inversion risk).
- Build-phase integration (Build's Step 4.5 stays separate; F0.5 in iterate
  is the SSoT for E2E gate at iterate-time).

## Design Notes

- **Single chokepoint.** F0.5 is the only normative gate. Steps 9 + 11 lose
  authoritative status; F0.5 is what F6 commits against.
- **Author + Execute split.** Step 11 → 11a (Author) + 11b (Execute) so
  spec-only authoring is mechanically distinct from spec execution.
- **Schema gate.** F0.5 extends `shipwright_test_results.json.iterate_latest`
  with a `surface_verification` block. Validation is two-layer:
  - Production-time gate in `surface_verification.py` (non-zero exit blocks
    F1+ via SKILL.md prose).
  - Post-commit audit in `iterate_checks.py` (severity ERROR; --strict and
    default both fail).
  - `finalize_iterate.py` is **not** extended (best-effort contract, see
    plan §F.1/F.2).
- **Justified opt-out.** `surface: none` + `justification` for surfaceless
  iterates; ADR records the reason.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| surface_verification.py | finalize_iterate.py + verify_iterate_finalization.py | JSON (`shipwright_test_results.json.iterate_latest.surface_verification`) |
| surface_verification.py | (logs/screenshots) | filesystem evidence path |

`touches_io_boundary` flag fires (new producer/consumer pair on a tracked
schema). Boundary probe: the test suite for `surface_verification.py`
must include a producer→file→consumer round-trip that proves the JSON
shape both sides agree on.

## Confidence Calibration

- **Boundaries touched:** see "Affected Boundaries" above.
- **Empirical probes run:** populated before F0.
- **Edge cases NOT probed + why acceptable:** populated before F0.
- **Confidence-pattern check:** populated before F0.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest plugins/shipwright-iterate/tests/ shared/tests/ -v`
- **Evidence path:** stdout captured to
  `.shipwright/runs/iterate-2026-05-06-e2e-verification-gate/surface_verification.json`
- **Justification (only if surface=none):** n/a — pytest is the natural
  surface for python-plugin-monorepo profile.

## Implementation Order

Per plan's "Implementation-Reihenfolge":

1. **Unit A** — F0.5 spec landen (SKILL.md F0.5 section + design-and-testing.md restructure + banners)
2. **Unit B** — surface_verification.py orchestrator (web/cli/api/none modes + tests)
3. **Unit C** — iterate_checks.py audit + tests
4. **Unit D** — SKILL.md tightening (Phase Matrix, Step 9, Step 11a/11b, AC template, F-step ordering invariant)
5. **Unit E** — iteration-planning.md AC section + conventions.md learning
6. **Unit F** — Doc-Sync (hooks-and-pipeline.md, guide.md, browser-fixer.md description)

One commit per unit. One ADR + finalization at end.
