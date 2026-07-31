# Iterate Spec: the dev-server proxy stops doing path work on a faked platform

- **Run ID:** iterate-2026-07-31-shared-tests-parallel-flake
- **Type:** bug · **Complexity:** medium
- **Risk flags:** none from `classify_complexity` (message stage). `cross_component`
  and `touches_ci_supplychain` are diff-driven and recomputed at F11 — confirmed
  below against `risk_detectors` once the diff existed.
- **Spec Impact: NONE.** Behaviour-preserving. `_SCRIPTS_DIR` resolves to a value
  measured byte-identical to the expression it replaces; only *when* and *how* it is
  computed moves. No FR behaviour changes, no public name changes.
- **Source:** F0 race card `trg-f64d1c27` (`f0-race:shared/tests`), raised on
  `iterate-2026-07-30-derived-gate-sees-the-pr`.

## The card, and what it actually was

> `shared/tests`: red in parallel (rc 1), GREEN alone (rc 0). It IS on the
> `suite.xdist` allowlist, so the fan-out inside the unit is a candidate cause:
> fix it, or drop it from `suite.xdist`.

The card offers two remedies and says only measurement can separate them. It is
neither of the two causes it names. It is **not** inter-unit pollution and **not**
an unreliable test. It is a **deterministic** production defect that the serial
running order had been hiding since the unit joined the xdist allowlist.

## Reproduction — the measurement the runner could not make

The F0 retry changes **two** variables at once: it re-runs the unit *alone* **and**
*without xdist*. A green retry therefore cannot say which one mattered. Splitting
them:

| Probe | Shape | Result |
|---|---|---|
| A | `shared/tests` **alone**, xdist **on** (`-n 8`), 3 runs | **RED 3/3** — same single test each time |
| B | that test's **file alone**, serial, no xdist | **RED, deterministic** |

Probe A removes every other unit and the failure stays — inter-unit pollution
falsified. Probe B removes xdist too and it *still* fails — "flaky" falsified.
What remains is an ordering dependency:

```
FAILED shared/tests/test_dev_server_windows_npm.py::test_start_one_does_not_resolve_on_unix
1 failed, 6548 passed, 12 skipped in 90.19s          # probe A, run 1 of 3
1 failed, 1 passed in 0.21s                          # probe B — the file by itself
```

## Root cause

`test_start_one_does_not_resolve_on_unix` fakes the platform with
`monkeypatch.setattr(dev_server.os, "name", "posix")`. `dev_server.os` **is** the
`os` module, so this mutates a process-global that `pathlib` reads. It then calls
`_start_one`, which reaches `dev_server.resolve_executable`.

That name is a **one-shot lazy proxy** (`dev_server/__init__.py`). Its first call in
a process — and only its first — ran:

```python
scripts_dir = _Path(__file__).resolve().parent.parent   # 3 platform-sensitive derivations
from lib.cmd_resolver import resolve_executable as _real # deferred on purpose (ADR-045)
```

`pathlib` picks its flavour from `os.name`, so under the fake that line builds the
foreign one:

```
NotImplementedError: cannot instantiate 'PosixPath' on your system
```

**Where exactly it raises is version-dependent**, which matters because the diff
originally documented one interpreter's answer as the answer:

| Python | What raises under a faked `os.name` |
|---|---|
| **3.11** (every CI workflow pins it) | **construction** — `Path.__new__` checks `_flavour.is_supported` |
| **3.12+** (what `uv run` picks here) | the first **derivation** — `.resolve()`, `.parent`, `/`, via `type(self)(...)`; construction slips past on `object.__new__` |

Measured on both (3.11.15 and 3.12.13). The old line did a construction *and*
three derivations, so it raised either way. The rule worth carrying is the plain
one — **no pathlib in that function** — not either version's mechanism.

This is also why `test_dev_server_multiservice.py`'s fakes are safe: they only
derive from `tmp_path`, whose `type(self)` is the host's NATIVE flavour, and it is
the foreign flavour that is unsupported.

