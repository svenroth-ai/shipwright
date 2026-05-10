# Iterate Spec: adopt-ci-scaffolders

- **Run ID:** iterate-2026-05-10-adopt-ci-scaffolders
- **Type:** feature
- **Complexity:** large (force-continue per user choice; safety floor: mandatory full review + full test suite)
- **Status:** draft

## Goal

Complete the abandoned CI-template-scaffolding initiative from v0.1.0 era
(commits `c3a6d2f` 2026-03-20 + `8aac61d` 2026-03-23): wire `/shipwright-adopt`
to scaffold profile-specific GitHub Actions CI workflows + the
Claude-Review workflow into adopted brownfield repos, analogous to the
security workflow scaffold landed by `d7a413c`/`3eff53b` (v0.12.0,
2026-05-01). Includes cross-platform OS matrix (ubuntu + windows) as the
default for every CI template — closes the test-portability footgun that
hit `shipwright-webui` v0.8.5 onward (9 push-runs on `main` red because
Windows-pathing tests run on Linux runners). Ship the supporting
`path-helpers.ts.template` so adopted Node projects do not re-invent the
cross-platform path-module heuristic.

## Trigger

The active source of the gap: `shipwright-webui@main`'s CI has been red
since v0.8.5 (4 failing tests in `server/src/core/cli-compat.path-self-heal.test.ts`
because `path.dirname` is POSIX on Linux runners while the tests mock
Windows paths). The webui's `ci.yml` is hand-written because adopt has
never scaffolded a CI workflow for vite-hono profile projects. The fix
in the webui repo is out-of-scope here (separate PR in shipwright-webui);
this iterate closes the structural gap so the next Brownfield-adoption
does not re-invent the same hand-written CI and hit the same trap.

The original intent is documented in:
- Commit `c3a6d2f`: *"GitHub Actions CI template for supabase-nextjs profile"*
- Commit `8aac61d`: *"CI/CD claude-review.yml template for independent review sessions"*
- `plugins/shipwright-adopt/tests/test_security_workflow_scaffold.py:7`:
  *"Auto-write on absence — adopt's whole point is to land Shipwright CI"*

## Acceptance Criteria

- [ ] **AC-1 — `ci_workflow_scaffolder.py`.** New
  `plugins/shipwright-adopt/scripts/lib/ci_workflow_scaffolder.py`,
  analogous in shape to `security_workflow_scaffolder.py`:
  `scaffold_ci_workflow(project_root, profile_name) -> ScaffoldResult`.
  Reads the matched profile name from snapshot.json
  (`snapshot.profile.matched`), picks the right CI template via a
  profile→template map, and writes to `.github/workflows/ci.yml` if
  absent. Idempotent: returns `wrote=False, reason="already_exists"` on
  pre-existing file. Returns `wrote=False, reason="no_template_for_profile"`
  if profile has no registered CI template (no error — graceful skip).

- [ ] **AC-2 — `claude_review_workflow_scaffolder.py`.** New scaffolder
  for `claude-review.yml.template`, profile-agnostic. Scaffolds to
  `.github/workflows/claude-review.yml`. Same idempotency semantics as
  AC-1.

- [ ] **AC-3 — Cross-platform matrix as default in CI templates.**
  `ci-supabase-nextjs.yml.template` (renamed from `ci-nextjs.yml.template`),
  `ci-vite-hono.yml.template` (NEW), and `ci-python-plugin-monorepo.yml.template`
  (NEW) all carry `strategy.matrix.os: [ubuntu-latest, windows-latest]`
  with `runs-on: ${{ matrix.os }}` and `fail-fast: false` for the
  `test` / type-check / lint jobs. Deploy and security-adjacent jobs
  remain Linux-only (Trivy/Gitleaks installation is hard-Debian).

- [ ] **AC-4 — New `ci-vite-hono.yml.template`.** Two jobs (`client-checks`
  + `server-checks`) mirroring the webui's current hand-written pattern
  but with cross-platform matrix. Uses Node 22.x per the `vite-hono`
  profile spec. `npm ci` + `npx tsc --noEmit` + `npm test -- --run` per
  workspace.

