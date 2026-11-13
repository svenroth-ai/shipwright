# Deterministic-first programme rev 5: measurements before Q1

**Stand:** 2026-11-07 · **Tree:** `origin/main` @ `a241a2575` plus brief rev 5 · **Purpose:** check the load-bearing assumptions of programme brief rev 5 (P18-P21, §0) before ac-at-start Q1 is merged. Everything here was measured in a worktree. No file on `main` was changed.

## 1. How much can the changelog promise lock protect (P19)?

FR-01.09 has 15 ACs. `covers` marks on the current tree, excluding the stopped BP's `test_baseline_*` fixtures, which only use the id as data:

| AC | Deterministic test on code the plugin runs | Note |
|---|---|---|
| AC01 | through the prose: `test_skill_event_blocks_behaviour.py` runs the `SKILL.md` Step 7 blocks against a clone | promise candidate that rebinds to the CLI (P18) |
| AC02-AC10, AC12-AC14 | yes (aggregator, `git_utils`, setup suggestion, manifest sync, release page) | 12 ACs |
| AC11 | only the aggregator (`test_aggregation_never_shells_out_to_git_or_gh`); the publishing order lives in Step 7 prose (pilot D2) | `oracle: trace` |
| AC15 | no mark; `test_publish_release_notes.py` checks that a failure is reported; "not undone" depends on the Step 7 order | `oracle: trace`, unmarked candidates |

**Result:** 13 of 15 ACs have a deterministic test, 12 of them on code. That is well above the P19 threshold of half. **Not yet checked:** whether each test exercises the path the skill actually takes. The AC04 precedent shows that a green test on a function the skill never called proves nothing. That check is the P0 ledger reconcile.

## 2. Prose pins, found by breaking the prose (P11, pilot P0.3)

Method:
- Run five roots twice: the changelog root, `shared/tests`, `integration-tests`, `shared/scripts/tests` and `shared/scripts/tools/tests`.
- The second run replaces `SKILL.md` and seven references with a placeholder. `release-notes-prompt.md` is kept, because code reads it at runtime.

Baseline: all green. Broken: **24 tests in 11 files** fail.

| Kind | Tests | Files |
|---|---|---|
| Behaviour through prose (runs `SKILL.md` blocks; AC01) | 7 | `test_skill_event_blocks_behaviour.py` |
| Text pins on changelog wording | 12 | `test_skill_event_ships_in_release_pr.py` (3, AC01), `test_skill_release_flag_wiring.py` (4, unmarked), `test_release_pathspec_doc_sync.py` (3), `test_changelog_judgement_drift.py` (1, AC01), `test_setup_changelog_version_suggestion.py::test_skill_step_3_uses_the_suggestion_not_its_own_rule` (1, AC04) |
| Cross-plugin guards over every phase skill | 5 | `test_multi_session_removal_residue.py`, `test_phase_skill_invocation_mode_canon.py`, `test_phase_gate_discipline_present.py`, `test_canon_marker_write_contract.py`, `test_events_reference_guard.py` |

Corrections to the pilot brief's known list:
- `test_condense_release_notes.py` and `test_changelog_aggregation_idempotency.py` are **not** pins.
- `test_skill_event_blocks_behaviour.py`, `test_setup_changelog_version_suggestion.py`, `test_events_reference_guard.py`, `test_multi_session_removal_residue.py` and `test_phase_gate_discipline_present.py` are missing from it.

The five cross-plugin guards are **constraints the thin `SKILL.md` must keep satisfying**, not pins to move or remove. They are the kind of test rev 5's dropped `rule` class described. P11 should name them as such.

## 3. What converting changelog saves in CI time (P24)

From the JUnit files of the baseline run (local, one root per process):

| Root | Tests | Wall-clock | Changelog-related tests (by file name) |
|---|---|---|---|
| `plugins/shipwright-changelog/tests` | 108 | 8 s | 108 |
| `shared/tests` | 13,862 | 1,393 s (23 min) | 304, about 11 s |
| `integration-tests` | 664 | 335 s | 2 |
| `shared/scripts/tools/tests` | 1,509 | 196 s | 37, about 4 s |
| `shared/scripts/tests` | 707 | 25 s | 79 |

