---
run_id: iterate-2026-07-15-finalize-bundle
type: mini-plan
---

# Mini-Plan — finalize_bundle.py

## Files to create / modify

| File | Change | Notes |
|---|---|---|
| `shared/scripts/tools/finalize_bundle.py` | **new** | The orchestrator. `main(argv)->int`, `run(payload, project_root, runner)->dict`. ≤300 LOC. |
| `shared/tests/test_finalize_bundle.py` | **new** | Unit tests (payload validation, argv construction, ordering, abort-on-failure, drift-abort, skip-report) via an injected runner. |
| `shared/tests/test_finalize_bundle_integration.py` | **new** | `category:"integration"` — real fixture repo, real sub-tools, bundle ≡ manual-sequence artifact-equivalence. NOT marked `slow` (gates in CI). |
| `plugins/shipwright-iterate/skills/iterate/references/F-finalize-bundle.md` | **new** (or extend an F-index note) | Documents the bundle: payload schema, order, abort semantics, when to use. |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md` | **edit** | F1..F12 index + Finalization prose: note that F1/F3/F4/F5c/F5b MAY be driven in one `finalize_bundle.py` call; F5/F2/F3a/F6 stay manual. |
| `plugins/shipwright-iterate/skills/iterate/references/F1.md` `F3.md` `F4.md` `F5b.md` `F5c.md` | **edit (light)** | One cross-link line each: "or run via `finalize_bundle.py` — see F-finalize-bundle.md". No change to the individual-tool contract. |
| `docs/hooks-and-pipeline.md` | **edit** | Between-phase / finalization section: record the bundle as the orchestration entry point (CLAUDE.md rule — finalization flow change). |
| `CHANGELOG-unreleased.d/Changed/…` | **new (F4)** | One bullet. |

## Work breakdown (sequential, TDD each)

1. **Payload contract + validation** (RED→GREEN). Define the JSON schema
   (`run_id`, `project_root?`, `artifact_sync?`, `decision`, `changelog[]`,
   `iterate_entry`, `finalize{reason,event_extras}`). Validate required sections
   present + well-shaped; error early naming the missing/bad key (AC4). Test:
   missing `finalize` → non-zero, no subprocess.
2. **argv construction per step** (RED→GREEN). Pure functions payload→argv for
   F1/F3/F4/F5c/F5b. Inject a `runner` (default `subprocess.run`) so tests capture
   argv without spawning (AC6, AC7).
3. **Orchestration + ordering + abort** (RED→GREEN). `run()` executes F1→F3→
   F4×N→F5c→F5b; F1 exit 1 = drift-abort (AC3); any step non-zero = abort naming
   the step (AC2); success → JSON with per-step "ok" (AC1). Skipped-when-absent
   reported explicitly.
4. **Idempotency guard** (RED→GREEN). Verify F4 numbering on re-run; if
   `write_changelog_drop` is not idempotent per run_id, the bundle clears this
   run's prior drops before writing (or documents the tool's existing idempotency).
   Test: second bundle run → drop count unchanged (AC-idem).
5. **Integration test** (RED→GREEN). Real fixture repo (model on
   `test_parallel_merge_cascade_integration.py` fixtures); run both paths; assert
   artifact-equivalence modulo event-id/timestamp (AC5).
6. **CLI `main`** — parse `--payload-file` + `--project-root`; print JSON result;
   exit 0/non-zero. Scripted-CLI F0.5 evidence.
7. **Wire into SKILL.md + refs + docs/hooks-and-pipeline.md** (AC8); re-run the
   doc drift/consistency + artifact-path-canon tests.

## Test strategy

- **Unit** (`test_finalize_bundle.py`): injected fake runner records `(argv,
  cwd)` and returns a scripted `(returncode, stdout, stderr)` per step. Covers
  AC1/2/3/4/6/7 + skip-report + ordering, fast, no real subprocess.
- **Integration** (`test_finalize_bundle_integration.py`, `category:"integration"`):
  real temp git repo + real sub-tools; bundle-path vs manual-sequence-path
  artifact-equivalence (AC5). This is the voluntary cross_component composition
  proof.
- **E2E / F0.5:** scripted CLI run of `finalize_bundle.py` on a fixture payload;
  surface=`cli`.
- Run everything under `CI=true` (conftest `$CI`-unset fixture landmine +
  silent-skip CI-discipline).

## Alternative approach (considered, rejected)

Full ~6→1 collapse: bundle also writes F5 (`shipwright_test_results.json` via a
coverage-preserving + surface_verification-folding merge) and the F2/F3a
agent-doc bullets. **Rejected** (user decision 2026-07-15): new write surface on
the framework's highest-blast-radius machinery for ~1 marginal turn. The W4
coverage-drop footgun a safe F5 merge would kill is noted as a possible small
follow-up.

## Rollback

Pure addition + doc edits. Revert = delete `finalize_bundle.py` + its tests and
revert the SKILL/doc cross-links; the individual tools and the manual F-phase
flow are untouched, so finalization keeps working exactly as before.
