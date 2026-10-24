"""Read tracked files as the NEXT COMMIT carries them (the git index).

Shared by the two stack-profile guards (``test_stack_profile_prose_guard.py`` for markdown /
``hooks.json``, ``test_stack_profile_py_guard.py`` for ``*.py``).

Policy (one for both guards): they read the INDEX, not the working tree. Generated renders
(``triage_inbox.md``) are rewritten locally between commits, and reading the index keeps the
guards identical on a developer tree and on a clean CI checkout. The price: a local run is blind to
unstaged, untracked and intent-to-add edits (stage the files first); CI vets the commit and is
the backstop. ``test_stack_profile_prose_commands.py`` is the deliberate exception: it EXECUTES
the prose a developer is editing, so it reads the working tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], input=data, capture_output=True, check=True).stdout


def tracked(*pathspecs: str) -> list[str]:
    """Tracked paths matching ``pathspecs``: NUL-separated (a non-ASCII name stays intact), de-duplicated."""
    out = _git("ls-files", "-z", "--", *pathspecs)
    return sorted({p.decode("utf-8") for p in out.split(b"\0") if p})


def read_index(names: list[str]) -> dict[str, bytes]:
    """name -> index content, via ONE ``cat-file --batch`` process. A file that cannot be read is an
    AssertionError, never a skip; an unmerged (conflicted) entry says so."""
    unmerged = {rec.split(b"\t", 1)[1].decode("utf-8") for rec in _git("ls-files", "-u", "-z").split(b"\0") if b"\t" in rec}
    out = _git("cat-file", "--batch", data="".join(f":{n}\n" for n in names).encode("utf-8"))
    blobs, pos = {}, 0
    for name in names:
        eol = out.index(b"\n", pos)
        header = out[pos:eol].split()
        if len(header) != 3 or header[1] != b"blob":
            why = "unmerged index entry (resolve the conflict first)" if name in unmerged else out[pos:eol].decode("utf-8", "replace")
            raise AssertionError(f"guard cannot read tracked file {name}: {why}")
        size = int(header[2])
        blobs[name] = out[eol + 1:eol + 1 + size]
        pos = eol + 1 + size + 1
    return blobs
