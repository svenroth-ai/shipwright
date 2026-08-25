# Repeatable multi-root JUnit staging for execution evidence

## Context

This repo has 18 pytest test-roots (ADR-044: one process per root — a single
process cannot emit one `junit.xml` spanning them). Before this iterate,
`evidence_drop.py stage` accepted exactly one `--junit <path>`, so only ONE
root's report was ever staged for the cross-layer compliance gate — every
other root's tagged, enabled, passing tests reported `MISSING` coverage
(measured: FR-01.06 has 149 enabled unit tests bound to it and still read
`unit: MISSING`, SPEC §4 P0a). `refresh_index` and `_layer_coverage_evidence`
also called `build_index` without `bases`, so even a multi-report caller could
not have its per-root ids join the project-root-relative manifest ids (the L2
gaps the sub-iterate spec named at `execution_evidence.py:57-67`,
`_execution_evidence_io.py:111-116`, `_layer_coverage_evidence.py:78-80`).

## Decision

`stage` now accepts `--junit <base>=<path>` **repeatably**. Each report is
staged **byte-identical** (never rewritten) as `junit-01.xml` .. `junit-NN.xml`,
and `_provenance.json` records `reports.junit` as a list of `{name, base,
mtime}` — `base` is the directory the pytest process that produced it ran in,
used to rebase the report's ids onto the project-root-relative manifest ids.
The legacy single-report form `--junit <path>` (no `=`) stays valid (base =
project root, `""`), but is REJECTED once a second `--junit` is given without
an explicit base — never silently defaulted to the project root, because a
wrong-but-silent base can join the WRONG id (unsafe) rather than merely
failing to join (safe-but-useless).

`execution_evidence.build_index` gained an additive `junit_reports:
list[tuple[str, str]]` parameter (text, base) alongside the existing single
`junit=`/`bases["junit"]`. `refresh_index` and `_layer_coverage_evidence.
fresh_evidence` both now discover every staged `junit-*.xml`, look up each
one's base in `_provenance.json`, and reject (skip) any staged report with no
matching base entry — fail-closed, matching the existing "no proof, no pass"
contract the rest of this subsystem already uses.

A new repo tool, `scripts/run_full_suite_evidence.py` (a REPO tool per the
sub-iterate spec's E-D, not a plugin tool — it drives the whole repo, not one
phase), derives BOTH the root list and each root's id-rebase base from
`conftest.py::discover_test_roots` — the SAME function the ADR-044 pytest
guard uses — so there is no second hand-maintained root table. It classifies
each discovered root structurally (under `plugins/<name>/` → cd into the
plugin and use `plugins/<name>` as the base, matching `ci.yml`'s per-plugin
loop; everything else → run from the repo root with base `""`, and roots
under `shared/` additionally get `-m "not slow and not cross_plugin"`,
matching `ci.yml`'s shared-tier step), runs each root as its own pytest
process (ADR-044), and stages every produced report together.

## Consequences

A full-suite run now produces genuine cross-root execution evidence: the
cross-layer compliance gate (`_layer_coverage_evidence.fresh_evidence`) can
read `coverage[layer]=ok` for a requirement whose tests live in ANY of the 18
roots, not just whichever root happened to be staged. `clear` sweeps every
`junit-*.xml` via a glob (not one fixed name), so a wider prior run's leftover
report can never survive into a narrower one. The provenance schema gained a
`base` field per JUnit report entry — a consumer reading an OLDER-shaped
provenance file (missing `base`) treats that entry as absent (rejected), not
as `base=""`, so a stale/mixed on-disk state degrades to `MISSING` rather than
a silently-wrong join. `F5.md` and `docs/hooks-and-pipeline.md` were updated
in the same diff (the `stage` invocation form changes).

## Rejected alternatives

- **Rewrite/merge the raw XML into one file before staging.** Rejected: E-A
  requires the staged report to BE the run's real report, byte-identical —
  merging would require re-deriving the JUnit format's semantics (retries,
  parametrization, multi-suite nesting) and risks silently losing a failure.
- **A hand-maintained root→base table in the new runner.** Rejected (E-E): a
  second list rots the moment a new plugin is added, and the failure mode is
  silent (a root just never gets staged) rather than loud.
