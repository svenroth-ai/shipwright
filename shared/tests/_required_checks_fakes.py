"""Shared loader + `gh` fakes for the required-check producer's two test modules.

Not a test module (the leading underscore keeps pytest from collecting it). It
owns loading `tools/check_required_checks.py` — a script, not an importable
module — and the fake `subprocess.run` both suites drive it with.

Split across ``test_check_required_checks_io.py`` (the host-call primitives:
which `gh` failures are controlled, how a slug is read) and
``test_check_required_checks_cli.py`` (what the producer DECIDES once the host
has answered, and the exit codes it reports).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def load_producer():
    """Load the tool by path, since it is a script rather than a module."""
    path = _SCRIPTS / "tools" / "check_required_checks.py"
    spec = importlib.util.spec_from_file_location("_check_required_checks", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_required_checks"] = module
    spec.loader.exec_module(module)
    return module


class Resp:
    """The subset of `subprocess.CompletedProcess` the producer reads."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# `gh` renders an API error as `gh: <message> (HTTP <code>)` on stderr, which is
# the only place the status survives — telling 404 ("no such policy") from 403
# ("I could not ask") rests on it, so the fakes reproduce that shape exactly.
REPO_OK = Resp(0, '{"default_branch": "main"}')
NOT_FOUND = Resp(1, "", "gh: Not Found (HTTP 404)")
FORBIDDEN = Resp(1, "", "gh: Resource not accessible (HTTP 403)")


def gh_router(routes: dict[str, Resp], recorder: list[str] | None = None):
    """Fake `subprocess.run` dispatching on the API path at the end of argv.

    A `git` call answers with a plain github.com origin so `resolve_repo`
    succeeds; every unrouted `gh` call raises rather than returning a default,
    so a test cannot silently pass on a request it never meant to make.
    """

    def _run(argv, **kwargs):
        if argv and argv[0] == "git":
            return Resp(0, "https://github.com/o/r.git\n")
        endpoint = argv[-1]
        if recorder is not None:
            recorder.append(endpoint)
        for pattern, resp in routes.items():
            if endpoint.endswith(pattern):
                return resp
        raise AssertionError(f"unrouted gh call: {endpoint}")

    return _run
