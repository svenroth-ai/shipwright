"""Can this requirement still be split? Group the criteria of ONE FR by what they actually share.

The rule (``shared/fr-authoring.md`` §3c): one FR names ONE capability. The AC count is only a symptom (20 criteria can be
one capability, 8 can be two), so this module never uses a count as a rule. It looks for SEAMS in code evidence:

* **bound tests** - two criteria named by the same test, or by tests in the same test file, belong together;
* **touched files** - two criteria whose tests import the same source module belong together (a module that the tests of
  many different FRs import is a repo-wide utility, a hub, and joins nothing);
* **vocabulary** - two criteria that share several distinctive words belong together.

Criteria joined by any of these form one cluster. Verdict per FR:

* ``yes``        - at least half of the FR's criteria are bound to tests AND two or more GROUPS (each of at least three
  criteria) share no test, test file, source file or vocabulary with each other: splittable;
* ``no``         - fewer than two such groups: the evidenced criteria are one connected cluster, or one cluster plus loose
  single criteria. It stays whole, however many criteria it has;
* ``partial evidence`` - fewer than half of the criteria are bound to tests: code cannot say;
* ``no evidence``- fewer than two criteria are bound to any test, so code cannot say. Never a guess: the AI capability test
  (one plain sentence without "and") is then the only judge, and the operator confirms every cut.

A criterion that no other evidenced criterion shares anything with is **loose**, listed apart and never counted as a group.

Criteria with no bound test never form a cluster of their own; they are attached to the cluster whose wording they share
most, else listed as ``unassigned``. Clusters show what is connected in code, not what is one capability: two promises that
share a test can still be two capabilities, so code proposes and a person confirms.

Pure and stdlib-only (loadable by the audit's sentinel loader, ADR-045): the inputs are plain dicts, see :func:`cluster_fr`.
"""

from __future__ import annotations

import re
from itertools import combinations

__all__ = ["VERDICT_NO", "VERDICT_NONE", "VERDICT_PARTIAL", "VERDICT_YES", "cluster_fr", "cluster_frs", "hub_files", "vocabulary"]

_STOP = frozenset("this that with from when then given have been will into than their there which what where while must does each also only more some such over under after before about other without within should them they being again same both".split())
_HUB_MIN_FRS = 4  # a source file touched by the tests of at least this many FRs ...
_HUB_SHARE = 0.25  # ... and of this share of all FRs with evidence is a repo-wide utility, not a seam
_VOCAB_MIN_SHARED = 3
_VOCAB_MIN_JACCARD = 0.3
_ATTACH_MIN_SHARED = 2
_TOP_WORDS = 5
_MIN_GROUP = 3  # a group is at least this many criteria: a new FR carved out of 1-2 criteria is too thin, those stay "loose"
_MIN_EVIDENCED_SHARE = 0.5  # below this share of the FR's criteria bound to tests, code cannot say

VERDICT_YES, VERDICT_NO, VERDICT_NONE, VERDICT_PARTIAL = "yes", "no", "no evidence", "partial evidence"


def vocabulary(text: str) -> set[str]:
    """The distinctive words (4+ letters, plural ``s`` dropped, no filler) of a criterion's wording."""
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w
            for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _STOP}


def _test_file(test_id: str) -> str:
    return test_id.split("::", 1)[0]


