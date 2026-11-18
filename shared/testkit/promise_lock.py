"""The promise lock's entries (programme P21): AC ids resolved through the spec's move map, the ``path::name`` key, the check.

``resolve_acs`` follows the ids a test declares (``promise_hash.covers_of``) through the spec's ``## AC-Move-Map``
(``| `FR-01.11/AC21` | `FR-01.22/AC21` |`` rows; the same format ``shared/scripts/lib/ac_move_map.py`` parses - a test pins the two
parsers together), and ``lock_entry`` joins the two: the id is stored beside the hash, never inside it. Stdlib only.
"""

from __future__ import annotations

import posixpath
import re
from typing import Any, Iterable, Mapping, Sequence

import promise_hash as ph

AC_ID = re.compile(r"^FR-\d{2}\.\d{2}/AC\d{2,}$")
MOVE_HEADING = "## AC-Move-Map"


def parse_move_map(spec_text: str) -> dict[str, str]:
    """``{old id: new id}`` from the ``## AC-Move-Map`` section of a spec (``{}`` when there is none)."""
    moves: dict[str, str] = {}
    inside = False
    for line in (spec_text or "").splitlines():
        if line.startswith("#"):
            inside = line.strip().lower() == MOVE_HEADING.lower()
        elif inside and line.startswith("|"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and AC_ID.match(cells[0]) and AC_ID.match(cells[1]):
                moves[cells[0]] = cells[1]
    return moves


def resolve_ac(ac_id: str, moves: Mapping[str, str]) -> str:
    """Follow ``ac_id`` through the move map to where it lives now (a cycle stops at the last id reached)."""
    seen = {ac_id}
    while ac_id in moves and moves[ac_id] not in seen:
        ac_id = moves[ac_id]
        seen.add(ac_id)
    return ac_id


def resolve_acs(ids: Iterable[str], moves: Mapping[str, str]) -> list[str]:
    return sorted({resolve_ac(i, moves) for i in ids})


def lock_entry(test: str, source: str, spec_text: str = "", conftests: Sequence[str] = ()) -> dict[str, Any]:
    """``{"acs": [...current ids...], "hash": ...}``: the AC ids sit beside the hash, never inside it."""
    ids = ph.covers_of(test, source)
    bad = [i for i in ids if not AC_ID.match(i)]
    if bad or not ids:
        raise ValueError(f"{test}: a promise test needs well-formed covers ids (got {ids!r})")
    return {"acs": resolve_acs(ids, parse_move_map(spec_text)), "hash": ph.fingerprint(test, source, conftests)}


def lock_key(path: str, test: str) -> str:
    """The key of a lock entry: ``path::name``, the path relative and posix. A bare test name is not a key: two files may hold the same name."""
    posix = posixpath.normpath(path.replace(chr(92), "/"))
    if posix.startswith(("/", "..")) or re.match(r"^[A-Za-z]:", posix):
        raise ValueError(f"{path}: a lock key needs a path relative to the repository, not an absolute one")
    return f"{posix}::{test}"


def lock_problems(lock: Mapping[str, Mapping[str, Any]], sources: Mapping[str, str], conftests: Sequence[str] = (),
                  spec_text: str = "") -> list[str]:
    """Everything wrong with a lock against the promise-test sources (``{path: source}``); ``[]`` when it holds.

    A test in a source with no entry, an entry whose name is no longer in its file, and an entry whose hash or AC ids
    differ are all failures: a missing name is never read as "nothing to check"."""
    problems: list[str] = []
    wanted = {lock_key(path, name): (path, name) for path, source in sources.items() for name in ph.tests_in(source)}
    problems += [f"{key}: a promise test that is not in the lock" for key in sorted(set(wanted) - set(lock))]
    for key in sorted(set(lock) - set(wanted)):
        problems.append(f"{key}: the lock names a test that is missing from its file")
    for key in sorted(set(lock) & set(wanted)):
        path, name = wanted[key]
        try:
            now = lock_entry(name, sources[path], spec_text, conftests)
        except ValueError as exc:  # e.g. the covers mark was removed: a problem to report, not a crash
            problems.append(f"{key}: {exc}")
            continue
        if {k: lock[key].get(k) for k in ("acs", "hash")} != now:
            problems.append(f"{key}: the promise differs from the lock (hash or AC ids)")
    return problems