The value being computed is a **constant of the module** — `__file__` cannot change
between import and first call — so deferring it bought nothing and cost exactly
this. The `lib.cmd_resolver` import is the part that must stay lazy (ADR-045),
though only narrowly: `import dev_server` **already** binds `sys.modules['lib']`,
because `state.py` does a module-scope `from lib.atomic_write import ...` and
`__init__.py` imports `.state` unconditionally. Deferring `lib.cmd_resolver`
keeps that one submodule out; it does not make the package lib-safe, and
`shared_lib_loader.py` says the general form outright — lazy import "was the
accepted mitigation, and it is not enough." Stage 2 caught this diff asserting
the wider, false version.

The test passed **iff something earlier in the same process had already burned the
proxy**, leaving it bound to a plain function that touches no `Path`. Measured:

```
1. fresh binding      : _lazy_resolve_executable
2. after one call     : resolve_executable
3. resolve under posix: 'npm' -> NO crash
```

Its sibling `test_start_one_resolves_npm_on_windows` does **not** prime it — it
monkeypatches `resolve_executable` outright and monkeypatch restores the proxy at
teardown. The primer is an unrelated test elsewhere in the 466-file unit.

**Why it looked intermittent.** Serially the unit runs in one process in a fixed
order and a primer always ran first — green. Under `-n 8`, pytest-xdist distributes
tests across eight worker processes by availability, so whether *this worker* had a
primer varies with machine timing. Whichever worker draws it unprimed goes red.
`#371` put `shared/tests` on the allowlist; the defect predates that (the proxy
arrived with the B4 package split, `fd6c5585`) and was invisible until then.

**Platform scope.** The original failure only ever fires on a **Windows** host,
where the real `os.name` is `"nt"` and the fake is `"posix"`. F0 runs on Windows;
`ci.yml` runs `ubuntu-latest`, which is why CI never saw it. That asymmetry is also
why the pins below fake the *foreign* flavour rather than a hard-coded one.

**The repo has paid for this class once already.**
`test_atomic_write_windows_retry.py` was written after F0 race card
`f0-race:shipwright-run` and carries the standing rule in its module docstring:

> **These tests patch `aw._is_windows`, NEVER `os.name`.** `os.name` is
> process-global and `pathlib.Path()` dispatches on it […]

### A correction the review cascade forced

An earlier version of this spec claimed the hoist below **could not** work, on the
strength of a probe showing the deferred import raising
`ModuleNotFoundError: No module named 'posix'` under the fake. **That was a probe
artifact and the claim was wrong.** The error comes from `shutil`'s module-level
`if os.name == 'posix': import posix`, which runs *only on a fresh import of
shutil*. The probe was a bare `python -c`; in any pytest process `shutil` is already
imported long before a test body runs (pytest imports it, and
`shared/tests/conftest.py:5` imports it directly for an autouse fixture), so the
deferred import has no such work left to do.

Stage 1 caught this; re-measured **inside pytest**, the hoist alone makes the test
pass. Recorded rather than quietly corrected, because the mistaken reasoning was the
sole stated basis for rejecting the production fix, and because the mistake is the
standing lesson of `feedback_gate_must_be_verified_in_its_own_environment`: a thing
measured outside its own environment measures something else.

## The fix

**Production (`shared/scripts/dev_server/__init__.py`) — the root cause.** Resolve
the constant once, at import, and derive it **without `pathlib`**:

```python
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
...
def _lazy_resolve_executable(name):
    if _SCRIPTS_DIR not in sys.path:                          # no path arithmetic
        sys.path.insert(0, _SCRIPTS_DIR)
    from lib.cmd_resolver import resolve_executable as _real  # still lazy: ADR-045
```

`os.path` is bound to `ntpath`/`posixpath` when `os` is first imported and never
re-dispatches, so this derivation is immune to `os.name` **at import time and
afterwards**. Import time alone would have been a narrower guarantee — it holds only
while nothing imports `dev_server` inside a faked-platform test body, which is true
today (every `import dev_server` is at module scope; there is no `importlib.reload`
in the repo) but is an unstated premise a future test could break. The `os.path`
derivation removes the premise instead of documenting it. Measured byte-identical to
the `pathlib` expression, and measured to survive both fakes where `pathlib` raises.

