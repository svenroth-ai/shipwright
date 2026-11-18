"""The infrastructure pass of the test-tag gate: which tests of a diff are legitimately classed infrastructure.

A Python test declares ``@pytest.mark.covers_none("tooling"|"infra")`` (see :mod:`._tag_binding_infra`); this pass
decides whether the declaration is HONOURED. It judges every test of a changed file that carries one, not only
the ones the gate would have flagged, so a tagged test, a legacy test and a new test meet one rule:

* the file is named EXACTLY in the catalog as it stood at the merge-base (a catalog edited in the same diff
  licenses nothing), and the catalog was readable;
* every same-named declaration carries the same single valid label and no ``covers`` mark anywhere in reach;
* a test that was requirement-tagged at base (same id, or moved with the same normalised body) is a stand-in
  CORRECTION: both its paths are in the catalog and every requirement / criterion it carried keeps another
  linked test at head - a correction never quietly drops the last proof of anything. It WARNs naming the tag.

Pure: no git, no filesystem; the caller hands in ``read`` and the two manifests' links.
"""

from __future__ import annotations

import json
from typing import Callable, NamedTuple

from ._tag_binding_infra import py_infra_info

__all__ = ["CATALOG_PATH", "InfraResult", "apply_infra", "classify", "parse_catalog", "units_by_test"]

Reader = Callable[[str, str], "str | None"]
Digests = Callable[[str, str], "tuple | None"]  # (test id, side) -> body digests
CATALOG_PATH = "shared/config/infra_test_paths.json"
#: Findings a judged ``covers_none`` declaration supersedes (valid: the test is infrastructure; invalid: ``bad-infra-class``).
_SUPERSEDED = frozenset({"untagged-added", "untagged-modified", "tag-removed", "ambiguous-name"})
_NEXT_STEP = "add its exact path to shared/config/infra_test_paths.json in its own earlier merge"


class InfraResult(NamedTuple):
    classed: set[str]
    bad: list[tuple[str, str]]  # (test id, why)
    warnings: list[str]


def units_by_test(manifest: dict) -> dict[str, set[str]]:
    """Test id -> the requirement (``FR``) and criterion (``FR/AC``) units a manifest links it to."""
    out: dict[str, set[str]] = {}
    for key, node in (manifest.get("requirements") or {}).items():
        if not isinstance(node, dict):
            continue
        fr = str(key).split("::")[-1]
        groups = [(fr, list((node.get("tests") or {}).values()))]
        for ac, ac_node in (node.get("acs") or {}).items():
            if isinstance(ac_node, dict):
                groups.append((f"{fr}/{ac}", list((ac_node.get("tests") or {}).values())))
        for unit, lists in groups:
            for links in lists:
                for link in links or []:
                    if isinstance(link, dict):
                        out.setdefault(str(link.get("id") or link.get("path") or ""), set()).add(unit)
    return out


def _valid_entry(entry: object) -> bool:
    if not isinstance(entry, str) or not entry.endswith(".py") or entry.startswith("/") or entry[1:2] == ":":
        return False
    name = entry.rsplit("/", 1)[-1]
    if not (name.startswith("test_") or name.endswith("_test.py")):
        return False  # a catalog lists test files, never production modules
    return not any(c in entry for c in "*?[]\\") and ".." not in entry.split("/")


def parse_catalog(text: str | None) -> tuple[frozenset[str] | None, str | None]:
    """``(paths, warning)`` of the catalog text read at the merge-base: ``""`` (absent) is the silent empty
    case, ``None`` (unreadable) means nothing can be granted, a malformed or invalid file is empty plus a WARNING.
    Exact repo-relative file paths only - a wildcard would let a future file approve itself."""
    if text is None:
        return None, None
    if not text.strip():
        return frozenset(), None
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, list) or not all(_valid_entry(e) for e in data):
        return frozenset(), (f"{CATALOG_PATH} is malformed or holds an entry that is not an exact repo-relative "
                             "test-file path (no wildcard, '..', backslash or absolute path); treated as empty")
    return frozenset(data), None


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _verdict(path: str, name: str, read: Reader, catalog: frozenset[str] | None,
             is_new: bool = False) -> tuple[str | None, bool]:
    """``(why not, declared)`` for one test: ``None`` = the declaration is valid at head."""
    text = read(path, "head")
    infos = py_infra_info(text, name) if text else None
    if not infos or not any(i.declared for i in infos):
        return None, False
    if catalog is None:
        return "the infrastructure-test catalog could not be read at the merge-base, so nothing can be granted", True
    if _norm(path) not in catalog:
        return f"{path} is not in the infrastructure-test catalog at the merge-base - {_NEXT_STEP}", True
    for info in infos:
        if info.bad:
            return "; ".join(info.bad), True
        if info.has_covers:
            return "carries a covers tag as well as covers_none - a test proves a requirement or none, not both", True
    if is_new and not all(i.direct for i in infos):
        return ("a test added after the file's module-level covers_none needs its own @pytest.mark.covers_none - "
                "the module-level declaration only classes the tests already there"), True
    if not all(i.declared and len(i.labels) == 1 for i in infos) or len({i.labels for i in infos}) != 1:
        return f"{len(infos)} tests share this name and not all carry the same single valid covers_none label", True
    return None, True


