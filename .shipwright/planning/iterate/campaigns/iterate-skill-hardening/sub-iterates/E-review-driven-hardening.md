# Sub-Iterate E — Review-Driven Hardening

> Part of campaign `iterate-skill-hardening`. **Depends on A, B, C, D**.
> Stacks on D. Fixes HIGH and critical MEDIUM findings raised by per-sub-iterate
> code reviews + external_review.py + holistic external review on the campaign.

## Context

After A/B/C/D shipped locally, we ran the reviews that the runner contract
should have triggered automatically (the gap that Sub-Iterate F closes):

- 4× code-reviewer subagents (one per sub-iterate)
- 4× external_review.py --mode code (one per sub-iterate, OpenRouter dual-LLM)
- 1× holistic external_review.py over the campaign-level diff

The reviews surfaced 6 HIGH findings (4 empirically verified by reading the
shipped code) and ~12 MEDIUMs. E addresses everything that is a real bug
or a load-bearing spec/code drift. Cosmetic and performance-only LOWs are
left as documented follow-ups; they do not block ship.

## Scope (HIGH first, then critical MEDIUM)

### HIGH-1 — A's AST-pair detection (spec/code disagreement)

The shipped `is_io_boundary_change()` is path-match-only with an explicit
"future enhancement" comment. The Implementation Plan in A's spec allowed
this; the Acceptance Criteria text in A's spec read it as required. Two
external reviewers flagged the disagreement.

**Resolution:** keep code as-is (path-match catches every known real-world
boundary bug, including the env-iterate's two latent bugs). **Amend A's spec**
to relabel the AST-pair AC as `(deferred)` with a one-line rationale and an
issue-tracking pointer. Add a `# DEFERRED` comment in
`classify_complexity.py:175-181` explicitly referencing the spec line.

### HIGH-2 — C's `detect_parallel_sessions` worktree blindness (real bug)

When called with `project_root = <a worktree path>`, the function only sees
that worktree's own marker — it never finds the main repo or sibling
worktrees. Defeats the function's purpose.

**Resolution:** before scanning, resolve the canonical repo root via
`git rev-parse --git-common-dir` (which returns the main repo's `.git` dir
even when called from a worktree). The parent of `--git-common-dir` is the
main repo root. Update `detect_parallel_sessions` to call this internally.
Document the new contract in the docstring.

Also add a regression test that calls `detect_parallel_sessions` from a
worktree directory and asserts it sees both the main marker and the
worktree marker. Spec said this was probed — the probe was actually never
done from worktree-cwd. This is the dog-food self-failure C admitted to in
its Confidence Calibration "Edge cases NOT probed" list.

### HIGH-3 — D's CLI signature divergence (spec/code disagreement)

D's spec AC says `--output {file|json}`. Code shipped `--output-markdown`,
`--output-json`, `--print-json` (richer than spec, less ambiguous).

**Resolution:** keep code's richer interface (it's strictly more capable
and clearer). **Amend D's spec** to reflect the shipped signature. Add a
deprecation-style note that the original `--output` mode-selector idea was
superseded.

### HIGH-4 — D's runner integration completely missing (real gap)

The `--report-boundary-coverage` flag is documented in
`plugins/shipwright-test/skills/test/SKILL.md` but no test-runner code
actually dispatches on it. Tool runs only by direct invocation.

**Resolution:** wire the flag into the test plugin. There is no
`test_runner.py` in the test plugin (verified via grep — only `result_io.py`
exists). Investigate the actual test-skill dispatcher and add a hook there.
If the test skill has no Python entry point (it's invoked as a slash
command per Claude-Code-skill convention), the wire is in
`plugins/shipwright-test/skills/test/SKILL.md` itself: add an explicit step
that runs the tool when the flag is present, AND add a small
`scripts/tools/merge_boundary_coverage.py` helper that does the
shipwright_test_results.json merge.

Concretely:
1. Create `plugins/shipwright-test/scripts/tools/merge_boundary_coverage.py`
   — reads the standalone JSON output, merges into
   `shipwright_test_results.json` under key `boundary_coverage_report`,
   atomic write via `tmp.replace(target)`.
2. Update `boundary_coverage_report.py` to support `--merge-into
   shipwright_test_results.json` as a one-shot alternative to the helper
   (so callers can pick either).
3. Update `plugins/shipwright-test/skills/test/SKILL.md`'s flag
   documentation to show the actual two-step flow (run tool → merge),
   with both invocation styles.
4. Test: `plugins/shipwright-test/tests/test_merge_boundary_coverage.py`
   covers the merge round-trip + idempotency + missing-input handling.

### HIGH-5 — D's round-trip heuristic unscoped (real bug)

Heuristic walks ALL `tests/**/test_*.py` files in the repo regardless of
whether they were added in the matched commit. Old unrelated tests
mentioning a producer name mark unrelated boundaries as `tested=True`.

