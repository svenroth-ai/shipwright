# Iterate Spec: f0-parallel-suite

- **Run ID:** iterate-2026-07-14-f0-parallel-suite
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

Make the F0 Fresh Verification Gate fast without making it weaker. Today F0 has
no runner at all — `F0.md` carries web-profile prose (`npx vitest`), so the agent
improvises the command each run and executes the repo's **18 independent pytest
units serially** (~589s / ~9.8 min measured). Introduce a canonical, config-driven
F0 suite runner that executes those units as parallel processes, with `pytest-xdist`
as a **per-unit opt-in** (never global), and a serial re-verify safety net that makes
the gate's verdict provably identical to today's.

## Acceptance Criteria

- [ ] **AC1 — Canonical runner.** A shared runner (`shared/scripts/tools/run_test_suite.py`)
      executes the project's test units and is the command `F0.md` points at. Exit
      code is non-zero iff at least one unit is red under the authoritative verdict
      (AC5) or any unit hit an infrastructure fault (AC11).
- [ ] **AC2 — Units are discovered, never hardcoded.** Selection mirrors `ci.yml`:
      every `plugins/*/` with both `pyproject.toml` and `tests/`, plus `shared/tests`,
      `shared/scripts/tests`, `shared/scripts/tools/tests`, plus `integration-tests/`.
      A newly added plugin is picked up automatically — a hardcoded list would silently
      stop testing it. A **parity guard** fails if `ci.yml` stops using this selection
      rule (CI stays serial, so the two selections must not drift apart).
- [ ] **AC3 — Identical test selection.** Shared dirs keep `-m "not slow and not
      cross_plugin"`; no unit gains or loses tests versus today.
- [ ] **AC4 — xdist is per-unit opt-in.** A `suite.xdist` allowlist in
      `shipwright_test_config.json` names the units allowed to fan out internally
      (here: `shared/tests`, `integration-tests`). Every other unit runs as ONE
      process. **`shipwright-compliance` is deliberately absent** — it is not
      xdist-safe (measured: serial 966 green, `-n 8` → 5 failures in
      `test_test_evidence.py`, which pass 37/37 serially = shared-state races).
      A global `-n auto` is forbidden.
- [ ] **AC5 — Serial re-verify → no false STOP (and an HONEST guarantee).** A unit that
      reports a genuine pytest **test failure** in the parallel run is automatically
      re-run **serially, without xdist**; that serial result is the authoritative
      verdict. Red-in-parallel + green-serially does NOT fail the gate (it is a race,
      not a code regression) but emits a loud `RACE` warning naming the unit.
      **Scope of the guarantee (external review, GPT high):** this eliminates false
      STOPs. It does *not* by itself exclude a parallel-only **false GREEN** (a test
      that passes under xdist but would fail serially is never re-run). That gap is
      closed by AC10, and the docs must state F0 as an *accelerated pre-gate* with the
      serial CI run as the authoritative serial gate — no overclaiming.
