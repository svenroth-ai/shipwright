# Mini-Plan: adopt-ci-scaffolders

- **Run ID:** iterate-2026-05-10-adopt-ci-scaffolders
- **Spec:** `2026-05-10-adopt-ci-scaffolders.md`
- **Complexity:** large (force-continued)

## Approach (chosen)

Mirror the established `security_workflow_scaffolder` pattern verbatim
across two new scaffolders (CI + Claude-Review), with a profile-aware
template registry in `shared/scripts/lib/ci_workflow.py`. The security
workflow already follows the canonical "Tier-1 auto-scaffold" pattern
(`Step E.13`, idempotent, dormant-default, drift-test pinned) — the CI
and Claude-Review scaffolders graft onto the same infrastructure.
Three new YAML templates land in `shared/templates/github-actions/`, all
shipping the cross-platform OS matrix as the default.

`path-helpers.ts.template` is deliberately **not** an auto-scaffolded
output. It lives alongside the existing Tier-2 opt-in templates (Vite
DX bundle, dev-error-overlay) per the documented pattern at
`plugins/shipwright-adopt/skills/adopt/SKILL.md:478-491` — operators
copy it manually when they hit cross-platform path bugs. This keeps the
auto-pushed surface minimal and avoids forcing a path-helper into every
adopted Node project.

## Files

### Created (10)

1. `plugins/shipwright-adopt/scripts/lib/ci_workflow_scaffolder.py` —
   ~120 LOC, mirrors `security_workflow_scaffolder.py` structure (file-
   path import of constants, `ScaffoldResult` TypedDict, idempotent
   write).
2. `plugins/shipwright-adopt/scripts/lib/claude_review_workflow_scaffolder.py` —
   ~80 LOC, profile-agnostic variant.
3. `plugins/shipwright-adopt/tests/test_ci_workflow_scaffold.py` — ~250
   LOC, five tests per scaffolder (AC-9).
4. `shared/scripts/lib/ci_workflow.py` — constants module (~40 LOC):
   `TEMPLATE_BY_PROFILE`, `WORKFLOW_PATH`,
   `CLAUDE_REVIEW_TEMPLATE_PATH`, `CLAUDE_REVIEW_WORKFLOW_PATH`,
   `MATRIX_OS_VALUES`.
5. `shared/tests/test_ci_workflow_convention.py` — ~200 LOC drift test
   (AC-8).
6. `shared/templates/github-actions/ci-supabase-nextjs.yml.template` —
   renamed from `ci-nextjs.yml.template`, matrix added.
7. `shared/templates/github-actions/ci-vite-hono.yml.template` — NEW
   (~70 LOC), modeled after current webui hand-written ci.yml + matrix.
8. `shared/templates/github-actions/ci-python-plugin-monorepo.yml.template` —
   NEW (~60 LOC), uv + pytest pattern with matrix.
9. `shared/templates/path-helpers.ts.template` — NEW (~25 LOC),
   `pickPathModule()` heuristic.
10. `shared/templates/path-helpers.test.ts.template` — NEW (~40 LOC)
    Vitest suite for AC-10.

### Modified (5)

