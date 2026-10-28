"""Phase-A figures of BL0b, recomputed from the REPLAY records and the ``phaseA.*`` keys (no git, no tests).

Every figure the hand-back and the report cite comes out of ``summarise_phase_a``; ``bl0b_analyze.py summary`` writes it
under ``phaseA.summary``. "Declared" is the author's ``affected_frs`` and is NOT independent ground truth (written at F5b
after the diff exists); it is only a reference until the blind labels exist.
"""

from __future__ import annotations

import statistics
from collections import Counter

__all__ = ["summarise_phase_a", "pr_sets", "pair_scores"]

N_BROAD = 5  # the REPLAY report's proposed threshold


def pr_sets(replay: dict, a: dict) -> dict[int, dict]:
    """Per PR: the FR sets of each source (existing FRs only) for the git leg, T-code at HEAD and the path baseline."""
    out: dict[int, dict] = {}
    for rec in replay["records"]:
        key, new = str(rec["pr"]), set(rec.get("new_frs", []))
        head = a["headmap"]["per_pr"].get(key, {"touched": {}, "fan_out": {}})
        broad = {k for k, frs in head["fan_out"].items() if len(frs) > N_BROAD}
        tcode = {fr for fr, keys in head["touched"].items() if fr not in new and not set(keys) <= broad}
        out[rec["pr"]] = {"git": set(rec["sources"]), "tcode": tcode, "tcode_all": set(head["touched"]) - new, "path": set(a["paths"]["per_pr"].get(key, {})) - new,
                          "declared": set(rec["declared"]), "class": rec["class"]}
    return out


def pair_scores(sets: dict[int, dict], source, truth, prs=None) -> dict:
    """Recall and precision of ``source(set)`` against ``truth(set)`` over (PR, FR) pairs."""
    tp = fp = fn = 0
    for pr, s in sets.items():
        if prs is not None and pr not in prs:
            continue
        pred, true = source(s), truth(s)
        tp, fp, fn = tp + len(pred & true), fp + len(pred - true), fn + len(true - pred)
    return {"tp": tp, "fp": fp, "fn": fn, "recall": round(tp / (tp + fn), 3) if tp + fn else None, "precision": round(tp / (tp + fp), 3) if tp + fp else None}


def _head_errors(a: dict) -> dict:
    kinds = Counter(n["kind"] for v in a["headmap"]["per_pr"].values() for n in v["notes"])
    mapped = sum(len(v["fan_out"]) for v in a["headmap"]["per_pr"].values())
    total = mapped + sum(v for k, v in kinds.items() if k in ("missing_at_head", "no_test", "only_unbound_tests", "no_coverage", "unreadable"))
    unresolved = kinds["missing_at_head"] + kinds["unreadable"]
    return {"changed_production_functions": total, "mapped_to_an_fr": mapped, "notes_by_kind": dict(sorted(kinds.items())), "missing_at_head": kinds["missing_at_head"],
            "unresolved_rate": round(unresolved / total, 3) if total else None, "pr_with_unresolved": sum(1 for v in a["headmap"]["per_pr"].values() if any(n["kind"] in ("missing_at_head", "unreadable") for n in v["notes"]))}


def _crosscheck(replay: dict, a: dict) -> dict:
    """Stored merge-base T-code results (20 PRs) against the HEAD mapping, per (PR, FR) pair and per changed function."""
    rows, agree, only_old, only_head = [], 0, 0, 0
    fn_old = fn_both = 0
    for pr in (replay.get("code") or {}).get("prs", []):
        old = {fr for fr in (pr.get("code") or {})}
        old_fn = set(pr.get("fan_out") or {})
        head = a["headmap"]["per_pr"].get(str(pr["pr"]), {"touched": {}, "fan_out": {}})
        new = set(head["touched"])
        agree, only_old, only_head = agree + len(old & new), only_old + len(old - new), only_head + len(new - old)
        new_fn = set(head["fan_out"])
        fn_old, fn_both = fn_old + len(old_fn), fn_both + len(old_fn & new_fn)
        rows.append({"pr": pr["pr"], "merge_base": sorted(old), "head": sorted(new)})
    union = agree + only_old + only_head
    return {"prs": len(rows), "pairs_agree": agree, "pairs_only_merge_base": only_old, "pairs_only_head": only_head,
            "disagreement_rate": round((only_old + only_head) / union, 3) if union else None,
            "merge_base_pairs_missed_at_head_rate": round(only_old / (agree + only_old), 3) if agree + only_old else None,
            "changed_functions_merge_base": fn_old, "of_which_attributed_at_head_too": fn_both, "rows": rows}


