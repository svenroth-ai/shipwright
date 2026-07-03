# Iterate Spec — grade G1: cold-repo signal projector (core)

- **run_id:** `iterate-2026-07-03-grade-g1-projector`
- **campaign:** `2026-07-03-shipwright-grade` · **sub-iterate:** G1 (projector)
- **intent:** feature (new read-only plugin) · **complexity:** medium
- **canonical spec + ACs:** `.shipwright/planning/iterate/campaigns/2026-07-03-shipwright-grade/sub-iterates/G1-projector.md`
- **plan (why):** `Spec/shipwright-grade-plan.md`

## Summary
Stand up the `plugins/shipwright-grade/` plugin and the cold-repo signal
projector: `resolve_target` seam → memoized capped `RepoContext` →
`synthetic_projection` (git log → events) → `grade_inputs_projector` (map onto
`GradeInputs`, call `compute_grade` **unchanged** via `engine_bridge`) → typed
`report_model` (per-dimension provenance) → deterministic terminal / markdown /
json card. Routing contract (authoritative-vs-heuristic) defined + tested.
Local-only, read-only, hostile-input hardened.

## Locked design decisions (see the campaign spec — do NOT re-litigate)
- **Scored in G1:** requirement-traceability (heuristic route/feature coverage +
  Conventional-Commit / PR-issue change classification) + change-traceability
  (strict PR/issue links). **n/a in G1:** security, dependency hygiene,
  size/maintainability, change reconciliation (deferred to G2 per plan §9).
- **test-health:** the static test inventory is **detected and surfaced**
  ("N tests — present, not executed") but **not scored** — fabricating a
  pass-ratio from static presence would violate the honesty principle; scored
  test-health lands in G2 with the CI JUnit / Scorecard check-run tiers (§9
  explicitly bundles the "gh test tiers" into G2). This is the honest reading of
  the AC's "test-inventory tier is lit" = detected + surfaced, not scored.
- **`expected_dimensions=()`** for cold heuristic grades → n/a dims are "controls
  Shipwright would light up", not dark-control caps.
- **Cross-plugin import:** grade modules import bare; `engine_bridge` lazily
  inserts the compliance plugin root and imports `scripts.lib.control_grade`.
  Grade never claims the `scripts.lib` namespace (ADR-045 collision avoided).

## Known G1 limitations (calibration signal for G5, not bugs)
- Requirement-traceability is **route→FR** only, so non-web repos (libraries,
  CLIs, this monorepo) render it `n/a` and grade on change-traceability alone —
  a thin but honest grade. Broadening FR inference is a G5 heuristic-tuning item.
- The reused adopt `feature_inferrer` truncates its file scan **before** sorting
  (`rglob(...)[:500]`), so on repos exceeding ~500 source files *which* files are
  scanned is filesystem-order-dependent → feature inference is a sample. G1
  cannot edit adopt (new-plugin-only phase scope), so it **labels** this honestly
  (`RepoContext.features_truncated` → requirement-traceability provenance
  `sampled/truncated`) and excludes vendored dirs to shrink the set.
  **Follow-up:** a small cross-plugin fix to make `feature_inferrer` sort before
  truncating (benefits adopt too) — bundle with the G2 detector-signal wiring.
- The empirical suite is **seeded** (manifest + record/replay + fixtures dir);
  real SHAs, cached payloads and the launch gate land in G5.

## G1 internal code review — dispositions (fresh-context adversarial pass)
All confirmed findings fixed before commit (no blockers):
1. **Determinism on >500-file repos** (detector truncates pre-sort) → mitigated
   (excludes + sorted features) + honestly labelled `sampled/truncated` + follow-up
   above.
2. **Coverage over-counting** (module-path match covered every route in a file) →
   `_feature_covered` now matches the **route-specific** token only (test:
   test_coverage_heuristic.py).
3. **Bounded-work claim** → git-log output byte-bounded (`git_exec` max_bytes);
   detectors given vendored excludes; SKILL claims made accurate.
4. **"A — full control" quotable out of context** → headline now carries
   "N of M controls measured" (both renderers).
5. **git run in untrusted repo** → single hardened `git_exec` runner
   (`safe.directory=*`, fsmonitor/pager/hooks off) for all git calls.
