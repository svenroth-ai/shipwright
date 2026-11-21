"""Scanner behind ``test_shipwright_paths_guard.py`` (campaign root-files-into-config, R0b).

Finds every way a module can name a root ``shipwright_*`` file WITHOUT going through
``lib/shipwright_paths.py``, so the resolver stays the only place that knows where
those files live. Pure functions over ``git ls-files``; the test file owns the
allowlists and the assertions.

What counts as a reference (BRIEF 11.2 classes 1-4, 8 and 11.9 6c):

- **Python, name-like string constants** (no whitespace, so prose/messages are out): any
  registry basename, its regex-escaped form, or a ``shipwright_<stem>`` prefix of one
  (``_OMIT = r"^(...|shipwright_events|...)"``); f-string / ``+`` construction of
  ``shipwright_`` names; ``.lock`` / ``.json.lock`` construction (``X + ".lock"``,
  ``with_suffix(".json.lock")``, ``f"{p}.lock"``).
- **class 8**: a function that reads a git object / compares git output (``git show``,
  ``cat-file``, ``ls-tree``, ``--porcelain``, a ``blob(...)`` helper) and builds the path with
  ``rel()`` instead of ``rel_at()``.
- **``.shipwright/`` prefix rules** (regex, glob, ``startswith``) that cover the whole tree.
- **Carriers** (bash, YAML, JSON data, md, templates): a per-file COUNT of registry names,
  held to a ratchet baseline; they cannot call a Python resolver, so they flip with the
  plugin version in R3.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO / "shared" / "scripts" / "lib"))
import shipwright_paths as sp  # noqa: E402

BASENAMES = sorted(sp.all_basenames())
# the event log stays at the root (operator decision 0.2): only its exact name is a reference,
# not the ``shipwright_events`` prefix of its sibling dirs / module names
STEMS = sorted({b.rsplit(".", 1)[0] for b in BASENAMES if b.startswith("shipwright_") and "events" not in b})
_NAMELIKE = re.compile("|".join(re.escape(x) for x in [*STEMS, "audit_config.json"]))
_NAME_TOKEN = re.compile("|".join(re.escape(b) for b in sorted(BASENAMES, key=len, reverse=True)))
_WS = re.compile(r"\s")
_NAME_PREFIX = re.compile(r"(?:^|[^_A-Za-z])shipwright_$")
_TREE_PREFIX = re.compile(r"^\^?\(?(?:\?:)?\\?\.shipwright(?:/|\\/)(?:\*\*?|\.\*)?(?:$|[|)])")
_GIT_SHAPES = {"show", "cat-file", "ls-tree", "--porcelain", "--porcelain=v1"}
_BLOB_CALLS = {"blob", "blob_oid", "committed_bytes_reader", "read_committed_text", "_read_at_commit"}
BASELINE = Path(__file__).parent / "fixtures" / "shipwright_paths_carriers.json"
CARRIER_SUFFIXES = {".md", ".yml", ".yaml", ".json", ".sh", ".template", ".ps1", ".toml", ".txt"}
CARRIER_EXCLUDED_TOP = {"docs", ".shipwright", "integration-tests"}


def tracked(*pathspec: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--", *pathspec],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [p for p in out.split("\0") if p]


def is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    return "tests" in parts or "testkit" in parts or parts[-1] == "conftest.py" or parts[0] == "integration-tests"


def production_py() -> list[str]:
    return [p for p in tracked("*.py") if not is_test_path(p) and p != "shared/scripts/lib/shipwright_paths.py"]


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                ids.add(id(first.value))
    return ids


def _is_rel_call(n: ast.AST) -> bool:
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"rel", "name", "path"} and isinstance(n.func.value, ast.Name)
            and n.func.value.id in {"_sp", "sp", "shipwright_paths"})


def _call_name(n: ast.Call) -> str:
    return n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")


def scan_python(rel: str) -> list[tuple[str, int, str]]:
    """``(rule, line, text)`` violations in one production file."""
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    skip = _docstring_ids(tree)
    out: list[tuple[str, int, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip:
            v = n.value
            if not _WS.search(v) and (_NAMELIKE.search(v) or sp.rel("events") in v):
                out.append(("literal", n.lineno, v[:80]))
            if not _WS.search(v) and (_TREE_PREFIX.match(v) or v in {".shipwright/**", ".shipwright/*", "**/.shipwright/**"}):
                out.append(("shipwright-prefix-rule", n.lineno, v[:80]))
        if isinstance(n, ast.JoinedStr):
            consts = [x.value for x in n.values if isinstance(x, ast.Constant) and isinstance(x.value, str)]
            if any(_NAME_PREFIX.search(c) for c in consts):
                out.append(("constructed-name", n.lineno, "f-string builds shipwright_<name>"))
            if any(c.endswith(".lock") for c in consts) and len(n.values) > 1:
                out.append(("lock-construction", n.lineno, "f-string ends in .lock"))
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            for side in (n.left, n.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    if _NAME_PREFIX.search(side.value):
                        out.append(("constructed-name", n.lineno, "concatenation builds shipwright_<name>"))
                    if side.value in {".lock", ".json.lock"}:
                        out.append(("lock-construction", n.lineno, side.value))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "with_suffix" and n.args and isinstance(n.args[0], ast.Constant) \
                    and "lock" in str(n.args[0].value):
                out.append(("lock-construction", n.lineno, f"with_suffix({n.args[0].value!r})"))
            if n.func.attr == "startswith":
                for a in n.args:
                    elts = [a] if isinstance(a, ast.Constant) else (a.elts if isinstance(a, ast.Tuple) else [])
                    if any(isinstance(e, ast.Constant) and e.value in {".shipwright/", ".shipwright"} for e in elts):
                        out.append(("shipwright-prefix-rule", n.lineno, "startswith('.shipwright/')"))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            consts = {c.value for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
            git_shape = bool(consts & _GIT_SHAPES) or any(
                isinstance(c, ast.Call) and _call_name(c) in _BLOB_CALLS for c in ast.walk(n))
            if git_shape:
                for c in ast.walk(n):
                    if _is_rel_call(c):
                        out.append(("class8-uses-rel", c.lineno, f"{n.name}: reads git objects/status but calls rel(); use rel_at()"))
    return out


def carrier_files() -> list[str]:
    out = []
    for p in tracked():
        top = p.split("/")[0]
        if top in CARRIER_EXCLUDED_TOP or is_test_path(p) or p.endswith(".py") or p.startswith("CHANGELOG"):
            continue
        if "/tests/" in p or p == "shared/tests/fixtures/shipwright_paths_carriers.json":
            continue
        if Path(p).suffix in CARRIER_SUFFIXES or p.startswith("scripts/hooks/"):
            out.append(p)
    return out


def carrier_counts() -> dict[str, dict[str, int]]:
    """path -> {root file name: occurrences}; per NAME so swapping one reference for another fails."""
    counts: dict[str, dict[str, int]] = {}
    for p in carrier_files():
        try:
            text = (REPO / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = _NAME_TOKEN.findall(text)
        if found:
            counts[p] = {n: found.count(n) for n in sorted(set(found))}
    return counts


def load_baseline() -> dict[str, dict[str, int]]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["files"]


if __name__ == "__main__":  # regenerate: uv run python shared/tests/_shipwright_paths_scan.py --write
    if "--write" in sys.argv:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        data = {"_about": "Ratchet for non-Python carriers of root shipwright_* names (bash, YAML, JSON data, md, "
                          "templates): per-file, per-name COUNT may only fall. R3 flips these with the plugin version.",
                "files": dict(sorted(carrier_counts().items()))}
        BASELINE.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(len(carrier_counts()), "carrier files")
