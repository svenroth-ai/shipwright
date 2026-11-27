# Iterate Spec: r1a-resolver-foundation

- **Run ID:** iterate-2026-11-27-r1a-resolver-foundation
- **Type:** change
- **Complexity:** medium (shared resolver imported by ~160 files incl. hooks; binding hand-off items from two review rounds)
- **Status:** implemented

## Goal
First of five R1 PRs of the root-files campaign (BRIEF `.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`, split approved by the operator 2026-11-27). R1a lays the foundation the dual read (R1c) needs and changes no production behaviour: one resolver module object, the pointer-stub recogniser of BRIEF section 14 item 1, an "all known locations" helper, and tests that pin the hook fallbacks and the `rel()`/`name()` distinction.

## Acceptance Criteria
- [x] AC1: Loading the resolver under any of its import names (`_ALIASES`: bare, `lib.`, and the three private packages over `shared/scripts/lib`), in any order, yields ONE module object; a load under any other name (a test probe) stays separate (BRIEF 12.3).
- [x] AC2: `shipwright_pointer.classify(data: bytes)` returns `stub` (version 1), `too_new` (version > 1), `edited` (signature but > 512 bytes after CR stripping) or `not_stub`, per BRIEF 14.1: `utf-8-sig` decode (invalid UTF-8 = not_stub), FIRST line only, CR + surrounding whitespace stripped, case-sensitive `^SHIPWRIGHT-POINTER/(\d+)$` with ASCII digits and no leading zero (`/0`, `/01` = not_stub; any longer number = too_new; recorded in BRIEF 14.1). The shared fixture matrix (`shared/testkit/pointer_stub_cases.py`, a Python table because the cases are bytes; a non-Python consumer in R1c/R3 can export it) covers LF, CRLF, BOM, trailing spaces, 512/513 bytes, `/2`, signature on line 2, empty file, non-UTF-8, conflict markers, JSON after the signature.
- [x] AC3: `shipwright_pointer.render(min_plugin_version)` produces the 11.5 stub text (ASCII, LF, ≤ 512 bytes) and `classify(render(v))` is `stub`; `moved_to` is text only — no function in the module returns a path read from the stub (BRIEF 14.2).
- [x] AC4: `shipwright_paths.new_rel(key)` returns `.shipwright/config/<basename>` for a moving file and `None` for a non-moving or retired one; `known_rels(key)` returns the candidate locations (new first, legacy second) for a moving file and `(legacy,)` otherwise. No production caller changes (R1b/R1c wire them).
- [x] AC5 (one known exception, see below): Every hook/lib fallback of the form `"<literal>" if _sp is None else _sp.rel("<key>")` names exactly `rel(key)`, and every shared hook with such a fallback imports cleanly with the resolver hidden (`sys.modules["shipwright_paths"] = None`) and takes the fallback (BRIEF 12.7b). **Exception:** `check_file_size` cannot import with the resolver hidden because its `lib.bloat_baseline` dependency imports the resolver unguarded - a pre-existing gap; fixing it changes production code, so it is a strict xfail here and BRIEF 12 item 8 for R1c.
- [x] AC6: With `rel()` pointed at `.shipwright/config/` (monkeypatched on the one module object and the consumers reloaded), the basename consumers `suite_worktree_diff`, `ac_surface`, `pr_review_generated`, `event_seeder` still match bare file names (BRIEF 12.2).
- [x] AC7: The session handoff's "Config Files to Read" list names each config through `lib.config.CONFIG_FILES` (the resolver), not a hand-built `shipwright_<name>.json`; the output is byte-identical today (BRIEF 12.7c).

**Pre-build AC record (Step 2a):** one `exempt` item — no user- or operator-observable behaviour changes (new helpers are unused by production; the handoff text is identical).

## Spec Impact
- **Classification:** none
- **ADD:** none · **MODIFY:** none · **REMOVE:** none
- **NONE justification:** Internal foundation for a file move that has not happened; every production output is byte-identical, the new recogniser and helpers have no production caller yet.

