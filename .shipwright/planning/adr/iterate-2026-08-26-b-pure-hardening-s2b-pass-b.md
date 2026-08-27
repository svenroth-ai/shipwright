# S2b pass B — pure hardening of the 15 planning-discovery call sites

**Run:** `iterate-2026-08-26-b-pure-hardening` · **Campaign:** `s2b-discovery-convergence`
**Prerequisite:** S2b pass A (PR #652), merged.

## What changed

`shared/scripts/lib/planning_discovery.py` (`iter_split_dirs` / `iter_spec_files`)
is the single shared walk that replaced 15 independent implementations
(campaign S2, S2b pass A). Pass B converges the *behavioral* divergences
those 15 call sites still carried, one flag at a time, with a single golden
regeneration.

### B1 — `require="is_file"` on the 5 non-recursive sites

`drift_parsers.py`, `spec_parser.py` (`read_top_level_spec`),
`backfill_test_links.py`, `rtm.py` (`collect_requirements`),
`_test_links_io.py` now pass `require="is_file"`. Before, a *directory*
named `spec.md` was accepted by `.exists()` and only exploded downstream at
`read_text()` (raising `IsADirectoryError`/`PermissionError` depending on
platform, or in `rtm.collect_requirements`'s case, uncaught). Now the walk
itself skips it, so those targets return an empty result instead of
raising. **This is a declared behavior change**, visible in the golden
diff as 4 cells flipping from `"outcome":"raised"` to
`"outcome":"returned","value":[]`. `fr_gates.py` (#4) and `group_i_rows.py`
(#10) already did this correctly and were left untouched except for the
A3 explicit-flags pass.

The 5 *recursive* sites (#6, #11, #12, #13, #15) are explicitly OUT of
scope — pass A's A2 decision makes `recursive=True` combined with a
non-default `require` raise `ValueError` at call time, so `require` cannot
apply there. `_DIR_READ_ALIAS` (`_serialize.py`) and its pinning test
(`test_requirements_corpus_registry.py:180-209`,
`test_reading_a_directory_as_a_spec_raises_this_platform_s_oserror`)
therefore stay live and unchanged: `#6` (`adopt_compliance`) and `#11`
(`validate_adoption`) still crash on a directory named `spec.md` — that
crash is deliberately preserved, not fixed, in this pass.

Verified before regenerating: the `spec-dir` fixture column in
`test_requirements_corpus_matrix.py::test_corpus_discriminates_between_targets`
still has ≥ 5 distinct signatures after B1 (28/28 green, including that
test) — the fixture keeps discriminating between targets.

### B2 — recursion depth: accepted, not fixed

`#6, #11, #12, #13, #15` keep `recursive=True` (`rglob`), unbounded depth,
unchanged code. In a mature repo this descends into
`.shipwright/planning/iterate/<run-id>/` and
`.shipwright/planning/iterate/campaigns/<slug>/sub-iterates/`. The original
rationale ("foreign repo layouts at adopt time") no longer applies once
adopt has run, but the unbounded depth is kept anyway: no case is known
where it causes harm, and bounding it would be a new behavior decision, not
a hardening one. Stated here so it reads as a decision, not an omission.

### B3 — `sort=True` at 4 of 6 unsorted sites, 2 declared exceptions

Before: `#4, #6, #11, #13, #14, #15` did not sort. After: `#6`
(`adopt_compliance`), `#11` (`validate_adoption`), `#13`
(`review_runner._iter_candidate_specs`), `#15`
(`setup-design-session.find_specs`) now pass `sort=True`. `#11` takes
`specs[0]` and `#13` `break`s after the first match, so which spec is
validated / sampled for external LLM review used to depend on filesystem
iteration order and is now fixed by sorted path order — a real, declared
behavior change (see the golden diff: several `"<unordered-pick>"`
placeholders resolved to real deterministic paths, and one `validate_adoption`
"edge" fixture cell flipped from an FR-missing error to a clean pass because
the alphabetically-first spec differs from the previously arbitrary pick).

**Exception #4** (`fr_gates.py`): stays `sort=False`. The result is a
boolean (`next(..., None) is not None`); order is irrelevant, and
`sort=True` would materialize `sorted(entries)` and falsify the existing
"short-circuits on the first hit" comment. Untouched beyond A3's explicit
flags.

**Exception #14** (`state.py`): stays `sort=False`. The site re-sorts
itself afterward with `sorted(key=get_split_index)`, a *stable* sort — at
`sort=False` the `iterdir` order is preserved as the tie-break for
duplicate split indices; `sort=True` would change that tie-break, which is
a real behavior change out of scope for a pass named "pure hardening"
(filed as `S2 — Tie-Break-Reihenfolge` in the campaign BRIEF's "Später"
section, owned by campaign card `trg-b17e5878`).

**Known no-op at #15**: `sort=True` at the helper has no observable effect
yet at `setup-design-session.find_specs`, because that call site re-sorts
its own OS-separator strings afterward (`sorted(specs)`, case-sensitive on
the string form). Effect arrives only with campaign pass C3, which changes
*what* is sorted (posix separators). Documented so it does not read as a
bug.

**Tests deliberately rewritten, not deleted, per the spec's explicit
guardrail:** the two seam probes in
`test_requirements_corpus_found_defects.py`
(`test_unsorted_walk_tracks_enumeration_order`,
`test_unsorted_walk_a2_tracks_enumeration_order`) asserted
`forward != reverse` (order-dependence); both now assert `forward ==
reverse` (determinism), with docstrings and the `_probe_runner.py` probe
docstrings rewritten to match. The five stale "adding a sort would be a
behaviour change" comments (`adopt_compliance.py`, `validate_adoption.py`,
`review_runner.py`, `setup-design-session.py`, plus the seam-probe
comments) are rewritten to describe what happened, not what was avoided.
`state.py`'s comment (#14) is intentionally left unchanged — it is still
true.

### B4 — `order_sensitive` masks dissolved

The 3 registry entries that carried `order_sensitive: True`
(`disc.adopt_compliance.check_a2_spec_has_frs`,
`disc.validate_adoption._validate_spec`,
`disc.review_runner._iter_candidate_specs` — exactly the sites B3 sorted,
cross-checked one-for-one) no longer set it. With no entry left setting
`order_sensitive`, `_mask_unordered` and the branch in `_serialize._record`
that called it are dead code (`ruff` cannot see this — it is data-driven
dead code) and are removed in the same diff, along with the now-unused
`json` import in `_serialize.py`. The larger golden diff (several
`"<unordered-pick>"` placeholders replaced by real paths, `"unordered_walk"`
keys dropped from every cell of the 3 formerly-masked targets) is the
intended evidence that ordering is now pinned, not a side effect to
minimize.

### A3 applied

All 15 production call sites (plus the two `iter_split_dirs`-based ones,
`spec_parser._iter_spec_files` and `rtm.collect_external_review_states`,
and the two `group_i.scan_fr_rows*` registrations that share one call site)
now pass `guard=`, `sort=`, `include_iterate=`, and — where applicable —
`require=` explicitly, even where the value equals the default. The
helper's own defaults (`planning_discovery.py:44-46` / `:105-109`) are
unchanged.

### Line-count discipline

`spec_parser.py` (350/300, grandfathered) and `drift_parsers.py` (383/300,
grandfathered) were already over their bloat-baseline `current` before this
pass; edits there were written to stay line-count-neutral (single-line
calls, folded comments) rather than bump an already-grandfathered baseline
entry upward, per the anti-ratchet rule. `registry.py` (a `deferred-plan`
entry, plan_ref = this campaign's B spec) dropped from 316 to 314 lines
after B4 removed the 3 `order_sensitive` flags; the baseline `current` was
lowered to match (a decrease, not a ratchet). `anti_ratchet_check.py
--staged` was run and reports zero ratchets.

## `regenerated_for`

`S2b passes A+B: pass A, plus require=is_file on non-recursive sites,
sort=True except fr_gates and state, order_sensitive masks dissolved`
(exact literal, per the campaign BRIEF's Q1).

## External Plan Review Findings (Step 3.5, `openai`+`deepseek`, both `revise`)

| # | Finding | Disposition |
|---|---|---|
| 1 | B4 removes `_mask_unordered`/masking without naming test cleanup | accepted-and-fixed — the two seam-probe assertions and their docstrings were rewritten in the same diff (see B3 above) |
| 2 | Cross-check that all `order_sensitive` entries are among the B3-sorted sites | accepted-and-verified — all 3 (`#6, #11, #13`) are a subset of `{#6, #11, #13, #15}` |
| 3 | REQ3.04a merge precondition not restated in the mini-plan | acknowledged — orchestrator responsibility per the campaign BRIEF's `serial` guarantee, not this runner's |
| 4 | "count spec-dir column before regenerating" wording is ambiguous about timing | acknowledged — executed correctly: checked via the matrix test's `≥5` assertion AFTER code changes + regeneration (28/28 green) |
| 5 | No repo-wide check for lingering imports of `_mask_unordered` | accepted-and-verified — grepped; only defined+called inside `_serialize.py`, both removed |
| 6 | `spec_parser.py` bloat reserve (350/300) at risk from A3 edits | accepted-and-fixed — kept line-count-neutral (see "Line-count discipline" above) |
| 7 | `sort=True` on recursive sites may force full-tree materialization before a caller's `break`, losing early-exit streaming (narrowed S2b pass C5: `specs[0]` after `list(...)`, e.g. `validate_adoption`, was already fully materializing and never streamed — only `review_runner`'s `break` actually loses anything) | rejected-with-reason — inherent to the campaign's own B3 determinism decision (BRIEF §B3), not something this pass can avoid without reopening B3; accepted as a bounded cost given typical planning-tree sizes |
| 8 | A3 "every site explicit" not mechanically verifiable by the corpus | rejected-with-reason — out of scope; verified manually against the 15-site inventory instead (documented above) |
| 9 | No new auth/injection/data-exposure surface | acknowledged, no action |
| 10 | (duplicate framing of #7 from the deepseek leg) | see #7 |

## External Code Review Findings (Step 3.7, `openai`; `deepseek` empty reply)

| # | Finding | Disposition |
|---|---|---|
| 1 | `_test_links_io.discover_specs`'s top-level `agent_docs/spec.md` check still uses `.exists()` not `.is_file()` | rejected-with-reason — this direct check bypasses `iter_spec_files` entirely and is not one of the 15 registered discovery call sites B1 was chartered to converge (the golden corpus's `spec-dir` fixture doesn't even materialize a directory there); filed as triage `trg-a95e6fdf` for a future pass |
| 2 | `backfill_test_links.discover_specs`'s `top.exists()` bypass, same issue | rejected-with-reason — same as #1, same triage card |
| 3 | `backfill_test_links.discover_specs`'s `root_spec.exists()` bypass, same issue | rejected-with-reason — same as #1, same triage card |
| 4 | This ADR/iterate-report itself was missing at review time | accepted-and-fixed — this file |

## Self-Review (Step 3.6)

1. **Spec Compliance** — pass. All B1/B2/B3/B4/A3 acceptance criteria met exactly; `regenerated_for` matches the required literal byte-for-byte.
2. **Error Handling** — pass. No new exception handling added; existing OSError-swallow/raise behavior at each site preserved as-is.
3. **Security Basics** — pass. No auth/authz/input-boundary surface touched (the `touches_auth` classifier flag was a keyword false-positive on the German word "autoritativ").
4. **Test Quality** — pass. Two seam-probe assertions rewritten (not deleted) to match new determinism; golden regenerated via the real tool with a reviewed diff.
5. **Performance Basics** — pass, with a documented accepted cost: `sort=True` on recursive sites forces full materialization before `specs[0]`/`break` (external review finding #7 above); inherent to the campaign's B3 design.
6. **Naming & Structure** — pass. Every touched comment rewritten to describe actual behavior; dead code (`_mask_unordered`, its branch, unused `json` import) fully removed.
7. **Affected Boundaries (ADR-024)** — pass. Two boundaries identified and round-trip-probed: (a) `golden.json` — producer `regen_golden.py`, consumers the 3 corpus test modules, probed by regenerating and running all 3 (28+11 green, spec-dir column still ≥5 signatures); (b) the 15 production call sites into `planning_discovery.py` — probed by running the full test suite of every affected plugin realm (adopt 638, compliance 1657, design 38, project 64) plus `shared/tests` (9381) and `integration-tests` (528), all green, plus `ruff` and `anti_ratchet_check.py --staged` clean.

## Confidence Calibration (Step 3.8 — fires: complexity medium, `touches_shared_infra`)

Boundary 1 (golden.json round-trip): probe 1 = regenerate + run 3 corpus
test modules → found the *expected* declared behavior changes (raise→[],
unordered-pick→real path), no unexpected findings. Probe 2 = re-ran after
line-count-neutralizing edits → still green, no findings. Two consecutive
no-finding probes → asymptote reached.

Boundary 2 (15 call sites round-trip): probe 1 = ran every affected
plugin's test suite + shared/tests + integration-tests → all green. Probe
2 = the external code-review cascade (a real empirical probe of a
different kind) → found one real in-scope gap (this ADR was missing) and
three genuine-but-out-of-scope gaps (filed as triage). Fixed the in-scope
one; two consecutive clean re-runs after the fix (ruff + anti-ratchet)
→ asymptote reached for the boundaries this pass owns. The 3 out-of-scope
findings are a known, not-yet-probed edge (deliberately deferred, not
missed) — see triage `trg-a95e6fdf`.

## Reflection / learnings

See `.shipwright/agent_docs/conventions.md` `## Learnings` for the one-line
pointer on `sort=True` + `recursive=True` materializing the full walk
before yielding (loses early-exit for `specs[0]`/`break` consumers).