**Resolution:** scope the heuristic to test files actually present in the
matched commit's `changed_files`. Concretely, in
`correlate_with_commits`, after matching a commit to a spec, intersect
`commit.changed_files` with `test_*.py` patterns; pass that intersection
into `_scan_test_files_for_producer` instead of the full filesystem walk.

If `changed_files` is missing on the event (HIGH-MEDIUM-D issue, see
below), fall back to the full-walk heuristic AND mark the row's
`round_trip_tested` field as `unknown` instead of `false` to preserve the
audit signal.

### HIGH-6 — D's spec→commit slug correlation (real bug)

`slug = spec_path.stem.lower()` matched as `slug in description`. Short
stems (`A.md`, `r1.md`) collide with arbitrary commit descriptions.

**Resolution:** require `len(slug) >= 8` for substring match; otherwise,
require word-boundary regex `\b{slug}\b`. Add explicit test: a spec named
`r1.md` and a commit `"refactor RouteParser regex"` must NOT match.

### MEDIUM-A1 — RISK_TAXONOMY keyword patterns too loose

`parse_`, `load_`, `write_`, `\bdump\b` are common verb prefixes that
fire on unrelated prompts ("rewrite the load_user route").

**Resolution:** anchor or remove. Replace with:
- `r"\bparse_env\b"` (specific function name)
- `r"\bjson\.dump(s)?\b"` and `r"\bjson\.loads?\b"` (specific stdlib calls)
- `r"\.env\b"` (already specific)
- `r"\bhooks\.json\b"`, `r"\bsettings\.json\b"`
- Drop bare `r"parse_"`, `r"load_"`, `r"write_"`, `r"\bdump\b"`,
  `r"serialize"` (too generic).

Add negative tests: prompts like "rewrite the load_user route", "improve
dump utility", "add parse_query helper" must NOT fire `touches_io_boundary`.

### MEDIUM-A2 — drift-protection test for `touches_io_boundary` literal

A's "Affected Boundaries" table identifies `classify_complexity.py
risk_flags[]` ↔ `SKILL.md` Repo Scout consumer as the most important
boundary. The literal string must match exactly across all touchpoints.
A's tests cover the producer side (key in RISK_TAXONOMY) but not the
consumer side (string appears in SKILL.md table + Phase Matrix +
Override Classes).

**Resolution:** add `tests/test_skill_risk_taxonomy_consistency.py`
which reads SKILL.md and asserts the literal `"touches_io_boundary"`
appears at least 3 times AND the same literal is the key in
`RISK_TAXONOMY`. Drift-protection pattern matches the
`_SHIPWRIGHT_FRAMEWORK_VARS` AST drift test referenced in
conventions.md.

### MEDIUM-A3 — Override Classes table missing "Advisory" cell

B's spec AC said: "Confidence Calibration is **Mandatory at medium+,
Safety-enforced at small with `touches_io_boundary`, Advisory otherwise**."
Shipped table only has Mandatory + Safety-enforced cells; "Advisory
otherwise" is implicit-by-omission.

**Resolution:** add a third row entry under the Advisory category making
the small-without-flag and trivial cases explicit. Update the Phase Matrix
test (which already exists from B) to cell-level-assert that all three
classifications are present.

### MEDIUM-B1 — drift-protection test scope leak

`test_iterate_spec_template_has_four_calibration_bullets` searches the
entire SKILL.md for the four bullet keywords. They appear BOTH in the
Step 7.5 prose AND in the iterate-spec template fenced block. Deleting
the template would not fail the test.

**Resolution:** scope the search to the fenced markdown block under
`### Step 1: Iterate Spec` in Path A. Use a regex to extract the first
` ```markdown … ``` ` block after that heading and assert the four
keywords appear inside it.

### MEDIUM-B2 — Phase Matrix row test only checks substring

`test_phase_matrix_has_confidence_calibration_row` only asserts the row
contains "confidence calibration"; doesn't validate the cells.

**Resolution:** parse the Phase Matrix table, locate the Confidence
Calibration row by its first cell, assert all 4 complexity cells
(`skip | if-flag | always | always`). Same fix applied to the new
Boundary Probe row from A (cells `skip | if-flag | if-flag | —`) for
symmetry.

### MEDIUM-C1 — SKILL.md hardcodes `'shared/scripts/lib'` literal

C's B1c phase shows inline `python -c` snippets with
`sys.path.insert(0, 'shared/scripts/lib')`. Every other shared-script
reference in SKILL.md uses the `{shared_root}` placeholder. On adopted
target projects, the literal path won't resolve.