def _find(parent: dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _link_reason(a: str, b: str, tests: dict, files: dict, words: dict, hubs: set[str]) -> str:
    """Why criteria ``a`` and ``b`` belong together ('' = nothing shared)."""
    if tests[a] & tests[b]:
        return "same test"
    if {_test_file(t) for t in tests[a]} & {_test_file(t) for t in tests[b]}:
        return "same test file"
    if (files[a] & files[b]) - hubs:
        return "same source file"
    shared = words[a] & words[b]
    if len(shared) >= _VOCAB_MIN_SHARED and len(shared) / len(words[a] | words[b]) >= _VOCAB_MIN_JACCARD:
        return "shared wording"
    return ""


def _top_words(members: list[str], words: dict[str, set[str]]) -> list[str]:
    tally: dict[str, int] = {}
    for m in members:
        for w in words[m]:
            tally[w] = tally.get(w, 0) + 1
    ranked = sorted((w for w, n in tally.items() if n >= 2 or len(members) == 1), key=lambda w: (-tally[w], w))
    return ranked[:_TOP_WORDS]


def _sort_key(ac_id: str) -> tuple[int, str]:
    m = re.search(r"AC(\d+)$", ac_id)
    return (int(m.group(1)) if m else 0, ac_id)


def hub_files(acs: dict[str, str], files: dict[str, set[str]]) -> set[str]:
    """Source files touched by the tests of many different FRs (repo-wide utilities): they say nothing about one FR's seams."""
    per_fr: dict[str, set[str]] = {}
    for ac_id, paths in files.items():
        if ac_id in acs:
            for p in paths:
                per_fr.setdefault(p, set()).add(ac_id.rsplit(".AC", 1)[0])
    evidenced = len({a.rsplit(".AC", 1)[0] for a, p in files.items() if a in acs and p})
    return {p for p, frs in per_fr.items() if len(frs) >= _HUB_MIN_FRS and len(frs) / max(evidenced, 1) >= _HUB_SHARE}


def cluster_fr(fr_id: str, acs: dict[str, str], tests: dict[str, set[str]] | None = None, files: dict[str, set[str]] | None = None,
               hubs: set[str] | None = None) -> dict:
    """Cluster the criteria of one FR.

    ``acs``   ``{ac id: wording}`` (every criterion of the FR);
    ``tests`` ``{ac id: {"path/to/test_x.py::test_name", ...}}`` (criteria with no bound test are absent or empty);
    ``files`` ``{ac id: {source file the bound tests import, ...}}``;
    ``hubs``  source files to ignore as repo-wide utilities (see :func:`hub_files`).

    Returns ``{"fr", "ac_count", "evidenced", "verdict", "reason", "clusters", "loose", "unassigned", "hub_files"}``; each
    cluster (a group of at least three criteria) carries its criteria, the tests and files behind them, the words they share and why they were joined.
    """
    tests, files = tests or {}, files or {}
    order = sorted(acs, key=_sort_key)
    words = {a: vocabulary(acs[a]) for a in order}
    bound = [a for a in order if tests.get(a)]
    t = {a: set(tests.get(a) or ()) for a in order}
    f = {a: set(files.get(a) or ()) for a in order}
    base = {"fr": fr_id, "ac_count": len(order), "evidenced": len(bound), "clusters": [], "loose": [], "unassigned": [], "hub_files": []}
    if len(bound) < 2:
        return {**base, "verdict": VERDICT_NONE, "unassigned": list(order),
                "reason": f"{len(bound)} of {len(order)} criteria are bound to a test; code cannot say whether this splits"}

    if len(bound) / len(order) < _MIN_EVIDENCED_SHARE:
        return {**base, "verdict": VERDICT_PARTIAL, "unassigned": [a for a in order if a not in bound],
                "reason": f"only {len(bound)} of {len(order)} criteria are bound to a test; code cannot say whether this splits"}
    hubs = set(hubs or ())
    parent = {a: a for a in bound}
    why: dict[str, set[str]] = {a: set() for a in bound}
    for a, b in combinations(bound, 2):
        reason = _link_reason(a, b, t, f, words, hubs)
        if reason:
            parent[_find(parent, a)] = _find(parent, b)
            why[a].add(reason)
            why[b].add(reason)
    groups: dict[str, list[str]] = {}
    for a in bound:
        groups.setdefault(_find(parent, a), []).append(a)
    loose = sorted((a for g in groups.values() if len(g) < _MIN_GROUP for a in g), key=_sort_key)
    members = sorted((g for g in groups.values() if len(g) >= _MIN_GROUP), key=lambda g: _sort_key(g[0]))

    unassigned = []
    for a in order:
        if a in parent:
            continue
        if not members:
            unassigned.append(a)
            continue
        best = max(members, key=lambda g: len(words[a] & set().union(*(words[m] for m in g))))
        if len(words[a] & set().union(*(words[m] for m in best))) >= _ATTACH_MIN_SHARED:
            best.append(a)
        else:
            unassigned.append(a)

    clusters = []
    for g in members:
        g.sort(key=_sort_key)
        clusters.append({
            "acs": g,
            "tests": sorted(set().union(*(t[m] for m in g))),
            "files": sorted(set().union(*(f[m] for m in g)) - hubs),
            "vocabulary": _top_words(g, words),
            "joined_by": sorted(set().union(*(why.get(m, set()) for m in g))),
        })
    verdict = VERDICT_YES if len(clusters) >= 2 else VERDICT_NO
    reason = (f"{len(clusters)} groups of at least {_MIN_GROUP} criteria share no test, test file, source file or wording with each other"
              if verdict == VERDICT_YES else "fewer than two groups of connected criteria; any other criteria are loose singles. It stays whole")
    return {**base, "verdict": verdict, "reason": reason, "clusters": clusters, "loose": loose, "unassigned": unassigned, "hub_files": sorted(hubs & set().union(*(f[a] for a in bound)))}


def cluster_frs(acs: dict[str, str], tests: dict[str, set[str]] | None = None, files: dict[str, set[str]] | None = None) -> list[dict]:
    """:func:`cluster_fr` for every FR in a flat ``{"FR-01.03.AC05": wording}`` map, as a WORKLIST.

    Order: splittable FRs first, then the rest; inside each, the FR with the most criteria first. The count only sorts the
    list - it never decides a verdict.
    """
    by_fr: dict[str, dict[str, str]] = {}
    for ac_id, text in acs.items():
        by_fr.setdefault(ac_id.rsplit(".AC", 1)[0], {})[ac_id] = text
    hubs = hub_files(acs, files or {})
    results = [cluster_fr(fr, group, tests, files, hubs) for fr, group in by_fr.items()]
    rank = {VERDICT_YES: 0, VERDICT_NO: 1, VERDICT_PARTIAL: 2, VERDICT_NONE: 3}
    return sorted(results, key=lambda r: (rank[r["verdict"]], -r["ac_count"], r["fr"]))
