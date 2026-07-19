"""ADR header parsing for ``.shipwright/agent_docs/decision_log.md``.

Split out of ``drift_parsers`` in campaign S2 (iterate-2026-07-19-one-discovery-
function). ``drift_parsers`` had grown into a five-cluster grab-bag -- CLAUDE.md
structure blocks, gitignore, dev blocks, FR tables and ADR headers -- so the
bloat-baseline "deep module" argument could not be made for it honestly. This
cluster is the one with no coupling to the others: it shares no regex, no
dataclass and no helper with them, and moving it took ``drift_parsers`` from
532 back under its 523-LOC grandfathered ceiling.

The public surface is unchanged in shape; only the import path moved. Consumers
are ``lib.adr_parser``, ``tools/verifiers/common.py`` and compliance Group G.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


# Old verbose format: "## ADR-001 | date | section | Commit <hash>"
_ADR_OLD_HEADER_RE = re.compile(
    r"^## (?P<id>ADR-\d+) \| (?P<date>.+?) \| (?P<section>.+?) \| Commit (?P<commit>.+)$"
)
# Compact format: "### ADR-001: Title"
_ADR_COMPACT_HEADER_RE = re.compile(r"^### (?P<id>ADR-\d+):\s*(?P<title>.+)$")

# Supersession marker, matching both "**Supersedes:** ADR-NNN" (Shipwright
# convention, colon inside the asterisks) and "**Supersedes**: ADR-NNN"
# (bold-then-colon style). Also accepts bare "Supersedes: ADR-NNN".
_ADR_SUPERSEDES_RE = re.compile(
    r"(?:\*\*Supersedes:\*\*|\*\*Supersedes\*\*:|Supersedes:)\s*(ADR-\d+)",
    re.IGNORECASE,
)

# Status bullet, same story — the canonical Shipwright form is
# "- **Status:** accepted" (colon inside the asterisks).
_ADR_STATUS_RE = re.compile(
    r"(?:\*\*Status:\*\*|\*\*Status\*\*:|Status:)\s*(?P<status>[A-Za-z_ -]+)",
)

ADR_VALID_STATUSES: frozenset[str] = frozenset({
    "proposed", "accepted", "rejected", "superseded", "deprecated",
})


@dataclass(frozen=True)
class ADRHeader:
    id: str                        # "ADR-027"
    title: str                     # "Modular Verifier Package + Canon Definition"
    line_no: int                   # 1-based line number of the header
    status: str | None = None      # parsed lowercase status, None if not stated
    supersedes: tuple[str, ...] = ()  # IDs superseded by this ADR


def parse_adr_headers(content: str) -> list[ADRHeader]:
    """Parse ADR headers out of a decision_log.md body.

    Supports both formats used in the Shipwright repo:

    - Old verbose: ``## ADR-NNN | date | section | Commit hash``
    - Compact: ``### ADR-NNN: Title``

    Each returned ``ADRHeader`` scans forward until the next ADR header
    (or end of file) to pick up the inline ``**Status:**`` and
    ``**Supersedes:**`` bullets. Callers that only need IDs can ignore
    those fields; iterate 12.0 common.py uses them for the F1/F2/F3 ADR
    integrity checks imported from the shipwright-check plan.
    """
    lines = content.splitlines()
    # First pass: find header line indices.
    header_hits: list[tuple[int, str, str]] = []  # (idx, id, title)
    for idx, line in enumerate(lines):
        m = _ADR_OLD_HEADER_RE.match(line)
        if m:
            title = f"{m.group('section')} ({m.group('date')})"
            header_hits.append((idx, m.group("id"), title))
            continue
        m = _ADR_COMPACT_HEADER_RE.match(line)
        if m:
            header_hits.append((idx, m.group("id"), m.group("title").strip()))

    out: list[ADRHeader] = []
    for i, (idx, adr_id, title) in enumerate(header_hits):
        body_end = header_hits[i + 1][0] if i + 1 < len(header_hits) else len(lines)
        body = "\n".join(lines[idx:body_end])

        status: str | None = None
        smatch = _ADR_STATUS_RE.search(body)
        if smatch:
            status = smatch.group("status").strip().lower()

        supersedes = tuple(_ADR_SUPERSEDES_RE.findall(body))

        out.append(ADRHeader(
            id=adr_id,
            title=title,
            line_no=idx + 1,
            status=status,
            supersedes=supersedes,
        ))
    return out


def extract_adr_id_number(adr_id: str) -> int | None:
    """Return the numeric part of an ADR id, or None if it doesn't match."""
    if not adr_id.startswith("ADR-"):
        return None
    try:
        return int(adr_id.removeprefix("ADR-"))
    except ValueError:
        return None


def find_duplicate_adr_ids(headers: Iterable[ADRHeader]) -> list[str]:
    """Return ADR ids that appear more than once in the parsed headers."""
    seen: dict[str, int] = {}
    for h in headers:
        seen[h.id] = seen.get(h.id, 0) + 1
    return sorted([adr_id for adr_id, count in seen.items() if count > 1])


def find_gaps_in_adr_ids(headers: Iterable[ADRHeader]) -> list[int]:
    """Return missing numeric ADR ids in the sequence present in ``headers``.

    Example: headers ``[ADR-023, ADR-025, ADR-027]`` → gaps ``[24, 26]``.
    Ignores duplicates and non-parseable ids.
    """
    numbers = sorted({
        n for h in headers
        if (n := extract_adr_id_number(h.id)) is not None
    })
    if len(numbers) < 2:
        return []
    low, high = numbers[0], numbers[-1]
    present = set(numbers)
    return [n for n in range(low, high + 1) if n not in present]
