"""`dev_server._start_one` executable resolution, and the lazy proxy behind it.

Regression 1 — WinError 2 when the profile command is `npm --prefix server run
dev`, because `subprocess.Popen` with `shell=False` cannot resolve `npm.cmd` from
`npm`. The fix is `cmd_resolver.resolve_executable`, NOT `shell=True` (which would
make profile-author-supplied command strings a command-injection surface).

Regression 2 (f0-race:shared/tests, trg-f64d1c27) — `dev_server.resolve_executable`
is a ONE-SHOT lazy proxy, and its lazy body used to derive a path with `pathlib`.
`pathlib` selects its flavour from the process-global `os.name`, which the tests
below fake, so that derivation raised — but only in a process where nothing had
already burned the proxy. Green in serial order, red under xdist by worker
assignment. The last three tests pin the fix: the lazy body does no path
arithmetic, `_SCRIPTS_DIR` still names the right directory, and the
`lib.cmd_resolver` import is still deferred.

**On patching `os.name` here at all.** The repo's standing rule is the opposite —
`test_atomic_write_windows_retry.py` says patch a predicate, never `os.name`, and
`test_atomic_write_windows_read_retry.py` enforces it with a source scan (scoped to
the atomic_write files, so this file is outside it by construction, not by
exemption). `test_playwright_setup_multiservice.py` takes a third route, skipping on
Linux with a TODO for an injectable seam. This file deviates deliberately: the
no-op being asserted lives in `cmd_resolver`, which reads `os.name` itself, so a
predicate would have to be threaded through two production modules to serve one
test. The fakes below use the FOREIGN name so they still bite on both platforms —
which is the property the standing rule exists to protect.
"""

from __future__ import annotations

import os
import shutil  # noqa: F401  -- see _foreign_os_name(); imported for its SIDE EFFECT
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # noqa: E402


def _foreign_os_name() -> str:
    """The `os.name` this host is NOT, for the platform fakes below.

    Faking the foreign flavour is what makes the pins bite on every host rather
    than only on Windows: `pathlib` raises `NotImplementedError` for whichever
    flavour is not the real one, so `"posix"` probes a Windows host and `"nt"`
    probes a POSIX one. `ci.yml` runs `ubuntu-latest` while the F0 suite runs on
    Windows, and a pin that only fires on one of them is not continuously
    enforced.

    The `shutil` import above is a real prerequisite, not tidiness. `shutil` runs
    `if os.name == 'posix': import posix` / `elif _WINDOWS: import nt` at module
    level, so a FIRST import of it under a fake would look for the other
    platform's builtin and raise `ModuleNotFoundError`. Anything reached under a
    fake here imports it transitively, so it is imported up front, on the real
    platform, instead of relying on pytest happening to have done so.
    """
    return "posix" if os.name == "nt" else "nt"


def test_start_one_resolves_npm_on_windows(tmp_path, monkeypatch):
    captured: dict = {}

    class FakeProc:
        def __init__(self, cmd_parts, **kwargs):
            captured["cmd_parts"] = cmd_parts
            captured["shell"] = kwargs.get("shell", False)
            captured["kwargs"] = kwargs
            self.pid = 4242

    service = {
        "name": "backend",
        "command": "npm --prefix server run dev",
        "host": "localhost",
        "scheme": "http",
        "port": 3847,
        "ready_path": "/api/diagnostics",
        "ready_timeout_seconds": 60,
        "primary": True,
    }

    monkeypatch.setattr(dev_server.os, "name", "nt")
    monkeypatch.setattr(dev_server.subprocess, "Popen", FakeProc)
    monkeypatch.setattr(
        dev_server,
        "resolve_executable",
        lambda name: r"C:\Program Files\nodejs\npm.cmd" if name == "npm" else name,
    )

    proc, record = dev_server._start_one(service, tmp_path)

    assert captured["cmd_parts"][0] == r"C:\Program Files\nodejs\npm.cmd"
    assert captured["cmd_parts"][1:] == ["--prefix", "server", "run", "dev"]
    # CRITICAL: shell stays False (no command-injection surface).
    assert captured["shell"] is False or "shell" not in captured["kwargs"]
    assert record["pid"] == 4242
    assert record["command"] == "npm --prefix server run dev"  # original preserved