All changelog-related tests take about 18 s together. **Converting changelog saves almost no test time.** These are deliberately serial, one-process runs without xdist. F0 runs the roots in parallel, with xdist on its allowlisted roots, and CI runs two parallel jobs since #1002 (about 12 minutes). So the 23 minutes are not what an iterate or a PR pays. The conversion's gain is clarity: which test protects which promise.

## 4. Per-test fingerprint for the promise lock (P21)

Spike: `ast_hash.py`, operator scratchpad, not committed. It hashes the AST of the test function, decorators and docstring stripped, plus every same-module function it calls or requests as a fixture, transitively. It was probed on five real AC test files with controlled edits:

- **Never changed a fingerprint:**
  - a ruff reformat at line length 60;
  - comments;
  - swapped imports and an added import;
  - an added marker;
  - an appended new test;
  - changed docstrings.
- **Changed exactly the affected tests:** an asserted value changed, or an assertion deleted.
- **One finding:** the first version hashed only the test body. It missed assertions inside a helper (`_event_blocks` in `test_skill_event_blocks_behaviour.py` asserts for six tests). Including called helpers fixed it. A helper change now correctly trips all six tests.
- **Known limit:** fixtures from `conftest.py` are not included yet.
- **Probe failure:** in one of the five files, a probe mutation produced invalid Python. That is a fault of the probe, not of the fingerprint.

## 5. Run evidence for AC bindings (§0): the join exists, its output is thrown away

- `ci.yml` already regenerates `test-traceability.json` from each run's real JUnit files. See the step "Check traceability manifest against a fresh regeneration".
- It uploads the regenerated file as the artifact `traceability-manifest-regenerated`, but only when the regenerated file matches the committed one (drift code 0).
- The committed file dates from 2026-10-09. Every push to `main` therefore reports structural drift: `::warning::` on run 42306045424, 2026-11-06. The upload is skipped.
- None of the last 8 push runs on `main` has that artifact.
- The committed file keeps `executed: not_run`, and the local pre-commit hook says so: "the 80% commit gate is NOT evaluating".

**Consequence for §0:** inside a PR the evidence already works, because the keystone AC gate reads the fresh regeneration. Fixing the upload would help only this repo: Shipwright ships no CI that regenerates the manifest (`shared/templates/github-actions/` has no such step). The gap that matters for every repo is local. F5 stages one run's JUnit into `.shipwright/compliance/evidence/` and the next run clears it, so the release regeneration sees at most one run. The proposal is in programme brief §0: one result file per run, assembled at release.

## 6. Feedback for the ac-at-start Q1 session

Checked on the Q1 branch at `8bda3bd4c`; `ac_record.py` is unchanged since `6e8605f43`. The kind `unchanged` is decided without an operator question. At F11, `ac_record._item_problems` raises two problems for a 1:1 conversion:
1. Every `unchanged` AC needs an **added** line in a test file of the diff that names it (`_mentions`). A conversion keeps its promise tests untouched, so it warns once per kept AC on every unit.
2. Every item's `files` must equal **all** observable files of the diff, so several items repeat the same list.

Proposal: also accept a mention in a test that exists at the base, or in the plugin's promise lock; keep rule 2. Also confirm that campaign unit runners emit `source: iterate`, because `pre_build_ac_check` skips every other source. A dry run of the F11 verifier on a real extraction diff was **not** done, at the operator's request: Q1 is still being reworked.

## 7. Checks before the pilot, 2026-11-09 (after Q1 #1014 and Q2 #1022/#1023)

### 7.1 F11 dry run on a real extraction diff (programme §2.1)

Throwaway worktree off `origin/main` @ `f42a28f5d`, local branch only, never pushed. The extraction moved the Step 7 "record the release event" block of `changelog/SKILL.md` into `plugins/shipwright-changelog/scripts/tools/record_release_event.py`; the prose became one call. The AC record was written first, the way a campaign unit runner does:
- `ac_decision.py --ac-mode auto --autonomous` (unattended through `SHIPWRIGHT_LOOP_UNIT_ID`), one item `unchanged FR-01.09.AC01` whose `files` are both observable files of the diff;
- `write_plan_stub.py --ac-decision`, which wrote `ac-record.jsonl`, committed before the code;
- `record_event.py --type work_completed --source iterate --adr-id <run_id>`.