This fixes **the proxy**, permanently — no code that fakes `os.name` can detonate
it again, today or next year. It does **not** clear the whole package, and the
first draft of this spec claimed it did. Three other `Path(__file__)` derivations
remain: `state.py:20` and `profile_config.py:98` (both at module scope, so
`os.name` is real when they run) and `spawn.py:47`, a runtime fallback reachable
only when the package attribute is missing, which nothing does. All latent, none
live — carried in the follow-up below rather than fixed here.

**Tests (`shared/tests/test_dev_server_windows_npm.py`) — four pins.**

1. The repaired scenario test rebinds `resolve_executable` to
   `_lazy_resolve_executable`, so it takes the previously-broken **unprimed** path on
   every run in every worker instead of inheriting whatever ran before it.
2. `test_lazy_resolve_does_no_platform_sensitive_work_on_first_call` fakes the
   **foreign** `os.name` (`_foreign_os_name()`), so it bites on Windows *and* on
   Linux. `pathlib` raises for whichever flavour is not the real one, so a bare
   `Path()` returning to the lazy body fails on `ubuntu-latest` too — without this
   the pin would be inert on the only platform CI runs.
3. `test_importing_dev_server_leaves_lib_cmd_resolver_unbound` pins the deferral in
   a subprocess, so the obvious future "simplification" of collapsing the proxy
   fails here rather than silently in an unrelated plugin's test run. It asserts
   all three values — including that `lib` itself IS bound — so it states the
   narrow truth rather than the flattering one.
4. `test_scripts_dir_matches_the_pathlib_derivation_it_replaced` compares the new
   `os.path` derivation against the `pathlib` one it replaced. Added after Stage 2
   showed AC5 was pinned by nothing: `state.py` already puts `shared/scripts` on
   `sys.path`, so a bogus `_SCRIPTS_DIR` left every other test green.

**Both pins demonstrated to bite:** with the bare `Path()` re-injected into the lazy
body, tests 1 and 2 fail with the original `NotImplementedError`, in the same context
that used to mask it. Then restored and re-verified green.

The original assertion is untouched. Nothing is weakened, skipped, xfailed or
deleted, and `shared/tests` stays on the `suite.xdist` allowlist.

### What the external review changed

Both providers were run (`external_review.py`, OpenRouter). OpenAI answered on both
passes (`revise` on the mini-plan, `approve` on the diff); Gemini was truncated by
the provider on the plan pass and returned empty on the code pass, so it is
recorded `unavailable` — but the fragment that did arrive carried a real finding
and is credited here rather than lost with the truncation.

1. **Gemini, medium — a first import under the fake could cache the fake.** If any
   module reached under the platform fake evaluates the platform at module scope
   (`IS_WIN = os.name == 'nt'`), that wrong value is cached in `sys.modules` for the
   rest of the worker. Checked both modules on the path: `lib/cmd_resolver.py` has
   no module-level platform evaluation at all (only `import os`, `import shutil`;
   `resolve_executable` reads `os.name` per call), so it is safe. `shutil` is
   **not** — it caches `_WINDOWS = os.name == 'nt'` and imports `posix`/`nt` at
   module scope. That is exactly why the test file imports `shutil` explicitly, on
   the real platform, instead of relying on pytest having done so.
2. **OpenAI, medium — import-time is a narrower guarantee than it reads.** Importing
   `dev_server` *after* a fake would raise the same error; the hoist only moves
   when. Answered by deriving with `os.path` rather than `pathlib`, which removes
   the flavour dispatch entirely instead of relocating it.
3. **OpenAI, medium — the pin was inert on the only platform CI runs.** `ci.yml` is
   `ubuntu-latest`; a hard-coded `"posix"` fake does nothing there. Answered by
   `_foreign_os_name()`, so the pin fires on both hosts (AC7).
