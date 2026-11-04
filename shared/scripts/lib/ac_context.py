"""Context lines for the operator's question, computed by code (never by a model): what the change affects, what the catalog already says.

* **Affects** - the changed paths (the working-tree diff plus the files an item declares) that sit under ``plugins/<name>/`` are named in
  everyday words. Fail-closed: a path under a plugin this table does not know omits the whole line; the line is never guessed.
* **Cross-cutting** - a change that touches two or more plugins is not one area's promise.
* **Already in the catalog** - the requirements whose title or criteria contain the same two-word phrase as the promise.
* **Meaningfully different** - a model's plain wording is shown only when it shares fewer than 3 in 4 of its words with the original.

Stdlib only.
"""

from __future__ import annotations

import re

__all__ = ["PLUGIN_NAMES", "affects_line", "differs", "is_cross_cutting", "plugins_touched", "related_titles"]

PLUGIN_NAMES = {
    "shipwright-run": "Orchestrator", "shipwright-project": "Requirements breakdown", "shipwright-design": "Design mockups",
    "shipwright-plan": "Planning", "shipwright-build": "Build phase", "shipwright-test": "Test phase",
    "shipwright-security": "Security checks", "shipwright-deploy": "Deployment", "shipwright-changelog": "Changelog and releases",
    "shipwright-compliance": "Compliance evidence", "shipwright-iterate": "Iterate", "shipwright-preview": "Local preview",
    "shipwright-adopt": "Adopting an existing project", "shipwright-grade": "Control grade",
}
SAME_ENOUGH = 0.75  # word overlap at or above which a "plain wording" says nothing new
_STOP = frozenset("this that with from when then given have been will into than their there which what where while must does each also only more some such over under after before about other without within".split())
_COMMON = 4  # a phrase found in more areas than this says nothing about any one of them


def plugins_touched(paths: object) -> list[str]:
    """The plugin directory names under ``plugins/`` that ``paths`` touch, sorted (any slash style, any case of garbage tolerated)."""
    found = set()
    for p in paths if isinstance(paths, (list, tuple, set)) else []:
        parts = str(p).replace("\\", "/").strip("/").split("/")
        if len(parts) > 2 and parts[0] == "plugins" and parts[1]:
            found.add(parts[1])
    return sorted(found)


def affects_line(paths: object) -> str:
    """``Affects: Build phase, Iterate.`` or an empty string when nothing is touched or any touched plugin has no plain name."""
    touched = plugins_touched(paths)
    if not touched or any(t not in PLUGIN_NAMES for t in touched):
        return ""
    return "Affects: " + ", ".join(PLUGIN_NAMES[t] for t in touched) + "."


def is_cross_cutting(paths: object) -> bool:
    return len(plugins_touched(paths)) >= 2


def _tokens(text: str) -> list[str]:
    return [w[:-1] if w.endswith("s") and len(w) > 4 else w for w in re.findall(r"[a-z0-9]+", str(text).lower())]


def differs(original: str, plain: str) -> bool:
    """True when ``plain`` is meaningfully different from ``original`` (word overlap, Jaccard, below :data:`SAME_ENOUGH`)."""
    a, b = set(_tokens(original)), set(_tokens(plain))
    return bool(a | b) and len(a & b) / len(a | b) < SAME_ENOUGH


def related_titles(text: str, cat: dict, limit: int = 3) -> list[str]:
    """Titles of the requirements that contain a two-word phrase of ``text`` (both words significant, side by side); best first, empty when none."""
    toks = _tokens(text)
    phrases = {f"{a} {b}" for a, b in zip(toks, toks[1:]) if all(len(w) >= 4 and w not in _STOP for w in (a, b))}
    if not phrases:
        return []
    pool: dict[str, str] = {fr: " " + " ".join(_tokens(title)) for fr, title in cat.get("titles", {}).items()}
    for ac, body in cat.get("acs", {}).items():
        fr = ac.rsplit(".AC", 1)[0]
        pool[fr] = pool.get(fr, "") + " | " + " ".join(_tokens(body))  # "|" keeps a phrase from running across two sentences
    hits: dict[str, set[str]] = {}
    for fr, blob in pool.items():
        for ph in phrases:
            if f" {ph} " in f"{blob} ":
                hits.setdefault(ph, set()).add(fr)
    score: dict[str, int] = {}
    for ph, frs in hits.items():
        if len(frs) <= _COMMON:
            for fr in frs:
                score[fr] = score.get(fr, 0) + 1
    ranked = sorted(score, key=lambda fr: (-score[fr], fr))
    return [t for fr in ranked if (t := " ".join(str(cat.get("titles", {}).get(fr, "")).split()))][:limit]