**Resolution:** either (a) replace literal with `{shared_root}` placeholder
to match conventions, or (b) extract the inline `python -c` snippets into
small CLI helpers under `shared/scripts/tools/` (e.g.
`detect_parallel_sessions.py`, `write_session_role.py`) so SKILL.md can
invoke them via `uv run "{shared_root}/scripts/tools/<name>.py"`. Option
(b) is cleaner and matches the patterns of every other SKILL.md script
invocation.

### MEDIUM-C2 — tmp file fixed name → race risk

`session_role.write_role` uses `path.with_suffix(".tmp")` — fixed name
`iterate_session_role.tmp`. Two concurrent writes (e.g. canonical session
+ probe-script run) could clobber.

**Resolution:** use `tempfile.NamedTemporaryFile(delete=False,
dir=path.parent, prefix=".iterate_session_role.", suffix=".tmp")` for a
unique tmp name in the same directory, then `Path(tmp.name).replace(path)`.
Add a regression test that simulates two near-concurrent writes (sequential
in test, but using two distinct tmp paths to prove the pattern is
race-safe by construction).

### MEDIUM-D1 — `record_event.py` events missing `changed_files` field

D's drift-detection logic depends on `changed_files` from
`shipwright_events.jsonl` to invoke `is_io_boundary_change`. Holistic
external review noted that the new event for D itself records only
`commit` without `changed_files`. Without that field, drift detection
falls back to weaker text heuristics.

**Resolution:** check whether `record_event.py` has a `--changed-files`
parameter; if yes, document its use in F4 (Changelog drop) sequence and
update SKILL.md F7 example to pass it. If no, add it. Goal: every
work_completed event records the list of files actually changed in that
commit (computable from `git diff --name-only ${prev}..${commit}`).

## Acceptance Criteria

- [ ] HIGH-1: A's spec amended (`(deferred)` label + rationale on the
      AST-pair AC); `classify_complexity.py:175-181` comment cross-references
      the AC line.
- [ ] HIGH-2: `detect_parallel_sessions` resolves canonical repo root via
      `git rev-parse --git-common-dir`; new test calls from worktree-cwd
      and asserts both markers visible.
- [ ] HIGH-3: D's spec amended to reflect shipped CLI (`--output-markdown`,
      `--output-json`, `--print-json`); deprecation note for the original
      `--output {file|json}` AC.
- [ ] HIGH-4: `merge_boundary_coverage.py` helper exists; OR
      `boundary_coverage_report.py` gains `--merge-into` flag. SKILL.md
      flag documentation updated to show the two-step flow with concrete
      shell commands. New test
      `test_merge_boundary_coverage.py` covers merge round-trip +
      idempotency + missing-input.
- [ ] HIGH-5: `correlate_with_commits` scopes round-trip detection to
      commit-changed test files; falls back to full-walk + `unknown`
      label when `changed_files` missing.
- [ ] HIGH-6: spec→commit correlation requires `len(slug) >= 8` OR
      word-boundary regex; new test asserts short-stem non-collision.
- [ ] MEDIUM-A1: RISK_TAXONOMY keywords tightened; new negative tests
      assert non-boundary prompts don't fire flag.
- [ ] MEDIUM-A2: SKILL.md drift-protection test for `touches_io_boundary`
      literal across all 3 sections.
- [ ] MEDIUM-A3: Override Classes table has explicit Advisory entry for
      Confidence Calibration; existing Phase Matrix test cell-level-asserts
      all three classifications present.
- [ ] MEDIUM-B1: drift-protection test extracts fenced template block
      before searching for the 4 bullet keywords.
- [ ] MEDIUM-B2: Phase Matrix row tests cell-level-assert (Confidence
      Calibration AND Boundary Probe).
- [ ] MEDIUM-C1: B1c SKILL.md uses `{shared_root}` placeholder OR shared
      CLI helpers; B1c snippets actually executable from adopted target
      project context.
- [ ] MEDIUM-C2: `write_role` uses unique tmp name; regression test for
      race-safe-by-construction.
- [ ] MEDIUM-D1: `record_event.py` accepts/records `changed_files`; F4
      sequence in SKILL.md updated.
