"""Where a moving Shipwright project file lives right now: the new place first, then the root.

Campaign ``root-files-into-config`` step R1c-1 (BRIEF
``.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`` sections 4.3,
12.10e and 14). :func:`locate` is the ONE lookup behind ``shipwright_paths.path()``, ``main_path()``
and ``json_path_or_none()``; the resolver loads this file by path (``shipwright_paths._sibling``), so
it is stdlib only and imports nothing from its package.

State table (``new`` = the post-move path, ``root`` = the legacy root path):

=================================  ===================  =========================================
new                                root                 result
=================================  ===================  =========================================
absent                             absent               root (writers create it there until R3)
absent                             present, no stub     root
present                            absent               new
present                            present, no stub     ``LayoutError("both_copies")``
present                            stub                 new                     (``run_config`` only)
absent                             stub                 ``LayoutError("incomplete_migration")``
any                                stub too new/edited  ``LayoutError("pointer_too_new"/"_edited")``
itself carries the signature       any                  ``LayoutError("stub_at_new_path")``
=================================  ===================  =========================================

Rows are checked in this order: stub at the new path (every moving key: a stub copied there would
otherwise parse as broken JSON and read as defaults), then the root stub's verdict (only the root
``shipwright_run_config.json`` can be a stub, BRIEF 14.1), then both copies. Identical copies are an
error too: a writer would update only the new one and the next read would fail anyway, so the error
comes at once, with the fix (contents are never compared). The stub's text is never followed (BRIEF
14.2): the new path is fixed by the registry. Only REGULAR files count as present and are read: a
directory or FIFO of that name is no copy and never blocks a hook. An unreadable file reads as "not a
stub" and the caller's own read reports it.

``LayoutError`` subclasses ``Exception`` directly, not ``OSError`` / ``ValueError`` / ``RuntimeError``,
which this codebase catches as "file missing", "bad JSON" or "lock timeout". The class is per tree (the
plugin cache and the dev tree each load their own copy), so code that may see another tree's error
matches ``getattr(exc, "code", None)``, not the class.
"""

from __future__ import annotations

from os.path import isfile as _isfile  # never raises (Path.is_file re-raises EACCES on 3.11)
from pathlib import Path
from typing import Callable

SIGNATURE = b"SHIPWRIGHT-POINTER"
_BOM = b"\xef\xbb\xbf"
_HEAD = 2048  # bytes read before deciding a large root file cannot be a stub
_TAIL = 64 * 1024  # cap on the follow-on read of a signature-led file (untrusted repos: adopt, grade)

_FIX = {
    "both_copies": "Shipwright found two copies and will not guess which one is current. Keep the one "
                   "you want at {new}, delete {old}, and commit.",
    "incomplete_migration": "The root file is a pointer stub but {new} is missing, so the move into "
                            "the new folder did not finish (or the copy was never committed). Restore "
                            "{new} from git or re-run the migration; config writes are refused until then.",
    "pointer_too_new": "{old} was written by a newer Shipwright release. Update the Shipwright plugins.",
    "pointer_edited": "{old} is a pointer stub that was edited (over 512 bytes). Restore it from git; "
                      "the real configuration lives at {new}.",
    "stub_at_new_path": "{new} holds a pointer stub instead of the configuration. Restore the real file "
                        "from git.",
}


class LayoutError(Exception):
    """A moving project file is in a state no reader or writer may act on (see the module table)."""

    def __init__(self, code: str, key: str, new: Path, old: Path) -> None:
        self.code, self.key, self.paths = code, key, (str(new), str(old))
        super().__init__(f"Shipwright file {key!r} ({code}): {_FIX[code].format(new=new, old=old)}")


def _verdict(p: Path, classify: Callable[[bytes], object]) -> str:
    """The pointer recogniser's kind for the file at *p*; ``not_stub`` when unreadable.

    A stub's first line, after an optional BOM and ASCII whitespace, starts with the signature
    (``shipwright_pointer`` rule 4). So a large file whose first :data:`_HEAD` bytes start otherwise is
    an ordinary file after one short read; only a signature-led head reads on, at most :data:`_TAIL` more
    (a pathological 2 KiB of leading blanks counts as not a stub; ``classify`` would call it edited)."""
    try:
        if not _isfile(p):
            return "not_stub"
        with open(p, "rb") as fh:
            head = fh.read(_HEAD)
            if len(head) == _HEAD:
                lead = (head[len(_BOM):] if head.startswith(_BOM) else head).lstrip(b" \t\r\f\v")
                if not lead.startswith(SIGNATURE):  # 2 KiB of blanks: not a stub either (accepted)
                    return "not_stub"
                head += fh.read(_TAIL)  # bounded: anything this large is an edited stub anyway
    except OSError:
        return "not_stub"  # the caller's own read reports the real error
    return getattr(classify(head), "kind", "not_stub")


def locate(key: str, root: Path | str, new_rel: str | None, legacy_rel: str, *,
           stub_capable: bool, classify: Callable[[bytes], object]) -> Path:
    """The path *key* lives at under *root* (see the module table). ``new_rel`` ``None``: the file
    does not move and resolves to the root. ``classify`` is ``shipwright_pointer.classify``."""
    old = Path(root) / legacy_rel
    if new_rel is None:
        return old
    new = Path(root) / new_rel
    new_there, old_there = _isfile(new), _isfile(old)
    if new_there and _verdict(new, classify) != "not_stub":
        raise LayoutError("stub_at_new_path", key, new, old)
    if stub_capable:
        kind = _verdict(old, classify) if old_there else "absent"
        if kind == "too_new":
            raise LayoutError("pointer_too_new", key, new, old)
        if kind == "edited":
            raise LayoutError("pointer_edited", key, new, old)
        if kind == "stub":
            if new_there:
                return new
            raise LayoutError("incomplete_migration", key, new, old)
    if new_there and old_there:
        raise LayoutError("both_copies", key, new, old)
    return new if new_there else old
