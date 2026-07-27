# Iterate: a multi-root pytest session refuses instead of misleading

- **Run ID:** `iterate-2026-07-27-pytest-root-composition`
- **Date:** 2026-07-27
- **Intent:** BUG (misleading failure mode)
- **Complexity:** medium
- **Spec Impact:** NONE (developer-facing test-session guard; no plugin
  behaviour changes)

## Problem

`uv run pytest shared/tests integration-tests -m "not slow and not cross_plugin"`
as a SINGLE invocation fails 21 tests in
`integration-tests/test_shared_contracts_consumers*.py` and
`test_events_log_parity.py`. Each root is fully green on its own.

Reproduced on a clean `origin/main`: **21 failed, 5944 passed** in 650s.

The failures name files the change under test never touched, so they read
as a regression the author just caused. The combined run is an attractive
convenience — one `junit.xml` for iterate F5 evidence staging — which is
exactly why it keeps getting re-attempted.

## Root cause (proven, not inferred)

The error is always `ModuleNotFoundError: No module named
'scripts.lib.data_collector'`, raised from `shared/contracts/compliance.py:93`.

The causal chain, each link verified empirically:

1. `shared/tests/__init__.py` exists and `shared/__init__.py` does not, so
   pytest's default `prepend` import mode inserts **`<repo>/shared`** at
   `sys.path[0]` and imports the modules as `tests.test_*`.
2. `<repo>/shared` on `sys.path` exposes `shared/scripts` as a portion of
   the top-level **namespace** package `scripts`.
3. `shared/scripts/lib/__init__.py` exists, so `scripts.lib` is a
   **regular** package — pinned to exactly one directory. It is cached in
   `sys.modules` on first touch **even when the submodule import that
   triggered it failed** (e.g. the `importorskip`-guarded
   `from scripts.lib.compliance_report import …` in
   `shared/tests/test_setup_writes_canonical.py:431`).
4. `shared/scripts/lib/data_collector.py` does not exist.
5. `shared/contracts/compliance.py` then prepends the compliance plugin
   root and does `from scripts.lib.data_collector import …`. The prepend
   **works** — `scripts.__path__[0]` really is the compliance plugin's
   `scripts` — but `scripts.lib` is already pinned in `sys.modules` and a
   cached regular sub-package never re-resolves against `sys.path`.

The decisive observation: the contract's own bootstrap comment claims it
inserts "ahead of any conflicting `scripts` packages from sibling plugins".
That is **structurally unachievable**. `sys.path` order cannot dislodge an
already-cached regular sub-package.

## Why "make the roots compose" was rejected

Both candidate composition fixes were built and measured, not assumed.

**Candidate A — delete `shared/tests/__init__.py`** (removes the
`<repo>/shared` capture at its source). Measured: it *does* clear all 16
contract failures in the two-module repro. But it breaks 3 collections,
because those tests depend on the capture:
`shared/tests/test_stamp_test_results.py` and `test_verifiers_adopt.py`
import `scripts.tools.*` / `scripts.lib.*` meaning *shared's*, and
`shared/tests/tools/` becomes a top-level `tools` that collides with
`shared/scripts/tools`.

**Candidate A' — keep `__init__.py`, rewrite the `scripts.*` imports.**
Raised by the Stage-3 adversarial review, which correctly observed that
`shared/tests` overwhelmingly uses top-level `lib.*` / `tools.*` (its
conftest puts `shared/scripts` on `sys.path`) and that only a handful of
statements use `scripts.*`. `<repo>/shared` on `sys.path` is indeed
harmless on its own — the pin is created by the *imports*, not the path.
Corrected position: the objection is right about the mechanism, and two
of those statements (`test_verifiers_adopt.py:15`,
`test_stamp_test_results.py:25`) do target shared's own modules and could
be rewritten. It is not pursued because:

- The remaining ones are deliberate **cross-plugin** probes, not sloppy
  imports: `test_setup_writes_canonical.py:418/431` is
  `@pytest.mark.cross_plugin` and imports the *compliance plugin's*
  `scripts.lib.compliance_report` on purpose. Rewriting it to `lib.X`
  would change what it tests.
- It leaves the trap exactly one import away from returning. The next
  `from scripts.lib.<x>` anyone adds to a shared test silently restores
  the 21 misleading failures, with no gate to catch it.
- It would fix this ONE pair while other pairs still cannot compose (see
  below), so the guard is needed regardless — and a guard plus a
  hand-maintained "except these two" exception is worse than a uniform
  rule.

This variant was reasoned about, not executed; the combined run was not
re-measured with those two statements rewritten. Recorded as the one
judgement call in this change that a reader might reasonably revisit.

