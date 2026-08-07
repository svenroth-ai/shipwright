"""Shared real-git plumbing for the ``test_sweep_outbox*`` modules (D2).

Not a test file (leading underscore → pytest does not collect it). Holds the
git/worktree/outbox fixtures-on-disk plumbing so the two ``test_sweep_outbox*``
modules each stay under the 300-LOC guideline without duplicating it. Mirrors
the ``_reconcile_helpers.py`` pattern. EVERYTHING here uses REAL git — the sweep
is the most data-loss-sensitive unit in the campaign, so nothing is mocked.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

TRIAGE = ".shipwright/triage.jsonl"
OUTBOX = ".shipwright/triage.outbox.jsonl"
QUARANTINE = ".shipwright/triage.outbox.quarantine.jsonl"
HEADER = '{"v":1,"schema":"triage","created":"2026-06-08T00:00:00Z"}'


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # errors="surrogateescape" matches how the store itself reads and writes these
    # bytes: a fixture may seed a line carrying a byte that is not valid UTF-8 (an
    # interrupted multi-byte append), and a STRICT decode would make the helper
    # raise before the test under it ever ran.
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, encoding="utf-8",
        errors="surrogateescape", check=check,
    )


def write_store_bytes(path: Path, text: str) -> None:
    """Write ``text`` the way the triage store writes it — bytes, surrogateescape,
    no newline translation.

    ``Path.write_text(..., encoding="utf-8")`` raises ``UnicodeEncodeError`` on a
    lone surrogate, so it cannot express a log line carrying a broken byte at all.
    ``sweep_outbox`` and ``reconcile_triage`` both encode exactly this way.
    """
    path.write_bytes(text.encode("utf-8", errors="surrogateescape"))


def set_identity(work: Path) -> None:
    git(work, "config", "user.email", "sweep@test.invalid")
    git(work, "config", "user.name", "Sweep Test")


def item(iid: str, title: str = "x", original_ts: str | None = None) -> str:
    """An append line. ``original_ts`` is OPTIONAL and omitted by default, so every
    existing fixture keeps its exact bytes.

    Pass it when the fixture means a REFRESH of an existing item. Two same-id appends
    that do not agree on ``originalTs`` are treated as a possible 32-bit id collision
    and both are kept (``lib.triage_dedup``), which is not what a refresh fixture
    intends — and an append without one is a shape neither of ``triage.py``'s
    constructors can emit, so omitting it there models something that cannot occur.
    """
    anchor = f'"originalTs":"{original_ts}",' if original_ts else ""
    return (
        f'{{"event":"append","id":"{iid}","ts":"2026-06-08T00:00:00Z",'
        f'{anchor}"title":"{title}","status":"triage"}}'
    )


def status(iid: str, new_status: str = "dismissed") -> str:
    """A status event line (orphan if no matching append exists in the log)."""
    return (
        f'{{"event":"status","id":"{iid}","ts":"2026-06-08T00:00:01Z",'
        f'"newStatus":"{new_status}"}}'
    )


def reserialize(line: str) -> str:
    """The SAME record with a different key order + insignificant whitespace.

    THE definition of the equivalence class the GC's canonical-form membership
    turns on, shared so the two test modules that assert it cannot drift apart
    (Stage-2 code review, catalog D). NOT an added key: adding one is different
    CONTENT, which the GC must KEEP (audit finding 14) — using it as the stand-in
    for "re-serialized" is what made the FIX B tests assert that loss as correct
    behaviour until iterate-2026-08-05-it1-audit-remainder.
    """
    obj = json.loads(line)
    return json.dumps(dict(reversed(list(obj.items()))), indent=1).replace("\n", " ")


def read_store_text(path: Path) -> str:
    """Read back what :func:`write_store_bytes` wrote ('' if absent)."""
    if not path.exists():
        return ""
    return path.read_bytes().decode("utf-8", errors="surrogateescape")


#: One raw 0xFF byte — not valid UTF-8, and what an interrupted multi-byte append
#: leaves behind. ``lib.jsonl_records`` names that truncation as an EXPECTED case and
#: the sweep re-encodes with ``surrogateescape`` in two places, so such a byte
#: genuinely reaches the committed log: rare, not contrived.
BAD_BYTE = b"\xff"


#: A SECOND invalid byte, for building a pair that COLLIDES under ``errors="replace"``
#: but stays distinct under ``surrogateescape``. Two different bad bytes at the SAME
#: offset both render as one ``U+FFFD``; two occurrences of the same bad byte at
#: DIFFERENT offsets do not. Only the former can catch a non-injective membership rule
#: — see ``test_an_undelivered_line_still_survives``.
OTHER_BAD_BYTE = b"\xfe"


def broken_bytes(line: str, marker: str = "caf", bad: bytes = BAD_BYTE) -> bytes:
    """``line`` encoded, with one invalid ``bad`` byte spliced in after ``marker``."""
    raw = line.encode("utf-8")
    assert marker.encode() in raw, f"marker {marker!r} must be present to splice after"
    return raw.replace(marker.encode(), marker.encode() + bad, 1)


def broken(line: str, marker: str = "caf", bad: bytes = BAD_BYTE) -> str:
    """:func:`broken_bytes` as the store would read it back (lone surrogate)."""
    return broken_bytes(line, marker, bad).decode("utf-8", errors="surrogateescape")


def spliceable_status(iid: str) -> str:
    """A STATUS event carrying a spliceable ``note`` marker.

    It parses as a dict, so under canonical-form membership it is compared by its
    canonical form — which is precisely why the decode asymmetry now reaches EVERY
    such line rather than only the unparseable ones the old id rule left on the
    text path.
    """
    return json.dumps(
        {"event": "status", "id": iid, "ts": "2026-08-06T00:00:00Z",
         "newStatus": "dismissed", "note": "caf"},
        sort_keys=True, separators=(",", ":"),
    )


def quarantine_text(work: Path) -> str:
    """Raw quarantine-log text ('' if absent)."""
    return read_store_text(work / QUARANTINE)


def seed_tracked(work: Path, *items: str) -> None:
    """Commit a tracked triage.jsonl (header + items) + the union .gitattributes
    + a .gitignore for the outbox on ``main``, push to origin, set origin/HEAD."""
    (work / ".shipwright").mkdir(parents=True, exist_ok=True)
    body = "\n".join([HEADER, *items]) + "\n"
    write_store_bytes(work / TRIAGE, body)
    (work / ".gitattributes").write_text(f"{TRIAGE} merge=union\n", encoding="utf-8", newline="\n")
    (work / ".gitignore").write_text(f"{OUTBOX}\n", encoding="utf-8", newline="\n")
    git(work, "add", "--", TRIAGE, ".gitattributes", ".gitignore")
    git(work, "commit", "-m", "seed triage")
    git(work, "push", "origin", "main")
    git(work, "remote", "set-head", "origin", "main")


def write_outbox(work: Path, *lines: str) -> None:
    p = work / OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(line + "\n" for line in lines)
    with p.open("ab") as fh:
        fh.write(payload.encode("utf-8", errors="surrogateescape"))


def make_worktree(work: Path, slug: str) -> Path:
    wt = work / ".worktrees" / slug
    git(work, "worktree", "add", str(wt), "-b", f"iterate/{slug}", "origin/main")
    return wt


def branch_triage_lines(wt: Path) -> set[str]:
    """Committed triage lines on the worktree branch HEAD (stripped, non-blank)."""
    proc = git(wt, "show", f"HEAD:{TRIAGE}", check=False)
    if proc.returncode != 0:
        return set()
    return {ln.strip() for ln in proc.stdout.split("\n") if ln.strip()}


def outbox_lines(work: Path) -> set[str]:
    return {ln.strip() for ln in read_store_text(work / OUTBOX).splitlines() if ln.strip()}


def outbox(work: Path) -> Path:
    return work / OUTBOX


def write_tracked(work: Path, *lines: str) -> str:
    body = "\n".join(lines) + "\n"
    write_store_bytes(work / TRIAGE, body)
    return body


@pytest.fixture
def seeded(git_origin_repo):
    """A main tree whose tracked triage log holds one committed item.

    A bare top-level name so pytest resolves it as a fixture when imported
    (``from _sweep_helpers import seeded``) — unlike the plain functions above,
    a fixture cannot be called through the ``h.`` module-qualified convention
    the rest of this file uses. Extracted here (code review, Stage 2) so a
    third test module did not duplicate what ``test_sweep_drift_guards.py`` and
    ``test_sweep_drift_commit.py`` each already define inline; those two keep
    their own copies for now — de-duplicating pre-existing code is a separate,
    boy-scout change."""
    work, _origin = git_origin_repo
    set_identity(work)
    seed_tracked(work, item("trg-seed"))
    return work
