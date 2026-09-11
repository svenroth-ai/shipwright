# Mechanisable checks for the 18 flagged FR-01.03 / FR-01.04 lines

Run-ID: `iterate-2026-09-11-e1-checks-plan-design`
Campaign: `req3-06-enforcement-mono`, sub-iterate `e1-checks-plan-design`

## Context

The AC-evidence ledger
(`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`)
carried 9 `prompt-only (mechanisable)` lines under FR-01.03 (`/shipwright-plan`)
and 9 under FR-01.04 (`/shipwright-design`) — criteria stated in a SKILL.md or
step-reference as prose the agent should verify, with no mechanised check
behind them. Per campaign decision D7 ("Kein LLM-Drift-Gate"), a
`prompt-only (judgement)` criterion may never be turned into an LLM-judged
gate — each of the 18 lines had to become either a hard check or an
explicitly-reasoned downgrade to `judgement`.

## Decision

CHECK FIRST, TEST SECOND, for all 18 flagged lines (FR-01.03 #1,2,3,4,7,8,9,10,11
and FR-01.04 #1,2,3,4,5,6,8,9,11): for each, wrote or wired a small pure
function under `shared/scripts/lib/{plan_gate_extras,design_gate_extras,
phase_write_boundary}.py`, called it from `check-plan-gates.py` /
`check-design-gates.py`, wrote its test, and flipped the ledger line to
`enforced, tested` in the same edit. All 18 closed — none needed a
downgrade to `judgement`; every one had a concrete, checkable shape once
written out as a function. Three of the nine FR-01.03 rows (#2, #3, #4) turned
out to already be enforced by pre-existing code the original ledger walk
mis-classified (`check-plan-gates.py`, created 2026-07-27, predates that
walk) — those three needed only their missing test + the ledger correction,
not new production code. FR-01.03 #3b and FR-01.04 #10 are separate,
pre-existing `unimplemented` rows outside the 18-line scope this spec named
(tracked under `trg-88f721be` / `trg-e9e5188e` respectively) — untouched by
this pass.

Two real regressions were found and fixed by the external code-review
cascade before landing (see table below): a leniency-breaking Prerequisites
check that would have made every pre-existing Shipwright plan hard-fail, and
a silent-cwd-default in `check-plan-gates.py --project-root` that could make
the write-boundary gate a false pass. Both are exactly the class of bug this
sub-iterate's own review discipline exists to catch.

## Consequences

29 mechanisable / 19 judgement / 16 enforced-untested / 33 unimplemented / 68
enforced-tested lines remain in the ledger's backlog count post-run (measured
by `measure_ac_evidence_ledger.py`, unchanged across every later edit — no new
backtick-quoted status phrase was introduced in explanatory prose). The
`--project-root` argument of `check-plan-gates.py` is now `required=True`,
a breaking change for any external caller relying on the cwd default;
`SKILL.md` and `step-9-completion.md` were updated in the same commit to pass
`--project-root "$(pwd)"` explicitly everywhere it is invoked.

## Rationale

Writing the check before the test (per the spec's explicit instruction)
kept each of the 18 edits small and reviewable — one function, one gate
wire-up, one test, one ledger-line flip, discoverable as a single diff hunk.
Splitting `plan_section_quality.quality_problems()` into a `core_quality_
problems` (purpose/steps/tests) and `prerequisite_problem` (the new #9 check)
pair, each gated by its OWN adoption signal in `plan_gate_checks.py`, was
necessary because a single shared `adopted` flag silently made a lenient
legacy-plan warning into a hard failure the moment ANY quality check gained
a criterion older plans never wrote to.

## Rejected alternatives

Downgrading any of the 18 lines to `judgement` was considered per-line and
rejected in every case — each had a concrete, checkable shape (file
existence + content shape, git evidence, ledger text counting) with no
subjective judgement call needed, so D7 never had to be invoked to protect
a line from becoming an LLM gate.

## External Plan Review Findings

Both GLM and OpenAI reviewed the mini-plan (`--mode iterate`) and returned
"revise", 13 findings combined.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM | high | `git_dirty_paths` drops the old side of a git rename, so a production file renamed into an allowed prefix disappears from boundary evidence | accepted-and-fixed — keep both sides of `old -> new` |
| 2 | GLM | medium | `standalone_html_violations` only matched double-quoted, absolute `https?://` URLs | accepted-and-fixed — added single-quote + protocol-relative + exact-hostname matching |
| 3 | GLM | medium | `chrome_gate` passes unconditionally when `chrome-definition.md` is absent, even if a screen visibly uses nav markup | accepted-and-fixed |
| 4 | GLM | medium | No test proves the ADR-045 `_load_own_lib_module` loader actually leaves the shared `lib` package resolvable end-to-end | accepted-and-fixed — added `test_the_shared_verifier_import_resolves_after_the_own_lib_loader_runs` |
| 5 | GLM | low | `uploads_preserved`'s modified-file predicate reads ambiguously without parentheses | accepted-and-fixed |
| 6 | GLM | low | No test pins CLI behaviour independent of caller cwd | accepted-and-fixed — added `test_the_cli_is_independent_of_the_caller_s_working_directory` |
| 7 | OpenAI | high | `review_key_honesty` only enforces the false-skip direction, not "missing key ⇒ stops and asks" | accepted-and-documented — clarified in ledger row FR-01.03 #1's evidence text; a conversational stop-and-ask has no file artifact this check can observe |
| 8 | OpenAI | medium | `iteration_gate`'s evidence is live `git status`, not a per-round baseline snapshot — commit-timing edge cases can false-pass/false-fail | accepted-and-documented — docstring "Known scope" section; a baseline snapshot is out of this bounded pass's scope |
| 9 | OpenAI | medium | `screen_registry.py`'s module docstring referenced a stale `add --frs` CLI that does not exist | accepted-and-fixed |
| 10 | OpenAI | low | Manifest renders `"none"` for an unlinked screen — could read as a literal FR id downstream | rejected — `design_screens_parser.py:64` already treats `"none"` case-insensitively as "no FR linked" |
| 11 | OpenAI | low | Tests assume `tmp_path` sits outside a git worktree | rejected — matches the pre-existing convention across the whole test family |
| 12 | GLM | low | Mini-plan's Risk section under-states the Prerequisites-check leniency risk | accepted — surfaced concretely in the code review below |
| 13 | OpenAI | low | Mini-plan does not name which existing verifier tests would need updating for the Prerequisites check | accepted — surfaced concretely in the code review below |

## External Code-Review Findings

Both GLM and OpenAI reviewed the full diff (`--mode code`) and returned
"revise", 14 findings combined.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM | high | `--project-root` defaults to cwd in `check-plan-gates.py`, letting the boundary gate silently pass with zero evidence when invoked from the wrong directory | accepted-and-fixed — made `required=True`; `SKILL.md` and `step-9-completion.md` now pass `--project-root "$(pwd)"` explicitly at every call site |
| 2 | GLM | high | The new `## Prerequisites` check (`prerequisite_problem`) shared one `adopted` signal with the original three quality checks in `plan_gate_checks.check_section_quality`, so it silently turned a lenient legacy-plan warning into a hard failure for every pre-existing plan — proven by the diff itself needing to patch the `LEGACY` fixture to add Prerequisites just to keep tests green | accepted-and-fixed — split into `core_quality_problems` / `prerequisite_problem` with two independent per-split adoption signals (`adopted`, `adopted_prerequisites`) |
| 3 | GLM | medium | `git_dirty_paths` dropped the old side of a rename | accepted-and-fixed (same fix as plan-review #1) |
| 4 | GLM | medium | `standalone_html_violations` single-quote/protocol-relative/substring-host gaps | accepted-and-fixed (same fix as plan-review #2) |
| 5 | GLM | medium | `iteration_gate` false-pass/false-fail on commit timing | accepted-and-documented (same as plan-review #8) |
| 6 | GLM | low | `uploads_preserved` precedence/path-quoting fragility | accepted-and-fixed (same fix as plan-review #5) |
| 7 | GLM | low | Manifest `"none"` rendering | rejected (same as plan-review #10) |
| 8 | GLM | low | Tests rely on `tmp_path` outside a git worktree | rejected (same as plan-review #11) |
| 9 | OpenAI | high | `chrome_gate` passes unconditionally when `chrome-definition.md` is absent, even with visible shared nav | accepted-and-fixed (same fix as plan-review #3) |
| 10 | OpenAI | high | `review_key_honesty` enforces only the false-skip direction | accepted-and-documented (same as plan-review #7) |
| 11 | OpenAI | medium | `chrome_nav_targets_consistent`'s regex could over/under-match nested markup in pathological HTML | rejected — the fixture family this repo generates never nests `nav-item` anchors; out of scope for a bounded enforcement pass |
| 12 | OpenAI | medium | New shared lib modules (`design_gate_extras.py`, `phase_write_boundary.py`) have no module-level usage example | rejected — every public function's own docstring already names its FR/criterion and caller; a redundant top-of-file example would drift independently |
| 13 | OpenAI | low | `plan_section_quality.py` and 3 test files crossed the 300-LOC non-blocking bloat guideline | accepted, not fixed — flagged to the operator (see Bloat Checklist note in the sub-iterate result); non-blocking by the framework's own contract, offered as a follow-up split |
| 14 | OpenAI | low | `check-plan-gates.py`'s new `required=True` on `--project-root` is a breaking CLI change with no deprecation window | accepted — this is an in-session, in-repo CLI with no external consumers outside the plugin's own SKILL.md/tests, both updated in the same commit; no deprecation window is needed |

## Confidence Calibration

Effective complexity is `medium` (Step 3.4 `diff_risk_recheck.py`), so this
section is mandatory (SKILL.md Step 7.5 / campaign runner Step 3.8).

**Boundaries identified** (ADR-024, per the Self-Review's item 7):

1. **Ledger status-count boundary.** Producer: this session's own prose
   edits to the ledger file. Consumer: `measure_ac_evidence_ledger.py`,
   which counts every backtick-quoted status phrase across the whole flat
   text, not just table cells.
2. **Screen-linked-FRs boundary.** Producer: a design screen's
   `<!-- Requirements: ... -->` HTML comment. Consumer:
   `screen_registry.scan_designs_dir` / `generate_manifest`.

**Probes run:**

- Boundary 1: ran `measure_ac_evidence_ledger.py` after the initial 18-line
  edit — found a self-inflation bug (new prose had backticked status phrases,
  inflating the count). Fixed by removing the backticks, matching the
  document's own established convention. Ran again — count matched the
  expected 29/19/16/33/68 exactly (no finding). Ran a THIRD time after the
  FR-01.03 #1 clarification edit in this same session — count unchanged
  (no finding). Two consecutive no-finding probes after the fix: asymptote
  reached.
- Boundary 2: ran `test_scan_populates_linked_frs_from_the_screen_comment`
  and `test_generate_manifest_renders_linked_frs_in_the_table` (pre-existing
  tests exercising the real producer/consumer round trip) both before and
  after this sub-iterate's edits — passed both times, no finding either run.
  Two consecutive no-finding probes: asymptote reached.

**Edge cases not probed, and why acceptable:** a ledger status phrase split
across a line-wrap boundary (the counter's regex is line-oriented) — not
probed because the document's own paragraph style never wraps mid status
phrase, and the existing count has been stable across four prior campaign
edits. A screen's Requirements comment with a malformed/empty FR list beyond
`"none"` (e.g. trailing comma) — not probed because `design_screens_parser.py`
already has dedicated tests for that shape from a prior sub-iterate, and this
session touched neither the comment format nor its parser.

**Asymptote reached for both identified boundaries** — no further probes
run.