4. **OpenAI, medium — a hidden `shutil` prerequisite.** Same fix as Gemini's (1):
   declared by an explicit import rather than inherited from pytest.
5. **OpenAI, low — no new security exposure**; `sys.path` insertion and the deferred
   import keep their existing behaviour. Confirmed: same value, same index.

### What the adversarial pass changed

Stage 3 ran six attacks; five failed and are recorded as failed, which is the part
worth keeping — `residual-nondeterminism`, `pin-bites-on-linux`,
`test-order-pollution`, `os.path-vs-pathlib-equivalence` and `made-something-worse`
were each traced through the real code and did not reproduce. The sixth landed:

1. **medium — the shipped comment's mechanism was measured on the wrong
   interpreter.** "Constructing a `Path` is safe, only derivations raise" is true
   on 3.12 and **false on 3.11**, which every CI workflow pins. Nothing breaks
   today (the fix removes pathlib from that function outright, and both pins were
   re-verified to bite on 3.11), but the comment invited a maintainer to write
   `p = Path(__file__)` back into the lazy body and ship a 3.11-only failure —
   green locally, red on `ubuntu-latest`. That is the precise shape this iterate
   exists to remove, re-armed by its own explanation. Fixed: the comment now gives
   both versions and leads with the rule instead of the mechanism. **Third time in
   this run** that a claim was measured outside the environment that judges it.
2. **low — "fixes the class" was too broad.** Narrowed above, with the three
   surviving `Path(__file__)` sites named.
3. **low — the LOC figures were stale**, taken before the review rounds. Re-measured
   (probe 12) under the same rule the spec applies to its own test runs.
4. **low — the subprocess pin compared the child's whole stdout.** A printing
   `sitecustomize` or `.pth` would redden it with the code correct. Now compares the
   last three tokens.
5. **low — the deviation from the repo's `os.name` rule was undocumented.** That rule
   is *executable* (`test_atomic_write_windows_read_retry.py` scans source for it,
   scoped to the atomic-write files), and a third precedent skips on Linux instead.
   The new module docstring names all three and says why this file differs.

Also corrected from Stage 3's trace: the multiservice fakes are safe because
`tmp_path`'s type is the host's **native** flavour, not because `/` avoids
dispatch — the spec had the right conclusion for the wrong reason.

### Residual assumption, bounded and recorded

The pins deliberately run the **deferred import under the fake**. That is safe only
because `shutil` is already imported — so the test file imports it explicitly rather
than relying on pytest happening to have done so, which turns an incidental
prerequisite into a declared one. It is narrower still in practice: under xdist every
worker performs full collection, and `test_cmd_resolver.py` imports
`lib.cmd_resolver` at module scope, so it is a `sys.modules` cache hit before any
test body runs. Recorded as a known bound; `os.name` is never faked outside tests.

### Rejected alternatives

