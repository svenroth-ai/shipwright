# Mini-Plan — iterate-2026-08-01-pin-python-311

Spec: `2026-08-01-pin-python-311.md`

## Chosen approach — pin on the argv, plus tracked version files

Two source files change, 15 version files are added, plus the guard and one doc.

1. **`shared/scripts/tools/run_test_suite.py`**
   - `build_command()` — insert `--python`, `3.11` into the `uv run` prefix.
   - `warm_up()` — same pin, so the one serial call populates the **shared uv
     cache** (interpreter download + wheels) that all 18 units then draw from.
     Unpinned it would warm the cache for a *different* interpreter and every
     unit would still cold-fetch 3.11 concurrently — re-creating the contention
     the warm-up exists to remove.
     *(Corrected after external review: an earlier draft said the warm-up
     "creates the environment the 18 units reuse". It cannot — it runs at
     `project_root`, so it warms only the ROOT venv, shared by the 4 root-cwd
     units; the 14 plugin units are separate uv projects and each still builds
     its own venv. What they genuinely share is the uv cache.)*
2. **`shared/scripts/tools/suite_units.py`**
   - `ensure_xdist_available()` — same pin. It answers "can xdist be provisioned
     here"; if it answers for 3.11 while units run 3.13 (or the reverse) the
     pre-flight is checking a different environment than the one it clears.
3. **`.python-version`** (new) — `3.11`, at the repo root **and** in each of the
   14 plugin directories (see the resolved scope question below).
4. **`shared/scripts/tools/tests/test_f0_ci_parity.py`** — the AC5/AC6 guards
   (workflow agreement, version-file agreement, per-plugin presence).
   `test_run_test_suite.py` owns the argv half of AC5, because argv assertions
   belong with the module that builds the argv; both files are the same F0 unit.
5. **`plugins/shipwright-iterate/skills/iterate/references/F0.md`** — records the
   interpreter invariant beside the parity invariants it already documents
   (Test-Update-Klausel: test-infrastructure rules change in the same diff).

The pin is defined **once** as `suite_units.UV_RUN`, the prefix all three `uv
run` sites spread — so it cannot be present at two sites and forgotten at the
third. The parity test asserts its version equals what every workflow installs
and what every tracked `.python-version` holds: one interpreter fact, one owner.

## Why the argv and not the environment

`_exec()` already builds a per-unit `env`, so `env["UV_PYTHON"] = "3.11"` would
pin every invocation with a one-line change and no argv edit. Rejected:
`UnitResult.retry_cmd` renders the argv as the operator's "reproduce me"
command, and an env-only pin is **invisible** in that string — the card would
print a command that resolves a different interpreter than the run it claims to
reproduce. This repo has already been bitten by a plausible-but-wrong reproduce
command (`run_test_suite.py` docstring; the 2026-07-27 F0-race learning). The
argv is the honest surface.

## Alternative considered — `requires-python = "==3.11.*"`

Pin the floor-and-ceiling in all 15 `pyproject.toml` files and let uv resolve
3.11 naturally, needing no runner change at all.

**Rejected: it states something false.** The code runs fine on 3.12 and 3.13;
we want to *test* on the version CI judges with. Declaring the packages
incompatible with 3.12+ would misinform anyone installing them and would fight
the `>=3.11` the repo deliberately declares. Testing policy does not belong in
package metadata.

## Scope question → RESOLVED at the approval gate

A root `.python-version` does not reach plugin subdirectories (measured). So
`cd plugins/shipwright-build && uv run pytest tests/ -v` — the per-plugin
command **CLAUDE.md documents** — would keep resolving 3.12/3.13 after the F0
fix. F0 and CI are both correct; only the hand-run path drifts.

**Operator decision 2026-08-01: close it** — add a `.python-version` to each of
the 14 plugin directories (AC4), guarded so the 15 files cannot disagree (AC6).
The duplication is accepted because the alternative leaves a documented command
that can green-light code CI rejects.

## Risks

| Risk | Handling |
|---|---|
| Pinning forces a venv re-resolve mid-F0, read as an infra fault | Measured: uv removes and rebuilds the mismatched venv itself, 1.40s, exit 0. The junit-report-exists heuristic is untouched. |
| 3.11 absent on a contributor machine | uv auto-downloads managed interpreters by default; CI already runs `uv python install 3.11` explicitly. |
| F0 slower on first run after the pin | One-off per tree: every unit rebuilds its env once. The serial `warm_up()` absorbs it for root-cwd units. |
| The pin rots silently later | AC5/AC6 guards assert argv pin ↔ every workflow's `uv python install` ↔ all 15 version files. Each direction verified by mutation, not assumed. |

## Out of scope

- Adding `.python-version` to `classify_complexity`'s `touches_build` pattern
  list. It is a real hole — the file this run introduces is a build-graph input
  that would raise no risk flag when edited — but it is a *classification*
  change in the IT-5 subsystem, not part of this defect. Filed as a follow-up.
- Anything under `suite_report.py` / junit (`trg-348386e4`), per the brief's
  sequencing constraint. This diff does not touch either.
