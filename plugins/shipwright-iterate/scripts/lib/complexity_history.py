"""History-calibrated complexity prior from finalized iterate runs.

Replaces the bare "trivial" fall-through in classify_complexity when no
scope keyword matches: the median final complexity of the last finalized
runs is a far better default than the lowest rung (measured on this repo:
64% of Stage-1 outputs were trivial while only 14% of runs finalized
trivial — the Stage-2 scout had to bump nearly every run).

Reads the file-per-iterate store `.shipwright/agent_docs/iterates/*.json`
written by the SHARED writer `shared/scripts/tools/append_iterate_entry.py`
(F5c). This module deliberately does NOT import shared/ — at runtime the
plugin stands alone; the field/path/sort contract is pinned by the
round-trip test in tests/test_complexity_history_roundtrip.py, which feeds
this reader through the real shared writer.

Skip criteria (fail closed per entry, never crash the classifier):
- file not a regular file, larger than MAX_ENTRY_BYTES, or unparseable JSON
- JSON not an object
- `complexity` missing or not one of trivial/small/medium/large
- `date` missing, non-string, or not ISO-8601 (naive dates are assumed
  UTC — mirrors shared iterate_entry.sort_key)
Subdirectories (e.g. _quarantine/) are never read. Entries are sorted by
(date, run_id), filtered to valid FIRST, then the most recent
HISTORY_WINDOW are taken — invalid entries never displace valid ones.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from complexity_vocabulary import COMPLEXITY_ORDER

HISTORY_WINDOW = 20      # most recent finalized runs considered
HISTORY_MIN_ENTRIES = 3  # below this, no prior (cold start → old default)
MAX_ENTRY_BYTES = 262_144

# The prior alone must never route into the large escape hatch.
_PRIOR_CEILING = COMPLEXITY_ORDER.index("medium")


def _parse_utc(date_str: str) -> datetime:
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_history_prior(project_root) -> dict | None:
    """Median final complexity of recent runs, or None when unavailable.

    Returns {"prior": <level>, "n": <entries considered>} or None when
    project_root is falsy, the store is missing, or fewer than
    HISTORY_MIN_ENTRIES valid entries exist. The median uses the lower
    middle on even counts (conservative), clamped to at most "medium".
    """
    if not project_root:
        return None
    store = (
        Path(project_root).resolve()
        / ".shipwright" / "agent_docs" / "iterates"
    )
    if not store.is_dir():
        return None

    valid: list[tuple[datetime, str, int]] = []
    for path in store.glob("*.json"):
        try:
            if not path.is_file() or path.stat().st_size > MAX_ENTRY_BYTES:
                continue
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(entry, dict):
            continue
        complexity = entry.get("complexity")
        if complexity not in COMPLEXITY_ORDER:
            continue
        try:
            dt = _parse_utc(entry["date"])
        except (KeyError, TypeError, ValueError, AttributeError):
            # AttributeError: non-string date (null/number/list) — mirrors
            # shared iterate_entry.sort_key's except tuple.
            continue
        valid.append((
            dt,
            str(entry.get("run_id", "")),
            COMPLEXITY_ORDER.index(complexity),
        ))

    if len(valid) < HISTORY_MIN_ENTRIES:
        return None

    valid.sort(key=lambda item: (item[0], item[1]))
    window = valid[-HISTORY_WINDOW:]
    ranks = sorted(rank for _, _, rank in window)
    median_rank = ranks[(len(ranks) - 1) // 2]
    return {
        "prior": COMPLEXITY_ORDER[min(median_rank, _PRIOR_CEILING)],
        "n": len(window),
    }
