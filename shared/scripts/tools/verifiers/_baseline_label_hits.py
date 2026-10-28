"""Per-hit labels for the REPLAY report (BP unit BL0, brief section 5 item 1).

A HIT is one ``(PR, FR, source)`` the replay reported. This module re-decides, from the raw git
content of the PR and WITHOUT the touched-set derivation, whether the source attributed it
correctly: the cited test really is bound to that FR (text of its ``covers`` marks) AND really
changed; the cited helper/conftest really changed AND an FR-bound test really reaches the changed
names; the FR's normative spec text really differs; the changed function really is executed by a
test bound to the FR. A hit that fails this check is ``wrong``.

Labels (provisional where intent is needed - that needs the operator, not a diff):
``wrong`` | ``correct-benign`` (the author declared the FR, so the hold is friction) |
``correct-undetermined`` (right FR, author did not declare it: harmful vs benign needs intent).
"""

from __future__ import annotations

import ast
import random
import re
from pathlib import Path

from ._baseline_touch_git import GitRev

__all__ = ["label_all", "label_test_hit", "label_static_hit", "label_spec_hit", "label_code_hit"]

_FR = re.compile(r"FR-\d+\.\d+")


def _tree(text: str | None):
    try:
        return ast.parse(text) if text else None
    except SyntaxError:
        return None


def _names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.add(n.value)
    return out


def _marks(tree: ast.Module) -> str:
    return "".join(ast.dump(n) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets))


def _test_nodes(tree: ast.Module):
    """``qualified name -> (dump of everything that defines the test, text that binds it to FRs)``."""
    out = {}
    marks = _marks(tree)

    def visit(body, prefix, cls_dump):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
                out[prefix + n.name] = (ast.dump(n) + cls_dump + marks, ast.dump(ast.Module(body=[], type_ignores=[])) + "".join(ast.dump(d) for d in n.decorator_list) + cls_dump + marks)
            elif isinstance(n, ast.ClassDef):
                members = "".join(ast.dump(m) for m in n.body if not (isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("test")))
                visit(n.body, prefix + n.name + ".", cls_dump + "".join(ast.dump(d) for d in n.decorator_list) + members)

    visit(tree.body, "", "")
    return out


def label_test_hit(rev: GitRev, fr: str, test_ids: list[str]) -> tuple[bool, str]:
    why = []
    for tid in test_ids:
        path, _, qual = tid.partition("::")
        old_t, new_t = _tree(rev.read(path, "base")), _tree(rev.read(path, "head"))
        old = _test_nodes(old_t).get(qual) if old_t else None
        new = _test_nodes(new_t).get(qual) if new_t else None
        if old is None and new is None:
            why.append(f"{tid}: not found on either side")
        elif not any(fr in x[1] for x in (old, new) if x):
            why.append(f"{tid}: not bound to {fr} by its covers text")
        elif old is None:
            why.append(f"{tid}: did not exist at base")
        elif new is None or old[0] != new[0]:
            return True, f"{tid}: bound to {fr} and {'deleted' if new is None else 'changed'}"
        else:
            why.append(f"{tid}: bound but unchanged")
    return False, "; ".join(why) or "no test cited"


def _top(tree: ast.Module) -> dict[str, str]:
    out = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[n.name] = ast.dump(n)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            for t in n.targets if isinstance(n, ast.Assign) else [n.target]:
                if isinstance(t, ast.Name) and t.id != "pytestmark":
                    out[t.id] = ast.dump(n)
    return out


def _effects(old: ast.Module, new: ast.Module) -> bool:
    """True when module-level statements (outside defs/assignments) or ``pytestmark`` changed in a way
    that can alter an existing test. Purely ADDED imports cannot (they exist for new code) and do not count."""
    keep = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign)
    pick = lambda t: [ast.dump(n) for n in t.body if not isinstance(n, keep)]  # noqa: E731
    a, b = pick(old), pick(new)
    if _marks(old) != _marks(new):
        return True
    added_only_imports = all(x in b for x in a) and all(isinstance(n, (ast.Import, ast.ImportFrom)) or ast.dump(n) in a
                                                         for n in new.body if not isinstance(n, keep))
    return a != b and not added_only_imports


def _wide(tree: ast.Module, changed: set[str]) -> bool:
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in changed:
            if n.name.startswith("pytest_") or "autouse=True" in "".join(ast.unparse(d) for d in n.decorator_list):
                return True
    return "pytest_plugins" in changed


