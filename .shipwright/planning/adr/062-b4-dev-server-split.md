# ADR 062 — Campaign B / B4: Split `dev_server.py` (997 LOC)

## Status
Accepted — 2026-05-26

## Context

`shared/scripts/dev_server.py` was 997 LOC, well over the 300-LOC source
budget enforced by the bloat baseline. It is the producer/consumer
boundary for every Shipwright skill's `browser-verify` and `test`
phase: every plugin invokes `uv run shared/scripts/dev_server.py
start --profile <X> --cwd <project>` to spawn dev servers, then
`uv run shared/scripts/dev_server.py stop` to tear them down. Five
skill `.md` files reference the absolute path
`shared/scripts/dev_server.py`.

The existing test suite (`shared/tests/test_dev_server*.py`,
79 tests pre-B4) heavily monkeypatches the **package-level**
namespace — `@patch("dev_server._kill_one")`,
`@patch("dev_server._is_port_in_use_for_host")`,
`monkeypatch.setattr("dev_server.subprocess.Popen", ...)`,
`monkeypatch.setattr(dev_server.os, "name", "nt")`. Any split that
breaks `dev_server.X` lookups breaks the test contract.

## Decision

Replace `shared/scripts/dev_server.py` with a 10-file package under
`shared/scripts/dev_server/`, organized along the file's natural seams:

| File                          | LOC | Responsibility                                |
|-------------------------------|----:|-----------------------------------------------|
| `__init__.py`                 | 187 | Re-exports public surface; lazy `resolve_executable` |
| `__main__.py`                 |  16 | `python -m shared.scripts.dev_server` entry   |
| `cli.py`                      |  94 | argparse + `--services-json` handling         |
| `health.py`                   | 124 | TCP port + HTTP readiness probes              |
| `spawn.py`                    | 179 | Process spawn / kill / rollback               |
| `profile_config.py`           | 272 | Profile loading + normalization + `_get_config` |
| `validation.py`               | 128 | Schema validation + topo sort                 |
| `state.py`                    |  86 | v1-read-compat + v2 atomic write IO           |
| `multiservice.py`             | 267 | `cmd_start` / `cmd_stop` / `cmd_status`       |
| `_proxies.py`                 |  68 | Internal package-surface dispatch stubs       |

Each submodule ≤ 300 LOC.

Keep `shared/scripts/dev_server.py` as a 29-LOC shim. Empirical
behaviour of CPython 3.13: when both a `.py` file and a same-named
directory containing `__init__.py` live on the same `sys.path` entry,
the package directory takes precedence. `import dev_server` always
resolves to the package; `uv run shared/scripts/dev_server.py`
executes the file directly as `__main__` (file path, not import path)
and forwards into the package via `from dev_server import main`.

Internal cross-module calls dispatch through the package surface via
`_proxies.py` (which does `sys.modules[__package__].X(...)`) so test
monkeypatches against `dev_server.X` propagate into submodule code
paths. This preserves the test contract without rewriting any of the
79 existing tests.

`resolve_executable` (from `shared/scripts/lib/cmd_resolver.py`) is
bound lazily on the package object. The `lib.cmd_resolver` import is
deferred to first call so pytest collection of unrelated plugins
never caches `lib` in `sys.modules` pointing at the SHARED scripts
copy (B3 lesson — see ADR-???-b3-phase-quality-split for the original
pollution incident).

## Consequences

- `shipwright_bloat_baseline.json` entry for
  `shared/scripts/dev_server.py` REMOVED in the same atomic commit
  per cleanup-invariant rule (b) — the path now exists at 29 LOC,
  well under the 300-LOC budget, and the bulk of the implementation
  lives in the new package directory.
- Two new parity tests guard the surface contract empirically:
  - `test_b4_split_public_surface_present` enumerates every name
    callers / tests / monkeypatches address on `dev_server` and
    asserts they remain reachable.
  - `test_b4_split_import_resolves_to_package_not_shim` asserts
    `dev_server.__file__` ends with `dev_server/__init__.py`, not the
    sibling shim path. If a future CPython change ever inverts file/
    package precedence, this test fails loudly.