def test_start_one_does_not_resolve_on_unix(tmp_path, monkeypatch):
    """On non-Windows, resolve_executable is a no-op — npm stays as 'npm'."""
    captured: dict = {}

    class FakeProc:
        def __init__(self, cmd_parts, **kwargs):
            captured["cmd_parts"] = cmd_parts
            self.pid = 1

    service = {
        "name": "backend",
        "command": "npm run dev",
        "host": "localhost",
        "scheme": "http",
        "port": 3000,
        "ready_path": "/",
        "ready_timeout_seconds": 60,
        "primary": True,
    }

    # REGRESSION PIN (f0-race:shared/tests, trg-f64d1c27). `resolve_executable` is
    # a ONE-SHOT lazy proxy, so only its FIRST call in a process runs the lazy body
    # — and this test fakes `os.name` around it. When that body still did
    # `Path(__file__).resolve()`, the fake made pathlib build the foreign flavour
    # and raise `NotImplementedError: cannot instantiate 'PosixPath'`. The test
    # nonetheless passed whenever anything earlier in the same process had already
    # burned the proxy, so it was green in serial order and red under xdist,
    # depending on which worker drew it. Re-binding the proxy forces the unprimed
    # path on EVERY run, in every worker: if platform-sensitive work returns to the
    # lazy body, this fails deterministically instead of by lottery.
    #
    # On a Windows host only. On Linux `os.name` is already "posix", so the fake is
    # inert and this pins nothing there — the standing rule in
    # test_atomic_write_windows_retry.py (patch a predicate, never `os.name`) is
    # the general answer; see the mini-plan for why it is disproportionate here.
    monkeypatch.setattr(dev_server, "resolve_executable",
                        dev_server._lazy_resolve_executable)

    monkeypatch.setattr(dev_server.os, "name", "posix")
    monkeypatch.setattr(dev_server.subprocess, "Popen", FakeProc)
    # resolve_executable on posix is a no-op even if called
    dev_server._start_one(service, tmp_path)
    assert captured["cmd_parts"][0] == "npm"


def test_scripts_dir_matches_the_pathlib_derivation_it_replaced():
    """`_SCRIPTS_DIR` must still name `shared/scripts`, however it is derived.

    Not a tautology: it compares the new `os.path` derivation against the
    independent `pathlib` one it replaced, which IS the equivalence claim. It
    needs its own test because nothing else notices a wrong value —
    `dev_server/state.py` already inserts `shared/scripts` into `sys.path` at
    import, so the proxy's deferred `lib.cmd_resolver` import resolves through
    THAT entry no matter what this constant holds. Measured: setting it to
    "/nope/does/not/exist" leaves every other test in this file green, while the
    proxy inserts the bogus path at `sys.path[0]` — a live shadowing hazard. So a
    dirname-count slip in a future refactor would ship silently.

    Runs under the real `os.name`; constructing a `Path` is only unsafe under the
    platform fakes the other tests install.
    """
    assert dev_server._SCRIPTS_DIR == str(
        Path(dev_server.__file__).resolve().parent.parent)


