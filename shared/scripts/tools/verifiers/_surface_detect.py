"""Which runnable surfaces a change touches, re-derived from its diff.

F0.5 lets a medium+ run record ``surface: none`` ("nothing a person can start
or call changed"). Until this module, F11 took that on trust. Here the claim is
checked against the diff: a change that touches one of the four surface kinds
below has something to drive, so ``none`` is refused.

``ui``                a frontend source file (the same rule Browser Verify uses,
                      ``lib/detect_frontend_changes``)
``api_route``         a code file under a route / API / controller / handler
                      directory, or named ``route(s)`` / ``router`` / ``urls`` /
                      ``endpoints`` / ``controller(s)``, or whose changed lines
                      declare an HTTP handler (``@app.get(``, ``APIRouter(``,
                      ``express.Router(``, ``@Get(`` ...)
``realtime``          a code file whose name or directory says SSE, WebSocket or
                      socket, or whose changed lines open one (``new WebSocket(``,
                      ``EventSource(``, ``text/event-stream``, ``socket.io``)
``message_contract``  an over-the-wire schema (``.proto``, GraphQL, Avro,
                      OpenAPI / AsyncAPI / Swagger) or a code file under a
                      ``contracts/`` or ``messages/`` directory

Never a surface: tests and fixtures, prose (``.md``, ``.rst``, ``.txt``),
``docs/``, ``.github/``, and the iterate's own finalization records.

**Conservative on purpose.** A false positive costs one real F0.5 run (``cli``
is always available); a false negative is the bypass this module exists to
close. So ambiguous names count: in a tooling repo ``router.py`` may be
dispatch logic, and the run then drives it as ``cli``. Known blind spot: a
surface change whose path says nothing and whose changed lines match no
content signal (an edit deep inside an existing handler's body, a contract
type in an ordinary model file). The detail names the path that tripped each
kind, so a refusal is always explainable.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.detect_frontend_changes import _is_frontend_path  # noqa: E402
from lib.review_diff_threshold import is_counted_path  # noqa: E402

__all__ = ["SURFACE_KINDS", "detect_surfaces", "is_test_or_prose", "is_test_path", "split_patch"]

SURFACE_KINDS = ("ui", "api_route", "realtime", "message_contract")

_TEST_SEGMENTS = frozenset({"tests", "test", "__tests__", "__mocks__", "fixtures", "e2e"})
_PROSE_SUFFIXES = (".md", ".mdx", ".rst", ".txt")
_SKIP_PREFIXES = ("docs/", ".github/")
_CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb",
                  ".java", ".kt", ".rs", ".php", ".cs", ".vue", ".svelte")
_ROUTE_SEGMENTS = frozenset({"routes", "route", "api", "controllers", "endpoints",
                             "handlers", "routers", "router"})
_ROUTE_TOKENS = frozenset({"routes", "route", "router", "routers", "urls", "endpoints",
                           "controller", "controllers"})
_REALTIME_TOKENS = frozenset({"sse", "websocket", "websockets", "ws", "socket", "sockets",
                              "socketio", "eventsource", "eventstream"})
_CONTRACT_SUFFIXES = (".proto", ".graphql", ".gql", ".avsc")
_CONTRACT_STEMS = ("openapi", "asyncapi", "swagger")
_CONTRACT_SEGMENTS = frozenset({"contracts", "messages"})
_TOKEN = re.compile(r"[a-z0-9]+")
_CONTENT_SIGNALS = {
    "api_route": re.compile(
        r"@\w+\.(?:route|get|post|put|patch|delete|websocket)\(|\bAPIRouter\(|\bBlueprint\("
        r"|express\.Router\(|\b(?:app|router|server)\.(?:get|post|put|patch|delete)\(\s*['\"`]/"
        r"|@(?:Get|Post|Put|Patch|Delete|Controller)\("),
    "realtime": re.compile(r"new WebSocket(?:Server)?\(|\bEventSource\(|text/event-stream"
                           r"|socket\.io|\bwebsockets?\.serve\("),
}


def _norm(path: str) -> str:
    norm = path.strip().strip('"').replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def is_test_path(path: str) -> bool:
    """True for a test file, a fixture, or anything under a test directory."""
    *dirs, name = _norm(path).lower().split("/")
    if _TEST_SEGMENTS.intersection(dirs) or name == "conftest.py":
        return True
    return (name.startswith("test_") or name.endswith(("_test.py", "_test.go"))
            or ".test." in name or ".spec." in name)


def is_test_or_prose(path: str) -> bool:
    """True for a path that can never be a runnable surface."""
    norm = _norm(path).lower()
    if not norm or not is_counted_path(norm) or norm.startswith(_SKIP_PREFIXES):
        return True
    return norm.endswith(_PROSE_SUFFIXES) or is_test_path(norm)


def split_patch(patch: str) -> dict[str, str]:
    """``{path: changed lines}`` from ``git diff -U0 --no-renames`` output (both sides of a move)."""
    out: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_header = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            current, in_header = None, True
        elif in_header and line.startswith(("--- ", "+++ ")):
            side = line[4:].strip()
            if side != "/dev/null":  # a deletion's lines are kept under its old path
                current = out.setdefault(_norm(side[2:] if side[:2] in ("a/", "b/") else side), [])
        elif line.startswith("@@"):
            in_header = False
        elif current is not None and not in_header and line[:1] in ("+", "-"):
            current.append(line[1:])
    return {path: "\n".join(lines) for path, lines in out.items()}


def _kinds_of(norm: str, changed: str) -> list[str]:
    lower = norm.lower()
    *dirs, name = lower.split("/")
    stem = name.rsplit(".", 1)[0]
    tokens = set(_TOKEN.findall(stem))
    is_code = lower.endswith(_CODE_SUFFIXES)
    kinds = []
    if _is_frontend_path(norm):
        kinds.append("ui")
    if is_code and (_ROUTE_SEGMENTS.intersection(dirs) or _ROUTE_TOKENS & tokens
                    or _CONTENT_SIGNALS["api_route"].search(changed)):
        kinds.append("api_route")
    if is_code and (_REALTIME_TOKENS & tokens or _REALTIME_TOKENS.intersection(dirs)
                    or _CONTENT_SIGNALS["realtime"].search(changed)):
        kinds.append("realtime")
    if (lower.endswith(_CONTRACT_SUFFIXES) or stem.startswith(_CONTRACT_STEMS)
            or (is_code and _CONTRACT_SEGMENTS.intersection(dirs))):
        kinds.append("message_contract")
    return kinds


def detect_surfaces(paths: list[str], changed: dict[str, str] | None = None) -> dict[str, list[str]]:
    """``{kind: [paths...]}`` for every surface kind touched; ``{}`` when none.

    ``changed`` (:func:`split_patch`) adds the content signals; without it only
    the path rules apply.
    """
    changed = changed or {}
    found: dict[str, list[str]] = {}
    for raw in paths:
        norm = _norm(raw)
        if is_test_or_prose(norm):
            continue
        for kind in _kinds_of(norm, changed.get(norm, "")):
            found.setdefault(kind, []).append(norm)
    return {kind: sorted(set(found[kind])) for kind in SURFACE_KINDS if kind in found}