def label_static_hit(rev: GitRev, fr: str, items: list[str]) -> tuple[bool, str]:
    why = []
    for item in items:
        x, _, y = item.partition(" (fixture/helper) -> ")
        y = x if y in ("same module", "") else y
        old_t, new_t, y_t = _tree(rev.read(x, "base")), _tree(rev.read(x, "head")), _tree(rev.read(y, "head"))
        if y_t is None:
            why.append(f"{item}: consumer unreadable")
            continue
        bound = {q: n for q, n in _test_nodes(y_t).items() if fr in n[1]}
        if not bound:
            why.append(f"{y}: no test bound to {fr}")
            continue
        if new_t is None or old_t is None:  # a conftest/helper that appeared or vanished reaches its whole directory
            return True, f"{x} {'deleted' if new_t is None else 'added'}; {y} has {len(bound)} test(s) bound to {fr}"
        a, b = _top(old_t), _top(new_t)
        changed = {n for n in set(a) | set(b) if a.get(n) != b.get(n)}
        if x == y:  # test module: only non-test statements count, the tests themselves are T-test
            changed = {n for n in changed if not n.startswith("test")}
        if _effects(old_t, new_t) or _wide(new_t, changed) or _wide(old_t, changed):
            return True, f"{x}: module-level/scope-wide change reaches {len(bound)} test(s) bound to {fr}"
        used = set().union(*(_names(ast.parse(ast.unparse(_node_of(y_t, q)))) for q in bound))
        for _ in range(8):  # follow helper -> helper references to a fixpoint
            grown = used | {m for nm in used & set(b) | used & set(a) for tree in (new_t, old_t) for m in _names(_def(tree, nm))}
            if grown == used:
                break
            used = grown
        if changed & used:
            return True, f"{x}: changed {sorted(changed & used)[:3]} used by a test bound to {fr} in {y}"
        why.append(f"{item}: changed names {sorted(changed)[:3]} not used by tests bound to {fr}")
    return False, "; ".join(why) or "no evidence cited"


def _node_of(tree: ast.Module, qual: str):
    parts = qual.split(".")
    body = tree.body
    for i, part in enumerate(parts):
        node = next(n for n in body if getattr(n, "name", None) == part)
        body = node.body
    return node


def _def(tree: ast.Module, name: str):
    return next((n for n in tree.body if getattr(n, "name", None) == name or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))), ast.Module(body=[], type_ignores=[]))


def _spec_lines(text: str | None, fr: str) -> set[str]:
    out: set[str] = set()
    section = False
    for line in (text or "").splitlines():
        if line.startswith("#"):
            section = fr in line
            continue
        if line.lstrip().startswith("|") and fr in line.split("|")[1:2][0]:
            cells = [c.strip() for c in line.strip().strip("|").split("|")][:5]  # ID..Description; Basis/Layers are bookkeeping
            line = "|".join(cells)
        elif not section:
            continue
        line = re.sub(r"\(inferred\)|\[AC\d+\]", "", line)
        norm = re.sub(r"\s+", " ", line).strip()
        if norm:
            out.add(norm)
    return out


def label_spec_hit(rev: GitRev, fr: str) -> tuple[bool, str]:
    for _s, _old, new in rev.changed():
        if new.endswith("spec.md"):
            a, b = _spec_lines(rev.read(new, "base"), fr), _spec_lines(rev.read(new, "head"), fr)
            if a != b:
                return True, f"{new}: {len(b - a)} line(s) added/changed, {len(a - b)} removed in {fr} text"
    return False, f"no spec.md changes the normative text of {fr}"


def label_code_hit(rev: GitRev, fr: str, funcs: list[str], contexts: dict, tid_to_fr) -> tuple[bool, str]:
    from ._baseline_touch_coverage import _spans

    for func in funcs:
        path, _, name = func.partition("::")
        base = rev.read(path, "base") or ""
        removed, _added = rev.line_changes(path, path)
        for sym, a, b in _spans(base):
            if sym == name and any(a <= ln <= b for ln in removed):
                tests = set().union(*(contexts.get(path, {}).get(ln, set()) for ln in range(a, b + 1)))
                bound = sorted(t for t in tests if tid_to_fr(t, fr))
                if bound:
                    return True, f"{func} changed; executed by {len(bound)} test(s) bound to {fr} (e.g. {bound[0]})"
    return False, f"no changed function is executed by a test bound to {fr}"