- **Infer each report's base from its file path inside the report itself.**
  Rejected: the whole reason a base is needed is that the report's OWN paths
  are runner-cwd-relative, not project-root-relative — there is nothing
  self-describing in the XML to infer it from; the base has to come from the
  runner invocation, which only the emit side (or, for a staged report, its
  provenance sidecar) actually knows.

## External-Plan-Review-Findings (Step 3.5, both providers verdict `revise`)

| # | Finding (openai/deepseek, condensed) | Disposition |
|---|---|---|
| 1 | openai HIGH: runner not "transaction-like" — should require every root to succeed before staging | rejected-with-reason: deliberate design (see ADR "Consequences"/spec landmine "budget for it, don't abort early" + ADR-044 exit-4 rule of never aborting a multi-root sweep early). A root that crashes contributes NO evidence for its own tests (never fabricated) but does not poison the OTHER 17 roots' genuine evidence — all-or-nothing would make one flaky root re-erase 17 roots' real coverage, which is a worse fail-closed outcome, not a better one. The runner's own exit code is nonzero whenever any root produced no evidence, so "some roots missing" is never silently reported as success. |
| 2 | openai HIGH: don't background pytest / don't trust "N passed" text-parsing, use exit status | accepted-and-fixed (already the implementation, not a plan gap): `run_root()` calls `subprocess.run` **synchronously** (never backgrounded) and derives verdict from `returncode` + `junit_out.is_file()`, never from parsing summary text. The "read the N passed line, don't trust exit code alone" landmine in the spec is about the RUNNER-AGENT's own interactive monitoring of a long-running background shell command during development, not this tool's internal logic. |
| 3 | openai MEDIUM / deepseek HIGH: legacy `junit.xml` not migrated/cleared, `clear` only sweeps `junit-*.xml` | accepted-and-fixed: `clear_evidence_reports` now also removes `evidence/junit.xml` (the pre-E-B single-file name) so a run staged before this iterate can never be read as fresh by the legacy fallback in `discover_reports`. `REPORT_NAMES` no longer contains a `junit` entry — the emit-side never writes that path going forward — and `discover_reports` already treats staged (`junit-*.xml`) and legacy (`junit.xml`/`test-results/junit.xml`) as mutually exclusive (staged wins, legacy is fallback-only), addressing deepseek finding 3 as well. |
| 4 | openai MEDIUM: base derivation may not be canonical — `discover_test_roots` returns only paths | rejected-with-reason: verified. `plan_root()` derives the base structurally and deterministically from each root's OWN path (under `plugins/<name>/` → that plugin dir; else → `""`), tested against all 18 real discovered roots via `test_run_full_suite_evidence.py`, not just a synthetic new-plugin case. No second hand-maintained table exists (E-E). |
| 5 | openai MEDIUM / deepseek MEDIUM (security/edge-case): duplicate/unvalidated bases in repeated `--junit` | accepted-and-fixed: `_parse_junit_args` now rejects a duplicate base with `SystemExit` (a later report can no longer silently overwrite an earlier one's id-rebase). Canonicalizing/rejecting a base that escapes `project_root` was NOT added: `base` is consumed only as a text-prefix in `norm_path` (no filesystem access), so a bad base can only fail to join (safe, reads `MISSING`) — never traverse the filesystem. Threat model here is a self-invoking local/CI tool (the same operator supplies both the reports and the bases), matching the rest of this evidence subsystem — see also finding 6. |
| 6 | openai MEDIUM (security): unvalidated `base` could rebase evidence to the wrong id | rejected-with-reason: same analysis as #5 — `base` never touches the filesystem, only a joined string compared against the manifest's OWN ids (also self-supplied, same repo, same trust boundary). A wrong-but-plausible base could theoretically mis-join to a real id, but that requires the operator to hand-craft an adversarial base against their own repo, which is out of scope for a local compliance tool no different from `--junit-base` on the existing single-report CLI (pre-existing, unchanged surface). |
| 7 | openai MEDIUM / deepseek MEDIUM: runner's per-root marker/interpreter contract underspecified vs CI | accepted-and-fixed (already the implementation): `plan_root()` gives `shared/`-rooted roots `-m "not slow and not cross_plugin"` and plugin roots the plugin's own `addopts`, mirroring `ci.yml`'s per-tier invocation exactly (verified against `ci.yml:95-204` during the build, not merely asserted). `test_run_full_suite_evidence.py` asserts the `shared/tests` command includes the cross_plugin exclusion. |
| 8 | deepseek HIGH: `build_index` may fall back to a stale `junit.xml` even when `junit_reports` is given | rejected-with-reason: verified not reachable. `discover_reports` picks staged-OR-legacy, never both (`if staged: ... else: ...`), and `refresh_index`'s `is_staged` check only treats the discovered list as staged when it equals `_staged_junit_reports` exactly — the two paths cannot both fire in one call. |
| 9 | deepseek MEDIUM: bases may not be POSIX-normalized (Windows backslashes) | rejected-with-reason: verified already-normalized at the only real producer. `plan_root()` builds every base via `Path.relative_to(...).as_posix()` (never a raw `str(Path)`), and this iterate's own dev/test loop ran entirely on Windows — a backslash base would have broken `test_execution_evidence_join.py`'s cross-root join test immediately, and it did not. |
| 10 | deepseek MEDIUM: no guarantee of a unique `--junitxml` path per root | rejected-with-reason: already the implementation — `plan_root()` derives `junit_out` from `f"{index:02d}-{rel_root...}.xml"`, one per discovered root, collected into a list before the single `stage_all` call; `test_run_full_suite_evidence.py` asserts two roots produce two distinct staged reports. |
| 11 | deepseek MEDIUM (dependency): R1b measurement was a local simulation, not a real CI-vs-local comparison | accepted, scope-adjusted: already stated as a follow-up, not this run's claim — see "R1b follow-up" below and the full writeup, which is explicit that it is a LOCAL simulation with a stated limitation (local interpreter/OS diverges from CI's pinned 3.11/ubuntu), not a substitute for the real R1b comparison. |