- **Drop `shared/tests` from `suite.xdist`** (the card's second option). Rejected:
  it re-hides a deterministic production bug. xdist did not cause this failure, it
  *revealed* it — probe B fails with no xdist at all. Removing the allowlist would
  restore the masking and cost the measured 297s → 79s speed-up for nothing.
- **Fix it in the test only**, by priming the proxy before faking `os.name`. Built
  and verified first (green 3/3 on the `-n 8` shape that was red 3/3), then
  discarded: it makes one test tolerate the wart instead of removing it, and any
  future test that fakes `os.name` reacquires the same failure.
- **Hoist with `pathlib`, kept at module scope.** The intermediate version, also
  verified green 3/3. Superseded because it only moves *when* the flavour dispatch
  happens; `os.path` removes the dispatch.
- **Import `lib.cmd_resolver` eagerly at module top.** Exactly what ADR-045 forbids:
  it binds `sys.modules['lib']` in the shared scripts path and shadows plugin-local
  `lib/` packages. The laziness of the *import* is load-bearing; only the path
  arithmetic moved — now pinned by test 3.
- **Add an `_is_windows()` predicate to `dev_server` and patch that**, per the
  standing rule. Cleanest in the abstract, but the no-op being asserted lives in
  `cmd_resolver`, which reads `os.name` itself; the predicate would have to be
  threaded through two production modules to serve one test. Disproportionate —
  recorded so it is not re-derived.
- **Patch `resolve_executable` to an identity function** (mirroring the sibling
  Windows test). Removes the fake entirely, but the test then proves only that
  `_start_one` passes the resolver's result through, and stops exercising the real
  posix path end-to-end. Rejected as a genuine loss of coverage.
- **Convert the other `os.name` fakes** (`test_cmd_resolver.py`,
  `test_dev_server_multiservice.py`). Checked and deliberately not done: they are
  safe. `test_cmd_resolver` calls an already-imported pure function; the multiservice
  pair only derives from `tmp_path`, whose `type(self)` is the host's NATIVE
  flavour — and it is the foreign flavour that carries the raising `__new__`, so
  the derivation is safe on either host. Unrelated churn in a bug fix.

## Acceptance criteria

- **AC1** `test_start_one_does_not_resolve_on_unix` passes when its file is run
  **alone** in a fresh process (probe B, the deterministic reproduction).
- **AC2** `shared/tests` passes **alone with xdist on** (`-n 8`) — the shape that
  was red 3/3 in probe A.
- **AC3** The repaired test exercises the **unprimed** proxy on every run, not only
  when scheduled first: re-injecting the bare `Path()` fails it deterministically.
  (Windows-only by construction — its `"posix"` fake is inert on a POSIX host; AC7
  is what covers Linux.)
- **AC4** The assertion is unchanged: `cmd_parts[0] == "npm"`. No test is weakened,
  skipped, xfailed or deleted, and `shared/tests` stays on the `suite.xdist`
  allowlist.
- **AC5** The production change is behaviour-preserving: `_SCRIPTS_DIR` equals the
  value the replaced expression produced, and the `lib.cmd_resolver` import stays
  deferred (ADR-045 unbroken).
- **AC6** The full F0 suite (all units, parallel) is green and files **no** new
  `f0-race:shared/tests` card.
- **AC7** The regression is caught on **`ubuntu-latest`** too, not only on the
  Windows F0 host — otherwise the pin is absent from the gate that runs most often.

## Affected Boundaries

- `shared/scripts/dev_server/__init__.py` — the one-shot proxy; consumed by
  `spawn.py::_start_one` via `_resolve_via_pkg`, and reachable from
  `/shipwright-preview` and `/shipwright-test` through `cmd_start`.
- `shared/tests/test_dev_server_windows_npm.py` — the four pins.
- Read, and deliberately NOT changed: `shared/scripts/dev_server/state.py`, which
  derives the same `shared/scripts` constant a second way (`pathlib`, at import)
  and inserts it into `sys.path` first. One derivation and one insert for the
  package is the right end state, but changing it here would be a refactor wearing
  a bug-fix label (Karpathy #3) — filed as a follow-up instead.
- Read, not modified: `shared/scripts/dev_server/spawn.py`,
  `shared/scripts/lib/cmd_resolver.py`.
- `shipwright_test_config.json → suite.xdist` — inspected and **deliberately left
  unchanged**.
- `sys.path` is mutated exactly as before, with a value measured identical.
- No config file, no env var, no hook, no workflow is touched. `touches_io_boundary`
  does not fire: nothing here parses or serialises a config, and the `os.path` call
  is path arithmetic on `__file__`, not an I/O contract.

## Test Completeness Ledger

Principle: **testable ⇒ tested.** Five tests in the changed file — one pre-existing
and untouched, one repaired, three new.

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | The lazy body survives a faked `os.name` on **any** host | `tested` | `test_lazy_resolve_does_no_platform_sensitive_work_on_first_call` — fakes the foreign flavour, so it fires on Windows and Linux alike |
| 2 | The lazy body runs to completion (rebinds) rather than short-circuiting | `tested` | same test, second assertion (`is not _lazy_resolve_executable`) |
| 3 | The scenario test takes the **unprimed** path every run, not by scheduling luck | `tested` | `test_start_one_does_not_resolve_on_unix` rebind; **demonstrated to bite** by re-injecting the bare `Path()` (2 failed) |
| 4 | `lib.cmd_resolver` is NOT bound by `import dev_server` — and `lib` itself **is** | `tested` | `test_importing_dev_server_leaves_lib_cmd_resolver_unbound` (subprocess — unobservable in-session), asserting all three values including the known-True `lib` |
| 5 | `_start_one` leaves `npm` unresolved on posix | `tested` | the original, **unchanged** assertion in `test_start_one_does_not_resolve_on_unix` |
| 6 | `_start_one` resolves `npm` → `npm.cmd` on Windows | `tested` | `test_start_one_resolves_npm_on_windows`, untouched |
| 7 | `_SCRIPTS_DIR` equals the `pathlib` expression it replaced | `tested` | `test_scripts_dir_matches_the_pathlib_derivation_it_replaced`; **demonstrated to bite** — a bogus value fails it (1 failed) where it previously left all tests green |
| 8 | The proxy restores `shared/scripts` on `sys.path` when it is absent | `tested` | `test_lazy_resolve_restores_shared_scripts_on_sys_path_when_absent` — added after CI; see below |
| 9 | The public surface is unchanged by the new private name | `untestable` — `covered-by-existing-test` | `test_dev_server_b4_surface_parity.py` — verified additive-only (`missing = ... not hasattr`), so private additions cannot trip it |

**0 testable-but-untested.** 9 rows against 7 ACs.

**Row 8 was missing until CI failed the build.** The first version of this ledger claimed 0 testable-but-untested while `__init__.py:87` — the `sys.path.insert` under the proxy's guard — was never executed by any test. It is dead in a normally imported process, because `state.py` inserts that path first (Stage 2 said so, and it was recorded as a follow-up rather than read as a coverage gap). The diff-coverage gate caught it at 66.7% and blocked the merge, which is the gate doing exactly its job: a line I touched was unverified. Fixed by exercising the branch — the proxy must not be a free-rider on `state.py` — not by deleting it. `dev_server/__init__.py` is now 22/22 statements.

**Row 7 was wrong until Stage 2 falsified it.** It read `untestable`, on the
reasoning that a bad `_SCRIPTS_DIR` would break the deferred import. It does not:
`dev_server/state.py` already inserts `shared/scripts` into `sys.path` at import,
so the import resolves through *that* entry regardless. Measured — with
`_SCRIPTS_DIR = "/nope/does/not/exist"` all other tests stayed green while the
proxy inserted a bogus `sys.path[0]`. AC5 was unpinned and the ledger said
otherwise, which is the failure mode the ledger exists to prevent; it is now a
real test, recorded here rather than silently upgraded.

## Confidence Calibration

- **Boundaries touched:** `dev_server/__init__.py`'s module init and its `sys.path`
  insertion; no config, no env var, no hook, no workflow, no I/O contract.
  `touches_io_boundary` does not fire.
- **Empirical probes run:**
  1. *Split the two variables the F0 retry conflates* — `shared/tests` alone **with**
     xdist: RED 3/3, same test each time. Inter-unit pollution falsified outright.
  2. *Removed xdist as well* — the file alone, serial: RED, deterministic. "Flaky"
     falsified. What the card called a race is neither of the things it names.
  3. *The masking mechanism, observed directly* — fresh binding is
     `_lazy_resolve_executable`; one call rebinds it; with it rebound, resolving
     under a faked posix does not crash. That is the whole ordering dependency.
  4. *`os.path` vs `pathlib` under both fakes* — identical value; `os.path` survives
     `os.name` in both directions, `pathlib` raises `NotImplementedError` for the
     foreign flavour. This is why the fix is `os.path` and why probe 2's pin can be
     platform-symmetric.
  5. *What the deferral actually buys* — after `import dev_server`,
     `lib.cmd_resolver` is absent from `sys.modules` and `resolve_executable` is
     still the proxy, **but `sys.modules['lib']` is already bound** to
     `shared/scripts/lib` by `state.py`'s eager `lib.atomic_write` import. So the
     package is not lib-safe and lazy import is not by itself an ADR-045
     mitigation — `shared_lib_loader.py` says so in writing. The first draft of
     the test claimed otherwise; it now asserts all three values, the `lib` one at
     its known-True state, so a future `state.py` clean-up trips it instead of
     drifting past.
  6. *`_SCRIPTS_DIR` is load-bearing and was unguarded* — set to
     `/nope/does/not/exist`, every test in the file stayed green (`state.py`
     supplies the `sys.path` entry the deferred import needs), while the proxy
     inserted the bogus path at `sys.path[0]`. Now pinned, and the pin
     demonstrated to fail on that same injection.
  7. *Both pins shown to bite* — bare `Path()` re-injected into the lazy body: 2
     failed, original `NotImplementedError`, **in the context that previously masked
     it**. Restored and re-verified green.
  8. *The shape that was red* — `shared/tests` alone `-n 8`, the exact probe-A
     shape: **green 3/3 on the final tree** (6551 passed, 12 skipped, ~90s each).
     Re-run from scratch after the last edit, because the intermediate 3/3 runs
     had measured a tree that changed under them — a green from a tree you no
     longer ship is the same mistake as a probe in the wrong process.
  9. *The serial shape too* — `ci.yml` runs `shared/tests` SERIALLY on
     `ubuntu-latest`, which is the authoritative gate; the xdist runs above are
     the accelerated pre-gate. Serial on the final tree: **6552 passed, 12
     skipped, rc 0** (453s). Both shapes, not just the one that was red.
  10. *The real production entry point* — `uv run shared/scripts/dev_server.py
     status --cwd .` through the shim → package → CLI path: exit 0, clean JSON.
     The change is at **module import time**, so this is the cheapest end-to-end
     evidence that the package still imports and dispatches for
     `/shipwright-preview`'s caller.
  11. *Both interpreters* — CI pins **3.11** while `uv run` here picks 3.12; the
     mechanism differs between them (table above), so the file was run on both:
     5 passed each, and with the pathlib derivation re-injected **both pins bite
     on 3.11 too** (2 failed). The first version of this probe existed only on
     3.12, which is how the wrong mechanism reached a shipped comment.
  12. *Own environment, re-measured after the last edit* — lint
     (`uvx ruff@0.15.15`, the gating pin) clean; **220 / 258 lines**, both inside
     the 300 budget; neither file is in `shipwright_bloat_baseline.json`, so no
     anti-ratchet exposure and no new Group-H crossing. Re-taken because the
     earlier figures (188 / 208) predated the review rounds — the same rule
     probe 8 states.
- **Test Completeness Ledger:** see the table above.
- **Confidence-pattern check:**
  - *Asymptote (depth)* — depth was **not** reached by careful building. The first
    version was a test-only workaround justified by a measurement taken in the wrong
    process; Stage 1 falsified it, and the external review then falsified the
    replacement's guarantee twice more (import-time is a narrower promise than it
    read; the pin was inert on the only CI platform). Each correction was
    re-measured, not argued. What raises confidence now is that the two claims that
    were wrong are the two that are pinned by tests demonstrated to fail without the
    fix.
  - *Coverage (breadth)* — both platform directions (the foreign-flavour fake covers
    Windows and Linux), both halves of the proxy (path arithmetic hoisted, import
    still deferred), both callers' behaviour (posix passthrough, Windows resolution),
    the public surface, and the ordering dependency itself.
  - *Integration composition* — no obligation, and this is **measured rather than
    argued**: both changed paths were run against `risk_detectors`'
    `CROSS_COMPONENT_FILE_PATTERNS` and `CI_SUPPLYCHAIN_FILE_PATTERNS` directly —
    no match in either, so neither `cross_component` nor `touches_ci_supplychain`
    fires. (Neither file is a merge/churn/event-log resolver, a hook, a phase
    validator, a campaign drain, or anything under `.github/`.) F11 recomputes
    both from the diff and will reach the same answer.