def _label(correct: bool, fr: str, declared: list[str]) -> str:
    if not correct:
        return "wrong"
    return "correct-benign" if fr in declared else "correct-undetermined"


def label_all(repo: Path, data: dict, workdir: Path | None, seed: int = 20261028, per_source: int = 5) -> None:
    """Add ``hits`` to every record and a ``measure.hit_labels`` block (counts, wrong per 100 PRs, sample)."""
    all_hits: list[dict] = []
    for rec in data["records"]:
        hits = []
        if rec.get("merge") and not rec.get("error"):
            rev = GitRev(repo, f"{rec['merge']}^", rec["merge"])
            for fr, srcs in sorted(rec["sources"].items()):
                for src in srcs:
                    if src == "test":
                        ok, why = label_test_hit(rev, fr, rec["evidence"]["test"].get(fr, []))
                    elif src == "static":
                        ok, why = label_static_hit(rev, fr, rec["evidence"]["static"].get(fr, []))
                    elif src == "spec":
                        ok, why = label_spec_hit(rev, fr)
                    else:
                        continue
                    hits.append({"fr": fr, "source": src, "label": _label(ok, fr, rec["declared"]), "reason": why})
        rec["hits"] = hits
        all_hits += [{"pr": rec["pr"], **h} for h in hits]
    all_hits += _code_hits(repo, data, workdir)
    by: dict[str, dict[str, int]] = {}
    for h in all_hits:
        by.setdefault(h["source"], {}).setdefault(h["label"], 0)
        by[h["source"]][h["label"]] += 1
    rng = random.Random(seed)
    sample = [h for src in sorted(by) for h in rng.sample([x for x in all_hits if x["source"] == src], min(per_source, sum(by[src].values())))]
    n_prs = len(data["records"])
    data.setdefault("measure", {})["hit_labels"] = {
        "rule": "wrong = the source attributed an FR the raw PR content does not support (see module docstring)",
        "hits": len(all_hits), "by_source": by, "prs": n_prs,
        "wrong_per_100_prs": {s: round(c.get("wrong", 0) * 100 / n_prs, 2) for s, c in by.items()},
        "limit_per_source_per_100_prs": 3, "sample_seed": seed, "sample": sample}


def _code_hits(repo: Path, data: dict, workdir: Path | None) -> list[dict]:
    from ._baseline_touch_coverage import load_contexts, merge_contexts

    out = []
    if workdir is None:  # no context databases: keep the code hits an earlier run stored, never drop them
        return [{"pr": e["pr"], **h} for e in (data.get("code") or {}).get("prs", []) for h in e.get("hits", [])]
    cache: dict[tuple[str, str], bool] = {}
    for entry in (data.get("code") or {}).get("prs", []):
        if not entry.get("code"):
            continue
        rec = next(r for r in data["records"] if r["pr"] == entry["pr"])
        rev = GitRev(repo, f"{rec['merge']}^", rec["merge"])
        dbs = sorted(Path(workdir).glob(f"cov-{entry['pr']}-*")) or sorted((Path(workdir) / "codeleg").glob(f"cov-{entry['pr']}-*"))
        if not dbs:  # silently labelling against no contexts would call every code hit wrong
            raise FileNotFoundError(f"no context databases cov-{entry['pr']}-* under {workdir}")
        ctx = merge_contexts([load_contexts(db, repo) for db in dbs])  # every tier ran from the repo root: no prefix

        def bound(tid: str, fr: str, rev=rev, cache=cache) -> bool:
            path, _, qual = tid.partition("::")
            key = (rev.head + tid, fr)
            if key not in cache:
                tree = _tree(rev.read(path, "base"))
                node = _test_nodes(tree).get(qual) if tree else None
                cache[key] = bool(node and fr in node[1])
            return cache[key]

        for fr, funcs in sorted(entry["code"].items()):
            ok, why = label_code_hit(rev, fr, funcs, ctx, bound)
            out.append({"pr": entry["pr"], "fr": fr, "source": "code", "label": _label(ok, fr, rec["declared"]), "reason": why})
        entry["hits"] = [{k: v for k, v in h.items() if k != "pr"} for h in out if h["pr"] == entry["pr"]]  # replace, never append
    return out
