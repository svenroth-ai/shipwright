# Iterate: Requirements golden corpus — freeze today's discovery and parsing, bugs included

- **Run ID:** iterate-2026-07-18-requirements-golden-corpus
- **Date:** 2026-07-18
- **Type:** change
- **Complexity:** medium (`prior_source: history`, n=20)
- **Spec Impact:** NONE (test-only; no production code touched)
- **Campaign:** Requirements Catalog — sub-iterate **S1** (`Spec/design/2026-07-18-requirements-catalog-campaign-SPEC.md` §4)
- **Risk flags:** none detected at classify time (recomputed at F11)

## Problem

Campaign steps S2–S4 rewrite the requirements discovery and parsing machinery and
claim to be **behaviour-preserving**. Today that claim cannot be checked, only
asserted: there is no test that pins what the current machinery actually returns.

The machinery is more divergent than the campaign SPEC records. A survey of the
live tree found:

- **15 independent discovery walks**, not the 9 the SPEC names — and **5 of the
  9 named paths point at a directory that does not exist** (`shared/scripts/lib/compliance/`;
  the real root is `plugins/shipwright-compliance/scripts/`). Line numbers were
  accurate to within 3 lines, so the SPEC was written against real code with
  mis-transcribed roots.
- **5 parsers**, one of which has **moved** since the SPEC was written:
  `backfill_scan.py:181` is now `_load_events_fr_by_commit`; the parser was
  extracted to `shared/scripts/lib/_backfill_spec_parse.py::parse_frs`.

