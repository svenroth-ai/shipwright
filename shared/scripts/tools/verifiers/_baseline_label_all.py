"""Per-hit labelling over the whole replay (BP unit BL0): applies ``_baseline_label_hits`` to every stored hit
(re-deriving the UNTRUNCATED evidence at each merge commit), labels the T-code hits from the context databases,
and writes ``records[].hits`` plus the ``measure.hit_labels`` block. Idempotent: a rerun replaces, never appends."""

from __future__ import annotations

import random
from pathlib import Path

from ._baseline_label_hits import _test_nodes, _tree, fr_in, label_spec_hit, label_static_hit, label_test_hit
from ._baseline_touch_core import touched_set
from ._baseline_touch_git import GitRev

__all__ = ["label_all", "label_code_hit"]


def _changed_functions(rev: GitRev, path: str) -> dict[str, tuple[int, int]]:
    """Functions of ``path`` (by name, with their BASE span) that the diff changes: a removed or replaced base
    line, or an ADDED head line inside a function that also exists at base (a pure insertion changes it too).
    Follows a rename to the new path, as ``code_touched`` does."""
    from ._baseline_touch_coverage import _enclosing, _spans, enclosing_base_function, meaningful_lines

    new = next((n for _s, o, n in rev.changed() if o == path), path)
    base_text, head_text = rev.read(path, "base") or "", rev.read(new, "head") or ""
    removed, added = meaningful_lines(*rev.line_changes(path, new), base_text, head_text)
    b_spans, h_spans = _spans(base_text), _spans(head_text)
    out: dict[str, tuple[int, int]] = {}
    for ln in removed:
        sp = _enclosing(b_spans, ln)
        if sp:
            out[sp[0]] = (sp[1], sp[2])
    for ln in added:
        kind, sp = enclosing_base_function(b_spans, h_spans, ln)
        if kind == "base":
            out[sp[0]] = (sp[1], sp[2])
    return out


def label_code_hit(rev: GitRev, fr: str, funcs: list[str], contexts: dict, tid_to_fr) -> tuple[bool, str]:
    for func in funcs:
        path, _, name = func.partition("::")
        span = _changed_functions(rev, path).get(name)
        if span:
            tests = set().union(*(contexts.get(path, {}).get(ln, set()) for ln in range(span[0], span[1] + 1)))
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
            full = touched_set(rev)  # untruncated evidence: the recorded lists keep only the first few ids
            for fr, srcs in sorted(rec["sources"].items()):
                for src in srcs:
                    if src == "test":
                        ok, why = label_test_hit(rev, fr, sorted(full.test.get(fr, ())))
                    elif src == "static":
                        ok, why = label_static_hit(rev, fr, sorted(full.static.get(fr, ())))
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
    n_code = len((data.get("code") or {}).get("prs", [])) or n_prs  # T-code hits are per 100 PRs of ITS sample
    data.setdefault("measure", {})["hit_labels"] = {
        "rule": "mechanical consistency check: wrong = the evidence, re-derived untruncated at the merge commit, does not support the hit. "
                "It is not the brief's semantic 'wrong'; the 3-per-100 bar can only be judged from the operator's re-label of the sample",
        "hits": len(all_hits), "by_source": by, "prs": n_prs, "code_sample_prs": n_code,
        "wrong_per_100_prs": {s: round(c.get("wrong", 0) * 100 / (n_code if s == "code" else n_prs), 2) for s, c in by.items()},
        "limit_per_source_per_100_prs": 3, "sample_seed": seed, "sample": sample}


def _code_hits(repo: Path, data: dict, workdir: Path | None) -> list[dict]:
    from ._baseline_touch_replay_code import pr_contexts

    out = []
    if workdir is None:  # no context databases: keep the code hits an earlier run stored, never drop them
        return [{"pr": e["pr"], **h} for e in (data.get("code") or {}).get("prs", []) for h in e.get("hits", [])]
    cache: dict[tuple[str, str], bool] = {}
    for entry in (data.get("code") or {}).get("prs", []):
        if not entry.get("code"):
            continue
        rec = next((r for r in data["records"] if r["pr"] == entry["pr"]), None)
        if rec is None:
            raise KeyError(f"code entry for PR #{entry['pr']} has no record")
        rev = GitRev(repo, f"{rec['merge']}^", rec["merge"])
        ctx = pr_contexts(repo, Path(workdir), entry["pr"])

        def bound(tid: str, fr: str, rev=rev, cache=cache) -> bool:
            path, _, qual = tid.partition("::")
            key = (rev.head + tid, fr)
            if key not in cache:
                tree = _tree(rev.read(path, "base"))
                node = _test_nodes(tree).get(qual) if tree else None
                cache[key] = bool(node and fr_in(fr, node[1]))
            return cache[key]

        for fr, funcs in sorted(entry["code"].items()):
            ok, why = label_code_hit(rev, fr, funcs, ctx, bound)
            out.append({"pr": entry["pr"], "fr": fr, "source": "code", "label": _label(ok, fr, rec["declared"]), "reason": why})
        entry["hits"] = [{k: v for k, v in h.items() if k != "pr"} for h in out if h["pr"] == entry["pr"]]  # replace, never append
    return out
