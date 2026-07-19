# Iterate: one shared spec-discovery helper; all 15 call sites delegate

- **Run ID:** `iterate-2026-07-19-one-discovery-function`
- **Campaign:** `2026-07-18-requirements-catalog` · sub-iterate **S2**
- **Mode:** SIMPLIFY (behaviour-preserving) · **Spec Impact:** NONE
- **Complexity:** medium

## Problem

Fifteen independent implementations of "walk `.shipwright/planning/` and find the
spec files" were scattered across six import realms. They did not agree, and the
disagreements were invisible because each lived inside a different function.
Campaign S1 (PR #403) built a golden corpus that measured the divergence:

| axis | walks |
|---|---|
| raise `NotADirectoryError` on a `planning` FILE | 4 |
| exclude `iterate/` | 3 |
| do not sort | 3 |
| recurse (`rglob`) | 5 |
| require `is_file()` rather than any `exists()` | 2 |

## Decision

Extract ONE parameterized helper, `shared/scripts/lib/planning_discovery.py`,
exposing `iter_split_dirs()` and a thin `iter_spec_files()` built on it. Each
call site passes the flags that reproduce **what it does today**.

The helper is deliberately **parameterized, not opinionated**. Converging the
filter semantics is a behaviour change for ≥10 of the 15 sites and is a separate,
per-call-site decision (campaign S2b). The divergence now lives in one place,
expressed as arguments — which is the precondition for converging it later, not
a substitute for doing so.

## Per-call-site flag matrix

Derived by reading all 15 implementations, not inferred from corpus output
(external review, OpenAI finding 3). `guard` reproduces the pre-check; `req`
is `exists` unless noted; `rec` = recursive `rglob`.

| # | call site | guard | sort | iterate/ | rec | req | yields |
|---|---|---|---|---|---|---|---|
| 1 | `drift_parsers.collect_requirements_from_planning` | exists | Y | in | – | exists | files |
| 2 | `spec_parser.read_top_level_spec` | is_dir | Y | in | – | exists | files |
| 3 | `spec_parser._iter_spec_files` | is_dir | Y | special | – | exists | dirs |
| 4 | `fr_gates.collect_known_fr_ids` | is_dir | N | in | – | **is_file** | files |
| 5 | `backfill_test_links.discover_specs` | is_dir | Y | **out** | – | exists | files |
| 6 | `adopt_compliance.check_a2_spec_has_frs` | is_dir | **N** | in | **Y** | – | files |
| 7 | `rtm.collect_requirements` | **exists** | Y | in | – | exists | files |
| 8 | `rtm.collect_external_review_states` | **exists** | Y | **out** | – | – | dirs |
| 9 | `_test_links_io.discover_specs` | is_dir | Y | **out** | – | exists | files |
| 10/11 | `group_i.scan_fr_rows` (both flags) | is_dir | Y | in | – | **is_file** | files |
| 12 | `validate_adoption._validate_spec` | is_dir | **N** | in | **Y** | – | files |
| 13 | `setup_adopt._detect_existing_artifacts` | is_dir | Y | in | **Y** | – | files |
| 14 | `review_runner.run_review` | is_dir | **N** | in | **Y** | – | files |
| 15 | `state.detect_state` | **none** | N→own key | own filter | – | – | dirs |
| 16 | `setup_design_session.find_specs` | is_dir | N→own str sort | in | **Y** | – | files |

Three sites take **dirs** rather than files, which is why the module exposes
`iter_split_dirs` alongside `iter_spec_files` (see "Deviation" below).

## Code-review outcomes (ADR-029 Step 3.7)

- **Ordering equivalence — FALSIFIED, code unchanged.** `read_top_level_spec`
  was flagged for sorting split dirs where it once sorted full `*/spec.md`
  paths. The claimed mechanism (`PurePath.__lt__` comparing one joined string,
  so a proper-prefix pair inverts on `-` vs the separator) is wrong: pathlib
  compares a **parts list** on 3.11.15 / 3.12 / 3.13 alike, and with a constant
  trailing component `[planning, X, spec.md]` vs `[planning, Y, spec.md]`
  reduces to `X` vs `Y`. Raw *string* comparison genuinely does invert, which is
  presumably the source of the claim. Adding a redundant `sorted()` was rejected
  — it would imply a bug that does not exist. The reviewer's second-order point
  stood: no corpus fixture holds a proper-prefix split pair, so the corpus is
  structurally blind to this axis. Pinned instead by
  `test_sorting_split_dirs_equals_sorting_full_spec_paths` (4 pairs) plus a
  guard test asserting the pairs still invert under naive string sorting, so the
  equivalence test cannot silently stop testing anything.
- **`planning_dir()` deleted** — exported with zero callers while ~13 sites
  still built the path inline. Shipping the abstraction and the duplication it
  was meant to remove is exactly what YAGNI forbids.
- **`filename=` parameter dropped** — no call site passed it, and its docstring
  cited `rtm.collect_external_review_states`, which does **not** use it (that
  site calls `iter_split_dirs`, because it must emit `status="missing"` rows for
  splits LACKING the marker). A future caller following that docstring would
  have silently dropped every missing row. The docstring now records plainly why
  the knob does not exist.
- **`shared/tests/test_planning_discovery.py` added** — 19 tests covering the
  parameter matrix directly, including both `ValueError` guards and `guard="none"`
  in isolation, which no call site can reach. Non-vacuity checked by mutation:
  5/5 seeded mutants killed.

### Corrections to the sub-iterate spec's divergence table

Counted from source, the sub-iterate spec undercounted two rows:

- **recurse: 5, not 2** — `adopt_compliance`, `validate_adoption`, `setup_adopt`,
  `review_runner`, `setup_design_session` all use `rglob`.
- **do not sort: 3, not 2** — `adopt_compliance.check_a2` is unsorted too (the
  registry already flags it `order_sensitive`); the spec named only
  `validate_adoption` and `review_runner`.
- **hidden dirs: 15, not "≥10"** — pathlib's `glob`/`rglob` DO match a leading
  dot, so there is no hidden-dir axis at all. The corpus proves it: every walk
  that returns paths lists `.hidden-split/spec.md` on the `edge` fixture.
  Comments in `corpus_data.py` and `registry.py` claiming the opposite are
  corrected in this commit.

## Deviation from "ONE shared helper"

The AC says one helper; the module exposes two public functions. `iter_spec_files`
is a thin wrapper that delegates to `iter_split_dirs` for the non-recursive case —
there is exactly ONE walk implementation. `iter_split_dirs` stays public because
three call sites (#3, #8, #15) genuinely need the split *directories*: #8 emits a
row for a split that LACKS its target file, and #15 applies its own name filter
and sort key. Making it private would force those three to re-implement the walk,
which is the thing this iterate exists to remove. Accepted with reason
(external review, OpenAI finding 2). Code review then trimmed the surface to
exactly those two functions — `planning_dir()` and the `filename=` knob were
both removed as unused, so nothing is exported that no caller reaches.

## Affected Boundaries (ADR-024)

The changed serialized surface is `integration-tests/requirements_corpus/golden.json`.
Producer: `regen_golden.py` / `collect.py`. Consumer: the four
`test_requirements_corpus_*.py` suites. Round-trip probe: `regen_golden.py --check`
re-derives the whole matrix from the modified machinery and diffs it against the
committed baseline — run before and after every step of this iterate.

No user-facing artifact format changed. No data moved. No file was renamed.

## Acceptance Criteria

- [x] One shared helper exists; no call site retains its own walk (15/15).
- [x] `regen_golden.py --check` reports `golden.json is current`.
- [x] Corpus suites pass unchanged (51 tests).
- [x] `registry.py` still resolves every `source` path.
- [x] `spec_parser._iter_spec_files` is still a generator.
- [x] The unsorted walks still track enumeration order.
- [x] `state.detect_state`'s planning-dir signature unchanged.
- [x] `behavior_snapshot.py` snapshot → verify: behaviour preserved.

## Out of scope

- Converging filter semantics (→ S2b).
- Fixing the 4 planning-FILE crashers or the 3 unsorted walks.
- The parsers (→ S4) or the table shape (→ S5).
