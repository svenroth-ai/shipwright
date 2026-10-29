"""Blind mutation probes judged by test failure (BP unit BL0b, item 6).

The sample is drawn from an AST walk of ``shared/**`` and ``plugins/*/scripts/**`` with NO coverage involved: every function
that has a mutable site (a comparison, an ``and``/``or``, a ``return`` of a value) is eligible, and about 50 are drawn
uniformly with a fixed seed. One semantic mutation is applied in a scratch copy of the tree, the FR-bound tests that could
reach the module are run, and the verdict is "does an FR-bound test that passed before now fail". T-code's reading (does the
HEAD context run link the function to an FR) is recorded next to it, never used to pick or judge the probe.
"""

from __future__ import annotations

import ast
import random
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from ._baseline_b_headmap import index_tokens
from ._baseline_touch_coverage import _spans
from ._baseline_touch_git import is_test_path
from ._baseline_head_run import _WITH, prefix_of

__all__ = ["eligible_functions", "mutate", "candidate_tests", "run_probe", "junit_failures", "classify", "tokens_for", "draw"]

_CMP = {ast.Eq: "!=", ast.NotEq: "==", ast.Lt: ">=", ast.Gt: "<=", ast.LtE: ">", ast.GtE: "<", ast.Is: "is not", ast.IsNot: "is"}
_SKIP_DIRS = {".venv", "node_modules", "__pycache__", "fixtures", "site-packages"}


def _prod_files(tree: Path) -> list[Path]:
    files = [p for base in [tree / "shared", *sorted((tree / "plugins").glob("*/scripts"))] for p in base.rglob("*.py")]
    return sorted(p for p in files if not (_SKIP_DIRS & set(p.parts)) and not is_test_path(p.relative_to(tree).as_posix()) and p.name != "__init__.py")


def _site(node: ast.AST, lines: list[str]):
    """First mutable site in a function node: ``(line, col_start, col_end, replacement)`` or None."""
    for kind in ("cmp", "bool", "ret"):
        for n in ast.walk(node):
            if kind == "cmp" and isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _CMP and n.left.end_lineno == n.comparators[0].lineno:
                seg = lines[n.left.end_lineno - 1][n.left.end_col_offset:n.comparators[0].col_offset]
                tok = re.search(r"is not|!=|==|<=|>=|<|>|is", seg)
                if tok:
                    base = n.left.end_col_offset
                    return n.left.end_lineno, base + tok.start(), base + tok.end(), _CMP[type(n.ops[0])]
            if kind == "bool" and isinstance(n, ast.BoolOp) and n.values[0].end_lineno == n.values[1].lineno:
                seg = lines[n.values[0].end_lineno - 1][n.values[0].end_col_offset:n.values[1].col_offset]
                tok = re.search(r"\band\b|\bor\b", seg)
                if tok:
                    base = n.values[0].end_col_offset
                    return n.values[0].end_lineno, base + tok.start(), base + tok.end(), "or" if tok[0] == "and" else "and"
            if kind == "ret" and isinstance(n, ast.Return) and n.value is not None and n.value.lineno == n.value.end_lineno and not (isinstance(n.value, ast.Constant) and n.value.value is None):
                v = n.value
                flip = "False" if isinstance(v, ast.Constant) and v.value is True else "True" if isinstance(v, ast.Constant) and v.value is False else "None"
                return v.lineno, v.col_offset, v.end_col_offset, flip
    return None


