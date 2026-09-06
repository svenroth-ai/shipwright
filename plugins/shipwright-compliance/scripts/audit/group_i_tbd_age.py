"""I8 — how long has a `/shipwright-adopt` TBD acceptance-criteria placeholder
survived? (iterate-2026-09-06-fr-hygiene-touched-rows)

The gap this closes: ``spec_document.py`` (`/shipwright-adopt`) emits a literal
``"_TBD — refine via /shipwright-iterate._"`` line for any FR it could not
derive acceptance criteria for. That is a legitimate starting point — but
nothing ever escalated it, and a real adopted project has carried TBD criteria
for its earliest requirements across roughly fifty iterates with no signal
anywhere that it was still open.

**No new state.** The obvious fix — stamp a "TBD since" marker next to the
line — was rejected: ``lib.fr_criteria``'s ``_leading_bullet_run`` tolerates
exactly ONE non-bullet line between an FR heading and its bullets (the
``_Source: ...._`` attribution exception); a SECOND non-bullet line
disqualifies the whole leading-bullet run, which would zero out real
acceptance criteria for any FR that has both a TBD marker and actual bullets —
breaking I6, S5's FR-coherence check, and the cross-layer hard gate at once.
Instead, "how long has this survived" is read straight from git history via
``git blame`` on the TBD line's exact position — the same "read history, don't
store it" posture ``_layer_coverage_ac.py`` already takes for criteria digests.

**Advisory, deliberately, and for a different reason than I1-I3/I6/I7.** A
stale TBD targets exactly the LEGACY content this run did not touch — the
opposite of what the diff-scoped F11 gate (``fr_hygiene.py``) enforces — so
blocking on it would redden every dormant adopted repo's CI for content
nobody in the current run wrote. This is a dashboard/triage visibility signal,
never a gate.

**Known imprecision.** Age is per PHYSICAL LINE (via ``git blame``), not
per-FR-file: two FRs sharing one spec file each get their OWN line's true
introduction date, so two TBDs in the same file are timed independently. What
is NOT tracked is a TBD line that was later reworded and re-typed
byte-identically, OR one whose line simply MOVED because an unrelated edit
earlier in the same row (or file reflow) shifted it — either resets the
clock, since plain ``git blame`` attributes a line to whichever commit last
touched it, not the commit that first introduced its CONTENT (external
review, iterate-mode leg). Both read as a fresh introduction, understating the
real age. Understating age is the safe direction for an advisory signal (it
never over-claims staleness); silently never firing would be the unsafe one.
"""

from __future__ import annotations

import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

#: The exact literal `/shipwright-adopt` emits (spec_document.py) for an FR it
#: could derive no acceptance criteria for. Matched verbatim, not fuzzily — a
#: human's own placeholder prose should never be silently tracked by a marker
#: they did not write.
TBD_MARKER = "_TBD — refine via /shipwright-iterate._"

_FR_HEADING_RE = re.compile(r"^#{1,6}\s+(FR-\d+(?:\.\d+)*)\b")

DEFAULT_THRESHOLD_DAYS = 90
_SECONDS_PER_DAY = 86400


def _tbd_lines_by_fr(content: str) -> dict[str, list[int]]:
    """1-based line numbers of every literal TBD marker line, keyed by the
    nearest FR heading ABOVE it. A TBD line before any heading is skipped —
    it cannot belong to a requirement the document has not named yet."""
    out: dict[str, list[int]] = defaultdict(list)
    current: str | None = None
    for i, line in enumerate(content.splitlines(), start=1):
        heading = _FR_HEADING_RE.match(line)
        if heading:
            current = heading.group(1)
            continue
        if current and TBD_MARKER in line:
            out[current].append(i)
    return dict(out)


def _blame_epoch(project_root: Path, spec_path: str, lineno: int) -> int | None:
    """Committer-time (unix epoch) of the commit that introduced ``lineno`` of
    ``spec_path``, or ``None`` when unavailable — no git, a rename `git blame`
    cannot resolve without more history than is present, or any subprocess
    failure (including a timeout, so a slow/stalled ``git blame`` degrades
    this one advisory finding rather than crashing the whole compliance
    audit). Never fabricates an age from an absent answer.

    Deliberately unpinned (no revision argument): a bare ``git blame`` reads
    the working tree, which is the SAME source ``frs_with_stale_tbd`` reads
    ``lineno`` from — pinning to ``HEAD`` would decouple the two, and a
    working tree with uncommitted edits above this line would then blame the
    wrong physical line. An uncommitted TBD line blames as "Not Committed
    Yet" with `committer-time` set to the current wall-clock time (verified:
    porcelain does not zero it), so it reads as age 0 — safe, since
    understating age is the direction this module's docstring already
    prefers."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "blame", "-L", f"{lineno},{lineno}",
             "--porcelain", "--", spec_path],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="ignore",
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for out_line in result.stdout.splitlines():
        if out_line.startswith("committer-time "):
            try:
                return int(out_line.split(" ", 1)[1].strip())
            except ValueError:
                return None
    return None


def frs_with_stale_tbd(
    project_root: Path,
    rows: Iterable,
    *,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
    now_epoch: int | None = None,
) -> list[str]:
    """FR ids whose TBD placeholder has survived at least ``threshold_days``,
    formatted ``"FR-XX.YY (Nd)"``. See the module docstring for why this reads
    git history instead of any stamped state, and why it is advisory."""
    now = now_epoch if now_epoch is not None else int(time.time())
    by_file: dict[str, list] = defaultdict(list)
    for row in rows:
        by_file[row.spec_path].append(row)

    stale: list[str] = []
    for spec_path, group in by_file.items():
        try:
            content = (project_root / spec_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        live_ids = {r.id for r in group}
        for fr_id, linenos in _tbd_lines_by_fr(content).items():
            if fr_id not in live_ids:
                continue  # retired, or a heading with no live row backing it
            # `linenos[0]` deliberately, not the oldest of several: an FR
            # carrying two TBD lines where the first was recently re-typed
            # reads as fresh even if a second, older one exists elsewhere in
            # its section — a documented, intentional instance of the "known
            # imprecision" the module docstring already accepts (understating
            # age is the safe direction for an advisory signal).
            epoch = _blame_epoch(project_root, spec_path, linenos[0])
            if epoch is None:
                continue
            age_days = (now - epoch) // _SECONDS_PER_DAY
            if age_days >= threshold_days:
                stale.append(f"{fr_id} ({age_days}d)")
    return sorted(stale)


__all__ = ["DEFAULT_THRESHOLD_DAYS", "TBD_MARKER", "frs_with_stale_tbd"]