**Candidate B — have the contract swap `scripts.lib`/`scripts.tools` to the
compliance plugin's directories for the duration of its import, then
restore.** Rejected on evidence: the compliance plugin contains **26+
lazy, call-time `from scripts.lib.* import …` statements** across 10 files
(`_registry.py`, `group_e.py`, `change_history.py`, `sbom_generator.py`, …).
Those execute long after the import window closes, so a restore-after-import
leaves them resolving against the foreign binding. This is the recorded
"lazy import is not ADR-045-safe" landmine.

The two requirements are **mutually exclusive within one process**:
whichever tree binds `scripts.lib` / `scripts.tools` first owns it for the
whole process lifetime, and the compliance contract needs them to mean the
compliance plugin's tree. That is a genuine structural incompatibility —
the same class as the `cross_plugin` marker (ADR-044).

And it is not confined to the reported pair. The Stage-3 review found two
independent causes the first draft of this spec did not mention, which is
why the invariant holds repo-wide rather than only for `shared/tests`:

- `shared/scripts/tools/tests` binds `scripts.tools` to `shared/scripts/tools`
  through **production** modules, not tests — `run_test_suite.py`,
  `suite_race_triage.py` and `suite_report.py` all import
  `from scripts.tools.…` at module level. No test rewrite can move that.
- `shared/tests` and `shared/scripts/tests` collide on the package name
  `tests` for a completely different reason, already documented at
  `.github/workflows/ci.yml`. That pair fails during conftest import with
  `ImportPathMismatchError`, before any guard can run.

This is already the design intent. `.github/workflows/ci.yml` runs **one
test root per pytest process** and documents why. The invariant exists; the
only gap is that violating it produces 21 misleading assertion errors
instead of a refusal.

## Change

Make the unsupported combination fail loudly and actionably.

1. **`conftest.py` (repo root, new).** A `pytest_sessionstart` guard that
   maps the session's path arguments onto the repo's known test roots and
   raises `pytest.UsageError` when a session spans more than one. The
   message names the roots that collided, states the invariant, and gives
   the supported invocation — including how to produce per-root junit
   evidence, which is what drives people to combine the roots.
   Pure guard: no fixtures, no collection changes, single-root sessions and
   non-test-root sessions are untouched.
2. **`shared/contracts/compliance.py`.** Replace the false bootstrap claim
   with what is actually true, and add a precise pre-import diagnostic: if
   `scripts.lib` / `scripts.tools` are already bound to a directory outside
   the compliance plugin, raise `ImportError` naming the captured module,
   the directory that captured it, and the cause. Covers non-pytest
   processes, where the root conftest cannot help.
3. **`shared/scripts/tools/__init__.py`.** Correct the docstring's
   self-contradictory claim ("prefers a regular package … regardless of
   `sys.path` order; having a regular `__init__` here lets plain `sys.path`
   ordering resolve the conflict"). Both halves cannot hold; it actively
   misleads the next person debugging this.
4. **`CLAUDE.md`.** State the one-root-per-session rule in the Testing
   section, with the junit-evidence recipe.

## Acceptance Criteria

- **AC1** A session spanning two test roots exits non-zero before
  collection with a message naming both roots and the supported command —
  not with assertion errors from either root.
- **AC2** A single-root session is byte-for-byte unaffected: same
  collection, same pass count, no new output.
- **AC3** The guard recognises a parent-path argument (`pytest .`) that
  spans multiple roots, and path arguments carrying `::node-id` selectors.
- **AC4** Importing `shared.contracts.compliance` in a process where
  `scripts.lib` is already captured raises an `ImportError` naming the
  capturing directory, instead of `ModuleNotFoundError: No module named
  'scripts.lib.data_collector'`.
- **AC5** (E) `shared/scripts/tools/__init__.py` no longer asserts that
  `sys.path` ordering resolves a regular-vs-regular package conflict.

## Confidence Calibration

- **Boundaries touched:** pytest session startup (`pytest_sessionstart`,
  `config.args`), Python import machinery (`sys.modules` sub-package
  caching), `shared.contracts.compliance` import-time bootstrap.
- **Empirical probes run:**
  - Full combined run on clean `origin/main` → 21 failed / 5944 passed,
    matching the report exactly.
  - Two-module repro (`test_setup_writes_canonical.py` +
    `test_shared_contracts_consumers.py`) → 16 failures in 0.57s, a
    fast oracle for the whole class.
  - `probe3` — proved a regular `scripts/lib` pins to one directory:
    compliance root appended-after-sibling → FAIL; inserted-at-front → OK.
  - `probe4` — proved the full chain, including the smoking gun that the
    contract's prepend *succeeds* (`scripts.__path__[0]` is compliance's)
    and the import *still* fails because `scripts.lib` is cached.
  - Candidate A measured, not assumed: 16/16 contract failures cleared,
    3 collections broken.
  - Candidate B sized by counting lazy imports: 26+ across 10 files.
