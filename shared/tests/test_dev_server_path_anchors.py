"""`dev_server`'s filesystem anchors: one derivation, one `sys.path` insert.

Pins the consolidation done by `iterate-2026-08-01-dev-server-path-derivation`
(superseding trg-36f182f3). Before it, four places re-derived `shared/scripts`
or `shared/profiles` from their own `__file__` — three with `pathlib` — and
three of them independently inserted `shared/scripts` into `sys.path`. Now
`dev_server/_paths.py` owns the single derivation, the single guarded insert,
and the two constants.

**Why a separate file from `test_dev_server_windows_npm.py`.** That file owns
the neighbouring concern (the lazy `resolve_executable` proxy and its platform
fakes) and its `test_scripts_dir_matches_the_pathlib_derivation_it_replaced` is
the sibling of the profiles pin below — so these three could plausibly have
lived there. They do not, because adding them pushed it from 285 to 393 lines,
past the repo's 300-line guideline and into a new bloat-baseline crossing that
the Stop hook blocks on. `test_dev_server_b4_surface_parity.py` was split out
of the multiservice suite for exactly this reason; this follows that precedent
rather than growing a fourth oversized file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # noqa: E402


def test_profiles_dir_matches_the_pathlib_derivation_it_replaced():
    """`_profiles_dir()` must still name `shared/profiles`, however it is derived.

    The sibling of `test_scripts_dir_matches_the_pathlib_derivation_it_replaced`
    (in `test_dev_server_windows_npm.py`) and not a tautology for the same
    reason: it compares the new `_paths._PROFILES_DIR` derivation (one
    `os.path.dirname` off `_SCRIPTS_DIR`) against the independent three-step
    `__file__` walk it replaced, which IS the equivalence claim. Any one-off
    dirname slip fails it.

    It needs its own test because the failure is quiet — `_load_profile_data`
    treats a missing profile file as "no profile" and falls back to the legacy
    in-script map, so a wrong directory here degrades to the fallback instead of
    raising, and every test that monkeypatches `_profiles_dir` to a `tmp_path`
    (the multiservice suite) keeps passing.

    Runs under the real `os.name`; constructing a `Path` is only unsafe under the
    platform fakes the windows_npm suite installs.
    """
    assert dev_server._profiles_dir() == (
        Path(dev_server.__file__).resolve().parent.parent.parent / "profiles")


def test_ensure_scripts_on_path_inserts_once_and_at_the_front(monkeypatch):
    """The package's single `sys.path` mutation: guarded, front-inserting, idempotent.

    `_ensure_scripts_on_path` replaced three separate copies of this insert. The
    guard matters because the function is now called from three sites in one
    process (`state.py` at import, the `__init__.py` lazy proxy, `spawn.py`'s
    fallback) where previously each had its own — an unguarded version would grow
    `sys.path` by one entry per call.

    Asserted directly rather than only through the proxy: the proxy's own test
    covers the restore path, but nothing there would notice a duplicate entry.

    Deliberately value-BLIND — the filter and the assertion both read the alias
    the function inserts, so this would pass with a wrong path. That half is
    carried by `test_scripts_dir_matches_the_pathlib_derivation_it_replaced`;
    together they are composite coverage, separately neither is enough.
    """
    # A fresh list, so monkeypatch restores the real sys.path at teardown.
    monkeypatch.setattr(sys, "path",
                        [p for p in sys.path if p != dev_server._SCRIPTS_DIR])
    assert dev_server._SCRIPTS_DIR not in sys.path

    dev_server._paths._ensure_scripts_on_path()
    assert sys.path[0] == dev_server._SCRIPTS_DIR

    dev_server._paths._ensure_scripts_on_path()
    assert sys.path.count(dev_server._SCRIPTS_DIR) == 1


def test_spawn_fallback_puts_scripts_on_path_without_the_package_attribute(monkeypatch):
    """`spawn._resolve_via_pkg`'s last-resort branch still sets up its own import.

    That branch runs only when `sys.modules[__package__]` has no
    `resolve_executable` — the package not initialised through `__init__.py`.
    Nothing in normal operation produces that state, so it had NO coverage at
    all; it is exercised here because this run replaced the path arithmetic
    inside it with `_ensure_scripts_on_path()`, and an untested changed line is
    what the Test Completeness Ledger refuses.

    Stripping `sys.path` first is what makes the assertion load-bearing rather
    than incidental: `lib.cmd_resolver` is usually already in `sys.modules` from
    a sibling suite, so the deferred import would succeed even with the entry
    absent. Asserting on `sys.path[0]` therefore pins the CALL, not the import
    it enables — the one thing this branch is responsible for.
    """
    monkeypatch.delattr(dev_server, "resolve_executable", raising=False)
    # A fresh list, so monkeypatch restores the real sys.path at teardown.
    monkeypatch.setattr(sys, "path",
                        [p for p in sys.path if p != dev_server._SCRIPTS_DIR])
    assert dev_server._SCRIPTS_DIR not in sys.path

    resolved = dev_server.spawn._resolve_via_pkg("npm")

    # A str back, not an exception: on posix the real resolver is a no-op, and
    # on nt `shutil.which` may or may not find npm — neither outcome is the point.
    assert isinstance(resolved, str)
    assert sys.path[0] == dev_server._SCRIPTS_DIR


def test_importing_dev_server_does_no_pathlib_path_arithmetic():
    """`import dev_server` must survive a faked `os.name` — the MODULE-SCOPE half.

    `test_lazy_resolve_does_no_platform_sensitive_work_on_first_call` (windows_npm
    suite) pins the same property for the lazy proxy's body. This pins it for
    package import itself, which used to derive `shared/scripts` a second time in
    `state.py` with `Path(__file__).resolve().parents[1]` at module scope. Under
    the foreign flavour that line raises `NotImplementedError: cannot instantiate
    'PosixPath'/'WindowsPath' on your system` (whichever the host is NOT), so
    `import dev_server` under a fake was impossible — this fails with the old
    derivation restored rather than merely describing it.

    **`pathlib` must be pre-imported, and that is the whole test.** On 3.11
    `_PosixFlavour.is_supported` / `_WindowsFlavour.is_supported` are CLASS
    attributes evaluated once, at pathlib import time, from `os.name`;
    `Path.__new__` then picks a class from the CURRENT `os.name` and checks that
    class's flag. Import pathlib *after* the fake and the two agree, so
    construction quietly succeeds and the pin is dead. Measured both ways on
    3.11: pre-import → `NotImplementedError`; post-import → `Path('C:/x/y')
    .resolve()` returns normally. Without the pre-import the old derivation still
    reddens a Windows host by accident (`PosixPath` parses `C:\\...` as one
    component, so `parents[1]` raises `IndexError`) but passes clean on
    `ubuntu-latest`, where `ci.yml` runs — i.e. inert on the gate that runs most
    often.

    **The rule behind the pre-import list, not just the list.** The child fakes
    `os.name` before importing `dev_server`, so any stdlib module the chain
    reaches for the FIRST time evaluates its module-scope platform branch under
    the fake — and the fake is `posix` on a Windows host but `nt` on ubuntu, so
    the two hosts take different branches. Therefore: **no module first-imported
    by the `dev_server` chain may do a platform-gated import at module scope;
    pre-import any that does.** Today that is `shutil` (binds a platform builtin;
    reached via `tempfile` from `lib.atomic_write`, eager in `state.py`) — without
    it the child dies on `ModuleNotFoundError: No module named 'posix'`. Checked
    and currently safe: `urllib.request`'s `nturl2path` import (reached via
    `health.py`) is pure-Python and ships on Linux. Adding e.g. `ctypes` to the
    chain would break this on ubuntu only.

    Needs a subprocess: this module imported `dev_server` at import time, so the
    package is already in `sys.modules` and the module-scope work cannot be
    re-run in-process.
    """
    # !r, not a raw-string template: a repo path containing a quote or a
    # backslash escape would otherwise be a SyntaxError in the child and fail
    # this test for a reason that has nothing to do with what it pins.
    probe = (
        "import sys, os, pathlib, shutil, tempfile;"
        f"sys.path.insert(0, {str(REPO / 'scripts')!r});"
        "os.name = 'posix' if os.name == 'nt' else 'nt';"
        "import dev_server;"
        "print('IMPORTED');"
        "print(dev_server._SCRIPTS_DIR);"
        "print(dev_server._paths._PROFILES_DIR)"
    )
    # Explicit encoding because `text=True` alone decodes with the host locale
    # codec (cp1252 on the F0 host), which would turn a non-ASCII byte in a child
    # traceback into UnicodeDecodeError instead of a readable failure.
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(REPO.parent),
                          capture_output=True, encoding="utf-8",
                          errors="replace", timeout=120)

    assert done.returncode == 0, done.stderr
    # The VALUES, not their truthiness: `bool(str)` would be satisfied by any
    # non-empty string, so it would only re-assert that the import did not throw
    # — which the returncode above already covers. Line-per-value because a repo
    # path may contain spaces. Compared against this (unfaked) process, which is
    # the actual claim: a faked `os.name` does not perturb the anchors.
    assert done.stdout.splitlines()[-3:] == [
        "IMPORTED",
        dev_server._SCRIPTS_DIR,
        dev_server._paths._PROFILES_DIR,
    ], done.stdout