## Out of Scope
- Routing the ~100 `root / _sp.rel(...)` joins through `path()` and the guard rule against them (R1b).
- Any new-then-old lookup, both-copies error, incomplete-migration error, dual lock, `audit_config` moving (R1c).
- Silent-failure gates (bloat, review tier, AC baseline, events layout CI) (R1d); hook matrix test and external repos (R1e).
- Changing hook fallback literals to follow the move (12.7a; R1c, when `rel()` changes).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shipwright_pointer.render` (no production caller until R3) | `shipwright_pointer.classify` (no production caller until R1c) | plain-text stub, BRIEF 11.5/14.1 |

No existing serialized format changes.

## Confidence Calibration
- **Boundaries touched:** pointer stub text (new; producer `render` + consumer `classify` in one module); module identity of the resolver across import names (import-system boundary).
- **Empirical probes run:** (1) identity tests against the OLD resolver (origin/main): 18 of 28 red, so the tests detect the split; (2) the same four new test files on Python 3.11.15, 3.12.13, 3.13.13: 91 passed + 1 strict xfail each; (3) a hidden-resolver run of every shared hook with a fallback found that `check_file_size`'s fallback never runs (its `lib.bloat_baseline` import needs the resolver) - pre-existing, recorded as strict xfail + BRIEF 12 item 8; (4) the basename AST rule over all production Python: 0 hits, positive control flags all 5 misuse shapes; (5) moved-layout subprocess: `CONFIG_FILES["run"]` follows the move while all four basename sets keep bare names.
- **Test Completeness Ledger:**

| Behavior | Status | Evidence |
|---|---|---|
| AC1 one object under every alias, any order; probe/None/fake/foreign tree untouched | tested | test_shipwright_paths_identity.py (28) |
| importlib self-replacement mechanism | tested | test_importlib_hands_back_whatever_a_module_left_in_sys_modules |
| AC2 classify verdicts per 14.1, totality | tested | test_shipwright_pointer.py (27 fixture rows + total + versions) |
| AC3 render shape, SemVer validation, no path API | tested | test_render_* , test_nothing_in_the_module_returns_or_follows_a_path_from_the_stub |
| AC4 new_rel / known_rels / all_known_rels, target column | tested | test_known_locations |
| AC5 fallback literals equal the resolver; hidden-resolver branch used | tested | test_shipwright_paths_fallbacks.py (pairs, import-error literals, session_start, required_checks_state, suggest_iterate) |
| AC5 known gap pinned: check_file_size cannot import with the resolver hidden (deferred to R1c) | tested (strict xfail) | test_resolver_hidden_branch_check_file_size |
| AC6 basename sets survive a moved layout; path tables follow; static rule | tested | test_shipwright_paths_basenames.py (3) |
| AC7 handoff list byte-identical via CONFIG_FILES | tested | test_config_list_names_each_file_by_its_repo_relative_path |

- **Confidence-pattern check:** depth - the risky piece (module swap during exec) is pinned at the mechanism (toy package) and at the symptom (identity matrix), on three interpreters; breadth - every alias form in the repo (`shipwright_paths`, `lib.`, `from lib import`, `_shipwright_shared_review_lib`, `_shipwright_shared_lib`) is in the matrix; integration composition - not `cross_component` machinery.

## End-to-End Verification
- **Surface:** cli
- **Runner:** pytest over the five new/changed test files (139 tests, exit 0) — `.shipwright/runs/iterate-2026-11-27-r1a-resolver-foundation/surface_verification.json`

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** The no-behaviour-change promise holds, but load-time unification left gaps that would keep a second resolver object into R1c, and the recogniser spec left parts of BRIEF 14.1 open.
- **Findings:** architecture/medium fourth import name `_shipwright_shared_lib` — fixed (any `*.shipwright_paths`); architecture/medium no same-file check — fixed (resolved `__file__` equality); architecture/medium unspecified `_unify` branches — fixed (decision table + one test per branch); architecture/low importlib self-replacement only checked on 3.11 in CI — fixed (toy contract test); completeness/medium conflict markers after line 1 — fixed (any-line scan); completeness/medium open recogniser details (precedence, `/0`, `/01`, Unicode digits, line split, cap counting, JSON after signature) — fixed (ordered algorithm, explicit verdict per row); completeness/low stub-at-new-path row — fixed (shared fixture row, asserted in R1c); security/low unchecked `render` input — fixed (SemVer validation); completeness/medium AC6 tests nothing today — fixed (whole-layout patch incl. `names_of`/`snapshot_paths`, a follow-the-move assertion, AST rule extended); architecture/medium reload leaks patched constants — fixed (subprocesses); completeness/low hidden-resolver test name and `rel` tripwire — fixed (renamed, compares `legacy_rel`); completeness/low set-level helper and per-row target dir — fixed (`all_known_rels`, `target` column); completeness/low handoff `.name` — fixed (prints the repo-relative path, fallback dropped); architecture/low line cap, 12.1 docstring, `Verdict` identity — fixed; architecture/low scope of the AST rule — fixed (empty allowlist; 0 hits measured).
- **Known limitations:** `check_file_size` fallback is dead (pre-existing; strict xfail, BRIEF 12 item 8)
- **Status:** 15 fixed

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** low
- **Summary:** Worth building; option A (unify at load time in the resolver, recogniser as its own stdlib module, helpers unused until R1c) is the smallest workable choice.
- **Findings:** necessity/low — accepted; smallest-option/low — accepted (A); completeness/medium both load orders + the `None` sentinel + `from lib import` binding — fixed (identity tests); complexity-cost/low helpers frozen before first caller — fixed (docstring: R1c owns the final contract); security/low `classify` totality and BOM in the cap — fixed (total by contract, BOM counted, tested on random bytes); completeness/low fallbacks written another way — fixed (scan also covers `except ImportError` handlers).
- **Known limitations:** none
- **Status:** 4 fixed

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-27-r1a-resolver-foundation/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (option A).
- **Findings:** glm/low `render` has no production caller yet — accepted, kept to pin the format against its recogniser; R3 may still change it. openai: none.
- **Reconciliation:** The plan had rejected B (one canonical import name) because plugins cannot import shared `lib.*` (ADR-045) and C (fold into R1c) to keep the identity change apart from the first behaviour change; both reviewers reached the same choice independently.

## External Plan Review
- **Verdicts:** glm=approve · openai=revise
- **Findings:** glm/medium parent-package attribute binding — fixed (asserted); glm/medium partial init — fixed (`SPECS` defined before any import, half-loaded bare entry untouched); glm/low bare import now succeeds — accepted (intended); glm/low half-unified alias — fixed (`rel()` agreement across aliases); glm/low AST rule rot via allowlist — fixed (empty allowlist); glm/low resolver line budget — accepted (trimmed prose); openai/medium only two consumers run — fixed (all four, subprocesses); openai/medium precedence, long digits, render input — fixed; openai/medium handoff second naming source — fixed (direct lookup, entry-point test); openai/low fallback used, not just imported — fixed (module-level constant asserted).

## External Code Review
- **Verdicts:** openai=revise · glm=revise
- **Findings:** openai/high digit grammar vs `\d+` — fixed (any length; long = too_new; `/0`,`/01` stay not_stub, recorded in BRIEF 14.1); openai/medium concurrent-thread import race — disclosed (docstring; hooks are single-threaded, not R1a scope); openai/medium dotted probe names unify — fixed (explicit `_ALIASES`, same-file dotted probe test); openai/medium AC5 check_file_size + suggest_iterate depth — fixed (AC5 names the exception; pairs compared with `rel` and `legacy_rel`; every hook with a fallback imported with the resolver hidden, run as a script); openai/medium event_seeder not exercised — fixed (behavioural routing test with directory-bearing `rel`); openai/low SemVer grammar — fixed (semver.org 2.0.0 grammar, 4 new rejection rows); glm/medium hidden-resolver coverage of all hooks — fixed (parametrized over every hook the scan finds); glm/low odd fallback shapes crash collection — fixed (recorded + own failing test); glm/low 10-digit cap — fixed (removed); glm/low AC7 oracle — fixed (old expression as oracle); glm/low in-process `test_known_locations` — fixed (subprocess).

## Code Review (Stage 2, opus)
- **Findings (5 low), all fixed:** pointer docstring vs conflict scan — reworded; hidden-resolver test accepted "absent" — split: `_sp` hooks must take the fallback, LOOSE-only hooks are import-only by name; statement-form `if _sp is None:` and foreign receivers — now flagged as ODD; resolver at the 300-line cap — BRIEF 12 item 9 (R1c uses a sibling module); subprocess harnesses decode bytes as utf-8/replace.

## Doubt Review (Stage 3, opus)
- **Doubts (5 low), all addressed:** recogniser stripped Unicode whitespace — now ASCII only (space, tab, CR, FF, VT), fixture rows for NBSP, NEL, double BOM; bare re-import after the bare entry was dropped split the object — `_unify` now adopts any loaded same-file alias in both directions (test added); `__name__` claim — docstring corrected; `_shipwright_brief_dir_lib` missing from aliases — added, plus a static test that every `_shipwright_*_lib` package is listed; handoff "follows the move" untested — the moved-layout probe now renders the handoff and asserts the `.shipwright/config/` line.
- **Production behaviour change disproved?** No — reviewer found none (no test patches/reloads the resolver; no pickling; `FileSpec.target` default safe; `_select` equivalent).

## F0 Finding
- The first full suite run went red in one test, `test_dev_server_path_anchors::test_importing_dev_server_does_no_pathlib_path_arithmetic`: the doubt-review rewrite of `_unify` built a `pathlib.Path` on every import, and that breaks import when `os.name` is faked. It now compares files with `os.path.normcase(os.path.realpath(...))`. The same-file check and every identity test are unchanged.