def _claim_origin(vanished: dict[str, list[str]], digests: tuple, name: str) -> str | None:
    """The tagged base test this one moved from: same body digest, a same-named one preferred, each used once."""
    for digest in digests:
        pool = vanished.get(digest) or []
        if pool:
            pick = next((o for o in pool if o.partition("::")[2] == name), pool[0])
            pool.remove(pick)
            return pick
    return None


def classify(
    ids: list[str], read: Reader, digests: Digests, catalog: frozenset[str] | None,
    base_units: dict[str, set[str]], head_units: dict[str, set[str]],
    head_ids: set[str], changed: set[str], is_test_id: Callable[[str], bool],
) -> InfraResult:
    res = InfraResult(set(), [], [])
    gone = [o for o in sorted(base_units) if o not in head_ids and is_test_id(o) and o.split("::", 1)[0] in changed]
    vanished: dict[str, list[str]] = {}  # digest -> tagged base ids gone at head, to find a move
    for old in gone:
        for d in digests(old, "base") or ():
            vanished.setdefault(d, []).append(old)
    live = {t: u for t, u in head_units.items() if is_test_id(t)}  # a fixture tree never keeps a requirement
    for test in ids:
        path, _, name = test.partition("::")
        why, declared = _verdict(path, name, read, catalog, is_new=not (digests(test, "base") or ()))
        if not declared:
            continue
        if why is None and head_units.get(test):
            why = (f"the manifest links it to {', '.join(sorted(head_units[test]))}: a test proves a "
                   "requirement or none, not both")
        origin = test if test in base_units else _claim_origin(vanished, digests(test, "head") or (), name)
        if why is None and origin is not None:
            why = _correction(test, origin, catalog, base_units, live, res.warnings)
        if why is None:
            res.classed.add(test)
        else:
            res.bad.append((test, why))
    _refuse_quiet_loss(res, gone, base_units, live, lambda t: _declared_at_base(read, t))
    return res


def _declared_at_base(read: Reader, test: str) -> bool:
    path, _, name = test.partition("::")
    text = read(path, "base")
    infos = py_infra_info(text, name) if text else None
    return bool(infos) and all(i.declared for i in infos)


def _refuse_quiet_loss(res: InfraResult, gone: list[str], base_units: dict[str, set[str]],
                       live: dict[str, set[str]], was_infra: Callable[[str], bool]) -> None:
    """Whatever the identity matching found: when a requirement-tagged test vanished and its requirement or
    criterion has no linked test left, no infrastructure class may be granted in the same change - a renamed
    stand-in must not slip the correction rule. Retire the test in a change of its own."""
    fresh = sorted(t for t in res.classed if not was_infra(t))  # an already honoured test changed nothing
    if not fresh:
        return
    kept = {u for units in live.values() for u in units}
    lost = sorted({u for o in gone for u in base_units[o]} - kept)
    if lost:
        res.warnings[:] = [w for w in res.warnings if not any(w.startswith(f"{t} drops") for t in fresh)]
        why = (f"a requirement-tagged test vanished and {', '.join(lost)} has no linked test left; do not "
               "reclassify tests in the same change - tag a real test for it, or retire the old one in its own change")
        res.bad.extend((t, why) for t in fresh)
        res.classed.difference_update(fresh)


def _correction(test: str, origin: str, catalog, base_units, live, warnings: list[str]) -> str | None:
    """Why a stand-in correction is refused, ``None`` when it holds (and WARN naming the dropped tag)."""
    if _norm(origin.split("::", 1)[0]) not in (catalog or frozenset()):
        return f"{origin} was requirement-tagged outside the infrastructure-test catalog; it cannot be reclassified"
    carried = base_units.get(origin, set())
    others = {u for t, units in live.items() if t not in (test, origin) for u in units}
    lost = sorted(u for u in carried if u not in others)
    if lost:
        return (f"reclassifying it would leave {', '.join(lost)} with no other linked test - tag a real "
                "test for it first, or keep the stand-in tag")
    warnings.append(f"{test} drops stand-in tag {', '.join(sorted(carried)) or '(none)'} (reclassified as infrastructure)")
    return None


def apply_infra(v, base: dict, head: dict, head_ids: set[str], changed: set[str], read: Reader, digests: Digests,
                catalog: frozenset[str] | None, is_test_id, split) -> None:
    """Judge every Python test of a changed file that declares ``covers_none`` and fold the verdict into ``v``
    (a ``TagVerdict``). Runs BEFORE the exemption loop, so an infrastructure test never needs an exemption."""
    ids = sorted(t for t in head_ids if is_test_id(t) and split(t)[1] and split(t)[0] in changed
                 and split(t)[0].endswith(".py"))
    res = classify(ids, read, digests, catalog, units_by_test(base), units_by_test(head), head_ids, changed,
                   is_test_id)
    decided = res.classed | {t for t, _ in res.bad}
    v.findings = [f for f in v.findings if not (f[1] in decided and f[0] in _SUPERSEDED)]
    v.findings += [("bad-infra-class", t, why) for t, why in res.bad]
    v.infra, v.warnings = res.classed, v.warnings + res.warnings
    v.touched -= res.classed