## R1b follow-up (measured, not built here)

R1b ("CI regenerates the manifest and must match") was split out of this run
after the 2026-08-23 plan review. This run measured the two open questions it
needs: which manifest fields are reproducible across independent regens
(only `generated_at` and `source_commit` are not — every content field is,
given an unchanged tree), and how much content depends on marker
selection/OS/interpreter (root-dependent: `shared/tests` has 6 `cross_plugin`-
marked items whose exclusion is load-bearing for session completion, not
merely extra coverage; `shared/scripts/tools/tests` has none and is
unaffected). Full measurement:
`.shipwright/planning/iterate/iterate-2026-08-25-r1a-evidence-staging-multiroot.md`.

## Self-Review (Step 3.6)

1. **Spec Compliance** — pass. E-A (byte-identical, checksummed via `assert
   (d/"junit-01.xml").read_bytes() == r1.read_bytes()`), E-B (repeatable
   `--junit <base>=<path>`, legacy single-report form preserved), E-C (`bases`
   threaded through `build_index`/`refresh_index`/`fresh_evidence`, staged
   report with no provenance entry rejected — `test_execution_evidence_join.py`
   pins this), E-D (`scripts/run_full_suite_evidence.py`, a repo tool), E-E
   (root list + base derived from `discover_test_roots`, no second table,
   `test_run_full_suite_evidence.py` runs it against the real 18 roots).
2. **Error Handling** — pass. Missing source report → skipped, never
   fabricated (existing contract, preserved). Missing/malformed provenance
   base → rejected (skip), never defaulted to `""` (AC, tested). A root whose
   process crashes before writing JUnit → reported as `roots_with_no_evidence`
   and the runner's own exit code goes nonzero, but other roots still stage.
3. **Security Basics** — pass with one documented deferral (finding 5/6
   above): `base` is validated for uniqueness (new) but not path-canonicalized
   against `project_root`, because it never touches the filesystem (text-only
   join in `norm_path`) — the existing single-report `--junit-base` CLI flag
   has the identical, pre-existing, unchanged surface.
