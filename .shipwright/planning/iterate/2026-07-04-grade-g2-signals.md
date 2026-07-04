# Iterate: G2 — grade signals (security + deps + gh test-health tiers + size)

- **Run ID:** iterate-2026-07-04-grade-g2-signals
- **Campaign:** 2026-07-03-shipwright-grade · **Sub-iterate:** G2
- **Intent:** FEATURE · **Complexity:** medium (locked)
- **Spec (ACs, locked):** `.shipwright/planning/iterate/campaigns/2026-07-03-shipwright-grade/sub-iterates/G2-signals.md`
- **Design:** `Spec/shipwright-grade-plan.md` §4/§5/§8/§14
- **Risk flags:** `touches_io_boundary` (JUnit XML / SARIF-JSON / lockfile parsing),
  `touches_public_api` (`GradeInputs.oversize_file_ratio` — exported engine type),
  `touches_build` (grade `pyproject.toml`+`uv.lock` add `defusedxml`; perf layer
  skips — Python plugin, no dev_url / build artifacts).

## Spec Impact
**MODIFY** (engine: additive-only) + **ADD** (grade plugin: new signal modules).
The engine change is byte-identical for existing inputs (golden-regression gated).

## Design decisions (resolved from plan; not re-asking the user)
1. **Engine additive field** `oversize_file_ratio: float | None = None`; dim-6 gains an
   `elif inp.oversize_file_ratio is not None:` branch scored **only when
   `bloat_ratchet_delta is None`**. Byte-identical when the field is `None`
   (the ratchet + no-baseline paths keep their exact detail **and anchor**). New
   branch: honest distinct anchor ("bounded module size (ISO/IEC 25010)") + detail
   from the ratio; the precise "N/M source files over threshold" string is layered
   in via the projector's existing `detail_overrides` (which has the counts).
2. **Size curve** (`§12` open item): `score = 1 - oversize_ratio` (fraction of source
   files *within* the size threshold). Linear, interpretable, defensible for a v1
   heuristic. Threshold = 300 LOC (constitution source-file ceiling).
3. **Test-health tiers** (`§5`, best-available wins, tier stamped in provenance):
   - **Tier 1 — CI JUnit** (network): latest completed run on the default branch →
     `gh run download` → hardened JUnit parse → real `passed/total`.
   - **Tier 2 — Scorecard CI-Tests** (network): ONE GraphQL `statusCheckRollup` over
     recent merged PRs → `passed = PRs whose merge commit carried a successful
     test check`, `total = PRs examined`. Scorecard's own CI-Tests semantics, so
     mapping it into the pass-ratio dimension is faithful; the detail names the tier.
   - **Tier 3 — static inventory** (local): present-not-executed → **score stays n/a**
     (a static count cannot fabricate a pass ratio); surfaced as detail (G1 behavior).
4. **Security** (network): fetch code-scanning analysis SARIF for the default branch via
   `gh api` → parse with `security_findings._findings_from_sarif` (suppression-aware) →
   `summarize_ci_security` → `grade_security_signal`. `n/a` on local-only / no
   code-scanning / 403 / invalid SARIF. Never a false CRITICAL.
5. **Dependency** (local): `collectors.collect_dependencies` → `sbom_render._classify`.
   Grade **only the deps we could actually inspect** (`resolved + no_license`);
   `NOT_INSTALLED` (no venv — a scan-env artifact, not repo drift) is excluded. If
   nothing is inspectable → **n/a** (honest: "licenses not resolved without install").
6. **Network policy** (`§14 D`): `--allow-network` (default off) master switch. With it
   on, a detected **private** remote auto-disables enrichment unless
   `--allow-network-private` is also passed. Provenance stamps exactly which APIs ran
   (`network_enrichments`) or why they didn't (`network_note`). Local-only still grades
   on git-history + static inventory + local size/deps.
7. **XML hardening** (`§14 A`): JUnit parsed with `defusedxml` (DTD + external entities
   off) → XXE / billion-laughs safe. SARIF is JSON (already XXE-safe via `json.loads`).

## New / changed surface
- Engine: `_grade_types.py` (+field), `control_grade.py` (dim-6 elif).
- Grade lib (new, each ≤300 LOC): `gh_bridge.py`, `network_policy.py`, `junit_xml.py`,
  `test_health_signal.py`, `security_signal.py`, `dependency_signal.py`,
  `size_signal.py`, `signal_bundle.py` (aggregator the projector calls).
