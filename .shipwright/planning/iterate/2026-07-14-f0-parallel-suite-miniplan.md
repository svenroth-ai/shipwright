# Mini-Plan: f0-parallel-suite

- **Run ID:** iterate-2026-07-14-f0-parallel-suite
- **Spec:** `.shipwright/planning/iterate/2026-07-14-f0-parallel-suite.md`

## Problem

F0 (Fresh Verification Gate) has **no runner**. `references/F0.md` shows web-profile
prose (`npx vitest run`, `npx tsc --noEmit`) that does not even apply to this Python
monorepo, so the agent improvises the command every run and executes the repo's 18
independent pytest units **serially**.

Measured 2026-07-14 (this machine, 24 cores):

| | serial (today) | parallel | note |
|---|---|---|---|
| 18 units, sum | **589s (9.8 min)** | 324s wall (pool 8) | floor = `shared/tests` |
| `shared/tests` (3943 tests, 1 proc) | 297s | **79s** (`xdist -n 8`) | identical results |
| `integration-tests` | 83s | **18s** (`xdist -n 8`) | identical results |
| `shipwright-compliance` | 62s green (966) | **5 FAILURES** (`-n 8`) | **races** — pass 37/37 serially |

## Approach (chosen): discovery + declarative overrides

1. **`shared/scripts/tools/run_test_suite.py`** (new, < 300 LOC).
   - **Discovers** units exactly like `ci.yml` does: `plugins/*/` having both
     `pyproject.toml` and `tests/`, plus `shared/tests`, `shared/scripts/tests`,
     `shared/scripts/tools/tests`, plus `integration-tests/`.
   - Runs units as **parallel processes** (pool = `min(8, cpu_count-2)`).
   - Applies `pytest-xdist -n <k>` **only** to units named in the config allowlist.
   - Preserves today's selection: shared dirs get `-m "not slow and not cross_plugin"`.
2. **Config** — new `suite` block in `shipwright_test_config.json`:
   ```json
   "suite": {
     "max_workers": 8,
     "xdist": { "shared/tests": 8, "integration-tests": 8 },
     "_comment": "xdist is per-unit OPT-IN. shipwright-compliance is deliberately
                  ABSENT: it is not xdist-safe (shared-state races in
                  test_test_evidence.py). Never use a global -n auto."
   }
   ```
   No `suite` block → the runner refuses with an actionable message and F0 keeps its
   existing prose path. **No stack-profile parsing** (see review R5/R8).
3. **Serial re-verify safety net (the anti-regression core).**
   A unit that reports a genuine pytest **test failure** (exit code 1) in the parallel
   run is re-run **serially, without xdist**; that serial result is the authoritative
   verdict.
   - serial red → F0 fails (exactly like today, same output).
   - serial green → **RACE warning**, gate does NOT fail (a race must never produce a
     false STOP).
   - exit codes 2/3/4 (infra fault) and 5 (no tests collected) → **always fail**; they
     are never eligible for the race path (review R7).

## External Review — findings & dispositions (GPT + Gemini, OpenRouter, Branch A)

Both reviewers returned. Every finding is dispositioned; none dropped.

| # | Reviewer / sev | Finding | Disposition |
|---|---|---|---|
| R1 | GPT **high** | **Overclaim:** serial re-verify only re-runs RED units, so a parallel-only **false GREEN** (passes under xdist, would fail serially) is never caught. "Verdict provably identical to serial" is false. | **ACCEPTED — plan corrected.** AC5 now guarantees only *no false STOP*. F0 is documented as an **accelerated pre-gate**; the serial CI run is the authoritative serial gate (AC10). This is exactly why CI stays serial. |
| R2 | GPT high / Gemini med | `pytest-xdist` is not a declared dependency — the measurement provisioned it ad-hoc. A clean env would hard-fail on `-n`. | **ACCEPTED** — AC12: runner provisions deps like CI (`uv run --with …`), actionable error if unavailable. |
| R3 | Gemini high | Parallel subprocesses garble stdout/stderr — stack traces become unreadable. | **ACCEPTED** — AC13: capture per unit, print only failures + summary table. |
| R4 | Gemini med / GPT med | **CPU oversubscription:** outer pool 8 × inner xdist 8 → 16+ CPU-bound workers; thrashes on small machines; `cpu_count-2` can be ≤ 0. | **ACCEPTED** — AC11: one shared CPU budget (xdist unit costs its worker count), clamped ≥ 1. |
| R5 | Gemini low / GPT med | Fallback via stack-profile `testing.command` = brittle coupling to a foreign config boundary. | **ACCEPTED — simplified.** AC6: no stack-profile parsing at all; unconfigured projects keep the existing prose path. Less code, no coupling. |
| R6 | GPT med | Config schema underspecified (worker counts, unknown keys, `_comment`, path normalization). | **ACCEPTED** — AC7: strict validation before any subprocess starts. |
| R7 | GPT med | Subprocess/interruption semantics: an infra fault (OOM, spawn failure, no-tests-collected) must not be laundered into a `RACE` green. | **ACCEPTED** — AC11: pytest exit-code classes; only rc=1 is race-eligible. |
| R8 | GPT med | CI/F0 **parity drift**: runner duplicates CI's discovery while CI is left unchanged. | **ACCEPTED** — AC2: parity guard test + cross-reference comments in both files. |
| R9 | GPT med / Gemini med | **Inter-unit** state pollution (shared caches/tmp/artifacts) — distinct from the known intra-unit compliance race. | **ACCEPTED** — AC13: isolated `TMPDIR` per unit + `-p no:cacheprovider`; empirical probe asserts a clean tree after a full run. |
| R10 | GPT low | Command injection via hand-edited config / path names if commands are built as strings. | **ACCEPTED** — AC13: argv arrays, `shell=False`, ids validated against the discovered set. |
| R11 | GPT low | AC9's absolute ≤2.5 min target is machine-dependent and would make tests flaky. | **ACCEPTED** — AC9: benchmark evidence bound to the 24-core benchmark machine; never asserted in a unit test. |