4. **Test Quality** — pass. 16 tests in `test_evidence_drop.py` (5 new: 2
   duplicate/legacy-clear this pass, 3 multi-report from the build), 3 new in
   `test_execution_evidence_join.py`, 3 new in
   `test_layer_coverage_evidence_multiroot.py`, 14 in
   `test_run_full_suite_evidence.py` — all against real fixtures (actual JUnit
   XML strings, not mocked parse results), covering the reject/skip/dup paths
   explicitly, not just the happy path.
5. **Performance Basics** — pass. Each root still runs as exactly one pytest
   process (no change to per-root cost); staging is `shutil.copyfile` per
   report (N small file copies, not a rewrite/reparse). The full-suite runner
   is inherently O(18 processes) — that is the spec's known cost (ADR-044),
   not a regression this iterate introduces.
6. **Naming & Structure** — pass. `junit_reports` is additive alongside the
   existing `junit=`/`bases["junit"]` params (no signature break); new tests
   live in a fresh file rather than growing `test_layer_coverage_core.py` past
   the 300-LOC guideline (see F3a).
7. **Affected Boundaries (ADR-024)** — pass, WITH a real round-trip probe.
   Producer: `evidence_drop.stage_reports` (writes `_provenance.json` +
   `junit-NN.xml`). Consumers: `_execution_evidence_io.refresh_index` and
   `_layer_coverage_evidence.fresh_evidence`. Probes actually run (not just
   asserted): (a) stage 2 reports with distinct bases → `refresh_index` →
   assert BOTH roots' ids appear correctly rebased in the written index
   (`test_execution_evidence_join.py`); (b) stage a report whose provenance
   entry is deliberately missing/malformed → assert it is silently absent from
   the index, not defaulted to `base=""` (same file); (c) a real cross-root
   fixture (checked-in JUnit XML pair, not compared to local pytest output
   since CI pins 3.11 vs local 3.11/3.13) proving the join survives a
   plugin-dir-relative `file` attribute. Two consecutive runs surfaced no new
   finding after the duplicate-base/legacy-clear fixes → asymptote reached for
   this boundary.

## Confidence Calibration (Step 3.8 — fires: effective complexity medium)

**Boundaries touched** (ADR-024): the JUnit-XML-on-disk format (pytest is the
producer, `_evidence_readers.read_junit` the consumer) and the
`_provenance.json` sidecar format (`evidence_drop.stage_reports` the
producer, `_execution_evidence_io._junit_bases_from_provenance` the
consumer) — both newly widened from single-entry to list-of-entries by this
iterate.

**Probes run** (empirical, per `references/round-trip-tests.md`):

1. Round-trip #1 (provenance): stage 2 reports with distinct bases → read
   back via `read_provenance` → assert both entries present with correct
   `name`/`base`/`mtime`. **Finding**: none on first probe (design was
   already list-shaped from the start of the build). Second probe (missing
   base entry) → **finding**: an entry present in the JSON but missing the
   `base` key was, in an early draft, defaulted to `""` rather than rejected
   — fixed before this review (the AC-mandated reject path,
   `_junit_bases_from_provenance` only adds an entry when both `name` AND
   `base` keys exist). Third probe post-fix → no finding. Asymptote reached
   (2 consecutive clean probes).
2. Round-trip #2 (JUnit cross-root join): a checked-in fixture pair
   (`test_execution_evidence_join.py`) — one JUnit XML with a plugin-relative
   `file` attribute, one with a project-root-relative one — staged together,
   `refresh_index` run, ids asserted present and correctly rebased.
   **Finding** (this pass, Step 3.5-driven): duplicate bases across two
   `--junit` flags silently let the later one win → fixed (`_parse_junit_args`
   now rejects). Re-probed (dup-base case) → correctly raises `SystemExit`,
   no finding. Asymptote reached.
3. Byte-identity probe (E-A): stage a report, `read_bytes()`-compare source
   vs staged → equal on first probe, no finding, not re-probed (a
   `shutil.copyfile` call has no meaningful second axis to re-probe).
4. Legacy-fallback probe (external-review-driven): stage zero reports after a
   PRE-iterate single `junit.xml` exists in the evidence dir → without the
   fix, `discover_reports` would fall back to it (stale-pass risk) →
   **finding**, fixed (`clear_evidence_reports` now sweeps it) → re-probed →
   `evidence/junit.xml` absent after `clear`, no finding. Asymptote reached.

