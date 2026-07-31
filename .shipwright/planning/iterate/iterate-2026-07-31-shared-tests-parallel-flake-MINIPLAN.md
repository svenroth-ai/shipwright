# Mini-Plan: iterate-2026-07-31-shared-tests-parallel-flake

Spec: `iterate-2026-07-31-shared-tests-parallel-flake.md`. One production file,
one test file.

## Chosen approach — stop deferring a constant

**1. `shared/scripts/dev_server/__init__.py` (the fix).** Hoist
`Path(__file__).resolve().parent.parent` out of `_lazy_resolve_executable` to module
scope as `_SCRIPTS_DIR`. It is a constant of the file, so deferring it bought
nothing; and `pathlib` picks its flavour from the process-global `os.name` at
construction, so evaluating it on the proxy's *first call* could land after a test
had faked the platform and raise `NotImplementedError`. Import time is before any
test body, so `os.name` is necessarily real there.

The `from lib.cmd_resolver import ...` stays exactly where it is. That is the part
ADR-045 needs deferred; only the path arithmetic moves.

**2. `shared/tests/test_dev_server_windows_npm.py` (the pin).** Rebind
`dev_server.resolve_executable` to `_lazy_resolve_executable` before the existing
`os.name` fake, so the test takes the previously-broken unprimed path on every run
rather than inheriting a primer from whatever ran earlier in that worker. One line
plus its comment; no priming call, because with (1) the unprimed path is safe and
taking it is the whole point.

## Alternative considered — fix it in the test alone

Prime the proxy inside the test (call it once under the real `os.name`) and leave
production untouched. Built and verified first: green 3/3 on the `-n 8` shape that
was red 3/3.

**Why not chosen:** it makes one test tolerate the wart instead of removing it. Any
future test that fakes `os.name` before the proxy's first call reacquires the same
failure, and the next person debugging it starts from zero. The hoist costs three
lines, fixes the class, and — measured — makes the test-side priming unnecessary.

Recorded because the first version of this spec wrongly claimed the hoist *could
not* work; see the correction section in the spec.

## Verification

| AC | How | Result |
|---|---|---|
| AC1 | the file alone, fresh process, serial — was RED | **GREEN**, 4 passed |
| AC2 | `shared/tests` alone with `-n 8`, 3 runs — was RED 3/3 | **GREEN 3/3 on the final tree** (6551 passed, 12 skipped, ~90s each) |
| AC3 | re-inject the bare `Path()`, run in the context that used to mask it | **RED**, original `NotImplementedError`, 2 failed — then restored, green |
| AC4 | `git diff` — assertion untouched, `suite.xdist` untouched | **confirmed**; `"shared/tests": 8` still in `shipwright_test_config.json` |
| AC5 | `_SCRIPTS_DIR` == the replaced expression; `lib.cmd_resolver` absent from `sys.modules` after `import dev_server`; binding still the proxy | **confirmed** — equality asserted, and now a permanent test (`test_importing_dev_server_leaves_lib_cmd_resolver_unbound`) rather than a probe |
| AC6 | full F0 suite, all units parallel, no new `f0-race:shared/tests` card | F0 |
| AC7 | the pin fires on `ubuntu-latest`, not only the Windows F0 host | **covered** by faking the *foreign* `os.name`: `pathlib` raises for whichever flavour is not the real one, so the pin bites on both |

Serial `ci.yml` shape (the authoritative gate; xdist is the accelerated pre-gate):
**6552 passed, 12 skipped, rc 0**.

Lint (`uvx ruff@0.15.15`, the gating pin): clean on both files. LOC 215 / 230,
both inside the 300 budget; neither file is in `shipwright_bloat_baseline.json`.