1. `plugins/shipwright-adopt/scripts/tools/generate_adoption_artifacts.py` —
   add Step E.14 + E.15 (~25 LOC, mirror E.13's call shape).
2. `shared/templates/github-actions/claude-review.yml.template` —
   unchanged structurally (already correctly Linux-only — claude-review
   job is platform-neutral, no matrix needed); optional 2-line header
   comment documents why no matrix.
3. `plugins/shipwright-adopt/skills/adopt/SKILL.md` — document Step
   E.14 + E.15; list `path-helpers.ts.template` in Tier-2 templates.
4. `docs/hooks-and-pipeline.md` — adopt between-phase actions section
   gets two new rows.
5. `docs/guide.md` — Chapter 4 adopt-phase description mentions
   cross-platform CI default.

### Deleted (1)

1. `shared/templates/github-actions/ci-nextjs.yml.template` — renamed
   to `ci-supabase-nextjs.yml.template` (item 6 above). Tracked as a
   rename in git via `git mv` so history follows.

## Work Breakdown

Five logical chunks, each independently testable. Build order is
strict because later chunks depend on earlier ones:

### Chunk 1 — Constants module + drift test (RED first)

1. RED: write `shared/tests/test_ci_workflow_convention.py` skeleton
   asserting `from lib.ci_workflow import TEMPLATE_BY_PROFILE, ...`
   resolves and every value is a file on disk. Fails because module
   doesn't exist.
2. GREEN: write `shared/scripts/lib/ci_workflow.py` with the four
   constants pointing at the three template paths (two of which don't
   exist yet — drift test will catch this until Chunk 2 lands).
3. REFACTOR: assert convention-lock constants are importable + frozen
   (dict comprehension on TEMPLATE_BY_PROFILE).

### Chunk 2 — Three CI templates + drift assertions

1. RED: drift test grows to assert each template parses as YAML AND
   contains the canonical matrix block (`strategy.matrix.os`,
   `fail-fast: false`, `runs-on: ${{ matrix.os }}`) AND dormant trigger
   pattern (`workflow_dispatch` active, `pull_request` + `push` either
   absent or commented).
2. GREEN: `git mv ci-nextjs.yml.template ci-supabase-nextjs.yml.template`,
   add matrix block. Create `ci-vite-hono.yml.template` and
   `ci-python-plugin-monorepo.yml.template` from scratch per AC-4/AC-5.
3. REFACTOR: parametrize drift test over `TEMPLATE_BY_PROFILE.items()`.

### Chunk 3 — Scaffolder + scaffolder tests (RED first per file)

1. RED: write `test_ci_workflow_scaffold.py` with the 5 tests from
   AC-9. All fail because scaffolder module doesn't exist.
2. GREEN: write `ci_workflow_scaffolder.py`. Mirror
   `security_workflow_scaffolder.py` structure — file-path import of
   constants, idempotent `shutil.copyfile`, ScaffoldResult TypedDict.
   Adds `profile_name: str` arg, looks up template via
   `TEMPLATE_BY_PROFILE.get(profile_name)`, returns
   `wrote=False, reason="no_template_for_profile"` on miss.
3. GREEN: write `claude_review_workflow_scaffolder.py` (simpler, no
   profile argument — single template path).
4. REFACTOR: extract shared idempotency-write helper if duplication
   warrants (decide post-implementation).

### Chunk 4 — path-helpers template + Vitest

1. RED: write `path-helpers.test.ts.template` with the 4 cases from
   AC-10. Cannot fail today because template doesn't exist + no
   project-side test runner runs templates. **Verification deferred to
   F0.5**: the surface_verification runner copies both `.template`
   files into a temp `tmp_project/`, drops a minimal `package.json` +
   `tsconfig.json` + `vitest.config.ts`, and runs `npx vitest run` on
   Linux. (Skill mandates `tests_run > 0` at F0.5; we have 4 cases.)
2. GREEN: write `path-helpers.ts.template` implementing `pickPathModule`.

### Chunk 5 — Wire into adopt + SKILL.md + docs

1. RED: extend `test_adopt_pipeline_subprocess.py` to assert
   `results["ci_workflow"]["wrote"]` is `true` AND
   `.github/workflows/ci.yml` lands in the tmp_project after
   `generate_adoption_artifacts.py` runs against the fixture (which
   uses `vite-hono` profile).
2. GREEN: add Step E.14 + E.15 to `generate_adoption_artifacts.py`.
3. Update `plugins/shipwright-adopt/skills/adopt/SKILL.md` (Step E.14
   + E.15 prose, Tier-2 templates list).
4. Update `docs/hooks-and-pipeline.md` adopt between-phase actions
   rows.
5. Update `docs/guide.md` Chapter 4 short adopt-phase paragraph.

## Test Strategy

- **Unit:** every new module + every existing modified module gets
  its own test file. Total new tests: ~25-30 (five per scaffolder + ~10
  drift-test parametrizations + four Vitest path-helper cases + extension
  of `test_adopt_pipeline_subprocess.py`).
- **Integration:** `test_adopt_pipeline_subprocess.py` exercises the
  full subprocess pipeline against a vite-hono-profile fixture and
  asserts both new scaffolders fire.
- **Drift:** `test_ci_workflow_convention.py` is the parametrized N-
  consumer drift test from `references/round-trip-tests.md` Section 2.
- **Idempotency:** every scaffolder test includes the "second call =
  no-op" assertion (Probe 7).
- **Cross-platform Vitest:** path-helpers tests parametrize against
  `path.posix.dirname()` + `path.win32.dirname()` so they pass
  identically on Linux + Windows runners. F0.5 surface=cli runs them
  on the local (Windows) runner; CI matrix from AC-3 would run them on
  both once the monorepo's `ci.yml` is unlocked.

## Risks + Mitigations

- **Risk:** The webui's hand-written `ci.yml` differs from what
  `ci-vite-hono.yml.template` would scaffold. The template is an
  opinionated reset of what the *future-vite-hono adopt* gets — not a
  migration of the webui's current CI. **Mitigation:** explicit in
  spec out-of-scope (Section 4); webui's CI stays hand-written until
  someone deliberately re-scaffolds.
- **Risk:** Drift test becomes brittle as profile templates evolve.
  **Mitigation:** Test asserts the convention-lock invariants (matrix
  block, dormant trigger, parseable YAML), not surface specifics like
  Node version or workspace layout. Profile-specific evolution stays
  free to happen without touching the test.
- **Risk:** `generate_adoption_artifacts.py` import resolution differs
  in subprocess context (no PYTHONPATH set). **Mitigation:** mirror the
  exact `from security_workflow_scaffolder import ...` pattern from
  Step E.13 — already-proven to work in the subprocess.
- **Risk:** `git mv` of `ci-nextjs.yml.template` to
  `ci-supabase-nextjs.yml.template` could break a grep-based caller we
  did not find. **Mitigation:** ran `grep ci-nextjs` across the entire
  monorepo — zero callers outside the template itself. Safe rename.

## Alternative Considered: Single-template + slot-filling

Instead of three profile-specific templates, ship **one** generic
`ci.yml.template` with `{TEST_COMMAND}` + `{NODE_VERSION}` slots that
adopt fills per-profile (the same slot-filling pattern
`artifact_writer.py` uses for CLAUDE.md and agent_docs).

**Pros:** less template duplication; matrix block + dormant-trigger
contract live in one place; new profile = one new entry in
`TEMPLATE_BY_PROFILE` with no new YAML file.

**Cons:** profile-specific structural differences (vite-hono is
**two** jobs: client + server; supabase-nextjs has a
`security:` job needs-`test`; python-plugin-monorepo has
`uv sync` vs `npm ci`) cannot be expressed via flat slot-fill — would
need Jinja-style conditionals + a templating engine; that's a much
bigger architectural step than this iterate can fit. Three explicit
templates is the simpler honest fit. **Decision: rejected — premature
abstraction.** If a fourth profile shows up with overlapping shape, we
revisit and migrate to slot-fill at that point.

## Out of scope

See spec § "Out of Scope" — webui repo fix, dogfooding re-adopt against
this monorepo, auto-activation of scaffolded workflows, migration of
already-deployed CI in adopted projects.