- Grade lib (changed): `grade_inputs_projector.py`, `report_model.py`,
  `scripts/tools/grade.py` (flags), `git_exec.py` (remote/owner helper), `pyproject.toml`.
- Reuse (import, not fork): `security_findings.py`, `collectors.collect_dependencies`,
  `sbom_render._classify/is_copyleft`, `ci_security.summarize_ci_security/
  grade_security_signal`.

## Acceptance Criteria (from the sub-iterate spec) — tracked
See the sub-iterate spec; each AC maps to a test in the Ledger below.

## Confidence Calibration
- **Boundaries touched:** JUnit XML parse (untrusted), SARIF-JSON parse (reused),
  lockfile→license (reused), `gh` subprocess (network), `GradeInputs` engine schema.
- **Empirical probes run:**
  - **E2E on a real repo:** `grade.py <worktree>` (local-only) lit maintainability
    "153/1003 source files over 300 LOC" (0.85) + dependency "0/7 inspected … (2 not
    resolved without install)" (1.00); security/test-health honest n/a; grade F/49.0
    consistent with the repo's low change-traceability. Reasons match the dim table.
  - **XXE + billion-laughs fixtures** → both rejected to `None` (DTD forbidden), no
    file read, no crash.
  - **Malformed SARIF** `{"runs": null}` / `"x"` / `5` → `n/a`, NOT a clean 0-scan.
  - **Poisoned JUnit** `tests="inf"` / 400-digit → degrades to 0, one bad file never
    aborts aggregation (a good sibling's real ratio survives).
  - **Byte-identity:** the full compliance suite (916) + 8 golden-regression asserts
    stay green with the additive field.
  - **Adversarial fresh-context review** (Opus): 0 critical/high; 2 MEDIUM false-clean
    vectors (SARIF non-list `runs`; `_int` OverflowError) + 2 low hardening items — all
    4 fixed with regression tests.
- **Test Completeness Ledger:** every behavior introduced/changed is `tested`; the
  only `untestable` row is the live network round-trip, deferred to G5's opt-in suite.

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | Engine: `oversize_file_ratio` field + dim-6 elif; byte-identical when None | tested | test_grade_oversize_additive.py (8) + compliance suite (916) |
  | Size proxy (oversize ratio, strict `>`, caps) | tested | test_size_signal.py (6) |
  | Dependency hygiene (NOT_INSTALLED-honest, copyleft) | tested | test_dependency_signal.py (7) |
  | JUnit hardened parse (XXE/billion-laughs, aggregation, inf-guard) | tested | test_junit_xml.py (13) |
  | `gh` runner classification + remote/slug parse | tested | test_gh_bridge.py (20) |
  | Network policy (local-only / private auto-disable / override) | tested | test_network_policy.py (9) |
  | Security signal (SARIF→hc, suppression, n/a paths, ref-filter, false-clean guards) | tested | test_security_signal.py (15) |
  | Test-health 3 tiers, best-available, real fetchers | tested | test_test_health_signal.py (10) |
  | signal_bundle mapping (kwargs/details/provenance) | tested | test_signal_bundle.py (6) |
  | report_model provenance-override + network fields + reason consistency | tested | test_report_model.py (TestG2Provenance + reason) |
  | Renderers network line (both formats, both states) | tested | test_render_network.py (2) |
  | CLI flags + local-only-without-remote | tested | test_grade_cli.py (+2) |
  | Reused-collector read-only audit (compliance license libs) | tested | test_reused_collector_audit.py (+2) |
  | Live `gh` network round-trip to real GitHub | untestable — `requires-external-nondeterministic-service` (all logic hermetically injected; live path = G5 opt-in suite) | reuse_bridge + injected-`gh` tests cover the parsing/logic |
- **Confidence-pattern check:** *depth* — not "I'm confident" but empirical probes +
  an adversarial reviewer whose findings were fixed and pinned. *breadth* — 182 grade +
  62 engine tests cover every measurable/n-a/degradation/hardening path.
  *integration composition* — no `cross_component` machinery touched (the
  `CROSS_COMPONENT_FILE_PATTERNS` are merge/churn/hooks/phase-validators; none in this
  diff), so `check_integration_coverage` recomputes the flag as false → no
  integration-behavior required. Cross-plugin **reuse** (compliance collectors + shared
  `security_findings`) is nonetheless integration-tested via the real loaders in the
  dependency/security/audit tests.
