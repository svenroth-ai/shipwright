# Iterate: G5 — Empirical verification & calibration suite (shipwright-grade)

- **run_id:** `iterate-2026-07-06-grade-g5-empirical-suite`
- **Campaign:** `2026-07-03-shipwright-grade` · sub-iterate **G5** (final; gates the public launch)
- **Intent:** FEATURE (grows G1's seeded harness into the full curated real-repo verification set)
- **Complexity:** medium (overrides classifier `small`; new runner + multi-module harness + CI gate + docs + engine-adjacent capture refactor)
- **Spec Impact:** ADD (new test-harness + CI + docs; the shared scorer is UNCHANGED)
- **Risk flags:** `touches_io_boundary` (runner does `json.dump/load` + `yaml.safe_load`) → Boundary Probe + round-trip test enforced. `.github/workflows/` add → Tier-3 pr-review (handle at F11).
- **Full design:** `Spec/shipwright-grade-plan.md` §13 + §14.

## Intent

Point the grader at real, well-known OSS repos pinned to a commit SHA and prove the
rubric grades reality sensibly (bands + relative ordering), not just that the code does
what we coded. The rendered reports double as the launch-page example gallery. This is the
framework's own "empirical probe over unfalsifiable confidence" principle applied to the
grader itself.

## Locked decisions

1. **Determinism = SHA-pin + record/replay.** Every target pinned to a 40-hex SHA; the
   projected result is cached under `tests/empirical/fixtures/`. The suite **replays from
   cache** (fully offline, deterministic) and does NOT rot when GitHub expires run logs
   (~90d). Network only to `--refresh`.
2. **Cache boundary = projected `GradeInputs` + report-extras** (post-projection,
   pre-engine), NOT the final grade. Rationale: §14 wants ordering assertions to *catch
   rubric regressions* → the engine (`compute_grade`) MUST run on every offline replay.
   The raw `gh` call log is stored alongside as audit evidence (§7 "cache the fetched
   gh/JUnit/SARIF payloads") but is not on the offline-replay path.
3. **Assert bands + relative ordering** (`exemplary > average > poor`), never exact scores.
   A drift in an exact score is a **review signal** (a fixture JSON diff on `--refresh`),
   not a red build.
4. **Calibration tunes the projection heuristics (§4/§5), NEVER the shared scorer.**
5. **Reputational guard:** `poor` (D/F) entries in the public gallery use only
   archived / self-EOL repos (e.g. `request/request`), never a living single-maintainer
   project put on blast.

## Scope / deliverables

- **Manifest** `tests/empirical/repos.yaml`: SHA-pinned `{name, url, pinned_sha,
  expected_band, rationale, tags}` spanning A→F + edge cases (monorepo / no-CI / no-tests /
  huge / polyglot / non-English) that assert ROBUSTNESS + the ~60s budget, not a band.
- **Fetch-at-SHA** `tests/empirical/fetch.py`: hardened `git init + fetch --depth 1 <sha> +
  checkout FETCH_HEAD` (reuses `clone.normalize_url` scheme allowlist + `git_exec`), plus a
  recording `gh` wrapper.
- **Record** `tests/empirical/record.py`: fetch@SHA → project → capture `GradeInputs` +
  report-extras + raw-gh → write fixture JSON (network; `--refresh`).
- **Engine-adjacent capture:** additive refactor of `grade_inputs_projector.grade_context`
  to expose the pre-engine `GradeInputs`/extras via a `grade_context_captured` helper —
  `grade_context`'s public return is byte-identical (zero G1–G4 behavior change).
- **Replay+grade** `tests/empirical/assertions.py`: `GradeInputs(**fx) → compute_grade →
  build_report_model → band`; band + cross-repo ordering assertions.
- **Gallery** `tests/empirical/gallery.py`: per-repo HTML report + a summary index page.
- **Runner** `tests/empirical/run_empirical.py`: manifest → replay-or-refresh → grade →
  assert → write gallery + summary table. Standalone CLI + the `-m empirical` pytest driver.
- **CI** `.github/workflows/grade-empirical.yml`: `workflow_dispatch` opt-in (network + gh),
  uploads the gallery with size/retention caps; documented launch gate; NOT in the PR gate.
- **Docs:** calibration loop in the grade plugin (contradiction → tune projector → refresh →
  review the fixture diff).
- **Hermetic proof** `tests/empirical/test_run_empirical.py`: default-suite tests that build
  a synthetic git repo, record→replay end-to-end with NO network (proves the mechanism +
  the runner path in the PR gate).

## Affected boundaries

- `tests/empirical/fixtures/*.json` — record/replay cache (json.dump/load round-trip).
- `tests/empirical/repos.yaml` — manifest (yaml.safe_load).
- `gh` API responses — captured via a recording runner; replay is offline.
- `grade_context` internal seam — additive capture; public contract unchanged.

## Acceptance Criteria (from the sub-iterate spec)

- [ ] `repos.yaml` with SHA-pinned entries spanning the grade range + edge cases.
- [ ] Record/replay cache under `fixtures/`; deterministic offline (replays); `--refresh`+net.
- [ ] `run_empirical.py`: fetch/replay → grade → assert band + ordering; robust edge cases.
- [ ] Summary table + HTML report gallery (index) as CI artifacts; size/retention caps.
- [ ] Opt-in CI job (network+gh); skipped in the hermetic PR gate; documented launch gate.
- [ ] Calibration loop documented (contradictions → tune projection heuristics, never scorer).
- [ ] ruff clean; modules ≤300 LOC.

## Test plan

- Hermetic (default suite, PR gate): `test_replay_mechanism.py` (kept) + NEW
  `test_run_empirical.py` — synthetic-repo record→replay→grade→gallery, band + ordering,
  edge-case robustness (no-tests repo → n/a, never crash), offline-miss skips loudly.
- Empirical (`-m empirical`, launch gate): real repos, replayed from recorded fixtures;
  `--refresh` records live. Proof-subset recorded in this session (flask/express/request).

## Confidence Calibration

- **Boundaries touched:** fixtures JSON round-trip (`json.dump/load`); `repos.yaml`
  (`yaml.safe_load`); gh capture (redacted audit); the `grade_context` capture seam;
  `.github/workflows/` (opt-in gate).

- **Empirical probes run (findings):**
  1. Record→replay round-trip is **byte-identical** to the live ReportModel
     (`test_project_fixture_replays_to_identical_report`) — the touches_io_boundary probe.
  2. **Live record of the proof subset** (flask/express/request) succeeded over the real
     network + gh — the fetch@SHA + projection + gh enrichment path works end-to-end.
  3. **The suite caught a real defect in itself** (`--depth 1` starved history → `events_total=1`);
     fixed to depth-500; re-recorded → stable across runs (deterministic replay).
  4. **The suite caught a real projector miscalibration** (flask F 19.9 < deprecated request
     41.2; ordering inverted) — the gate is correctly RED; calibration is the follow-up (G6).
  5. ruff clean; all new modules ≤300 LOC; full grade suite 306 passed pre-review;
     external plan + code review (GPT-5.4 + Gemini 3.1 Pro) applied.

- **Test Completeness Ledger** (principle: testable ⇒ tested; 0 untested-testable):

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | `grade_context` byte-identical after capture refactor | tested | `test_projector_capture::delegates_identically` |
  | `GradeInputs` JSON round-trip → same grade | tested | `test_projector_capture::round_trip`, `test_run_empirical::json_round_trips` |
  | `grade_from_fixture` offline replay == live model | tested | `test_run_empirical::replays_to_identical_report` |
  | `schema_version` mismatch → actionable error | tested | `test_run_empirical::schema_version_mismatch_is_actionable` |
  | `parse_band_set` ranges | tested | `test_parse_band_set_ranges` |
  | `assert_band` / `assert_ordering` (cross-tier) | tested | `test_run_empirical::ordering_holds`, `test_run_offline_pass_path` |
  | gh audit log redacted (no raw body) + `input_text` passthrough | tested | `test_gh_audit_log_is_redacted`, `test_recording_gh_passes_through_input_and_redacts` |
  | no-signal repo → honest n/a, no crash | tested | `test_no_signal_repo_grades_with_honest_na` |
  | runner offline pass path + gallery render | tested | `test_run_offline_pass_path_and_gallery`, `test_main_offline_smoke` |
  | strict missing-fixture = FAIL / lenient skip | tested | `test_run_strict_missing_fixture_fails` |
  | record rejects authoritative target | tested | `test_record_rejects_authoritative_target` |
  | fetch rejects non-SHA before network | tested | `test_fetch_rejects_non_sha_before_network` |
  | `preflight_network` (missing git / unauth gh / ready) | tested | 3 `test_preflight_*` tests |
  | manifest well-formed + real SHAs + spread + ordering | tested | `test_replay_mechanism::TestManifest` |
  | fetch@SHA network + treeless fallback | untestable → `requires-external-nondeterministic-service` | covered empirically by the live proof-subset record |
  | `record_repo` remote fetch | untestable → `requires-external-nondeterministic-service` | covered empirically (live record) |
  | CI launch-gate workflow (`grade-empirical.yml`) | untestable → `requires-external-nondeterministic-service` | GH Actions runner; validated on dispatch |
  | grade `render_html` report content | untestable → `covered-by-existing-test` | G3 `test_html_report` |

- **Confidence-pattern check:** asymptote (depth) — the record/replay boundary is proven
  byte-exact + deterministic across re-records, not asserted by confidence. Coverage
  (breadth) — every hermetic behavior tested; the two network-only behaviors are covered by
  the empirical probe (the live record ran successfully). No `cross_component` machinery
  touched → no integration-composition ledger row required.