- Future contributors MUST NOT add module-level
  `from lib.cmd_resolver import resolve_executable` (or any other
  `from lib.X import ...`) in any submodule pytest may collect during
  unrelated test runs. Defer such imports to call-site or bind them
  lazily on the package.
- The shim's `from dev_server import main` line silently relies on
  package-wins import precedence. If a future refactor moves the
  package directory or renames it, the shim must be updated to
  match — the parity test will catch the most common regression
  (shim shadowing the package on PYTHONPATH).

## Alternatives Rejected

**(a) Delete `dev_server.py` entirely and use only the package.**
External-review feedback recommended this as the safer option. Rejected
because it would break every `uv run shared/scripts/dev_server.py`
caller across at least 5 skills (`shipwright-build`,
`shipwright-test`, `shipwright-preview`, `shipwright-adopt`,
`shipwright-iterate`) plus any user adopting shipwright with pinned
paths in their CI. Migrating those callers to `python -m
shared.scripts.dev_server` is a separate, additive refactor outside B4's
scope. The empirical parity test makes the shim-coexists-with-package
risk explicit and guarded.

**(b) Move test monkeypatch targets to submodule paths.** Reviewer
Gemini suggested rewriting `@patch("dev_server._kill_one")` →
`@patch("shared.scripts.dev_server.spawn._kill_one")` across the
test suite. Rejected because the campaign cleanup-invariant requires
"All existing callers of the public API work unchanged — verified by
running the relevant test suite." The tests ARE part of the API
contract; rewriting them is structural change beyond a bloat split.

**(c) Combine the 6 functional modules into the 3 named in the
spec (`spawn / health / multiservice`).** Rejected because the
literal 3-file split would put `multiservice.py` at ~600 LOC, still
over the 300-LOC budget. The spec's named layout is illustrative;
the cleanup-invariant requires "Each new module is ≤ 300 LOC" which
necessitates the additional `profile_config`, `validation`, `state`,
`cli`, `_proxies` modules.

## External LLM Plan-Review Findings

Run via `shared/scripts/tools/external_review.py --mode iterate`
against OpenRouter (openai + gemini providers, 2026-05-26):

| Finding                                          | Severity | Disposition                                                                                                  |
|--------------------------------------------------|----------|--------------------------------------------------------------------------------------------------------------|
| Plan adds modules beyond spec's named layout     | high     | accepted-and-fixed (this ADR documents the rationale; 3 modules would violate the 300-LOC cleanup-invariant) |
| File+package name collision risk                 | high     | accepted-and-fixed (empirical parity test added; alternative-(a) rejected with reason above)                  |
| Proxy pattern is non-trivial behavioral change   | high     | accepted-with-mitigation (`_proxies.py` is small, well-documented, and only routes — no semantic change)      |
| Multiservice smoke flow not explicitly listed    | medium   | accepted-and-fixed (existing `test_dev_server_multiservice.py` IS the multiservice suite, 58 tests passing)  |
| Empirical surface-runner + boundary probes needed | medium   | accepted-and-fixed (F0.5 ran with tests_run=80; surface_verification.json written under `.shipwright/runs/`) |
| Re-export curation risks accidental widening     | medium   | accepted-and-fixed (`test_b4_split_public_surface_present` asserts the curated list empirically)             |
| Lazy resolve_executable changes import semantics | medium   | accepted-and-fixed (lazy proxy caches the real fn on first call; `test_start_one_resolves_npm_on_windows` passes against it) |
| Shim direct-execution beyond --help / stop       | medium   | accepted-and-fixed (`uv run shared/scripts/dev_server.py stop` returns JSON identical to pre-split shape)    |
| State-file v1 compat probe missing               | medium   | rejected-with-reason (already covered by 3 pre-existing tests: `test_state_v1_read_compat`, `test_state_v1_not_rewritten_on_read`, `test_state_v2_round_trip`) |
| Behavioral refactoring smell in cleanup iterate  | medium   | accepted-with-mitigation (zero semantic changes; pre-split logic moved verbatim, proxy routing is the only addition) |
| Env-expansion not verified                       | low      | rejected-with-reason (covered by `test_dev_server_port_placeholder.py`, 5 tests passing)                     |
| Baseline producer/consumer not exercised         | low      | accepted-and-fixed (pre-commit hook runs on commit; baseline-removal pre-validated by re-reading the file)   |