def test_lazy_resolve_does_no_platform_sensitive_work_on_first_call(monkeypatch):
    """The proxy's lazy body must survive a faked `os.name` — on EVERY host.

    This is the pin for `_SCRIPTS_DIR` being resolved at import time with
    `os.path` rather than inside the proxy with `pathlib`. `Path()` selects its
    flavour from the process-global `os.name`, and the flavour that is not the
    host's raises `NotImplementedError` — on `<=3.11` at construction, on
    `>=3.12` at the first derivation (`.resolve()`, `.parent`, `/`). Either way,
    putting pathlib back into the lazy body fails this test; the version only
    moves which line the traceback names. Do not narrow this to "derivations" —
    CI pins 3.11, where the bare constructor is already enough.

    It fails on Windows *and* on Linux, because the fake is the FOREIGN name
    rather than a hard-coded one — unlike the scenario test above, whose
    `"posix"` fake is inert on a POSIX host. `ci.yml` runs `ubuntu-latest` while
    the F0 suite runs on Windows; pinning only one of them would leave the
    regression uncaught on the gate that runs most often.

    The rebind forces the one-shot proxy back to its unprimed state, because the
    lazy body runs exactly once per process and something else has usually run it
    already (f0-race:shared/tests, trg-f64d1c27 — the masking that let the
    original defect look intermittent).
    """
    monkeypatch.setattr(dev_server, "resolve_executable",
                        dev_server._lazy_resolve_executable)
    monkeypatch.setattr(dev_server.os, "name", _foreign_os_name())

    resolved = dev_server.resolve_executable("npm")

    # A str back, not an exception, is the whole contract: on a faked posix the
    # real resolver is a no-op, and on a faked nt `shutil.which` may or may not
    # find npm on the host — neither outcome is the point.
    assert isinstance(resolved, str)
    # The lazy body ran to completion rather than short-circuiting: reaching the
    # rebind is the last thing it does.
    assert dev_server.resolve_executable is not dev_server._lazy_resolve_executable


def test_importing_dev_server_leaves_lib_cmd_resolver_unbound():
    """The `lib.cmd_resolver` import must stay DEFERRED — and only that.

    Read the assertion narrowly, because the obvious wider reading is FALSE:
    `import dev_server` already binds `sys.modules['lib']` to
    `shared/scripts/lib`. `dev_server/state.py` does a module-scope
    `from lib.atomic_write import durable_atomic_write` and `__init__.py` imports
    `.state` unconditionally, so the package is in that state before the proxy is
    ever called. Deferring `lib.cmd_resolver` therefore does NOT make
    `import dev_server` lib-safe, and `shared/scripts/shared_lib_loader.py` says
    the general form outright: importing lazily "was the accepted mitigation, and
    it is not enough."

    What this pins is the narrow, real invariant: hoisting `_SCRIPTS_DIR` moved
    the *path arithmetic* out of the lazy body and must not have dragged the
    import out with it, so the tempting "simplification" of collapsing the proxy
    into a module-scope import fails here rather than silently in some other
    plugin's test run. The `lib` value is asserted at its known-True state so the
    day `state.py` stops binding it, this test notices instead of drifting.

    Needs a subprocess: inside this session `lib.cmd_resolver` is already in
    `sys.modules` (`test_cmd_resolver.py` imports it at module scope), so the
    invariant is only observable in a fresh interpreter.
    """
    # !r, not a raw-string template: a repo path containing a quote or a
    # backslash escape would otherwise be a SyntaxError in the child and fail
    # this test for a reason that has nothing to do with what it pins.
    probe = (
        f"import sys; sys.path.insert(0, {str(REPO / 'scripts')!r});"
        "import dev_server;"
        "print('lib' in sys.modules,"
        " 'lib.cmd_resolver' in sys.modules,"
        " dev_server.resolve_executable.__name__)"
    )
    # Generous timeout: this runs inside the F0 parallel suite, and a bound tight
    # enough to trip under CPU contention would make this test the very thing the
    # run it came from was investigating. Explicit encoding because `text=True`
    # alone decodes with the host locale codec (cp1252 on the F0 host), which
    # turns a non-ASCII byte in a child traceback into UnicodeDecodeError here
    # instead of a readable assertion failure.
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(REPO.parent),
                          capture_output=True, encoding="utf-8",
                          errors="replace", timeout=120)

    assert done.returncode == 0, done.stderr
    # Compare the LAST three tokens, not the whole of stdout: a printing
    # sitecustomize or a chatty `.pth` in some future environment would otherwise
    # redden this with the code correct, and a pin that fails for reasons other
    # than its invariant is how the original defect stayed unexplained for so long.
    assert done.stdout.split()[-3:] == [
        "True",                      # `lib` IS bound — by state.py, see above
        "False",                     # ...but `lib.cmd_resolver` is not
        "_lazy_resolve_executable",  # ...and the proxy is still the proxy
    ], done.stdout