- **Test Completeness Ledger:** see below.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the chain is proven at each link by a probe that
    prints the actual `sys.modules` / `__path__` state, not by reading code.
  - *Coverage (breadth):* guard tested for refusal, for single-root
    no-op, for parent-path spanning, and for `::` node-id args; contract
    diagnostic tested against a synthetically captured `scripts.lib`.
  - *Integration composition:* not applicable — `cross_component` does not
    fire (no merge/churn resolver, hook, phase validator, or campaign
    machinery in the diff).

## Test Completeness Ledger

Modules: `G` = `shared/tests/test_pytest_root_guard.py` (whole sessions in
child processes) · `D` = `shared/tests/test_pytest_root_discovery.py` (the
pure resolver/discovery rules) · `C` =
`shared/tests/test_contract_namespace_capture.py`.

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | Two-root session is refused before collection | `tested` | G·`test_multi_root_session_is_refused` |
| 2 | Refusal precedes the import errors it replaces | `tested` | G·`test_refusal_is_not_a_collection_or_assertion_error` |
| 3 | Refusal names every colliding root | `tested` | G·`test_refusal_message_names_both_roots` |
| 4 | Refusal gives a command for every root, not just two | `tested` | G·`test_refusal_message_gives_supported_command` |
| 5 | Single-root session still collects clean | `tested` | G·`test_single_root_session_is_untouched` |
| 6 | Single-root session still EXECUTES green | `tested` | G·`test_single_root_session_still_executes_green` |
| 7 | Two-root session from a subdirectory is refused | `tested` | G·`test_multi_root_is_refused_from_a_subdirectory` |
| 8 | `pytest .` inside one root is NOT refused | `tested` | G·`test_dot_inside_a_root_is_not_refused`, D·`test_dot_arg_inside_a_root_reaches_only_that_root` |
| 9 | Parent-path arg spanning roots is refused | `tested` | D·`test_parent_path_spanning_roots_is_refused` |
| 10 | `::` selector is split off before matching | `tested` | D·`test_node_id_selector_is_stripped` (root-level selector — the case that fails on revert) |
| 11 | Relative args resolve against the invocation dir | `tested` | D·`test_relative_args_resolve_against_the_invocation_dir`, D·`test_relative_args_from_a_subdir_can_still_span_roots` |
| 12 | Vendored `tests/` under `.venv`/`node_modules` are not roots | `tested` | D·`test_skip_dirs_keep_vendored_tests_out_of_discovery` |
| 13 | Discovery prunes rather than post-filters | `tested` | D·`test_discovery_does_not_descend_into_skipped_dirs` |
| 14 | Nested fixture `tests/` are not separate roots | `tested` | D·`test_fixture_tests_dirs_are_not_roots` |
| 15 | Every CI root survives alone | `tested` | D·`test_every_ci_root_survives_alone`, D·`test_discovered_roots_cover_the_ci_matrix` |
| 16 | Non-test-root args are ignored | `tested` | D·`test_unrelated_paths_are_ignored` |
| 17 | Captured `scripts.lib` raises `ImportError` (not `ModuleNotFoundError`) naming the capture | `tested` | C·`test_captured_scripts_lib_raises_named_importerror`, C·`test_capture_error_does_not_blame_the_compliance_plugin` |
| 18 | Capture error states that sys.path order cannot fix it | `tested` | C·`test_capture_error_explains_that_syspath_order_cannot_fix_it` |
| 19 | Uncaptured import path is unchanged | `tested` | C·`test_clean_process_imports_contract_normally` |
| 20 | `shared/scripts/tools/__init__.py` claim corrected | `tested` | C·`test_tools_init_docstring_has_no_false_ordering_claim` |

Zero testable-but-untested behaviours.

**Ledger corrections applied after Stage-1 review** (the first draft
over-claimed, which is exactly what the ledger exists to catch):

- Row 5's original evidence (`--collect-only` on one file) could not
  substantiate "unaffected"; row 6 now actually runs the root.
- Row 10's original evidence passed with the `::` split deleted, because
  `.parents` matching reached the root anyway. Replaced with a root-level
  selector, which resolves to nothing when unsplit.
- Row 17's original evidence passed with the whole capture check deleted
  (the traceback happens to contain every asserted substring). The probe
  now reports the exception TYPE, so a revert to `ModuleNotFoundError`
  fails.
- Rows 11-13 did not exist: the relative-arg rule and the `_SKIP_DIRS`
  pruning were implemented but unlisted and untested.

## Rollback

All four edits are additive or comment-only except the new root
`conftest.py`. Deleting `conftest.py` restores the previous (misleading)
behaviour exactly; the contract diagnostic only converts an error that was
already fatal into a better-labelled one.
