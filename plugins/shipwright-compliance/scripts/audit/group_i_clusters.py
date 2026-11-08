"""I10 - requirements that can still be split (atomic-frs U1). Advisory, never red.

Rule: ``shared/fr-authoring.md`` §3c - one FR names ONE capability. This is the code half of that rule: it groups the
criteria of each FR by bound tests, touched files and wording (``lib.fr_clusters``) and reports an FR as splittable only
when two or more groups of at least three criteria share none of them. The criterion COUNT never decides; it only orders the
list (biggest first). Code proposes; the AI capability test and the operator confirm every cut.

The detail says three distinct things, so a thin or unreadable catalog never reads as clean:

* ``N splittable`` - each with its evidence (the groups, a few tests and files behind them);
* ``M with no evidence`` - too few criteria are bound to tests for code to say anything (neither clean nor splittable);
* ``could not read`` - the requirement catalog or test tree could not be read (no spec.md at all, a spec with no parseable
  requirement, or an I/O fault): status ``skip``, with the reason;
* ``I10 broken`` - this check's own modules could not be loaded: status ``skip``, a different detail, so a loader fault never
  reads as "could not read" and never as clean.

A sibling module because ``group_i`` sits at the size limit; it returns ``(status, detail)`` that ``group_i`` wraps in a
``Finding``. Loaded through ``load_shared_lib`` (ADR-045).
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit.audit_adapters import load_shared_lib

_PREVIEW_CAP = 5
_EVIDENCE_CAP = 2


def _short(items: list[str], cap: int = _EVIDENCE_CAP) -> str:
    shown = [i.rsplit("/", 1)[-1] for i in items[:cap]]
    return ", ".join(shown) + (f" +{len(items) - cap}" if len(items) > cap else "")


def _hit(r: dict) -> str:
    groups = "; ".join(
        f"[{_short([a.rsplit('.', 1)[1] for a in c['acs']], 4)}] tests {_short(c['tests'])}"
        + (f", files {_short(c['files'])}" if c["files"] else "")
        for c in r["clusters"])
    return f"{r['fr']} ({r['ac_count']} criteria, {len(r['clusters'])} groups by test files: {groups})"


def splittable_report(project_root: Path) -> tuple[str, str]:
    """``(status, detail)`` for I10: ``("pass", ...)`` always when readable, ``("skip", "could not read ...")`` when not."""
    try:
        catalog_lib = load_shared_lib("ac_catalog")
        evidence_lib = load_shared_lib("fr_cluster_evidence")
        clusters_lib = load_shared_lib("fr_clusters")
    except ImportError as exc:  # ModuleNotFoundError included: a loader fault, not an unreadable catalog
        return "skip", f"I10 broken (cannot load its modules): {type(exc).__name__}: {str(exc)[:120]}"
    try:
        catalog = catalog_lib.load_catalog(project_root)
        if catalog.get("unparsed"):
            return "skip", "could not read: no spec.md at all, or a spec.md has text but no requirement this check can parse - nothing was examined"
        acs = catalog["acs"]  # a catalog of an unexpected shape raises KeyError/TypeError: caught below as an internal error
        tests, files = evidence_lib.collect_evidence(project_root, set(acs))
    except (OSError, UnicodeError, RuntimeError) as exc:
        return "skip", f"could not read: {type(exc).__name__}: {str(exc)[:120]}"
    except (KeyError, TypeError, AttributeError) as exc:
        return "skip", f"I10 broken (internal error): {type(exc).__name__}: {str(exc)[:120]}"
    try:
        report = clusters_lib.cluster_frs(acs, tests, files)
    except Exception as exc:  # noqa: BLE001 - advisory, never red: a fault in this check's own logic is its own skip, not a crash
        return "skip", f"I10 broken (internal error): {type(exc).__name__}: {str(exc)[:120]}"
    hits = [_hit(r) for r in report if r["verdict"] == "yes"]
    none = sum(r["verdict"] == "no evidence" for r in report)
    partial = sum(r["verdict"] == "partial evidence" for r in report)
    parts = [f"{len(hits)} splittable"]
    if hits:
        parts[0] += ": " + ", ".join(hits[:_PREVIEW_CAP]) + (f" (+{len(hits) - _PREVIEW_CAP} more)" if len(hits) > _PREVIEW_CAP else "")
    thin = f"{none} of {len(report)} with no evidence"
    thin += f", {partial} with too little evidence (fewer than half the criteria named by a test)" if partial else ""
    parts.append(thin + " (code cannot say, not clean)")
    return "pass", "advisory — " + "; ".join(parts)
