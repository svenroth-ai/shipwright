"""T-spec: the FRs whose NORMATIVE text changed (BP brief section 2).

Normative = the catalog row's name, priority and description plus the FR section's prose
and acceptance criteria. Ignored on purpose, so they never read as a change: status and
promotion lines, ``Layers`` / ``Basis`` / ``Evidence`` columns, ``(inferred)`` markers,
``[ACnn]`` id tokens, comments, whitespace and the ORDER of the criteria. A reworded
criterion, an added or removed one, or a changed description is a change.

Deliberate deviation from the brief's wording (reported to the operator in the REPLAY report):
the brief names keystone's AC digest, which covers acceptance criteria only and keys them by AC
id; the brief's own ignore list says AC-id tokens are NOT a change and the catalog row's
statement IS one, so this is a purpose-built reader (row + section prose + criteria text,
order- and marker-insensitive). Keystone's digests were tried as a union and rejected: they
turn an AC re-mint into a change. The 'existing' FR set is the union of the spec readers' ids
and the committed traceability manifest's requirement ids (the catalog the gates share).
"""

from __future__ import annotations

import hashlib
import json
import re

from ._baseline_touch_git import GitRev

__all__ = ["SPEC_PATH_RE", "fr_digests", "spec_touched", "existing_frs"]

SPEC_PATH_RE = re.compile(r"^\.shipwright/planning/[^/]+/spec\.md$")
_FR = r"FR-\d{2}\.\d{2}"
_ROW = re.compile(rf"^\|\s*({_FR})\s*\|(.*)\|\s*$")
_HEAD = re.compile(rf"^(#{{1,6}})\s+({_FR})\b(.*)$")
_ANY_HEAD = re.compile(r"^(#{1,6})\s")
_IGNORED_COL = re.compile(r"^(basis|layers?|status|evidence|promotion)\b", re.I)
_IGNORED_LINE = re.compile(r"^\W*(status|promot\w*|layers?|evidence|basis)\W*:", re.I)
_NOISE = re.compile(r"\[AC\d+\]|\(inferred\)|<!--.*?-->", re.I | re.S)
_BULLET = re.compile(r"^\s*[-*+]\s+")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub(" ", text)).strip()


def _row_text(cells: list[str], ignored: set[int]) -> str:
    return "|".join(_norm(c) for i, c in enumerate(cells) if i not in ignored)


def _items(lines: list[str]) -> tuple[list[str], list[str]]:
    """``(prose items in order, bullet items)``; an indented line continues the item above."""
    prose: list[str] = []
    bullets: list[str] = []
    current: list[str] | None = None
    for line in lines:
        if not line.strip():
            current = None
        elif _IGNORED_LINE.match(line.strip()):
            current = None
        elif _BULLET.match(line):
            current = bullets
            bullets.append(_BULLET.sub("", line))
        elif line[:1].isspace() and current is not None:
            current[-1] += " " + line
        else:
            current = prose
            prose.append(line)
    return [n for n in map(_norm, prose) if n], [n for n in map(_norm, bullets) if n]


def fr_digests(text: str) -> dict[str, str]:
    """FR id -> digest of its normative text; every block anchored to the id is pooled."""
    parts: dict[str, list[str]] = {}
    ignored: set[int] = set()
    lines = (text or "").splitlines()
    for line in lines:
        if line.startswith("|"):
            cells = [c for c in line.strip().strip("|").split("|")]
            if cells and cells[0].strip().lower() == "id":
                ignored = {i for i, c in enumerate(cells) if _IGNORED_COL.match(c.strip())}
                continue
        row = _ROW.match(line)
        if row:
            parts.setdefault(row[1], []).append("row:" + _row_text(row[2].split("|"), {i - 1 for i in ignored}))
    i = 0
    while i < len(lines):
        head = _HEAD.match(lines[i])
        if not head:
            i += 1
            continue
        level, j = len(head[1]), i + 1
        while j < len(lines):
            nxt = _ANY_HEAD.match(lines[j])
            if nxt and len(nxt[1]) <= level:
                break
            j += 1
        prose, bullets = _items(lines[i + 1:j])
        parts.setdefault(head[2], []).append(
            "sec:" + _norm(head[3]) + "\n" + "\n".join(prose) + "\n--\n" + "\n".join(sorted(bullets)))
        i += 1
    return {fr: hashlib.sha256("\n##\n".join(chunks).encode("utf-8")).hexdigest() for fr, chunks in parts.items()}


def _spec_files(rev: GitRev, side: str) -> list[str]:
    return [p for p in rev.listing(side) if SPEC_PATH_RE.match(p)]


def _all_digests(rev: GitRev, side: str, paths: list[str]) -> dict[str, str] | None:
    out: dict[str, str] = {}
    for path in paths:
        text = rev.read(path, side)
        if text is None:
            return None
        for fr, digest in fr_digests(text).items():
            out[fr] = hashlib.sha256((out.get(fr, "") + digest).encode()).hexdigest()
    return out


_MANIFEST = ".shipwright/compliance/test-traceability.json"


def _manifest_ids(rev: GitRev, side: str) -> set[str]:
    text = rev.read(_MANIFEST, side)
    if text is None:
        raise RuntimeError(f"cannot read {_MANIFEST} at the {side} commit")
    if not text:
        return set()  # absent at that side
    try:
        reqs = (json.loads(text).get("requirements") or {}).values()
    except ValueError as exc:
        raise RuntimeError(f"{_MANIFEST} is not valid JSON at the {side} commit") from exc
    return {str(n["id"]) for n in reqs if isinstance(n, dict) and re.fullmatch(_FR, str(n.get("id", "")))}


def existing_frs(rev: GitRev) -> set[str]:
    """FRs present at the merge base; an FR absent there is new and never 'existing'."""
    found = _all_digests(rev, "base", _spec_files(rev, "base"))
    if found is None:
        raise RuntimeError("cannot read the catalog at the merge base")
    return set(found) | _manifest_ids(rev, "base")


def spec_touched(rev: GitRev, changed_paths: set[str]) -> tuple[set[str], set[str]]:
    """``(touched existing FRs, new FRs)`` from the spec files this diff changed."""
    paths = sorted(p for p in changed_paths if SPEC_PATH_RE.match(p))
    if not paths:
        return set(), set()
    base = _all_digests(rev, "base", paths)
    head = _all_digests(rev, "head", paths)
    if base is None or head is None:
        raise RuntimeError("cannot read a changed spec file")
    touched = {fr for fr in set(base) | set(head) if head.get(fr) != base.get(fr)}  # reworded, removed or newly anchored
    return touched, set(head) - set(base)