- [ ] **AC-5 — New `ci-python-plugin-monorepo.yml.template`.** For this
  monorepo's profile. Cross-platform matrix `os: [ubuntu-latest,
  windows-latest]`. `uv sync` + `uv run pytest plugins/*/tests/` +
  `uv run ruff check .` + `uv run pyright`. Job stays dormant
  (`on: workflow_dispatch` only) — same Phase-B activation discipline as
  the security workflow.

- [ ] **AC-6 — Profile-CI registry in constants.** New
  `shared/scripts/lib/ci_workflow.py` analogous to `security_workflow.py`:
  declares `TEMPLATE_BY_PROFILE` dict mapping profile → template path
  + `WORKFLOW_PATH = ".github/workflows/ci.yml"` +
  `CLAUDE_REVIEW_TEMPLATE_PATH` + `CLAUDE_REVIEW_WORKFLOW_PATH`. Single
  source of truth consumed by both scaffolders and the upcoming drift
  test (AC-8).

- [ ] **AC-7 — Wire into `generate_adoption_artifacts.py`.** New
  Step E.14 (CI workflow scaffold) reads `snapshot.profile.matched` and
  calls `scaffold_ci_workflow`. New Step E.15 (Claude-review scaffold)
  calls `scaffold_claude_review_workflow` unconditionally. Results land
  in `results["ci_workflow"]` and `results["claude_review_workflow"]`
  with the same `{wrote, path, reason}` shape as `results["security_ci"]`.
  Both append their paths to `results["written"]` when `wrote=True`.

- [ ] **AC-8 — Drift tests pin the templates.** New
  `shared/tests/test_ci_workflow_convention.py` (analogous to
  `test_security_workflow_convention.py`): parses each CI template via
  PyYAML, asserts the canonical matrix block is present (`runs-on:
  ${{ matrix.os }}` + `os: [ubuntu-latest, windows-latest]` +
  `fail-fast: false` on the test job), the dormant-trigger contract
  matches (`workflow_dispatch:` active, `pull_request:` and
  `push:` either commented or absent), and that
  `TEMPLATE_BY_PROFILE` in `ci_workflow.py` resolves to a file on disk.

- [ ] **AC-9 — Scaffolder tests.** New
  `plugins/shipwright-adopt/tests/test_ci_workflow_scaffold.py`
  (analogous to `test_security_workflow_scaffold.py`): five tests —
  scaffolds-when-absent, preserves-existing, profile-without-template
  graceful-skip, content-matches-template byte-by-byte, claude-review-
  workflow round-trip.

- [ ] **AC-10 — `path-helpers.ts.template`.** New
  `shared/templates/path-helpers.ts.template` with
  `pickPathModule(input: string): typeof import("node:path")`:
  if `/\\/.test(input) || /^[A-Za-z]:/.test(input)` returns
  `path.win32`, else `path.posix`. Includes a co-located
  `path-helpers.test.ts.template` Vitest suite with at least four
  cases (POSIX path, Windows-with-backslash, Windows-with-forward-slash,
  Windows-drive-only). Template is **standalone, not auto-scaffolded** —
  adopt does not push it; it's a Tier-2 opt-in template like the Vite
  DX bundle (per existing pattern documented in
  `plugins/shipwright-adopt/skills/adopt/SKILL.md:478`).

- [ ] **AC-11 — SKILL.md + docs.**
  `plugins/shipwright-adopt/skills/adopt/SKILL.md` documents the new
  Step E.14 + E.15 in the existing pipeline-section (between E.13 and
  the Tier-5 Visual-frontend-docs step), and lists
  `path-helpers.ts.template` under the existing Tier-2 opt-in
  templates block. `docs/hooks-and-pipeline.md` "Between-Phase Actions"
  for adopt grows two rows. `docs/guide.md` Chapter 4 adopt-phase
  description mentions cross-platform CI as the new default.

- [ ] **AC-12 — All existing adopt tests stay green.**
  `test_adopt_pipeline_subprocess.py`, `test_data_preservation_realistic.py`,
  `test_ci_detector.py`, `test_security_workflow_scaffold.py`,
  `test_artifact_writer.py`, `test_dry_run_reporter.py` — all green
  after wiring.

## Affected FRs

- **FR-01.13 (/shipwright-adopt):** extends — adopt's scope grows from
  "scaffold security CI" to "scaffold CI + claude-review + security CI,
  profile-aware". New AC rows appended; existing FR-01.13 ACs around
  security-only stay verbatim (additive, no regression).

## Out of Scope

- The actual `shipwright-webui` repo fix — fixing the 4 failing
  `path-self-heal` tests in `server/src/core/cli-compat.path-self-heal.test.ts`
  by using `path.win32` vs `path.posix` correctly. That is a separate PR
  in the webui repo, opened immediately after this iterate is merged.
  The `path-helpers.ts.template` from AC-10 is the canonical reference
  for that fix.
- Migration of any pre-existing CI workflow in an already-adopted
  project. Scaffolders are idempotent and skip on pre-existing files.
  Operators who want the new template apply it manually.
- Re-running `/shipwright-adopt` against this monorepo (dogfooding) — the
  monorepo already has its own `.github/workflows/ci.yml`, which the
  new scaffolder would correctly skip via the idempotency rule.
  Verification is done via the subprocess test on a synthetic fresh repo,
  not by mutating this repo's CI.
- Auto-activation of any scaffolded CI workflow. All new templates ship
  dormant (`on: workflow_dispatch` only) per the same Phase-B discipline
  the security workflow uses.

## Design Notes

n/a — backend-only infrastructure change. No UI surfaces touched.

## Affected Boundaries

This iterate **does** touch producer/consumer boundaries:

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/templates/github-actions/*.yml.template` | `ci_workflow_scaffolder.py` + adopt-scaffolded `.github/workflows/ci.yml` | YAML (GitHub Actions schema) |
| `shared/scripts/lib/ci_workflow.py` constants | `ci_workflow_scaffolder.py` (TEMPLATE_BY_PROFILE) + `test_ci_workflow_convention.py` drift test | Python module |
| `generate_adoption_artifacts.py` Step E.14 | `results["ci_workflow"]` consumed by adopt handoff banner | JSON (in-process) |

The drift-protection test (AC-8) is the parametrized N-consumer pattern
from `references/round-trip-tests.md` Section 2: every CI template
must satisfy the same convention-lock assertions (matrix block, dormant
trigger, idempotency-safe header) — the test parametrizes across all
three templates so adding a fourth profile in the future cannot silently
break the contract.

Categories from `references/boundary-probes.md`:
- **Probe 1 (encoding):** PyYAML reads templates as UTF-8 — assert by
  reading via `Path.read_text(encoding="utf-8")` in test.
- **Probe 2 (line-endings):** templates are LF in repo; idempotent copy
  via `shutil.copyfile` preserves bytes — drift test asserts byte-equal
  match after `scaffold` → `read_text` → `template.read_text`.
- **Probes 3-5 (operator-input):** N/A — these are scaffolded
  machine-write outputs, not user-edited. Justified inline in drift
  test docstring.
- **Probe 6 (empty/whitespace):** N/A — templates are full YAML files.
- **Probe 7 (idempotency):** **Critical.** Drift test runs `scaffold`
  twice and asserts second call returns `wrote=False`.
- **Probe 8 (cross-platform):** **The thing this iterate fixes.**
  `path-helpers.ts.template` Vitest suite IS the probe — passes
  identically on Linux + Windows.

## Self-Review (7-point checklist)

Completed 2026-05-11 between build chunks and F0.5.

1. **Code matches spec.** AC-1 through AC-12 all delivered. Cross-checked
   AC IDs against actual files: 10 created + 5 modified + 1 deleted (via
   `git mv` semantic) = 16 changes total (close to mini-plan's estimate
   of "12-15 files"). ✓
2. **Tests are meaningful.** Drift test parses YAML and asserts
   structural invariants (matrix block, dormant triggers, explicit
   permissions). Scaffolder tests verify both happy path AND error paths
   (`profile_unresolved`, `no_template_for_profile`, `already_exists`).
   Vitest tests run real Node `path.win32`/`path.posix` semantics, not
   mock objects. ✓
3. **Edge cases covered.** External-review #O9 (UNC paths, empty
   strings, mixed separators, undefined/null) — all four cases in
   `path-helpers.test.ts.template`. External-review #O12 (profile-
   detection failure vs missing template) — distinct reason codes
   with parametrized tests. ✓
4. **Error paths handled.** `workflow_scaffold_helper.copy_template_if_absent`
   raises `FileNotFoundError` loudly if the source template doesn't
   resolve (development-time bug, not target-project condition).
   Scaffolders catch nothing — that's the right level. ✓
5. **No debug code / TODOs.** Searched all new files for `TODO`/`FIXME`
   /`XXX`/`pdb` — only the deliberate `# TODO` documentation block in
   templates remains, no actionable items. ✓
6. **Conventions respected.** Mirror `security_workflow_scaffolder.py`
   structure verbatim (file-path module loading, TypedDict result,
   `parents[4]` repo-root resolution). Comments follow CLAUDE.md
   "WHY non-obvious" guidance — every block-comment explains the
   reasoning, not the mechanism. ✓
7. **Affected Boundaries.** Producer/consumer triples covered:
   - templates ↔ scaffolder ↔ rendered workflow: round-trip via
     byte-equal test in `test_content_matches_template` (parametrized
     over all 3 profiles + claude-review = 4 round-trips).
   - constants module ↔ drift test: parametrized over `TEMPLATE_BY_PROFILE`
     so every entry is verified to resolve.
   - snapshot.profile.matched ↔ scaffolder: subprocess tests with three
     distinct fixture profiles confirm the lookup path end-to-end.
   ✓

## Confidence Calibration

Filled before F0.5 per Step 7.5 (mandatory at medium+ AND at large).

- **Boundaries touched:** as enumerated in "Affected Boundaries"
  (3 producer/consumer pairs: template/scaffolder, constants/drift-test,
  snapshot/scaffolder-arg).
- **Empirical probes run:**
  1. Drift test (32/32 pass) — every CI template parses as YAML and
     carries matrix + dormant + permissions invariants.
  2. Scaffolder unit tests (18/18 pass) — happy path, idempotency,
     profile-resolution edge cases, byte-equal content match.
  3. Subprocess integration tests (3 profile-parametrized cases pass)
     — real adopt pipeline writes the right CI template for each
     profile fixture.
  4. **Path-helpers Vitest empirical** (18/18 Vitest cases pass on the
     local Windows runner via real `npm install vitest@^3 typescript@^5`
     + `npx vitest run`). This is the regression-direct proof for the
     webui v0.8.5 footgun — `expected '.' to be 'C:\Users\Test\.local\bin'`
     no longer applies because `path.win32.dirname` is used explicitly
     on Windows-shaped input regardless of runner OS.
  5. Full adopt test suite (268 tests) — zero regression from build
     changes.
  6. Integration tests (101 tests) — zero regression.
  7. Cross-plugin sweep (shared/tests + every plugin except deploy/build
     which have pre-existing bash-on-Windows failures unrelated to this
     iterate) — 1488 + 1100+ tests green.
- **Edge cases NOT probed + why:**
  - Probes 3-5 (operator-input categories from
    `references/boundary-probes.md`: POSIX `export` prefix, inline
    `# comment`, quoted `#`) — N/A: templates are machine-write YAML,
    not operator-edited text. Operators may uncomment trigger blocks at
    Phase-B activation but that's a single textual edit, not a parsing
    contract.
  - Probe 6 (empty/whitespace) — N/A for the workflow YAML themselves
    (full files); IS probed for `pickPathModule` (empty + whitespace +
    undefined + null all default to POSIX).
  - Zero-byte / partial pre-existing target file (external-review #O4
    suggestion) — deferred to backlog. Same idempotency contract as
    `security_workflow_scaffolder.py`; consistency over hypothetical
    edge case in this iterate. Tracked in spec § "Risk Acknowledgments".
- **Confidence-pattern check:** No "are you confident?"-style answer
  produced a finding in this run. External-review feedback was applied
  PRE-build (before code existed), so the asymptote heuristic does not
  trigger an extra probe. The 18 empirical Vitest passes + 32 drift
  assertions + 18 scaffolder assertions + 3 subprocess pipeline runs
  are the marginal probes; their finding rate is 0 across the last
  asserted-pass cycle.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest plugins/shipwright-adopt/tests/test_ci_workflow_scaffold.py plugins/shipwright-adopt/tests/test_adopt_pipeline_subprocess.py shared/tests/test_ci_workflow_convention.py -v`
- **Evidence path:** `.shipwright/runs/iterate-2026-05-10-adopt-ci-scaffolders/surface_verification.json`
- **Justification (only if surface=none):** N/A — adopt is a CLI surface;
  the subprocess test in `test_adopt_pipeline_subprocess.py` exercises
  the full pipeline end-to-end against a synthesized fixture repo.

## Risk Acknowledgments

- **Force-continue at large complexity** (user-chosen — "Voll" option):
  this iterate touches ~12-15 files including new scaffolders, three new
  templates, drift tests, and SKILL/docs updates. Safety floor:
  mandatory full review + full test suite + external LLM plan review
  (Step 4). No skipping of Confidence Calibration, full review, or full
  test suite.
- **No regression in already-adopted projects.** This monorepo and the
  webui are both already adopted. Idempotency (AC-9) ensures rerun of
  adopt against them does not overwrite their hand-written CI.
- **Profile-CI map is the new SSoT.** Future profile additions MUST
  also register in `TEMPLATE_BY_PROFILE` or the scaffolder gracefully
  skips with `reason="no_template_for_profile"`. Drift test enforces
  every key in the map resolves to a file on disk.
