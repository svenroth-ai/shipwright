"""The hard conservation check of ``fr_split`` (atomic-frs U2): a split may move criteria, never lose, double or reword one.

Every function returns a list of problem strings; an empty list means the property holds. ``fr_split`` refuses to write
(dry-run) or restores the files (apply) on any problem. Pure and stdlib only; the evidence maps come from
:mod:`lib.fr_cluster_evidence`, the manifests from the compliance collector.

* :func:`check_catalog`  - every criterion of the old spec appears exactly once in the new one, with its text unchanged,
  at the id the move map says; untouched requirements are unchanged; the move map holds every move;
* :func:`check_bindings` - the tests that name each criterion are the same tests, under the criterion's new id, and no
  test still names a moved criterion by its old id;
* :func:`check_manifest` - the same for the generated traceability manifest (per criterion: layer, test id, tag source);
* :func:`check_names`    - the new requirement names pass the Group I1 name fence;
* :func:`coupling`       - tests, test files and source files shared between the parts (shared test = problem).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from lib.ac_catalog import parse_catalog
from lib.ac_move_map import parse_move_map
from lib.fr_hygiene_detectors import description_violations, name_violations

__all__ = ["check_bindings", "check_catalog", "check_manifest", "check_names", "coupling", "dirty_targets", "dotted"]


def dirty_targets(root: Path, rels: list[str]) -> list[str]:
    """Target files with uncommitted changes (an unrelated edit in the same file would be overwritten or lost on a restore). [] outside git."""
    try:
        proc = subprocess.run(["git", "status", "--porcelain", "--", *rels], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    return [ln[3:] for ln in proc.stdout.splitlines() if ln[:2].strip() and not ln.startswith("??")] if proc.returncode == 0 else []

_MARK = re.compile(r"^-\s+(?:\([A-Z]\)\s+)?\[AC\d+\]", re.M)


def dotted(ac: str) -> str:
    """``FR-01.11/AC21`` -> ``FR-01.11.AC21`` (the catalog / evidence key form)."""
    return ac.replace("/", ".")


def check_catalog(old: str, new: str, moves: dict[str, str], new_ids: list[str]) -> list[str]:
    old_acs, old_frs = parse_catalog(old)
    new_acs, new_frs = parse_catalog(new)
    problems: list[str] = []
    n_old, n_new = len(_MARK.findall(old)), len(_MARK.findall(new))
    if n_old != n_new:
        problems.append(f"criterion count changed: {n_old} -> {n_new} (one was lost or doubled)")
    m = {dotted(o): dotted(n) for o, n in moves.items()}
    expect = {m.get(o, o): (o, t) for o, t in old_acs.items()}
    for want, (o, text) in expect.items():
        if want not in new_acs:
            problems.append(f"{o} is missing from the new spec (expected as {want})")
        elif new_acs[want] != text:
            problems.append(f"{o} changed its wording on the way to {want}")
    problems += [f"{extra} is new; a split must not add criteria" for extra in sorted(set(new_acs) - set(expect))]
    problems += [f"{o} is still in the source after the move (doubled)" for o in sorted(m) if o in new_acs]
    problems += [f"{fr} disappeared from the new spec" for fr in old_frs if fr not in new_frs]
    problems += [f"new requirement {n} has no heading" for n in new_ids if n not in new_frs]
    table = parse_move_map(new)
    problems += [f"{o} -> {n} is missing from the AC-Move-Map" for o, n in moves.items() if table.get(o) != n]
    return problems


def check_bindings(old: dict[str, set[str]], new: dict[str, set[str]], moves: dict[str, str]) -> list[str]:
    """``old`` / ``new``: ``{"FR-01.11.AC21": {test ids}}`` over the whole repo before and after the tag rewrite."""
    m = {dotted(o): dotted(n) for o, n in moves.items()}
    want = {m.get(ac, ac): set(tests) for ac, tests in old.items()}
    problems = []
    for ac in sorted(set(want) | set(new)):
        if want.get(ac, set()) != new.get(ac, set()):
            lost, added = sorted(want.get(ac, set()) - new.get(ac, set())), sorted(new.get(ac, set()) - want.get(ac, set()))
            problems.append(f"{ac}: test binding changed (lost {lost[:2]}, added {added[:2]})")
    problems += [f"{ac} is still named by a test under its old id" for ac in sorted(m) if new.get(ac)]
    return problems


def _manifest_acs(manifest: dict) -> dict[str, set[tuple[str, str, str]]]:
    out: dict[str, set[tuple[str, str, str]]] = {}
    for node in (manifest.get("requirements") or {}).values():
        for ac, body in (node.get("acs") or {}).items():
            out[f"{node.get('id')}/{ac}"] = {(layer, t.get("id", ""), t.get("tag_source", ""))
                                              for layer, tests in (body.get("tests") or {}).items() for t in tests}
    return out


def check_manifest(old: dict, new: dict, moves: dict[str, str]) -> list[str]:
    before, after = _manifest_acs(old), _manifest_acs(new)
    want = {moves.get(ac, ac): tests for ac, tests in before.items()}
    return [f"manifest: {ac} has a different test binding after the split"
            for ac in sorted(set(want) | set(after)) if want.get(ac, set()) != after.get(ac, set())]


def check_names(parts: list[dict], remaining: dict | None) -> list[str]:
    problems = []
    for p in list(parts) + ([remaining] if remaining else []):
        for what, vs in (("name", name_violations(p["title"])), ("description", description_violations(p["description"]))):
            if vs:
                problems.append(f"{what} of {p['title']!r} carries implementation detail: {', '.join(vs)}")
    return problems


def coupling(parts_acs: dict[str, list[str]], tests: dict[str, set[str]], files: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """``(problems, notes)``. ``parts_acs``: ``{part label: [dotted ac ids]}`` incl. the part that stays. A TEST that names criteria
    of two parts is a problem (stop rule, fr-authoring 3c); a shared test file or source file is only a note."""
    def of(label: str, src: dict[str, set[str]]) -> set[str]:
        return set().union(*(src.get(a, set()) for a in parts_acs[label])) if parts_acs[label] else set()

    problems, notes = [], []
    labels = sorted(parts_acs)
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if shared := of(a, tests) & of(b, tests):
                problems.append(f"{a} and {b} share {len(shared)} test(s), e.g. {sorted(shared)[0]}")
            if tf := {t.split("::")[0] for t in of(a, tests)} & {t.split("::")[0] for t in of(b, tests)}:
                notes.append(f"{a} and {b} share test file(s): {', '.join(sorted(tf)[:2])}")
            if sf := of(a, files) & of(b, files):
                notes.append(f"{a} and {b} touch the same source file(s): {', '.join(sorted(sf)[:2])}")
    return problems, notes