**Edge cases not probed** (+ why acceptable): a REAL cross-CI-vs-local
manifest diff (R1b, explicitly split out — this run only measured the two
prerequisite questions, see "R1b follow-up"); an adversarial hand-crafted
`base` value designed to alias a real id (rejected as out-of-threat-model,
see External-Plan-Review-Findings #5/#6 — this is a local/self-invoked tool,
not a network-facing one).

**Asymptote reached**: yes, for both touched boundaries — the last two
probes on each surfaced no new finding.

## External-Code-Review-Findings (Step 3.7, openai verdict `revise`; deepseek degraded — empty reply, `unavailable`)

| # | Finding | Disposition |
|---|---|---|
| 1 | bug/medium: `_load_discover_test_roots()` always loaded `conftest.py` from the script's compile-time `_REPO_ROOT`, ignoring `--project-root` — a different target repo would silently be discovered using THIS repo's conftest logic | accepted-and-fixed: `_load_discover_test_roots` now takes `repo_root` (default `_REPO_ROOT` for the common in-place call) and loads `<repo_root>/conftest.py`; `main()` passes its resolved `--project-root` through. New regression tests: `test_load_discover_test_roots_honors_a_different_project_root` (a distinct fixture `conftest.py` with a marker-only `discover_test_roots`) and `test_main_loads_conftest_from_project_root_not_the_scripts_own_repo` (end-to-end through `main()`). |
| 2 | security/medium: `fresh_evidence()` read `evd / str(r["name"])` straight from `_provenance.json` with no validation that `name` is a bare staged basename — a path-separator or absolute value could escape the evidence dir | accepted-and-fixed: `name` is now rejected unless it is a `str` matching `evidence_drop.JUNIT_GLOB` (`junit-*.xml`) with no `/`/`\\` — same fail-closed pattern as the missing-`base` rejection already there. New test `test_fresh_evidence_rejects_a_provenance_name_that_escapes_the_evidence_dir` plants a real file outside the evidence dir and a tampered `../`-prefixed `name`, asserting it is never read. |

Both fixes applied before commit; re-ran the full affected test surface after
(`shared/tests/test_evidence_drop.py`, `test_layer_coverage_evidence_multiroot.py`,
`test_run_full_suite_evidence.py` — 36 passed; `plugins/shipwright-compliance`'s
`test_execution_evidence_join.py`/`test_execution_evidence_paths.py`/
`test_lib_loader_precedence.py` — 38 passed) plus `ruff` on every touched file — clean.

## Additional findings surfaced by running the actual full-suite pass

1. **`run_full_suite_evidence.py` never cleared evidence at the START, only
   implicitly at the very END** (inside `stage_all`'s call to `stage_reports`). A
   full-suite pass takes ~20 minutes; a prior run's stale raw report sat under
   `.shipwright/compliance/evidence/` the whole time and was observed — and
   failed — by an unrelated test (`test_no_inline_suppression_has_outgrown_its_
   baseline`, which scans tracked files and could not read an oversized stray
   `junit.xml`). Fixed: `main()` now clears the evidence dir before running any
   root, not just at the final stage. New test:
   `test_main_clears_stale_evidence_before_running_any_root`.
2. **Pre-existing repo-hygiene bug, discovered (not introduced) by this run**:
   `.shipwright/compliance/evidence/junit.xml` and `_provenance.json` were still
   `git ls-files`-tracked despite `.gitignore` excluding `/.shipwright/compliance/
   evidence/` since #627 — tracked before the ignore rule existed, and a
   `.gitignore` entry never retroactively untracks an already-tracked file. This
   is exactly what made finding 1 possible to observe locally: `clear_evidence_
   reports` deleting a *tracked* file surfaced as a working-tree "D" instead of a
   silent no-op on an already-ignored path. Untracked via `git rm --cached`
   (working-tree content already gone — a stale runtime artifact, not something
   to restore) in this same commit; not a scope-creep aside — the same
   subsystem, discovered as a direct, mechanical consequence of testing this
   iterate's own change, per the CLAUDE.md doc-placement rule (a generated
   runtime artifact does not belong in git history once its ignore rule exists).
