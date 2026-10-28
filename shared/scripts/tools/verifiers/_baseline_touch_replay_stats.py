"""Aggregation for the baseline replay (BP unit BL0): rates, per-class hold, agreement, sample.

Pure functions over the per-PR records ``replay_baseline_lock.py`` produces, so the numbers in
the REPLAY report are reproducible from the JSON alone and testable without git or ``gh``.
"""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict

__all__ = ["pr_class", "declared_frs", "summarise", "sample_for_operator"]

_RULES = (
    ("release", lambda b, t: b.startswith("release/") or re.match(r"^(chore\(release\)|release[:(\s])", t, re.I)),
    ("layer-promotion", lambda b, t: re.search(r"promot", t, re.I) and re.search(r"layer", t, re.I)),
    ("revert", lambda b, t: t.lower().startswith("revert")),
    ("dependency-bot", lambda b, t: b.startswith(("dependabot/", "renovate/"))),
    ("campaign-unit", lambda b, t: "campaign-" in b),
    ("docs", lambda b, t: b.startswith("docs/") or re.match(r"^docs[(:]", t, re.I)),
    ("iterate", lambda b, t: b.startswith("iterate/")),
)


def pr_class(branch: str, title: str) -> str:
    for name, rule in _RULES:
        if rule(branch or "", title or ""):
            return name
    return "manual"


def declared_frs(event: dict | None) -> tuple[list[str], str]:
    """The FRs the author declared: ``fr_impact`` (add/modify/remove), else ``affected_frs``, else none."""
    if not event:
        return [], "no-event"
    impact = event.get("fr_impact")
    if isinstance(impact, dict) and impact:
        return sorted(fr for fr, kind in impact.items() if kind in ("add", "modify", "remove")), "fr_impact"
    affected = event.get("affected_frs")
    if isinstance(affected, list) and affected:
        return sorted(str(a) for a in affected), "affected_frs"
    return [], "none"


def summarise(records: list[dict]) -> dict:
    ok = [r for r in records if not r.get("error")]
    n = len(ok)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in ok:
        by_class[r["class"]].append(r)
    held = [r for r in ok if r["held"]]
    src_hits: Counter = Counter()
    src_declared: Counter = Counter()
    for r in ok:
        for fr, sources in r["sources"].items():
            for s in sources:
                src_hits[s] += 1
                src_declared[s] += fr in r["declared"]
    touched_nonempty = [r for r in ok if r["sources"]]
    with_fr_impact = [r for r in ok if r["declared_from"] == "fr_impact"]
    return {
        "prs": len(records), "prs_ok": n, "errors": [r["pr"] for r in records if r.get("error")],
        "touched_nonempty": len(touched_nonempty),
        "touched_nonempty_rate": round(len(touched_nonempty) / n, 3) if n else None,
        "with_fr_impact": len(with_fr_impact),
        "with_declared_any": sum(1 for r in ok if r["declared_from"] in ("fr_impact", "affected_frs")),
        "held": len(held), "hold_rate": round(len(held) / n, 3) if n else None,
        "hold_by_class": {c: {"prs": len(rs), "held": sum(r["held"] for r in rs),
                              "rate": round(sum(r["held"] for r in rs) / len(rs), 3)} for c, rs in sorted(by_class.items())},
        "hits_by_source": {s: {"hits": src_hits[s], "also_declared": src_declared[s]} for s in sorted(src_hits)},
        "derived_only_prs": sum(1 for r in ok if r["sources"] and not set(r["sources"]) & set(r["declared"])),
        "declared_only_prs": sum(1 for r in ok if r["declared"] and not r["sources"]),
        "agree_prs": sum(1 for r in ok if r["sources"] and set(r["sources"]) & set(r["declared"])),
        "frs_per_touching_pr": sorted(len(r["sources"]) for r in touched_nonempty),
        "incomplete_prs": [r["pr"] for r in ok if r["incomplete"]],
        "moved_prs": sum(1 for r in ok if r["moved"]),
    }


def sample_for_operator(records: list[dict], k: int = 15, seed: int = 20261028) -> list[dict]:
    """A reproducible random sample of held PRs, for the operator to re-label at stop 1."""
    held = sorted((r for r in records if r.get("held") and not r.get("error")), key=lambda r: r["pr"])
    return random.Random(seed).sample(held, min(k, len(held)))