Without a frozen baseline, "byte-identical before and after" (S2's AC) is
unfalsifiable.

## What the divergence actually looks like

The 15 walks disagree on nearly every axis. This is the surface S2 must preserve:

| Axis | Split across the 15 |
|---|---|
| Return type | 4 ways: dataclass lists, `Path` lists, a `list[str]`, a raw `str`, and one **generator** |
| `iterate/` dir | 3 exclude · 4 include · 1 special-cases it (yields *every* `*.md`) |
| Hidden dirs | excluded only by the 2 that use `glob`/`rglob` — accidentally, not by intent |
| Loose `planning/spec.md` | ignored by 14, picked up by exactly 1 (`setup-design-session.find_specs`) |
| `planning` is a file | **4 crash** with `NotADirectoryError`; the rest degrade (the survey predicted 3) |
| Sort order | 2 do not sort at all (`validate_adoption`, `review_runner`) |

None of the nine SPEC-named walks is the correct implementation. The only one that
filters non-dirs **and** dotdirs **and** `iterate/` is `plan_checks._find_planning_split_dirs`,
which the SPEC does not list.

The 5 parsers split cleanly into **2 positional** (`drift_parsers`, `rtm` — which
share a byte-identical regex) and **3 header-driven** (`_requirement_parse`,
`group_i`, `_backfill_spec_parse`), and they disagree on FR-id strictness across
three tiers:

| Tier | Pattern | Accepts `FR-7`? | Accepts `FR-1.1`? |
|---|---|---|---|
| Loose (`drift_parsers`, `rtm`) | `FR-[\d.]+` unanchored | **yes** | yes |
| Medium (`group_i`) | `^FR-\d+\.\d+$` | no | yes |
| Strict (`_requirement_parse`, `_backfill_spec_parse`) | `^FR-\d{2}\.\d{2}$` | no | **no** |

## The point most likely to be got wrong

**The harness must freeze today's behaviour INCLUDING its bugs.** Fixing anything
here destroys the baseline the refactor is measured against. Non-goal: fixing.

Every frozen-wrong assertion carries a `FROZEN-BUG:` comment stating what is wrong,
why it is not fixed here, and which campaign step flips it. Without that comment a
future reader sees a test asserting wrong output and "corrects" it — silently
destroying the baseline.

### The two verdicts the SPEC names

**FV-1 — a spec parsing to zero rows makes T1 SKIP rather than FAIL.**
`traceability_checks.check_t1_all_spec_frs_mapped:77-83` guards on
`if not requirements:` — a plain falsiness test. `collect_requirements_from_planning`
returns `[]` for **both** "no planning directory" and "spec present, every row
failed to parse", so the guard cannot tell them apart and the `FAIL` branch below
is unreachable on a zero-row parse. **Flipped by S4.**

**FV-2 — an empty manifest reads green.** Ten Tier-1 sites treat "no requirements"
as "nothing to audit". The sharpest is **not** in the SPEC's list:
`_group_d_traceability.py:186` emits `("pass", "LOW", "every active FR is covered
at its required layers", ...)` — a positive coverage claim over the empty set.
Every other site at least says `skip`. **Flipped by S6.**

### Three further wrong behaviours found during the survey

Not in the SPEC. Frozen here with `FROZEN-BUG:` comments, added to S4's AC, and
filed as a triage anchor so they survive if S4 is descoped.

**FV-3 — the RTM can display the wrong requirement text.** `drift_parsers` and
`rtm` are header-blind: a row carrying more cells than its header declares has a
*later* column read as the requirement body. Given a 3-column header and the row
`| FR-01.03 | ok | Should | extra | cells |`, both return text `"extra"`, not
`"ok"`. This is live wrong data in a shipped audit artifact, not merely a parse
divergence.

**FV-4 — Group I silently audits nothing when the header says `FR` instead of `ID`.**
`group_i._column_map` requires `low[0] == "id"` exactly. On the traceability-fixture
shape `FR | Description | Priority | Layers` it returns `None`, so `mapping` stays
`None` and **every row in the file is dropped**. All four naming-hygiene checks
then report against zero rows.

**FV-5 — Group I drops requirement rows after any heading.** `_scan_one_spec` resets
`mapping = None` at *every* heading, table-related or not. An FR row appearing under
a later heading without a repeated header row is silently dropped.

FV-3, FV-4 and FV-5 are all fixed by the same change — S4's single header-driven
reader — which is why they attach to S4 rather than becoming their own step.

## Design decisions

**D1 — the corpus is materialized into `tmp_path`, not committed as an on-disk tree.**
A committed `integration-tests/fixtures/**/.shipwright/planning/*/spec.md` tree would
be walked by the repo's own requirements machinery — the traceability collector, the
artifact-path-canon gate, staleness checks. A test corpus that pollutes the control
plane it measures is a self-inflicted false verdict. Corpus content lives as data in
a Python module; each test materializes what it needs.

**D2 — fixtures are written to disk, not passed as strings.** `rtm.collect_requirements`
takes a project root and does its own walk; it cannot be driven by a string. Writing
real files keeps one corpus for both the discovery and the parser dimension, and
exercises discovery+parse together as production does.

**D3 — `absent` and `empty` are separate fixtures.** This is the distinction FV-1
conflates. Freezing them separately means S4 updates **one** assertion, and the diff
shows exactly which cause changed. The pre-existing `shared/tests/test_traceability_checks.py`
pins the combined behaviour (`test_t1_skips_when_spec_has_no_frs`,
`test_t1_skips_without_planning_tree`) without separating the causes; it is left
untouched here.

**D4 — `group_i` gets its own import realm, i.e. its own subprocess.** Importing
it transitively runs `audit_adapters`, which at module level reorders `sys.path`
and **evicts `sys.modules['tools']`**; `_requirement_parse` resolves shared libs
through `_lib_loader` at *call* time, so a reordered path could change what it
resolves and produce a baseline that looks authoritative and is quietly wrong.

An earlier version of this decision said "import `group_i` last" — which was
both unimplemented (it was 4th of 7 in the compliance realm) and unenforceable,
since `collect()` walks targets in registry order and any cosmetic reordering
would silently move it. A process boundary cannot be undone by an edit. A guard
test now asserts the realms stay separate.

**D5 — corpus scope is 15 walks, not 9** (operator decision, 2026-07-18). Anything
left unfrozen can change under S2 without the harness noticing.

## Scope

**Ten fixtures.** The SPEC names five; five more were added for cause, three of
them on review findings:

| Fixture | Why |
|---|---|
| `greenfield-multi-split` | SPEC-named. 3 splits, template + example shapes |
| `brownfield-single-split` | SPEC-named. adopt 5-col shape |
| `empty` | SPEC-named. `planning/` exists, no splits |
| `malformed` | SPEC-named. ragged cells, unclosed pipes, no header, lowercase + invalid priority, escaped pipe, duplicate id |
| `mixed-shape` | SPEC-named. all 5 historical shapes + reordered + header-blind |
| `absent` | **added** — D3; separates FV-1's two causes |
| `zero-row-parse` | **added** — the fixture that actually expresses FV-1: a populated spec the positional parsers read as zero rows |
| `planning-file` | **added on external review** — `planning` is a regular file; 4 targets raise `NotADirectoryError`, the rest degrade |
| `spec-dir` | **added on adversarial review** — the inverse: `spec.md` is a directory. `drift_parsers` swallows the `OSError`, `rtm` raises. Two functions the campaign SPEC calls mirrors, diverging exactly where S2 unifies them |
| `edge` | **added** — hidden dir, `iterate/`, loose `planning/spec.md`, split without spec, removed-requirements section, fold-map section, all three id-strictness tiers |

**21 registry entries** covering 15 distinct discovery walks + 5 parsers:
`group_i.scan_fr_rows` appears twice to exercise both sides of its keyword-only
`include_retired` flag, and `rtm.collect_requirements` is registered under both
dimensions because it genuinely is both a walk and a parser.

**Seven import realms**, one subprocess each.

## Acceptance criteria

1. Every one of the 15 discovery paths has a pinned expected result per fixture
   (16 registry entries; `review_runner`'s inline walk is source-hash-frozen,
   see ledger row 18).
2. Every one of the 5 parsers has a pinned expected result per fixture.
3. FV-1 and FV-2 are recorded as current behaviour, each with a `FROZEN-BUG:`
   comment naming the flipping step (S4, S6).
4. FV-3, FV-4, FV-5 are recorded as current behaviour with `FROZEN-BUG:` comments,
   added to the campaign SPEC's S4 acceptance criteria, and filed as a triage anchor.
5. The harness runs in CI and is **not** marked `slow`.
6. No production code is modified. `git diff --stat` shows test files and this
   spec only — the campaign SPEC lives under the gitignored `Spec/`, so its
   correction is real but correctly outside the PR.
7. The campaign SPEC's stale paths and the 9→15 count are corrected.

## Out of scope

- Fixing any frozen behaviour (that is S2–S6).
- Retiring `integration-tests/test_fr_table_drift_protection.py` (S4 does that).
- Touching `shared/tests/test_traceability_checks.py` (see D3).

## Confidence Calibration

- **Boundaries touched:** no production code is modified. The harness READS
  across six import realms (`shared/scripts/lib`, `shared/scripts/tools`, and the
  compliance / adopt / project / design plugins) and writes only into `tmp_path`.
  The one persisted artifact is `golden.json`, a committed baseline.

- **Empirical probes run:**

| Probe | Finding |
|---|---|
| Import all 20 targets in one process | 3 of 20 fail. `plan_checks` and `state` need package-style import (relative imports); `setup-design-session` is hyphenated and needs `spec_from_file_location` + its plugin's `scripts/` on path. |
| `sys.path` / `sys.modules` damage per import | `group_i` reorders `sys.path` and evicts `sys.modules['tools']` via `audit_adapters`. Confirms an import-ORDER discipline is insufficient — pytest collection can defeat it. Drove decision D4 → subprocess-per-realm. |
| `fr_gates` under the naive realm path | `ModuleNotFoundError` — it lives inside `lib/` yet reaches siblings via `from lib.fr_classification`, so it needs the PARENT on path (ADR-045). Realm now carries both. |
| Collector run 3×, cell-by-cell diff | **Not deterministic.** Two causes: exception messages embed the temp path AND are locale-dependent (`Der Verzeichnisname ist ungültig` locally vs English in CI); and the two unsorted walks pick a spec by filesystem order. Fixed by recording exception TYPE only and masking the unordered pick. Re-verified: 3 runs identical. |
| `planning`-is-a-file across all discovery targets | **4** raise `NotADirectoryError`, 10 degrade — the survey predicted 3. The fixture the external review insisted on earned its place immediately. |
| FV-1 across `absent` / `empty` / `zero-row-parse` | All three return `SKIP` with the **identical** evidence string, including the one holding a real requirement. FV-1 confirmed in its purest form. |
| FV-2 at `_group_d_traceability.check_layer({})` | Returns `("pass", "LOW", "every active FR is covered at its required layers")` — a positive claim over the empty set, verbatim as predicted. |
| FV-3 / FV-4 / FV-5 | All three reproduce exactly: text `"extra"` instead of `"ok"`; `[]` on an `FR` header; `FR-01.20` dropped by `group_i` alone while all four other parsers keep it. |
| **Mutation test A** (lowercase priority accepted) | **SURVIVED** — harness stayed green. Exposed a real corpus gap: no fixture carried a lowercase or invalid priority. Gap closed; mutation now caught (and transitively catches `fr_gates`). |
| **Mutation test B** (body reads col2 not col4) | Caught, naming the two affected targets plus the whole-file check. Confirms the matrix bites rather than merely passing. |
| Full `integration-tests/` suite | 280 passed, 2 deselected, 78s. No regression. |
| Runtime of the new suites | 44 tests in ~3s — well clear of `slow`. |

- **Test Completeness Ledger:**

| # | Behavior | Disposition | Evidence |
|---|---|---|---|
| 1 | All 15 discovery paths pinned per fixture | `tested` | `test_target_behaviour_matches_the_frozen_baseline` (parametrized per target) |
| 2 | All 5 parsers pinned per fixture | `tested` | same, `parse.*` params |
| 3 | Registry holds exactly 15 + 5, no duplicates | `tested` | `test_registry_holds_exactly_the_claimed_inventory` |
| 4 | Every registry source path resolves (forward drift) | `tested` | `test_every_registry_source_file_exists` |
| 5 | Every declared realm is used (reverse drift) | `tested` | `test_every_realm_is_actually_used` |
| 6 | An import failure never reads as "no findings" | `tested` | `test_no_target_failed_to_import` |
| 7 | Golden schema version is pinned | `tested` | `test_golden_schema_version_matches` |
| 8 | Whole-file baseline currency | `tested` | `test_golden_file_is_byte_current` |
| 9 | FV-1 frozen, and its two causes kept apart | `tested` | 3 tests + a control proving T1 can still FAIL |
| 10 | FV-2 frozen across D-group, Group I, and the positive-claim site | `tested` | 3 tests |
| 11 | FV-3 / FV-4 / FV-5 frozen | `tested` | `test_fv3_…`, `test_fv4_…`, `test_fv5_…` |
| 12 | Unsorted walks track enumeration order | `tested` | `test_unsorted_walk_tracks_enumeration_order` (controlled seam, not luck) |
| 13 | Every frozen bug names its flipping step | `tested` | `test_every_frozen_bug_names_its_flipping_step` |
| 14 | Frozen-bug cells resolve in the matrix | `tested` | `test_frozen_bug_cells_exist_in_the_matrix` |
| 15 | The corpus discriminates between targets | `tested` | `test_corpus_discriminates_between_targets` — guards against a green-but-worthless matrix |
| 16 | `planning`-as-file still splits raise/degrade | `tested` | `test_planning_as_a_file_still_splits_the_targets` |
| 17 | Harness runs in CI, not `slow` | `tested` | placement in `integration-tests/`; CI step runs it under `-m 'not slow'` only |
| 18 | `review_runner`'s inline walk | `untestable` — `requires-external-nondeterministic-service` | The walk is inline inside `run_review`, which calls an external LLM. Registered `invoke: source_only`; compensating control is the registry source-path assertion (#4), which fires if the file moves. **Stated plainly rather than counted as covered.** |

0 testable-but-untested. One `untestable` row, with a closed-vocabulary reason and
a named compensating control.

- **Review rounds:** two external (GPT-5.4 + Gemini 3.1 Pro, plan then code)
  and one adversarial (internal doubt-reviewer, briefed to disprove the central
  claim). 14 findings adopted, 1 rejected with reasons. The three that changed
  the design materially:

  1. **The baseline was Windows-shaped and CI is `ubuntu-latest`.** 23 lines
     carried `01-auth\spec.md` from `setup-design-session.find_specs`, which
     returns `str(relative_path)`. The harness would have gone red on its first
     CI run — and the failure message points at `regen_golden.py`, so the S2
     author's first lesson would have been "regenerating is how you deal with
     this harness". A portability bug would have defeated the no-update-flag
     design before the corpus guarded anything. Fixed: the matrix stores the
     posix form, the OS-separator behaviour is pinned in a dedicated test, and
     a guard test forbids separator paths from re-entering the baseline.
  2. **The unordered-pick mask was keyed on text shape and destroyed
     compile-time literals** — including `"A2 .shipwright/planning/<split>/spec.md
     has >= 1 FR"`, emitted on a branch that returns before any walk happens. An
     operator-facing message change was invisible to the matrix. Now masked by
     actual materialized paths. Separately, only one of the two masked targets
     had a compensating seam probe; the second now has one. Masking without a
     compensating probe is a blind spot with good manners.
  3. **`review_runner` was frozen by a three-word constant.** The registry
     claimed a source-level guarantee while `{"kind": "source_only"}` froze
     nothing, so 1 of 15 walks was unpinned and the harness said otherwise. Now
     records a sha256 of the enclosing function plus its line count.

  Also adopted: `group_i` moved to its own realm (it was 4th of 7 in the
  compliance realm, so its import-time `sys.path` reorder preceded
  `_requirement_parse`); `test_golden_file_is_byte_current` de-circularized;
  six unexercised load-bearing branches given fixtures; the discrimination test
  strengthened from a global floor that could not fail to per-fixture floors;
  `regen_golden.py` now requires `--reason`, stamped into the baseline so the
  justification travels in the diff a reviewer reads.

  **Rejected:** replacing the custom golden with `syrupy`/`pytest-snapshot`.
  The proposed mitigation for the update-flag risk — block it in CI — misses
  where the danger is: a developer regenerates *locally*, commits a destroyed
  baseline, and CI validates happily against the new "truth". The flag's
  existence is the hazard. It would also not provide the outcome-kind/type/
  ordering/exception schema, since snapshot libraries serialize reprs.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the two mutation tests are the depth probe. Test A
    surviving is the most valuable single result of this iterate — it showed the
    corpus had a blind spot that pure inspection had not revealed, and "44 tests
    pass" would otherwise have read as adequacy.
  - *Coverage (breadth):* 20 targets × 9 fixtures. Breadth is bounded by the
    registry, which is count-asserted in both directions, so a silently shrinking
    matrix fails rather than passes.
  - *Integration composition:* not applicable — `cross_component` does not fire
    (test-only diff, no merge/hook/phase-validator machinery touched). The
    subprocess-per-realm design is nonetheless an integration concern and is
    covered by #6: a realm that fails to load fails the suite loudly rather than
    contributing an empty, green result set.