- [ ] All existing tests remain green (1505+ from D's run); new tests added
      this iterate are also green.
- [ ] DOG-FOOD applied: own iterate spec carries Affected Boundaries +
      Confidence Calibration sections, and own probes are run.

## Implementation Plan

Order:
1. HIGH-2 (detect_parallel_sessions worktree fix) — atomic 30-LOC change +
   2 new tests in `shared/tests/test_session_role.py`.
2. MEDIUM-C1 (B1c SKILL.md uses helpers) — extract two inline `python -c`
   blocks into `shared/scripts/tools/` CLIs; SKILL.md updated.
3. MEDIUM-C2 (tmp file unique name) — 5-LOC change in `write_role`.
4. MEDIUM-A1 (RISK_TAXONOMY tightening) — edit `classify_complexity.py`
   patterns; add negative tests.
5. MEDIUM-A2 (drift test for `touches_io_boundary` literal) — new test
   file `test_skill_risk_taxonomy_consistency.py`.
6. MEDIUM-A3 (Override Classes Advisory row) — SKILL.md edit + extend
   existing Phase Matrix test.
7. MEDIUM-B1 (template-block scoping) — fix
   `test_iterate_spec_template_has_four_calibration_bullets`.
8. MEDIUM-B2 (Phase Matrix cell-level asserts) — extend tests for both
   Boundary Probe + Confidence Calibration rows.
9. HIGH-5 + HIGH-6 (D heuristic scope + slug correlation) — two
   `boundary_coverage_report.py` edits + 2 new tests.
10. HIGH-4 (D runner integration) — biggest piece. Create
    `merge_boundary_coverage.py`, add `--merge-into` to the report tool,
    update test SKILL.md, write tests.
11. MEDIUM-D1 (record_event changed_files) — check tool, add field if
    missing, document.
12. HIGH-1 + HIGH-3 (spec amendments only) — edit A's and D's specs;
    add deferral labels and rationale.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `detect_parallel_sessions` (E-fixed) | B1c phase printout | List of dicts |
| `merge_boundary_coverage.py` (NEW) | `shipwright_test_results.json#boundary_coverage_report` | JSON file merge |
| `boundary_coverage_report.py::correlate_with_commits` (E-tightened) | rest of report | List of CoverageRow |
| `record_event.py --changed-files` (E-extended) | `shipwright_events.jsonl` events | JSON-lines field |
| RISK_TAXONOMY patterns (E-tightened) | `detect_risk_flags` | regex source list |
| SKILL.md B1c snippets (E-rewritten) | operator running B1c on adopted project | shell snippet |

The new highest-risk boundary is the **`shipwright_test_results.json` merge**
— `merge_boundary_coverage.py` writes to a JSON file that other tools
read. All 8 probe categories from A's `boundary-probes.md` apply
(BOM, CRLF, non-ASCII in nested values, empty merge target, etc.).

## Confidence Calibration

- **Boundaries touched:** see Affected Boundaries.
- **Empirical probes (to be filled by runner):**
  - For each boundary, run a real round-trip per A's
    `references/round-trip-tests.md`.
  - For HIGH-2: probe `detect_parallel_sessions` from a fixture worktree
    cwd; assert main + worktree markers BOTH visible.
  - For HIGH-4: probe the merge — write a fixture standalone JSON, run
    the merge, read shipwright_test_results.json, assert the
    `boundary_coverage_report` key exists with the right shape.
  - For HIGH-5: probe with a fixture events.jsonl that has
    `changed_files: ["tests/test_unrelated.py"]` for one commit and
    `changed_files: ["tests/test_producer.py"]` for another; assert
    the heuristic does NOT mark the unrelated test as evidence.
  - For MEDIUM-A1: probe with prompts that should NOT fire — "rewrite
    the load_user route", "improve dump utility", "add parse_query
    helper".
- **Edge cases NOT probed + why acceptable** (to be filled by runner)
- **Confidence-pattern check** (to be filled by runner — apply
  asymptote heuristic strictly)

## Runner Overrides

1. **DO NOT push** (Step 5 of runner contract). Orchestrator handles
   all pushes at campaign-end with explicit user authorization.
2. **DO NOT amend prior commits.**
3. **After F7, write result.json** to
   `.shipwright/runs/{loop_id-or-manual}/E/result.json`.
4. F2 Browser Verify does NOT apply.
5. Suggested ADR: `ADR-028: Review-Driven Hardening`.
6. Branch name: `iterate/skill-hardening-E-review-driven-hardening`.
   Branched from `iterate/skill-hardening-D-boundary-coverage-report`.

## DOG-FOOD Notes

- **Boundary Tests (A):** every new producer/consumer pair appears in
  Affected Boundaries; round-trip tests cover them.
- **Confidence Calibration (B):** the runner populates it strictly,
  including the negative-probe class that A and B's runners under-used.
- **Multi-Session Discipline (C):** orchestrator is canonical, runner
  doesn't push.
- **Boundary-Coverage Awareness (D):** Affected Boundaries table is
  populated; D's tool, once HIGH-4 wires the merge, would auto-detect
  this iterate's boundaries.

## What's NOT in scope

These reviewer findings are deferred to follow-up, not bug-blocking:

- All LOW-severity findings (cosmetic / minor performance / dead code).
- D's events.jsonl performance for 1000-spec scale.
- B1c lexical ordering reverse (B1c before B1a).
- Tests for symlinked worktrees (acceptable degraded behavior).
- A's `is_io_boundary_change(None)` type vs sibling `touches_build_files(list[str])`
  signature inconsistency.