Then `check_pre_build_ac_recorded` (the F11 check itself) and `ac_decision.py verify`. The event was written by hand: that a campaign unit runner writes `source: iterate` and `adr_id` is not shown here (pilot start condition 1 checks it on the first unit).

| Case | Result |
|---|---|
| One squashed commit (what F11 sees for a unit) | **pass, zero warnings.** AC01 counts as named by a test that exists at the base (`named_in_base_tests`); no test was edited. That is a mention of the id, not proof that a test checks it, and the `kind` is the runner's own label (programme §2.1). |
| `ac_decision.py verify` | no problems |
| The record shows | `decided_by: code`, `confirmed: false`, `unconfirmed` count 0: an `unchanged` item is decided by code and is not an "assignment made without you" |

Three findings:
1. **The check skips silently without `adr_id`.** It finds the run's event by `adr_id == run_id`. An event recorded without it reports `skipped (no work_completed event)`, not a warning. A real iterate sets it at F5b. The pilot's STRICT-STOP therefore reads the AC record itself (programme §2.1), never this check's verdict.
2. **Bug in Q1's order check (advisory, false warning).** `ac_record._order_problem` reads `git log --name-only`, and the empty line after each commit hash counts as an observable file (`is_observable_path("")` is true). The first commit of the range therefore always counts as code. A branch whose AC record is not in its first commit gets "the AC record was committed after the first code commit" although it was committed before. Reproduced on the unsquashed branch (record in commit 2, code in commit 3). On a squashed unit the check is vacuous (record and code are the same commit), so record-before-code is only checked on the unsquashed branch. Fix: skip empty lines; fixed by its own iterate before the pilot.
3. `ac-mode.json` is written by `ac_decision.py` before the stub, so a runner that commits it on its own also hits finding 2.

### 7.2 L3 tool (programme §2.5)

**`claude plugin eval <path>`** loads a plugin from a path. Its documented case options do not fit the scenarios:
- the case `env` accepts `EVAL_*` keys only;
- there is no stub directory on `PATH` and no scrubbing of inherited variables;
- the network is not blocked;
- Bash needs `--allow-tools`;
- no grader runs a script.

**The fallback works** (probe on Haiku, USD 0.003). From a scratch git repository:

```
PATH=<stub dir>:$PATH env -u <keys> claude -p --model <m> --setting-sources project --plugin-dir <worktree>/plugins/shipwright-changelog --output-format stream-json --verbose
```

- The init event lists only that plugin, from the worktree path, plus built-ins. The installed Shipwright plugins are not loaded.
- `SHIPWRIGHT_PLUGIN_ROOT` is the worktree path.
- `gh --version` printed the stub's output.

**Warning from the first probe.** Without `--setting-sources project`, the child loaded the operator's settings, installed plugins and hooks, and went beyond the question. To satisfy a Stop hook that could not find `../../shared` from a copied plugin, it created a directory junction in the scratch folder. L3 runs therefore always pass `--setting-sources project`, a permission mode the operator chooses, and the plugin from a full checkout (the plugin reaches `shared/` as `../../shared`).

### 7.3 Prose pins and AC tests, re-measured on `origin/main` @ `f42a28f5d`

Same method as §2: five roots, then again with `SKILL.md` and the seven references replaced by a placeholder. Baseline all green.

**Broken: 30 tests in 13 files fail** (§2: 24 tests in 11 files). All 24 earlier pins still fail. Six are new, from the events-drop-files units:
- `shared/tests/test_events_drop_hardening.py`, 4 tests. They run the Step 7 snippet in projects without the bullet docs and check that the skill never names `architecture.md` or `conventions.md` unconditionally. These are behaviour through prose, the same kind as `test_skill_event_blocks_behaviour.py`.
- `plugins/shipwright-changelog/tests/test_skill_upgrade_notes_check.py`, 2 tests. Step 4 runs the upgrade-notes check before any aggregator call.

The events flip may add more. The pilot's P0 measures again on the tree it starts from (pilot start condition 8).

**AC tests:** the test files that name each FR-01.09 AC (fixtures `test_baseline_*` excluded) are unchanged in kind. AC15 is still unnamed, and AC11 is still named only by the aggregator test.