def summarise_phase_a(replay: dict, a: dict, strata: dict[str, str]) -> dict:
    sets = pr_sets(replay, a)
    git = lambda s: s["git"]  # noqa: E731 - tiny selectors keep the table below readable
    union_t = lambda s: s["git"] | s["tcode"]  # noqa: E731
    union_p = lambda s: s["git"] | s["path"]  # noqa: E731
    dec = lambda s: s["declared"]  # noqa: E731
    with_dec = {pr for pr, s in sets.items() if s["declared"]}
    declared_only = {int(p) for p, k in strata.items() if k == "declared_only_behaviour"}
    nc = {str(p): v["new_code"] for p, v in a["headmap"]["per_pr"].items()}
    held = lambda src, scope: sum(1 for s in sets.values() if src(s) - (s["declared"] if scope else set()))  # noqa: E731
    per_week = lambda n: round(n / (28 / 7), 2)  # noqa: E731 - window 2026-10-02 .. 2026-10-28 is 27 days
    sources = {"git": git, "path": lambda s: s["path"], "tcode_head": lambda s: s["tcode"], "git+path": union_p, "git+tcode_head": union_t, "git+tcode+path": lambda s: s["git"] | s["tcode"] | s["path"]}
    ac_units = {}
    for pr, per in a["ac_git_leg"].items():
        toks = {t for kind in per.values() for t in kind}
        toks |= {t for keys in a["headmap"]["per_pr"].get(pr, {}).get("tokens", {}).values() for t in keys}
        ac_units[int(pr)] = toks
    held_ac = {pr: t for pr, t in ac_units.items() if t or sets[pr]["git"] or sets[pr]["tcode"]}
    explicit = sum(1 for t in held_ac.values() for x in t if "/AC" in x)
    bare = sum(1 for t in held_ac.values() for x in t if "/AC" not in x)
    per_pr_acs = [len({x for x in t if "/AC" in x}) for t in held_ac.values()]
    ac_declared_hold = sum(1 for pr, t in ac_units.items() if any(x.split("/")[0] not in sets[pr]["declared"] for x in t) or (sets[pr]["git"] | sets[pr]["tcode"]) - sets[pr]["declared"])
    return {
        "head_mapping": _head_errors(a), "crosscheck_vs_merge_base_db": _crosscheck(replay, a),
        "prs_with_fr_by_source": {k: sum(1 for s in sets.values() if f(s)) for k, f in sources.items()},
        "vs_declared_reference_45_prs": {k: pair_scores(sets, f, dec, with_dec) for k, f in sources.items()},
        "tcode_added_beyond_git": {"prs": sum(1 for s in sets.values() if s["tcode"] - s["git"]), "pairs": sum(len(s["tcode"] - s["git"]) for s in sets.values()),
                                   "pairs_declared": sum(len((s["tcode"] - s["git"]) & s["declared"]) for s in sets.values())},
        "declared_only_16": {"prs": sorted(declared_only), "tcode_head_finds_a_declared_fr": sorted(p for p in declared_only if sets[p]["tcode"] & sets[p]["declared"]),
                             "path_finds_a_declared_fr": sorted(p for p in declared_only if sets[p]["path"] & sets[p]["declared"]),
                             "new_code_class": dict(Counter(nc[str(p)]["class"] for p in declared_only)), "new_code_class_by_pr": {str(p): nc[str(p)]["class"] for p in sorted(declared_only)}},
        "new_code_class_all_100": dict(Counter(v["class"] for v in nc.values())),
        "hold_empty_scope": {k: held(f, False) for k, f in sources.items()},
        "hold_scope_eq_declared_fr_level": {k: held(f, True) for k, f in sources.items()},
        "hold_per_week_scope_eq_declared": {k: per_week(held(f, True)) for k, f in sources.items()},
        "ac_level": {"prs_with_any_touch": len(held_ac), "explicit_ac_tokens": explicit, "fr_wide_tokens": bare, "median_acs_per_touching_pr": statistics.median(per_pr_acs) if per_pr_acs else None,
                     "max_acs_per_touching_pr": max(per_pr_acs, default=0), "hold_scope_eq_declared_ac_level": ac_declared_hold,
                     "note": "the author declares FRs, never ACs, so a declared scope approves all ACs of an FR: the AC-level hold equals the FR-level hold by construction; the AC level changes the size of what an approval covers, not who is held"},
    }
