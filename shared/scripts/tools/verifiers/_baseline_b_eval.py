"""Evaluate the pre-registered BL0b rules against the two blind labelers (BP unit BL0b, item 8). Rules are fixed in the spec; nothing here tunes them.

A (PR, FR) pair is CONFIRMED when both labelers said ``changed_behavior == yes`` for the PR and both name the FR. A yes-PR whose labelers
name no FR in common is "outside every FR" (listed, neither hit nor miss). Disagreement and ``unclear`` are listed, never counted.
A hit (a source named FR for PR) is WRONG only on a PR both labelers judged (both yes, or both no) when neither labeler names that FR;
a hit one labeler names and the other does not is DISPUTED (listed). Sources: BP = git leg + T-code at HEAD (N=5 applied).
"""

from __future__ import annotations

import math
import re

from ._baseline_b_summary import pr_sets

__all__ = ["evaluate"]


def _frs(label: dict) -> set[str]:
    return {m for f in label.get("affected_frs", []) for m in re.findall(r"FR-\d{2}\.\d{2}", f)}


def _wilson(k: int, n: int) -> list[float] | None:
    if not n:
        return None
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def evaluate(replay: dict, a: dict, la: dict, lb: dict) -> dict:
    sets = pr_sets(replay, a["phaseA"])
    held = a["phaseA"]["summary"]
    confirmed: dict[int, set[str]] = {}
    outside, disagree, unclear, agree_no, judged = [], [], [], [], {}
    for k in sorted(la, key=int):
        pr, x, y = int(k), la[k], lb[k]
        cx, cy = x["changed_behavior"], y["changed_behavior"]
        if "unclear" in (cx, cy):
            unclear.append(pr)
        elif cx != cy:
            disagree.append(pr)
        elif cx == "no":
            agree_no.append(pr)
            judged[pr] = (set(), set())
        else:
            judged[pr] = (_frs(x), _frs(y))
            common = _frs(x) & _frs(y)
            if common:
                confirmed[pr] = common
            else:
                outside.append({"pr": pr, "labeler_A_frs": sorted(_frs(x)), "labeler_B_frs": sorted(_frs(y))})
    pairs = {(pr, fr) for pr, frs in confirmed.items() for fr in frs}
    bp = lambda s: s["git"] | s["tcode"]  # noqa: E731
    src = {"git": lambda s: s["git"], "tcode_head": lambda s: s["tcode"], "path": lambda s: s["path"], "BP(git+tcode)": bp,
           "git+path": lambda s: s["git"] | s["path"]}
    found = {name: {(pr, fr) for pr, fr in pairs if fr in f(sets[pr])} for name, f in src.items()}
    recall = {n: {"found": len(v), "of": len(pairs), "rate": round(len(v) / len(pairs), 3) if pairs else None, "wilson95": _wilson(len(v), len(pairs))} for n, v in found.items()}

    wrong, disputed, right = {n: [] for n in src}, {n: [] for n in src}, {n: 0 for n in src}
    for n, f in src.items():
        for pr, (fa, fb) in judged.items():
            for fr in sorted(f(sets[pr])):
                if (pr, fr) in pairs:
                    right[n] += 1
                elif fr in fa | fb:
                    disputed[n].append([pr, fr])
                else:
                    wrong[n].append([pr, fr])
    benefit = sorted((pr, fr) for pr, fr in found["BP(git+tcode)"] if fr not in sets[pr]["declared"])
    benefit_by = {n: sorted(p for p, fr in found[n] if fr not in sets[p]["declared"]) for n in src}
    gain = round(recall["BP(git+tcode)"]["rate"] - recall["git+path"]["rate"], 3) if pairs else None
    hold = held["hold_scope_eq_declared_fr_level"]["git+tcode_head"]
    return {
        "labels": {"prs": len(la), "both_yes": len([1 for pr in judged if pr not in agree_no]), "both_no": agree_no, "disagree": disagree, "unclear_either": unclear,
                   "confirmed_pairs": len(pairs), "confirmed_prs": len(confirmed), "yes_pr_outside_every_fr": outside},
        "confirmed_pairs": sorted([pr, fr] for pr, fr in pairs),
        "recall_on_confirmed": recall, "hits_on_judged_prs": {n: {"confirmed": right[n], "wrong": len(wrong[n]), "disputed": len(disputed[n]), "wrong_list": wrong[n], "disputed_list": disputed[n]} for n in src},
        "rules": {
            "R-benefit": {"threshold": ">= 3 confirmed behaviour changes, FR not declared by the author, found by BP sources", "prs": sorted({p for p, _ in benefit}), "pairs": benefit,
                          "by_source_prs": benefit_by, "result": "PASS" if len({p for p, _ in benefit}) >= 3 else "FAIL"},
            "R-recall": {"threshold": ">= 70 % of confirmed pairs found by BP sources", "denominator_pairs": len(pairs), "found": recall["BP(git+tcode)"], "result": "PASS" if pairs and recall["BP(git+tcode)"]["rate"] >= 0.7 else "FAIL",
                         "caveat": f"{len(pairs)} pairs on {len(confirmed)} PRs: the 95 % interval is {recall['BP(git+tcode)']['wilson95']}"},
            "R-T-code-value": {"threshold": "recall(git+T-code) - recall(git+path) >= 0.20", "git_plus_tcode": recall["BP(git+tcode)"]["rate"], "git_plus_path": recall["git+path"]["rate"], "gain": gain,
                               "result": "PASS" if gain is not None and gain >= 0.2 else "FAIL"},
            "R-precision": {"threshold": "<= 3 wrong hits per 100 PRs", "wrong_hits_on_the_35_labeled_prs": len(wrong["BP(git+tcode)"]), "labeled_prs": len(la), "window_prs": 100,
                            "note": "the other 65 PRs are unlabeled, so the true count can only be higher; disputed hits are not counted", "result": "PASS" if len(wrong["BP(git+tcode)"]) <= 3 else "FAIL"},
            "R-cost": {"threshold": "<= 20 % of PRs held when scope equals the declared FRs", "fr_level_held_of_100": hold, "ac_level_held_of_100": held["ac_level"]["hold_scope_eq_declared_ac_level"],
                       "git_leg_only_held_of_100": held["hold_scope_eq_declared_fr_level"]["git"], "holds_per_week_git_plus_tcode": held["hold_per_week_scope_eq_declared"]["git+tcode_head"],
                       "result": "PASS" if hold <= 20 else "FAIL"},
        },
    }