**Timing:** `shared/tests` took 1,802 s serial in this run, against 1,393 s on 2026-11-07, while other sessions were running on the machine. As in §3, this is not what an iterate pays.

## 8. Re-measured on `origin/main` @ `aec0284d8` (2026-11-14, after the events flip #1033 and the events-folder move #1054)

#1054 changed the changelog `SKILL.md` and `references/event-fold.md`, so the 2026-11-09 values were stale (pilot start condition 8). Same method as §2 and §7.3, in a throwaway worktree on `origin/main`; no file on `main` was changed.

| Measure | 2026-11-09 | 2026-11-14 |
|---|---|---|
| `changelog/SKILL.md` lines | 443 | **440** (the bloat entry still says `current: 443`, limit 400, exception, ADR-348; the baseline is refreshed last, programme P12) |
| FR-01.09 ACs with a deterministic test | 13 of 15 | **13 of 15**: AC01-AC10 and AC12-AC14 have a `covers` mark on a test; AC11 only the aggregator test (`oracle: trace`); AC15 none |
| Prose pins (tests that fail with the prose replaced) | 30 tests in 13 files | **30 tests in 13 files**, the same set |

**Pin list.** Method: the five roots (`integration-tests`, `shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`, `plugins/shipwright-changelog/tests`), one pytest process each, with `SKILL.md` and every reference except `release-notes-prompt.md` replaced by a placeholder. Only this broken pass was run on this tree; the 2026-11-09 baseline was all green, and every failing name is a changelog-prose test from that list.

| Root | Failed | Files |
|---|---|---|
| `plugins/shipwright-changelog/tests` | 18 | `test_skill_event_blocks_behaviour.py` (7), `test_skill_release_flag_wiring.py` (4), `test_skill_event_ships_in_release_pr.py` (3), `test_skill_upgrade_notes_check.py` (2), `test_changelog_judgement_drift.py` (1), `test_setup_changelog_version_suggestion.py` (1) |
| `shared/tests` | 10 | `test_events_drop_hardening.py` (4), `test_release_pathspec_doc_sync.py` (3), `test_canon_marker_write_contract.py`, `test_events_reference_guard.py`, `test_phase_gate_discipline_present.py` (1 each) |
| `integration-tests` | 2 | `test_multi_session_removal_residue.py`, `test_phase_skill_invocation_mode_canon.py` |
| `shared/scripts/tests`, `shared/scripts/tools/tests` | 0 | (704 and 1,502 passed) |

The pin set is unchanged since 2026-11-09 (the flip #1033 and the folder move #1054 are among the merges since). P0 still measures once more on its own starting tree.

**Timing.** The five roots ran in parallel on a busy machine: `shared/tests` 1,859 s, `integration-tests` 513 s, `shared/scripts/tools/tests` 241 s, the rest under a minute. Not what an iterate pays (as in §3).

**Overlap check (pilot start condition 4), 2026-11-14.** No open unit names a file in the pilot's touch sets:
- Events follow-ups U1-U3 (#1042, #1046, #1047) are merged; U2 had touched `condense_release_notes.py`.
- The e2e-run-findings units E1-E6 are merged (#941, #943-#948, #950, #951). Campaign B units B0-B4 are not in the pilot's touch sets, and B5 is merged (#926).
- Campaign U (`needs_input`, gate-pending result, preflight, harness) has not started. Its units name run-plugin status readers, `result_contract.py`, preflight, design `SKILL.md` and fixtures; none names the changelog plugin, `shared/testkit/`, the release tools under `shared/scripts/tools/`, `ci.yml`, `verify_local.py`, the hooks doc or the bloat baseline.
- Branches that touch changelog files (`iterate/e6-judgement-drift-tests`, `iterate/changelog-event-ships-in-pr`, `iterate/events-under-shipwright-dir`, `iterate/release-event-before-merge`, `iterate/dfp-f11-dryrun-throwaway`) are merged, closed or throwaway. The only open PRs are two Dependabot bumps of `ci.yml` (#1020, #1021).
- atomic-frs: FR-01.09 and FR-01.01 are not splittable (checked 2026-11-11).