def eligible_functions(tree: Path) -> list[dict]:
    """Every production function with at least four statements and a mutable site (no coverage consulted)."""
    out = []
    for path in _prod_files(tree):
        try:
            text = path.read_text(encoding="utf-8")
            mod = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        lines = text.splitlines()
        rel = path.relative_to(tree).as_posix()
        qual = {name: (a, b) for name, a, b in _spans(text)}
        nodes = {(n.lineno, n.end_lineno): n for n in ast.walk(mod) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name, (a, b) in qual.items():
            node = nodes.get((a, b))
            if node is None or sum(1 for _ in ast.walk(node) if isinstance(_, ast.stmt)) < 5:
                continue
            site = _site(node, lines)
            if site:
                out.append({"file": rel, "func": name, "lines": [a, b], "site": list(site)})
    return out


def mutate(tree: Path, probe: dict) -> bool:
    """Apply the probe's mutation to the file in ``tree``; False when the result does not parse."""
    path = tree / probe["file"]
    lines = path.read_text(encoding="utf-8").split("\n")
    ln, c0, c1, new = probe["site"]
    row = lines[ln - 1]
    lines[ln - 1] = row[:c0] + new + row[c1:]
    text = "\n".join(lines)
    try:
        ast.parse(text)
    except SyntaxError:
        return False
    path.write_text(text, encoding="utf-8", newline="")
    return True


def _root_of_test(rel: str) -> str:
    m = re.match(r"^(plugins/[^/]+/tests)/", rel)
    return m[1] if m else next((r for r in ("shared/scripts/tools/tests", "shared/scripts/tests", "shared/tests", "integration-tests") if rel.startswith(r + "/")), "")


def candidate_tests(tree: Path, probe: dict, cap: int = 8) -> dict[str, list[str]]:
    """Root -> test files (relative to the tree) that mention the module's stem and carry a ``covers`` mark. Textual, no coverage."""
    stem = Path(probe["file"]).stem
    pat = re.compile(rf"\b{re.escape(stem)}\b")
    found: dict[str, list[tuple[bool, str]]] = {}
    roots = [tree / r for r in ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests", "integration-tests")] + sorted((tree / "plugins").glob("*/tests"))
    for base in roots:
        for f in base.rglob("test_*.py"):
            if _SKIP_DIRS & set(f.parts):
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if "covers(" in text and pat.search(text):
                rel = f.relative_to(tree).as_posix()
                found.setdefault(_root_of_test(rel), []).append((stem in f.name, rel))
    return {root: [r for _n, r in sorted(files, key=lambda x: (not x[0], x[1]))][:cap] for root, files in found.items() if root}


def junit_failures(xml: Path, cwd: Path, prefix: str) -> set[str]:
    """Repo-relative ``path::name`` ids of failed or errored testcases (the longest classname prefix that is a file wins)."""
    out: set[str] = set()
    if not xml.is_file():
        return out
    for case in ET.parse(xml).getroot().iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        parts = [p for p in case.get("classname", "").split(".") if p]
        for i in range(len(parts), 0, -1):
            if (cwd / ("/".join(parts[:i]) + ".py")).is_file():
                cls = ".".join(parts[i:])
                out.add(f"{prefix}{'/'.join(parts[:i])}.py::{cls + '.' if cls else ''}{case.get('name', '')}")
                break
        else:
            out.add(f"?::{case.get('classname', '')}.{case.get('name', '')}")
    return out


def run_probe(tree: Path, root: str, files: list[str], out_dir: Path, env: dict, timeout: int) -> dict:
    junit = out_dir / f"probe-{root.replace('/', '_')}.xml"
    junit.unlink(missing_ok=True)
    pre = prefix_of(root)
    cwd = tree / pre.rstrip("/") if pre else tree
    marker = ["-m", "not slow and not cross_plugin"] if root.startswith("shared/") else []
    cmd = ["uv", "run", *_WITH, "pytest", *[f[len(pre):] for f in files], "-q", "-p", "no:cacheprovider", "--maxfail=20", f"--junitxml={junit}", *marker]
    started = time.monotonic()
    try:
        rc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        rc = -9
    return {"root": root, "rc": rc, "seconds": round(time.monotonic() - started, 1), "failed": sorted(junit_failures(junit, cwd, pre))}


def classify(probe: dict, tokens_of_failing: dict[str, bool], fr_attributed: bool, executed_any: bool, referenced: bool, ran: bool) -> str:
    """Cause for a probe: ``caught`` or why not."""
    if any(tokens_of_failing.values()):
        return "caught"
    if not ran:
        return "no_candidate_bound_test_references_module"
    if fr_attributed:
        return "bound_test_executes_but_assertion_survives"
    if executed_any:
        return "executed_only_by_unbound_tests"
    return "no_test_executes_it_in_process" if not referenced else "referenced_by_bound_test_but_not_executed_in_process"


def tokens_for(tree: Path, test_ids: set[str]) -> dict[str, bool]:
    """Failed test id -> whether it carries any covers binding."""
    cache: dict[str, dict] = {}
    out = {}
    for tid in test_ids:
        path, _, name = tid.partition("::")
        file = tree / path
        if str(file) not in cache:
            cache[str(file)] = index_tokens(file.read_text(encoding="utf-8", errors="replace")) if file.is_file() else {}
        base = re.split(r"[\[(]", tid.partition("::")[2])[0]  # Class.test_x[param] -> Class.test_x
        out[tid] = bool(cache[str(file)].get(base))
    return out


def draw(funcs: list[dict], n: int, seed: int) -> list[dict]:
    return random.Random(seed).sample(funcs, min(n, len(funcs)))
