# R1a — Execution evidence across all pytest test-roots (campaign req3-04-ac-identity-mono)

**Sub-iterate:** R1a of `req3-04-ac-identity-mono` (Welle 1, unit 2 of 2).
**Spec:** `.shipwright/planning/iterate/campaigns/req3-04-ac-identity-mono/sub-iterates/R1a-evidence-staging-multiroot.md`
(campaign dir is gitignored — this file is the durable, tracked record of the same
work; the worktree/branch this ran in never touches the shared main tree directly).

## What shipped

- `shared/scripts/lib/evidence_drop.py` — `stage` now accepts REPEATED
  `--junit <base>=<path>` (E-B). N reports are staged byte-identical (E-A) as
  `junit-01.xml` .. `junit-NN.xml`, each with its `base` recorded per-report in
  `_provenance.json`. The single-report form `--junit <path>` (no `=`) stays valid
  (base = project root) but is REJECTED once a second `--junit` is given without an
  explicit base — never silently defaulted.
- `execution_evidence.build_index` gained an additive `junit_reports: list[tuple[str,
  str]]` (text, base) parameter (E-C) alongside the existing single `junit=`.
- `_execution_evidence_io.refresh_index` and `_layer_coverage_evidence.fresh_evidence`
  both now thread every staged report's OWN base through to `build_index` (closes the
  two L2 gaps the spec named) — a staged report with no matching provenance base is
  REJECTED (skipped), never silently read at base="".
- `scripts/run_full_suite_evidence.py` (E-D, repo tool) drives all 18 test-roots one
  pytest process at a time (ADR-044), deriving BOTH the root list and each root's
  id-rebase base from `conftest.py::discover_test_roots` (E-E — no second
  hand-maintained list), then stages every produced report together.
- `plugins/shipwright-iterate/skills/iterate/references/F5.md` and
  `docs/hooks-and-pipeline.md` updated for the new `stage` invocation form and the new
  runner (same diff, per the spec's AC).

## The R1b measurement (this run's required sub-task)

R1b ("CI regenerates the manifest and must match", D8) is deferred to a future
sub-iterate. Before it can be built, two questions had to be answered EMPIRICALLY —
this run answers them; it does not build the CI gate.

### Q1 — which manifest fields are actually reproducible across two regens?

**Method.** `plugins/shipwright-compliance/scripts/lib/collectors/test_links.py
generate_file()` was called directly (never against the live main tree — a throwaway
scratch project under this session's own scratchpad dir) twice in a row against an
UNCHANGED tree:

1. Two regens at the same commit, a few seconds apart (`data.timestamp` set to two
   different real-looking values, mirroring two separate real invocations):
   - **Only `generated_at` differed.** Every other top-level key — `schema_version`,
     `collector_version`, `source_commit`, `spec_hash`, `requirements`, `orphans`,
     `invalid_tags`, `invalid_layers`, `untagged_tests` — was **byte-identical**.
2. The same scratch project turned into a real git repo, regenerated at commit 1, then
   regenerated again after a second commit:
   - `source_commit` (`commit1`): `3b1469c3767f3e1fd67dc5078fce179d3f7cb83d`
   - `source_commit` (`commit2`): `0057807dc741382bf25649eae2b6e53f23e6179e`
   - Confirms `source_commit` tracks the CURRENT commit exactly as
     `test_links.py:258`'s `io.git_head(project_root)` implies — a CI regen (on the
     PUSHED commit) and a local regen (on a mid-work, not-yet-pushed commit) are
     necessarily at DIFFERENT commits for the entire duration of a PR's review, so a
     naive whole-file compare is red from the first PR onward, by construction.

**Conclusion:** exactly TWO fields are inherently non-reproducible across independent
regens — `generated_at` (wall clock, always) and `source_commit` (whenever the two
regens are not at the identical commit, which is the CI-vs-local norm, not the
exception). Every content field the manifest actually carries (requirements, tags,
coverage-relevant data) IS reproducible when the underlying tree content is unchanged.
An R1b gate must diff with those two fields excluded (or diffed separately with a
"same-commit" precondition), never the whole file.

### Q2 — how much does content depend on marker selection / OS / interpreter?

**Method.** Real counts from this repo (not estimated):

- `shared/tests` carries 1 file / 6 marked items tagged `@pytest.mark.cross_plugin`
  (`grep -rn "pytest.mark.cross_plugin" shared/tests`). `ci.yml`'s shared-tier step
  restates `-m "not slow and not cross_plugin"` explicitly — WITHOUT that explicit
  restatement, a `shared/tests` session collects those 6 items too, and per ADR-044 /
  `test_hygiene.import_or_fail_in_ci` they import another plugin's `lib`/`tools` and
  HARD-FAIL from a `shared/tests` session (this is not a benign extra-coverage case;
  it is a session that would not even complete).
- `shared/scripts/tools/tests` carries ZERO `cross_plugin`-marked tests — running it
  with vs. without the explicit `-m` produced IDENTICAL collected-id sets (575 == 575,
  0 only-in-either) in a real side-by-side run in this worktree. So the marker's
  measured impact is root-dependent, not uniform across the repo — a gate that assumes
  "the marker never matters" is wrong for `shared/tests` and right for
  `shared/scripts/tools/tests` alike, for different, verifiable reasons.
- Repo-wide, 15 files / 24 occurrences carry `@pytest.mark.slow` — every one of them
  is EXCLUDED from BOTH the local default (`root pyproject.toml`'s addopts
  `-m 'not slow'`) and CI, so this one is currently NOT a source of local/CI
  divergence by itself (both sides agree to exclude); it would only start mattering if
  a future change ran CI or a local regen WITHOUT that shared default.
- OS/interpreter: observed directly in this run's own `uv run pytest` banners — local
  is Windows / CPython 3.13.13; `.github/workflows/ci.yml` pins 3.11 on
  `ubuntu-latest`. A test skipped only on one platform, or a marker-selected test,
  emits NO `<testcase>` element at all (pytest never emits one for a DESELECTED test;
  a collected-but-skipped one emits `<skipped/>`) — `_evidence_readers.py:85-86` maps
  BOTH outcomes to `not_run`, so the manifest cannot distinguish "never collected
  here" from "collected and skipped here" by content alone; only the marker
  expression + platform the regen ran under explain the difference.

**Conclusion:** manifest content is a function of marker expression, and that function
is NOT uniform across roots (some roots have zero marker-gated tests, others do not);
OS/interpreter differences surface exclusively through which tests get COLLECTED, not
through any explicit "platform" field in the manifest. An R1b gate needs to either (a)
run the exact same marker expression + OS/interpreter CI uses (as `run_test_suite.py`'s
F0 already does for the interpreter pin), or (b) diff only the fields Q1 showed are
tree-content-derived and accept that a marker/platform difference can legitimately
shift `untagged_tests`/coverage counts without being a "wrong" regen.

### Why this split existed

The original R1 draft bundled a CI regenerate-and-compare gate with this staging work;
the 2026-08-23 plan review split it into R1a (staging, this run) and R1b (the gate,
after this measurement) because a naive whole-file CI compare would have gone red on
the very first PR — `source_commit` differs by construction — and the SPEC's own
landmine list (`SPEC:202-206`) named timestamps/fixtures/flakes but not
`source_commit` or marker-selection as a class. This measurement is the missing input;
R1b is not built here.