- [ ] **AC6 — Unconfigured projects are untouched (no stack-profile coupling).** With
      no `suite` block the runner refuses with a clear, actionable message and F0 keeps
      the existing prose path (the project's own test command). The runner does NOT
      reverse-parse the stack profile — that coupling is rejected (external review,
      Gemini/GPT). Zero behavior change for every adopted project.
- [ ] **AC7 — Strict config validation BEFORE any subprocess starts.** `suite` is an
      object; `max_workers` a positive int; `xdist` an object mapping a **discovered**
      unit id → positive int; `_comment` is tolerated; an unknown unit id is a **hard
      error** (a typo would otherwise silently disable the speedup); a non-dict /
      unreadable config is reported, never swallowed.
- [ ] **AC8 — Docs follow the code (Test-Update-Klausel).** `references/F0.md` and
      `docs/hooks-and-pipeline.md` state the runner, the allowlist rule, the serial
      re-verify semantics, and the honest pre-gate framing from AC5/AC10.
- [ ] **AC9 — Measured win (benchmark, not a timing assertion).** F0 wall-clock on this
      repo drops from the ~9.8 min serial baseline to ≤ 2.5 min **on the benchmark
      machine (24 cores)**, with the pass/fail set unchanged. Recorded as evidence;
      never asserted in a unit test (that would be flaky on other hardware).
- [ ] **AC10 — CI stays serial and is the authoritative serial gate.**
      `.github/workflows/ci.yml` is NOT touched. CI remains the independent serial
      cross-check that would catch a parallel-only false green (AC5).
- [ ] **AC11 — No CPU oversubscription; a fault is classified, never guessed.** The outer
      process pool and the inner xdist workers draw from **one** CPU budget (an xdist unit
      costs its worker count, a plain unit costs 1), clamped to ≥ 1. A hang is capped by
      `suite.timeout_seconds` and becomes a fault, not a silent infinite block.
      **"Did pytest run?" is PROVEN by a JUnit report file, not sniffed from output**
      (doubt review D1: `uv run` also exits 1 on its own faults, and pytest pluralises
      `error`→`errors`, so a fixture-level race — the exact thing AC5 exists for — would
      be misread as a fault and skip the re-verify = a **false STOP**). An infra fault is
      retried **once with the identical command shape (xdist still on)**: a deterministic
      fault (rc `5`, usage error, unprovisionable xdist) reproduces and still fails —
      nothing is laundered — while a transient one (uv-cache contention, which 18
      concurrent processes *create*) recovers instead of false-STOPping the gate (D2).
      **The infra retry must never strip xdist.**
- [ ] **AC12 — xdist is provisioned, not assumed.** The runner provisions its own test
      deps exactly like CI does (`uv run --with pytest --with pytest-mock [--with
      pytest-xdist]`); if xdist is unavailable for an allowlisted unit it fails with an
      actionable message instead of a cryptic `-n` error.
- [ ] **AC13 — Readable output, no interleaving, no shell.** Per-unit output is
      captured and printed only for failing units, plus a summary table (parallel
      subprocesses would otherwise garble stack traces). Units are invoked as argv
      arrays with `shell=False`; unit ids are validated against the discovered set.
      Each unit gets an isolated `TMPDIR` + `-p no:cacheprovider` so units cannot
      collide through shared caches/temp state; the working tree is clean after a run.

## Spec Impact

- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.11 (`/shipwright-iterate`) — the finalization verification gate
  gains a declared, config-driven execution model (parallel units + per-unit xdist
  opt-in + serial re-verify) in place of an improvised serial command.
- **REMOVE:** none
- **NONE justification:** n/a

## Out of Scope

- Finalization bundling (F1–F5c round-trip reduction) — separate iterate.
- Hook fan-out de-duplication (12× duplicate hook registrations) — separate iterate.
- Speeding up CI (explicitly declined: CI stays serial as the independent cross-check).
- Fixing the `shipwright-compliance` xdist races (it simply stays off the allowlist).

## Design Notes

No UI. Chosen shape: **discovery + declarative overrides**.

- Units are *discovered* (AC2); the config only carries *overrides* (the xdist
  allowlist + optional worker count). Rejected alternative: enumerate all 18 units in
  the config — a new plugin would then be silently untested (drift), the exact failure
  class the registry-SSoT rule exists to prevent.
- Rejected alternative: global `pytest-xdist -n auto`. Measured to break
  `shipwright-compliance` (5 race failures). Speed at the cost of a false red is the
  regression we are explicitly avoiding.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shipwright_test_config.json` (repo-maintained, hand-edited) | `shared/scripts/tools/run_test_suite.py` (`load_suite_config`) | JSON |
| stack profile `python-plugin-monorepo.json` `testing.command` | same runner (fallback path, AC6) | JSON |

`touches_io_boundary` fires (`*_config.json`) → Boundary Probe + round-trip test are
mandatory, covered by AC7.

## Confidence Calibration

- **Boundaries touched:** `shipwright_test_config.json` → `test_suite_units.load_suite_config`
  (new `suite` block). The stack-profile boundary was **removed** from the design
  (external review R5/R8) — the runner parses no foreign config.

- **Empirical probes run** (measured on this machine, 24 cores, 2026-07-14):
  1. **Serial baseline:** 18 units run one after another = **589s** (sum), which matches
     the 8.7 min `test` node in the `phase_timings` telemetry.
  2. **`shared/tests` xdist equivalence:** serial 297s vs `-n 8` 79s → **identical**
     result set (3943 passed, 11 skipped, same 1 pre-existing failure). Parallelism did
     not change a single verdict.
  3. **`integration-tests` xdist equivalence:** 83s → 18s, 184 passed both ways.
  4. **Counter-probe (the reason for the allowlist):** `shipwright-compliance` under
     `-n 8` produced **5 failures** in `test_test_evidence.py`; the same 5 pass **37/37
     serially** → shared-state races. It is therefore NOT allowlisted. A global
     `-n auto` would have shipped a false red.
  5. **Real end-to-end run of the runner against this repo:** 18/18 units GREEN in
     **93s** (vs 589s serial) — a 6.3x speed-up with an unchanged pass/fail set.
  6. **Pre-existing tree leak, disproved as ours:** `plugins/shipwright-test/tests/
     fixtures/.shipwright/` also appears when that plugin's suite is run **alone and
     serially** → not caused by the runner. Filed as `trg-11196d99`, deliberately not
     fixed here (surgical-changes rule).

- **Test Completeness Ledger** — principle: testable ⇒ tested. 0 untested-testable.

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Units discovered like `ci.yml`; a NEW plugin is auto-included | tested | `test_discovers_plugins_shared_dirs_and_integration`, `test_a_new_plugin_is_picked_up_automatically` |
  | 2 | A dir lacking `pyproject.toml` or `tests/` is not a unit | tested | `test_plugin_without_pyproject_or_tests_is_not_a_unit` |
  | 3 | Shared dirs keep `-m "not slow and not cross_plugin"` (selection unchanged) | tested | `test_shared_dirs_keep_the_marker_expression` |
  | 4 | xdist ONLY for allowlisted units, and the dep is provisioned | tested | `test_xdist_only_when_allowlisted_and_dep_is_provisioned` |
  | 5 | Commands are argv, never a shell string (no injection surface) | tested | `test_command_is_argv_never_a_shell_string` |
  | 6 | Config boundary: missing file / missing block / unknown key / unknown unit / non-positive or non-int workers / bad JSON / valid round-trip | tested | `test_test_suite_units.py` (12 cases incl. an 8-case malformed matrix) |
  | 7 | Exit-code classes: 0 pass, 1+pytest-evidence = test failure, 1 without evidence (uv fault) = INFRA, 2/3/4/5/-9 = INFRA | tested | `test_exit_code_classes` (9 cases) |
  | 8 | CPU budget never below 1 | tested | `test_cpu_budget_is_never_below_one` |
  | 9 | One shared budget: no oversubscription, no deadlock, an over-heavy unit is clamped | tested | `test_budget_never_oversubscribes_and_never_deadlocks` |
  | 10 | xdist pre-flight fails loudly when unprovisionable; skipped when nothing allowlisted | tested | `test_unprovisionable_xdist_is_an_actionable_error`, `test_xdist_preflight_is_skipped_when_nothing_is_allowlisted` |
  | 11 | **RACE:** red in parallel + green serially → gate GREEN (no false STOP), re-verify ran WITHOUT xdist | tested | `test_red_in_parallel_but_green_serially_is_a_RACE_not_a_stop` |
  | 12 | Red in parallel AND serially → gate RED | tested | `test_red_in_parallel_and_red_serially_fails_the_gate` |
  | 13 | A **deterministic** infra fault (rc 2/3/4/5) reproduces on its retry and still fails the gate | tested | `test_a_reproducing_infra_fault_fails_the_gate` (4 cases) |
  | 14 | A **transient** infra fault recovers on retry — but is reported, not hidden | tested | `test_a_transient_infra_fault_recovers_but_is_reported` |
  | 15 | The infra retry **never strips xdist** (else a suite greens without ever running the fan-out its config demands) | tested | `test_an_infra_retry_never_strips_xdist` |
  | 16 | **"pytest ran" is proven by the JUnit report, not by prose** — the plural `12 errors` summary (what a fixture-level race emits) must classify as a TEST failure, and a uv fault with no report as INFRA | tested | `test_pytest_ran_is_proven_by_the_junit_report_not_by_prose` |
  | 17 | A hang becomes a fault instead of blocking F0 forever | tested | `test_a_hung_unit_becomes_a_FAULT_instead_of_blocking_forever` |
  | 18 | An unlaunchable unit (`uv` off PATH) is a fault, not a traceback that discards the other 17 results | tested | `test_an_unlaunchable_unit_becomes_a_FAULT_not_a_traceback` |
  | 19 | `_exec` isolates TMPDIR/TEMP/TMP + cwd per unit and never uses a shell | tested | `test_exec_isolates_tmpdir_and_cwd_and_never_uses_a_shell` |
  | 20 | Zero discovered units is a refusal, never a GREEN suite that ran nothing | tested | `test_zero_discovered_units_is_a_refusal_not_a_green_suite` |
  | 21 | All green → exit 0 | tested | `test_all_green_exits_zero` |
  | 22 | Operator-facing strings are ASCII (a cp1252 console must not crash the retry path) | tested | `test_operator_facing_strings_are_ascii_only` (source-level drift guard) |
  | 23 | CI/F0 selection parity **and CI stays SERIAL** (the only cross-check against a parallel-only false green — now a guard, not prose) | tested | `test_f0_ci_parity.py` (6 assertions incl. `test_ci_stays_SERIAL`) |
  | 24 | The real suite runs green and fast on this repo (AC9) | untestable | `requires-manual-visual-judgment` — a wall-clock assertion would be flaky on other hardware (external review R11). Measured instead: 18/18 GREEN in 90s vs 589s serial. |

  Counts: testable 23 · tested 23 · untestable 1 · **untested-testable 0**.
  Enumeration basis: 13 ACs → all covered (AC6 = row 6, AC9 = row 24, AC10 = row 23).

- **Confidence-pattern check:**
  - *Asymptote (depth):* the two ways this change could weaken the gate were both driven
    empirically, not asserted: a **false STOP** (probe 4 → the allowlist + rows 11/13/14)
    and a **false GREEN** (probe 2/3 → measured identical verdicts; and structurally
    bounded by keeping CI serial, AC10). The spec-reviewer found a third path into a
    false green (a uv fault laundered through the race branch) — now closed and pinned
    by row 14.
  - *Coverage (breadth):* every AC maps to a row; the config boundary is probed from both
    sides (producer = hand-edited JSON, consumer = the loader).
  - *Integration composition:* the `cross_component` flag does NOT fire — the diff touches
    no hook, no `hooks.json`, no phase validator, no campaign/event/merge machinery. The
    F11 verifier recomputes this from the diff; if it fires, an integration behavior must
    be added.
