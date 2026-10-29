"""T-code from ONE context run at a recent commit, mapped to historical changes by qualified name (BP unit BL0b, item 2),
and the "new code" classes (item 4).

The BL0 replay ran contexts at each PR's merge base (20 PRs, four tiers). Here one run at HEAD serves every PR: a function
changed in an old PR is looked up in the HEAD file by its qualified name (``Class.method``) and attributed to the FRs of the
HEAD tests that execute any line of it. A function absent at HEAD (renamed, deleted, file moved) is reported as
``missing_at_head`` for a merge-base fallback; nothing is guessed. Test bindings are read at HEAD, not at the PR's base.

New code (item 4): (a) new code that a MODIFIED base function reaches (it calls a new function, or imports a new file) is
counted through that caller; (b) new code nothing at base calls is additive: listed, never held. A PR's own new tests are
never used to attribute anything: the HEAD run is a different commit and only reads bindings of tests that exist there,
and for a new function the lookup is by caller, not by tests.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ._baseline_touch_binding import _module_covers, _walk
from ._baseline_touch_coverage import _enclosing, _spans, enclosing_base_function, meaningful_lines
from ._baseline_touch_git import GitRev, is_test_path
from ._tag_binding_py import _FUNC, _covers, parse

__all__ = ["HeadMapper", "index_tokens", "new_code_class"]

_TOKEN = re.compile(r"^FR-\d{2}\.\d{2}(?:/AC\d+)?$")


def index_tokens(text: str) -> dict[str, frozenset[str]]:
    """``test name -> raw covers tokens`` (``FR-01.09`` or ``FR-01.09/AC03``), own + class + module marks."""
    tree = parse(text)
    if tree is None:
        return {}
    found: list = []
    _walk(tree.body, "", (), found, _module_covers(tree), set())
    return {name: frozenset(t for t in _covers(list(fn.decorator_list)) | inherited if _TOKEN.match(t)) for name, fn, _c, inherited in found}


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def _defs(text: str) -> set[str]:
    tree = parse(text)
    return {n.name for n in (tree.body if tree else []) if isinstance(n, (ast.ClassDef, *_FUNC))}


class HeadMapper:
    def __init__(self, tree: Path, contexts: dict[str, dict[int, set[str]]]) -> None:
        self.tree, self.contexts = Path(tree), contexts
        self._tokens: dict[str, frozenset[str]] = {}
        self._test_index: dict[str, dict[str, frozenset[str]]] = {}

    def tokens_of(self, test_id: str) -> frozenset[str]:
        path, _, name = test_id.partition("::")
        if path not in self._test_index:
            file = self.tree / path
            self._test_index[path] = index_tokens(file.read_text(encoding="utf-8", errors="replace")) if file.is_file() else {}
        return self._test_index[path].get(name, frozenset())

    def _lookup(self, rel: str, func: str, text: str):
        """(kind, tests) for one function at HEAD: kinds ``missing_at_head`` / ``no_test`` / ``ok``."""
        span = next((s for s in _spans(text) if s[0] == func), None)
        if span is None:
            return "missing_at_head", set()
        lines = self.contexts.get(rel, {})
        tests = set().union(*(lines.get(ln, set()) for ln in range(span[1], span[2] + 1)))
        return ("ok" if tests else "no_test"), tests

    def map_pr(self, rev: GitRev, changes: list[tuple[str, str, str]]) -> dict:
        """Changed production functions of one PR attributed through the HEAD run. ``fan_out_tokens`` keeps AC tokens."""
        out: dict = {"fan_out": {}, "tokens": {}, "notes": [], "modified_base_funcs": [], "new_funcs": [], "new_files": [], "callers": {}, "added_imports": []}
        for status, old, new in changes:
            if status == "D" or not new.endswith(".py") or is_test_path(new):
                if status == "D" and old.endswith(".py") and not is_test_path(old):
                    out["notes"].append({"kind": "file_deleted", "key": old})
                continue
            if status == "A":
                out["new_files"].append(new)
                continue
            base_text, head_text = rev.read(old, "base"), rev.read(new, "head")
            if base_text is None or head_text is None:
                out["notes"].append({"kind": "unreadable", "key": old})
                continue
            removed, added = meaningful_lines(*rev.line_changes(old, new), base_text, head_text)
            if not removed and not added:
                continue
            src = head_text.splitlines()
            for ln in added:
                if 0 < ln <= len(src) and re.match(r"\s*(from|import)\s", src[ln - 1]):
                    out["added_imports"] += re.findall(r"[A-Za-z_]\w*", src[ln - 1])
            b_spans, h_spans = _spans(base_text), _spans(head_text)
            funcs: set[str] = set()
            for ln in removed:
                span = _enclosing(b_spans, ln)
                funcs.add(span[0] if span else "<module>")
            for ln in added:
                kind, where = enclosing_base_function(b_spans, h_spans, ln)
                if kind == "base":
                    funcs.add(where[0])
                elif kind == "new":
                    out["new_funcs"].append(f"{new}::{where}")
                else:
                    funcs.add("<module>")
            rel = next((p for p in (new, old) if (self.tree / p).is_file()), None)
            cur = (self.tree / rel).read_text(encoding="utf-8", errors="replace") if rel else ""
            head_nodes = {n.name: n for n in ast.walk(parse(head_text)) if isinstance(n, _FUNC)} if parse(head_text) else {}
            for func in sorted(funcs):
                key = f"{old}::{func}"
                if func == "<module>":
                    out["notes"].append({"kind": "module_level", "key": key})
                    continue
                out["modified_base_funcs"].append(key)
                leaf = func.rsplit(".", 1)[-1]
                if leaf in head_nodes:
                    out["callers"][key] = sorted(_names(head_nodes[leaf]))
                if rel is None:
                    out["notes"].append({"kind": "missing_at_head", "key": key, "why": "file not at HEAD"})
                    continue
                if rel not in self.contexts:
                    out["notes"].append({"kind": "no_coverage", "key": key})
                    continue
                kind, tests = self._lookup(rel, func, cur)
                if kind != "ok":
                    out["notes"].append({"kind": kind, "key": key})
                    continue
                toks = {t for test in tests for t in self.tokens_of(test)}
                if not toks:
                    out["notes"].append({"kind": "only_unbound_tests", "key": key})
                    continue
                out["tokens"][f"{rel}::{func}"] = sorted(toks)
                out["fan_out"][f"{rel}::{func}"] = sorted({t.split("/")[0] for t in toks})
        out["touched"] = {}
        for key, frs in out["fan_out"].items():
            for fr in frs:
                out["touched"].setdefault(fr, []).append(key)
        return out


def new_code_class(rev: GitRev, mapped: dict) -> dict:
    """Item 4. ``a``: new code a modified base function reaches (counted through that caller); ``b``: additive only; ``none``."""
    new_symbols: dict[str, str] = {}
    for path in mapped["new_files"]:
        text = rev.read(path, "head") or ""
        new_symbols[Path(path).stem] = path
        for name in _defs(text):
            new_symbols.setdefault(name, path)
    for item in mapped["new_funcs"]:
        file, _, qual = item.partition("::")
        new_symbols.setdefault(qual.rsplit(".", 1)[-1], file)
    if not new_symbols:
        return {"class": "none", "reached_via": {}, "symbols": 0}
    reached: dict[str, list[str]] = {}
    for caller, names in mapped["callers"].items():
        for sym, where in new_symbols.items():
            if sym in names:
                reached.setdefault(sym, []).append(caller)
    for stem, path in list(new_symbols.items()):  # a new FILE imported by a modified base file's added import line
        if stem == Path(path).stem and stem in mapped["added_imports"]:
            reached.setdefault(stem, []).append("<module imports it>")
    return {"class": "a" if reached else "b", "reached_via": {k: sorted(set(v))[:3] for k, v in sorted(reached.items())},
            "symbols": len(new_symbols), "new_files": len(mapped["new_files"]), "new_funcs": len(mapped["new_funcs"])}