6. **Wasted `--numstat` pass** → dropped; `files_changed` deferred to G2.
7. **Bare `#N` as provenance** → contract relabelled ("PR/issue reference token,
   not a gh-verified link"); a bare SHA still does not count.

## Confidence Calibration
- **Boundaries touched:** filesystem read of an untrusted repo tree (bounded,
  within-root, no symlink-follow); `git log`/`rev-parse` via list-arg subprocess
  (`shell=False`); cross-plugin Python import of the compliance engine; terminal
  stdout (ANSI/bidi/control-char sink). No writes to the target repo. No network.
- **Empirical probes run:**
  - Ran the CLI against the **real shipwright monorepo** → `F (45.4)`, 1 of 7
    dims measurable (change-traceability 227/500 linked; req-trace n/a — no web
    routes; test inventory 631 files surfaced). Deterministic across two runs.
  - Ran it against 3 synthetic fixtures → `A (100)` / `D (62.5)` / `F (0)` in the
    intended order (well-run > no-tests > messy), byte-stable across repeats.
  - Hostile-repo probe (commit subject with ANSI + BEL + bidi override) → the
    rendered card contains no `\x1b`, `\x07`, or bidi override chars.
  - Bare / empty / shallow / huge+binary repos → graceful `Not Gradeable` or a
    grade, never a crash.
- **Test Completeness Ledger:** below — 91 hermetic tests, 0 untested-testable.
- **Confidence-pattern check:** *depth* — the projection asserts exact
  `GradeInputs` values + grade letters against `compute_grade` (reused unchanged),
  not just "runs". *breadth* — parser units + integration fixtures + negative
  fixtures + CLI + cross-plugin coexistence + audit. *integration composition* —
  `test_engine_bridge.test_grade_modules_and_engine_coexist_without_collision`
  proves grade's bare modules and the engine's `scripts.lib.*` compose in one
  process (the ADR-045 concern), and the full pipeline is exercised end-to-end by
  `test_grade_cli` + `test_projector_fixtures`.

### Test Completeness Ledger (testable ⇒ tested)
| Behavior | Disposition | Evidence |
|---|---|---|
| resolve_target: local-git accept; URL/missing/file/non-git reject; bare/shallow/remote flags | tested | test_resolve_target.py (9) |
| synthetic_projection: conv-type, PR/issue ref, is_traced/has_provenance, files_changed deferred, newline-safe records | tested | test_synthetic_projection.py (9) |
| git_exec: hardened runner (safe.directory/fsmonitor/pager/hooks), bounded read, non-repo rc | tested | test_git_exec.py (4) |
| coverage heuristic: route-specific (no module-path over-count), param routes excluded | tested | test_coverage_heuristic.py (5) |
| features_truncated → requirement-traceability provenance sampled/truncated | tested | test_repo_context.py, test_report_model.py |
| RepoContext: bounded caps, lexicographic walk, prune .git, test-file detection, head sha, events, within-root byte-capped read_text | tested | test_repo_context.py (7), test_reused_collector_audit.py |
| detectors_bridge: read-only reuse, safe degradation, no writes | tested | test_reused_collector_audit.py (4), test_negative_fixtures.py |
| engine_bridge: compute_grade unchanged, cached, all-green→A, all-n/a→Not Gradeable, no scripts.lib collision | tested | test_engine_bridge.py (5) |
| projector: events+context→GradeInputs; lit vs n/a dims; static inventory surfaced not scored | tested | test_projector_fixtures.py (9) |
| report_model: n/a semantics (N/A, excluded, would-light, never 0), per-dim provenance, detail override | tested | test_report_model.py (5) |
| routing: authoritative/heuristic incl absent/partial/stale/malformed/mixed | tested | test_routing.py (5) |
| sanitize: strip CSI/OSC/ESC/control/bidi; one_line collapse+truncate | tested | test_sanitize.py (9) |
| renderers: deterministic card; hostile strings neutralised end-to-end; UTF-8 encodable | tested | test_negative_fixtures.py, test_grade_cli.py |
| CLI: terminal/markdown/json + exit codes (0/2/3) | tested | test_grade_cli.py (7) |
| negative fixtures: bare/empty/shallow/huge+binary graceful | tested | test_negative_fixtures.py (6) |
| empirical record/replay + manifest well-formedness | tested | tests/empirical/test_replay_mechanism.py (7) |
| empirical real-OSS band + ordering assertion | untestable (`requires-external-nondeterministic-service`) | opt-in `-m empirical`; SHAs `PENDING-G5`; loud skip; the launch gate is G5 |
