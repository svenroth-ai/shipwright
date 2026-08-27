# S2b Durchgang C — the two real behaviour changes + two follow-ups

**Run ID:** iterate-2026-08-27-s2b-discovery-c
**Type:** change · **Complexity:** medium (escalated from classifier's "small" —
multi-plugin span + golden-corpus regeneration warranted the fuller rigor)
**Card:** `trg-b17e5878` · **Brief:** `.shipwright/planning/campaigns/2026-08-24-s2b-discovery-convergence-BRIEF.md`
**Precondition:** campaign `s2b-discovery-convergence` (A #652, B #655) merged — verified via `registry.py`'s `EXPECTED_DISCOVERY_COUNT = 17` and the "S2b pass B3" sort comments already present on `origin/main`.

## Gate before building (per the BRIEF, this run started with a halt)

**Question:** does the `planning-file` golden-corpus fixture survive C1's
guard rework, and if not, what replaces its discriminating power?

**Answer, verified (not assumed):** the corpus's `_record()` helper records
`{"outcome": "raised"|"returned", ...}` purely from whether the invoked
target function itself raises. `test_planning_as_a_file_still_splits_the_targets`
needs the four `disc.*` outcomes on `planning-file` to be `{"raised","returned"}`
(not all one or the other); `test_corpus_discriminates_between_targets`
(`dupes==0`) needs only *some* target to differ between `planning-file` and
`absent`. Both hold as long as at least one of `#1`/`#7`/`#14` keeps raising —
not all four need to.

**Scope decision made with the operator before building:** of the two
finding-capable sites (`#7 rtm.collect_requirements`, `#8
rtm.collect_external_review_states`), only **`#8` converts** this round.
`#7`'s return type (`list[RequirementInfo]`) is a pure positive-data record
with no status/reason slot and exactly one production caller with no
existing error channel — giving it a finding would mean widening its return
*contract*, not adding a value, and that risk (a heterogeneous list reaching
downstream traceability/RTM checks that assume every entry is a real
requirement) could not be ruled out without auditing every consumer, which
was judged disproportionate for an edge case that is already broken today.
`#7`, `#1`, and `#14` all continue to raise, unchanged.

## C1 — guard: the broken planning path

`rtm.collect_external_review_states` (`#8`) now catches `NotADirectoryError`
from the `guard="exists"` walk and returns one `ExternalReviewState(split="(planning root)", status="error", reason="planning path is not a directory")`
row instead of letting the exception escape. `#1`, `#7`, `#14` unchanged.

Investigated but not applied: the BRIEF's citation of `frozen_bugs.py` FV-2
as prose calling this raise "locally correct" does not match the file — FV-2's
"raises" reference is to `campaign_status.py`, an unrelated module. No
`frozen_bugs.py` edit was needed; `FROZEN_BUGS`'s `cells` never pinned the
planning-file guard sites in the first place.

## C2 — `include_iterate=False`

Flipped at 9 of the 12 `include_iterate=True` sites: `#1` drift_parsers,
`#2` spec_parser.read_top_level_spec, `#4` fr_gates, `#6` adopt_compliance,
`#7` rtm.collect_requirements, `#10` group_i_rows, `#11` validate_adoption,
`#13` review_runner._iter_candidate_specs, `#15` setup-design-session.

**Exceptions left untouched:** `#3` spec_parser._iter_spec_files (R0's M6
scope over `planning/iterate/*.md`), `#12` setup_adopt (a user-facing
disclosure list, not a spec source). **Non-change:** `#14` state.py — its
regex never matches `"iterate"` so the flag has no effect; left unset so a
missing effect is never mistaken for a bug later.

**Real effect verified, correcting the BRIEF's own scoping.** The BRIEF
frames C2 as "no live effect, prevention only" but scopes that claim
explicitly to the *non-recursive* sites (`#1,#2,#4,#7,#9,#10`). This repo
has four real nested `.shipwright/planning/iterate/<run-id>/spec.md` files
(confirmed via `find`), visible only to the *recursive* sites — `#6, #11,
#13, #15`. For those, C2 is a genuine correctness fix, not prevention: it
stops iterate run docs (which happen to be named `spec.md` but aren't split
specs) from being treated as adoption evidence, an FR source for the naming
audit, or a design-session candidate. Confirmed via the golden-corpus diff:
exactly 8 targets changed, matching this analysis precisely (`#2/#4/#6/#9/#11`
show no diff because their "first match" or boolean-style checks were never
sensitive to iterate/'s presence in this fixture; `#3/#12/#14` show no diff
because they were left alone).

## C3 — posix separators in `setup-design-session.find_specs`

`str(relative)` → `relative.as_posix()`. Removed the now-dead
`platform_sep` apparatus: the registry flag, `_posixify()`, its call
branch, and the now-unused `target` parameter on `_record()` (3 call sites
updated). Rewrote the Windows-only-meaningful pinning test
(`test_platform_separator_behaviour_is_pinned` →
`test_find_specs_emits_posix_separators_on_every_platform`) since its old
`assert all(os.sep in s ...)` was a tautology on the Linux CI that actually
runs it.

## C4 — same defect class, outside the 15-site inventory

`_test_links_io.discover_specs` and `backfill_test_links.discover_specs`
gated `agent_docs/spec.md` (and the latter's repo-root `spec.md`) on
`.exists()`, letting a directory reach `read_text()` and raise. Both now
gate on `.is_file()`, matching the `require="is_file"` half of the same
functions (S2b pass B1).

## C5 — five pass-B nits

1. Renamed `test_unsorted_walk*_tracks_enumeration_order` /
   `unsorted_seam*` probes to `test_sorted_walk*_ignores_enumeration_order`
   / `sorted_seam*` — names had inverted since B3 made the walk sorted.
2. **Not cosmetic** (verified, not assumed): added a `candidate_count >= 2`
   liveness assertion to both renamed tests. Empirically confirmed both
   probes currently DO distinguish sorted from unsorted order on the `edge`
   fixture (temporarily reverted `sort=True`→`sort=False` at each call site
   and observed forward/reverse diverge, then restored) — so today's tests
   are not vacuous. The guard exists so a future shrink of the `edge`
   fixture to 1 spec can never silently turn them vacuous.
3. **Revised mid-flight.** Originally moved the "was sorted"/S2b-provenance
   trailing inline comments at `spec_parser.read_top_level_spec` and
   `drift_parsers.collect_requirements_from_planning` into their docstrings,
   which grew both already-over-300-line files further and tripped the bloat
   anti-ratchet gate (zero headroom once a file already exceeds the cap).
   Reverted to inline comments, extended in place (same line, no new lines)
   to also cover the C2 `include_iterate=False` rationale — net line delta
   against `origin/main` is now zero for both files.

## Bloat baseline

`test_data_collector.py` already carries an accepted bloat exception
(`ADR-092`, `state: "exception"`) since it is a deep test module for
`data_collector.py`'s many code paths. The mandatory C1 test
(`test_planning_path_is_a_file_reported_as_error`) grew it past the
exception's pinned `current` ceiling (1029). Trimmed a redundant docstring
on the new test (the name is already self-explanatory), then deliberately
bumped `current` to 1039 in `shipwright_bloat_baseline.json` in this same
commit — exactly the case ADR-092's exception exists for, not a new
exception. No other file in this diff needed a baseline change.
4. Resolved by C4 (the `_test_links_io.py` comment no longer overstates scope
   once the agent_docs/spec.md check also gates on `is_file()`).
5. Narrowed `conventions.md`'s streaming-loss learning and the B-pass
   ADR's finding #7: only `review_runner`'s `break` actually loses
   early-exit streaming; `validate_adoption`'s `specs[0]` follows a
   `list(...)` call that was already fully materializing and never streamed.

## Affected Boundaries

- `shared/scripts/lib/{drift_parsers,fr_gates,spec_parser}.py` — discovery call sites
- `shared/scripts/tools/{backfill_test_links,verifiers/adopt_compliance}.py`
- `plugins/shipwright-compliance/scripts/{lib/collectors/{rtm,_test_links_io},audit/group_i_rows}.py`
- `plugins/shipwright-adopt/scripts/{checks/validate_adoption,lib/review_runner}.py`
- `plugins/shipwright-design/scripts/checks/setup-design-session.py`
- `integration-tests/requirements_corpus/{registry,_serialize,_collect_realm,golden.json}.py`
- `.shipwright/agent_docs/conventions.md`, one ADR decision-drop (narrowed finding text)

## Confidence Calibration

- **Boundaries touched:** see above — compliance collectors, shared
  discovery-adjacent scripts across 3 plugins, and the golden-corpus harness
  itself.
- **Empirical probes run:**
  - Precise per-target diff of `collect_all()` vs committed `golden.json`
    after each pass, confirming exactly the expected targets changed (and no
    others) at C1 and C2.
  - Manual `sort=True`→`sort=False` revert-and-restore on both C5 seam
    probes to verify they are not currently vacuous (nit 2).
  - Direct read of `RequirementInfo`/`ExternalReviewState` dataclasses and
    their call graphs to settle the `#7` vs `#8` scope question empirically
    rather than by inference from the BRIEF's prose.
- **Test Completeness Ledger:**

| Behavior | Status | Evidence |
|---|---|---|
| C1: `#8` returns explicit finding on planning-file | tested | `test_planning_path_is_a_file_reported_as_error` |
| C1: planning-file fixture still splits {raised,returned}; dupes==0 | tested | `test_planning_as_a_file_still_splits_the_targets`, `test_corpus_discriminates_between_targets` (golden-pinned) |
| C2: 9 sites now exclude iterate/; 3 exceptions/non-change untouched | tested | golden-corpus diff (8 targets changed, matches analysis exactly) |
| C3: posix separators emitted unconditionally | tested | `test_find_specs_emits_posix_separators_on_every_platform` |
| C3: `platform_sep` apparatus fully removed (no dead code) | tested | ruff clean + grep confirms zero remaining references + full suite green |
| C4: `_test_links_io.discover_specs` skips a dir named agent_docs/spec.md | tested | `test_test_links_io_spec_directory.py` (2 cases) |
| C4: `backfill_test_links.discover_specs` skips dir at both agent_docs + repo-root | tested | `test_discover_specs_skips_a_directory_named_spec_md` |
| C5 nit 1+2: renamed tests carry a real liveness guard | tested | `test_sorted_walk_ignores_enumeration_order`, `test_sorted_walk_a2_ignores_enumeration_order` |
| C3 posix-separator test detects a revert on Linux CI (external review finding 1) | tested | `test_find_specs_emits_posix_separators_on_every_platform`'s new source-level assertion; verified it actually fails against a reverted `str(relative)` call before fixing the false-positive substring bug, then passes clean |
| C5 liveness guard's candidate_count matches the probed target's real discovery config (external review finding 2) | tested | `test_sorted_walk_ignores_enumeration_order`, `test_sorted_walk_a2_ignores_enumeration_order` (both still pass with the narrower, correctly-scoped count) |

  0 untested-testable.
- **Confidence-pattern check:** asymptote (depth) — the two riskiest claims
  (does C1 preserve corpus discrimination; is the C5 liveness guard real) were
  both settled empirically, not by re-reading the BRIEF harder. Coverage
  (breadth) — every one of the 15 inventoried call sites was checked against
  each of C1/C2's rules (touched or explicitly exempted with a reason), not
  just the sites the BRIEF called out by name.

## Mid-flight corrections

- **Rebase.** `origin/main` advanced by one commit (`c23172a6`, PR #659) after
  this worktree branched. A first `git diff origin/main` therefore showed a
  spurious revert of #659 plus unrelated stale `agent_docs` content; caught by
  Stage-1 `spec-reviewer` before commit. Fixed by stashing (`-u`), fetching,
  rebasing onto `origin/main` (clean, no conflicts — #659 touches
  `_fr_table_columns.py`/`test_fr_table_shape.py`, untouched by C1-C5), and
  popping the stash back. Full suite + `verify_local.py` re-run clean after.
- **Untracked file, invisible diff.** The same Stage-1 pass flagged
  `test_test_links_io_spec_directory.py` (C4) as "claimed tested but absent
  from the diff" — a false positive caused by generating the review diff with
  a plain `git diff` (which never shows untracked files), not a real gap; the
  file was on disk and staged at commit time all along. Fixed the review
  process, not the code: diffs for reviewers are now generated from `git diff
  --cached` after `git add -A`, so new files are visible.

## External-Code-Review-Findings

External LLM cascade (Branch A, `--mode code`): `openai` via `openrouter`
returned `revise` with two findings; `deepseek` returned `status: degraded`
("provider returned an empty reply") — `openai`'s pass carries the gate per
the medium+ floor (at least one leg completed).

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium | `test_find_specs_emits_posix_separators_on_every_platform` cannot detect a revert to `str(relative)` on the Linux host this suite's CI runs on, because `os.sep` is already `"/"` there — `str(relative)` and `relative.as_posix()` produce identical output on Linux. | accepted-and-fixed: added a source-level assertion (strips comments, checks the exact `specs.append(...)` call) that fails on any host regardless of native separator, kept alongside the original behavioural check as defense-in-depth for an actual Windows run. |
| 2 | low | The C5 liveness guard's `candidate_count` (`_probe_runner.py`) counted every `spec.md` under `.shipwright/planning` via a bare `rglob`, including `iterate/` entries — even though both probed targets pass `include_iterate=False` — so it could stay "alive" from iterate/ noise while the target's real candidate set shrank to one. | accepted-and-fixed: added `_eligible_candidate_count()`, which delegates to the exact `iter_spec_files(...)` call each probed site makes (`include_iterate=False`, matching `guard`/`require`), so the guard's count can never drift from what the target actually sees. |

## Test Results

Full suites green post-change: `shared/tests` (9535 passed, 32 skipped),
`shared/scripts/tools/tests` (619 passed, 16 skipped), `plugins/shipwright-compliance`
(1658 passed, 5 skipped), `plugins/shipwright-adopt` (638 passed),
`plugins/shipwright-design` (38 passed), `plugins/shipwright-project` (64 passed),
`integration-tests` (528 passed). `ruff check .` clean. `verify_local.py`: 3/3
mirrored gates green.
