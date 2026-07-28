"""The tracked handoff and its canon marker — one reader, one renderer.

Two checks ask questions of ``.shipwright/agent_docs/session_handoff.md``:

* ``handoff_freshness.check_session_handoff_fresh`` — the F11 iterate check
  ("does this note belong to the run finishing now").
* ``handoff_phase_canon.check_c3_session_handoff_fresh_after_phase`` — Canon C3
  ("did THIS phase leave the note").

They ask different questions of the same bytes, so the *reading* lives here and
only the judging lives in each check. ``lib.canon_frontmatter`` was extracted in
iterate-2026-07-27-name-the-blocker for the same reason one level down: two
implementations of one format drift, and these two would drift on what counts as
a readable handoff. This module split out in
iterate-2026-07-27-c3-phase-history-join when C3 grew a phase_history join and
the combined module crossed the 300-LOC limit.

Nothing here decides pass or fail. It reports what is on disk — including, as
distinct states, "no file", "unreadable file", and "file without a marker",
because those three have three different operator remedies.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.canon_frontmatter import parse_canon_frontmatter  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402

#: Marker values are host-of-record data but still arbitrary file content; clip
#: before they reach a Stop-hook finding so a malformed handoff cannot dump a
#: wall of text into operator output.
MAX_MARKER_CHARS = 120

#: C0, DEL and C1 ranges, plus the bidi/zero-width formatting controls. These
#: details are rendered into terminals and logs (``format_report`` emits real
#: ANSI itself), so an ESC/OSC sequence — or a RIGHT-TO-LEFT OVERRIDE, the
#: Trojan-Source trick — carried in a tracked handoff could rewrite what the
#: operator sees. Strip rather than escape: nothing downstream needs the bytes.
#: Built from codepoints so this source stays pure ASCII — a literal RLO sitting
#: in this file would be exactly the hazard the class exists to remove.
_CONTROL_RANGES: tuple[tuple[int, int], ...] = (
    (0x00, 0x1F),      # C0
    (0x7F, 0x9F),      # DEL + C1
    (0x200B, 0x200F),  # zero-width space/joiners, LTR/RTL marks
    (0x202A, 0x202E),  # bidi embeddings + overrides (Trojan-Source)
    (0x2066, 0x2069),  # bidi isolates
)
_CONTROL_CHARS_RE = re.compile(
    "[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _CONTROL_RANGES) + "]"
)


@dataclass(frozen=True)
class Handoff:
    """A structured read of the tracked handoff.

    ``problem`` is non-empty exactly when the file could not be read at all;
    ``marker`` is ``None`` when the file was read but carries no canon marker.
    Distinct states with distinct remedies, which is why this is a record rather
    than an optional string.
    """

    problem: str = ""
    content: str = ""
    marker: dict[str, str] | None = None

    @property
    def missing(self) -> bool:
        """True when the file does not exist (as opposed to being unreadable).

        A named property, not a comparison against the message text: the F11
        check's branch ordering depends on telling these apart, and encoding
        that contract in an exact string would break silently the first time
        anyone reworded it.
        """
        return self.problem == _MISSING


_MISSING = "session_handoff.md missing"


def read_handoff(project_root: Path) -> Handoff:
    """Read the tracked handoff and parse its canon marker, without judging it.

    Missing and unreadable are resolved by ATTEMPTING the read, not by
    ``is_file()``: that helper swallows the ``OSError`` from an inaccessible path
    and answers ``False``, which would report a handoff that exists but cannot be
    opened as one that was never written — two different defects with two
    different remedies, collapsed into the wrong one.
    """
    path = Path(project_root) / ".shipwright" / "agent_docs" / "session_handoff.md"
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return Handoff(problem=_MISSING)
    except OSError as exc:
        return Handoff(problem=f"session_handoff.md unreadable ({type(exc).__name__})")
    # `parse_canon_frontmatter` already returns None for absent, malformed, and
    # non-canon (`canon_generated` not true) blocks — one gate, not three.
    return Handoff(content=content, marker=parse_canon_frontmatter(content))


def clip(value: str) -> str:
    """Bound and de-fang a value before it enters an operator-facing detail."""
    value = " ".join(_CONTROL_CHARS_RE.sub(" ", str(value)).split())
    return value if len(value) <= MAX_MARKER_CHARS else value[:MAX_MARKER_CHARS] + "…"


def warn(name: str, detail: str) -> CheckResult:
    """A WARNING-severity finding — the handoff is advisory, never load-bearing."""
    return CheckResult(name, False, detail, severity=Severity.WARNING.value)


def skip(name: str, detail: str) -> CheckResult:
    """An explicit, NAMED skip — never a silent pass."""
    return CheckResult(name, None, detail, severity=Severity.SKIPPED.value)


__all__ = [
    "MAX_MARKER_CHARS",
    "Handoff",
    "clip",
    "read_handoff",
    "skip",
    "warn",
]