## Stage-1 `spec-reviewer` — REJECT, then fixed (all three were real)

The hard-gate reviewer rejected the first implementation. All three findings attacked
the same weak spot: **rc 1 is ambiguous** (`uv run` returns it both for a test failure
*and* for its own faults), and the race branch trusted it.

| # | Finding | Fix |
|---|---|---|
| S1 | **AC12 hole.** If `uv` cannot provision `pytest-xdist`, `uv run` exits 1 → classified as a test failure → re-run serially **without xdist** → passes → reported as a green `RACE`. The unit never ran the way the config demands, and the gate goes GREEN. | New `ensure_xdist_available()` pre-flight (in `test_suite_units.py`) runs BEFORE any unit whenever `suite.xdist` is non-empty and raises an actionable `SuiteConfigError`. Pinned by `test_unprovisionable_xdist_is_an_actionable_error`. |
| S2 | **AC11 unfaithful.** `classify()` was documented against *pytest* exit codes but actually receives *uv's*. Any uv-level fault (resolution, interpreter, env build) is rc 1 and was therefore race-eligible → an infrastructure fault could be laundered into a green. | `classify(rc, output)` now only accepts rc 1 as a TEST failure when pytest **demonstrably ran** (`_PYTEST_RAN` summary regex). No evidence → `INFRA` → always fails, never re-verified. Pinned by `test_a_uv_provisioning_fault_is_a_FAULT_not_a_race`. |
| S3 | **Encoding — the ironic one.** The `RACE` note/warning and every `SuiteConfigError` message contained em-dashes. On a cp1252 console `print()` raises `UnicodeEncodeError` → traceback → non-zero exit, so **a RACE would abort the gate** — precisely the false STOP the race path exists to prevent (regression class of #244). | Every operator-facing string in both modules is ASCII. Source-level drift guard `test_operator_facing_strings_are_ascii_only` makes the class unrepeatable. |

Consequence: the fixes pushed the runner past the 300-line limit, so discovery + the
config boundary were extracted into `test_suite_units.py` (135 lines) and re-exported
from `run_test_suite.py` (228 lines) — one import site, both modules inside budget.

Self-review additionally found `_Budget` was **testable but untested** (the ledger
forbids "could-test-but-didn't") → `test_budget_never_oversubscribes_and_never_deadlocks`.

## Stage-2 `code-reviewer` — 12 findings, all fixed

Concurrency core cleared (`_Budget`: no deadlock, no lost wakeup, no oversubscription;
result mutation is post-pool, single-threaded). The findings were about the edges — five
of them in the "gate silently weaker" class:

- **Zero discovered units exited 0 GREEN** (a suite that ran nothing) → hard refusal.
- **The temp dir was cleaned before the verdict was computed** → a Windows file-handle
  leak could turn a GREEN suite into a traceback (a false STOP) → `ignore_cleanup_errors`.
- **The serial re-verify reused the DIRTY temp dir of the failed parallel run** — the
  authoritative verdict was not a clean room → separate `p/`+`s/` roots.
- **No timeout** → a hung unit blocks F0 forever with zero output → `suite.timeout_seconds`.
- **An `OSError` (uv off PATH) escaped the pool** and discarded all other results → FAULT.
- **The CI-parity guard was substring-anywhere** and would have passed even if `ci.yml`
  deleted the loop (the dirs also appear in comments) → pin the executable lines.
- `_exec` itself was untested (TMPDIR/cwd/shell) → pinned.
- Plus: regex false-positive surface, pre-flight skipped on the explicit-config path, a
  dead `_used and` guard, and an over-broad re-export block.

## Stage-3 `doubt-reviewer` — it BROKE two of the three safety legs

The adversarial pass disproved the claim as stated. Both were real:

| # | Disproof | Fix |
|---|---|---|
| D1 **high** | **The classifier was blind to pytest's plural.** `_PYTEST_RAN` matched `error\b`, but pytest emits `errors` when count != 1. So `12 errors in 30.14s` (rc 1) → no match → INFRA → **the unit skipped the serial re-verify and hard-failed the gate**. And that summary shape is exactly what a fixture-level race produces (every test ERRORs at setup, zero passed/failed) — i.e. the one scenario the safety net exists for was the one it could not see. **A false STOP.** | Stop guessing from prose: every unit now writes a **JUnit report**, and its existence PROVES pytest ran. `classify(rc, pytest_ran)`. Pinned by `test_pytest_ran_is_proven_by_the_junit_report_not_by_prose`. |
| D2 **high** | **"An infra fault always fails" was a guarantee pointing the wrong way.** INFRA got zero retries — but 18 concurrent `uv` processes *create* transient infra faults that serial runs never had (hardlink races in the shared uv cache, spawn EAGAIN). The net covered the class the change makes rarer and refused the class it makes commoner → **false STOP on good code**. | An infra fault is retried **once with the identical command shape** (xdist still on). Deterministic faults (rc 5, usage error, unprovisionable xdist) reproduce and still fail — nothing laundered — transient ones recover. Plus an unconditional serial `warm_up()` so the cold-env creation cannot be raced by 18 processes. Pinned by three tests. |
| D3 med | **CI-stays-serial — the load-bearing leg — was unenforced.** A future PR adding `-n auto` to `ci.yml` would pass every guard in this repo while deleting the only cross-check against a parallel-only false green. | `test_ci_stays_SERIAL` now fails if `ci.yml` gains `-n`/`--numprocesses`/`pytest-xdist`. A convention became a guard. |
| D4 med | The "clean-room" claim was overstated: only TEMP is isolated, the **repo working tree is shared** and not reset, so a unit reddened by another unit's tree pollution reproduces on retry and stops the gate. | Claim corrected in the module docstring, `F0.md` and `hooks-and-pipeline.md` — stated as a known limit, not a guarantee. |
| D5 med | `ensure_xdist_available` was accidentally the ONLY serialization of cold uv env creation — and it is skipped when the allowlist is empty (which `F0.md` tells operators to do). | `warm_up()` runs unconditionally, independent of the allowlist. |
| D6 med | TMPDIR redirection cost ~58 chars of Windows MAX_PATH headroom (long slugged paths), a fragility only F0 would hit. | Short temp segments (`swf0-…/p/u3`), index-based instead of slugged. |

Not broken (attacked and cleared): `_Budget` (no deadlock/lost wakeup/starvation over a
finite unit set), and no silent-weakening path beyond the acknowledged parallel-only-pass
class that AC10 bounds.
4. **Docs (Test-Update-Klausel):** rewrite `references/F0.md` around the runner;
   update `docs/hooks-and-pipeline.md`.
5. **CI untouched** — stays serial, and is therefore an independent serial cross-check
   that would catch a hypothetical parallel-only *false green*. This is why we
   deliberately do NOT parallelize CI (user decision, 2026-07-14).

## Alternative considered (rejected)

- **Enumerate all 18 units in the config.** Rejected: a newly added plugin would be
  silently untested — the exact drift the registry-SSoT rule exists to prevent.
  Discovery has no such hole.
- **Global `pytest-xdist -n auto`.** Rejected: measured to produce 5 false failures in
  `shipwright-compliance`. Speed bought with a false red is the regression we are
  explicitly forbidden to introduce.
- **Also parallelize CI.** Rejected by the user: keeping CI serial preserves an
  independent cross-check.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Parallel run turns a serially-RED test green (false green → weaker gate) | Measured identical both ways for both allowlisted units; CI stays **serial** as the independent authority before merge |
| A race causes a false STOP | Serial re-verify (AC5): the serial verdict always wins |
| Typo in the xdist allowlist silently disables the speedup | Unknown unit name = hard error (AC7) + drift test |
| A new plugin is not tested by F0 | Discovery, not a hardcoded list (AC2) + test asserting parity with CI's selection rule |
| Config malformed | Round-trip/boundary probe (AC7) — `touches_io_boundary` fires |

## Test strategy (TDD)

- Unit: discovery (finds all plugins + 3 shared dirs + integration; a synthetic new
  plugin dir is picked up), xdist allowlist application, unknown-unit hard error,
  fallback when no `suite` block, exit-code logic.
- **Serial re-verify:** a fake unit that fails in parallel and passes serially → gate
  green + RACE warning; a fake unit red both ways → gate red.
- **Boundary probe / round-trip:** `shipwright_test_config.json` → runner
  (missing block, non-dict, unknown key, empty allowlist).
- Empirical: run the real runner against the real repo, compare the pass/fail set to
  today's serial run (AC9).
