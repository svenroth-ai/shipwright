"""Baseline of currently-known ADR spec-folder number collisions.

Mirrors the bloat anti-ratchet idiom (``lib/bloat_baseline.py`` +
``shipwright_bloat_baseline.json``): pins today's known debt so the drift
guard (``shared/tests/test_adr_index_no_duplicate_numbers.py``) fails on any
*new* numeric-prefix collision without also failing on the 15 files this
run's operator explicitly declined to rename (iterate-2026-08-08-
index-readers-adr-lock — a wrong rename is worse than a known collision).

Regenerated only by ``scripts/tools/rebuild_adr_collision_baseline.py``,
never by the guard test itself — a self-regenerating guard would silently
absorb a same-run collision as "baseline" and protect nothing.

``BASELINE_RELPATH`` is project-root-relative (the ``shipwright_`` config-file
prefix, matching ``shipwright_bloat_baseline.json``), NOT under ``shared/`` —
this module is reused by any Shipwright project's own iterate skill, and a
monorepo-relative path would be unrunnable in an adopted repo, which has no
``shared/`` directory at all (the same hazard ``lib/adr_index.py`` documents
for its own regen-command string).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from lib.adr_index import parse_adr_number

BASELINE_RELPATH = "shipwright_adr_collision_baseline.json"


def collect_collisions(folder: Path) -> dict[str, list[str]]:
    """Numeric ADR numbers with 2+ files under ``folder``, mapped to filenames.

    A missing folder is a no-op (``{}``), matching ``rebuild_adr_index``'s
    stance on the same case, rather than raising ``FileNotFoundError``.
    """
    if not folder.is_dir():
        return {}
    by_number: dict[int, list[str]] = defaultdict(list)
    for md in sorted(folder.iterdir()):
        if md.is_symlink() or not md.is_file() or md.suffix.lower() != ".md":
            continue
        num = parse_adr_number(md.name)
        if num is not None:
            by_number[num].append(md.name)
    # No sort here: the writer's `json.dumps(..., sort_keys=True)` re-sorts
    # the string keys alphabetically anyway, so a numeric sort here would be
    # a dead effort implying an ordering the artifact never actually has.
    return {str(num): names for num, names in by_number.items() if len(names) > 1}


def load(project_root: Path) -> dict[str, list[str]]:
    """Load the committed baseline. ``{}`` on missing/corrupt/unparseable.

    This makes the drift guard fail CLOSED, not open: an empty or missing
    baseline means nothing is pinned, so every existing collision reads as
    brand new and the guard fails. That is the safer failure mode for an
    anti-ratchet guard — a baseline that silently disappears must not
    silently disarm the check (unlike the bloat baseline's own
    ``load_baseline_override``, which fails open, because THAT gate's
    absence-of-baseline case means "no known debt to protect" rather than
    "nothing stops new debt").

    Keys are re-normalized via ``str(int(...))``: a hand-edited baseline
    keyed ``"097"`` (the visually obvious choice, since every file in that
    bucket is ``097-*.md``) must still match the computed key ``"97"`` that
    :func:`collect_collisions` produces — otherwise the pin is silently
    inert and a grandfathered file reads as a brand-new collision.
    """
    path = Path(project_root) / BASELINE_RELPATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for num, names in entries.items():
        if not (isinstance(names, list) and all(isinstance(n, str) for n in names)):
            continue
        try:
            normalized[str(int(num))] = list(names)
        except (TypeError, ValueError):
            continue
    return normalized


def unpinned_collisions(
    actual: dict[str, list[str]], pinned: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Files in ``actual`` not accounted for by ``pinned``, per number.

    An empty result means every actual collision is covered by a subset of
    its pinned baseline entry — shrinking a pinned number (renaming ONE of
    its files away) is always allowed and never appears here.
    """
    result: dict[str, list[str]] = {}
    for number, files in actual.items():
        extra = sorted(set(files) - set(pinned.get(number, [])))
        if extra:
            result[number] = extra
    return result
