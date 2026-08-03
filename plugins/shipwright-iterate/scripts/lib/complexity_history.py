"""History-calibrated complexity prior from finalized iterate runs.

Replaces the bare "trivial" fall-through in classify_complexity when no
scope keyword matches: the median final complexity of the last finalized
runs is a better default than the lowest rung (measured on this repo:
64% of Stage-1 outputs were trivial while only 14% of runs finalized
trivial — the Stage-2 scout had to bump nearly every run).

The result is capped at `small` (`_PRIOR_CEILING`, rationale below). That
cap is load-bearing, and it narrows what this module does: where the
history is richer than `small` the prior no longer discriminates, so the
question it answers is "is this repo's fall-through floor `trivial` or
`small`?" — not "which tier does this change need?". Stated plainly here
because the module is easy to read as still predicting the tier.

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

# The fall-through may inform how LOW to go, never how HIGH.
#
# `medium` is the first tier that buys an iterate spec, a mini-plan, an
# approval gate and an external LLM plan review. Those are bought with POSITIVE
# evidence — a scope keyword, a risk flag, a cross-split, or the Stage-2 Repo
# Scout — never with the absence of evidence.
#
# The ceiling is also what breaks the ratchet (trg-ee7b83e5). The prior is the
# median of FINAL complexities, and for a run with no scope keyword the final
# complexity IS the prior, so `prior = median(finals)` is self-consistent at any
# level and carries no information about the change being classified. It had
# settled on `medium`: measured 2026-07-31 over the 50 retained entries, 84%
# medium / 14% small / 2% trivial, each new no-keyword run re-depositing
# `medium` into the window that produced it. Capping at `small` bounds the loop
# whatever the history contains.
#
# Direction chosen from the asymmetry: under-classification is recoverable
# in-session (Stage 2 confirms/upgrades; SKILL.md ships Mid-Flight Escalation),
# while over-classification is not — complexity locks after Stage 2 and nothing
# de-escalates.
#
# NOT chosen (yet): "median over keyword-classified runs only" — the anchor's
# other option. The reason is the BACKFILL BLACKOUT, and only that: no entry
# written before 2026-07-31 carries `prior_source`, so the filter would find
# zero qualifying entries, fall under HISTORY_MIN_ENTRIES, return None, and
# drop the fall-through to bare `trivial` — a far larger process cut than this
# cap — until >=3 (usefully, >=20) new runs accumulate.
#
# An earlier draft of this comment also claimed the option was BLOCKED because
# recording the field needs an edit to the 425/425-grandfathered
# `shared/scripts/tools/append_iterate_entry.py`. Both halves were false and
# are retracted (doubt review, 2026-07-31): that file is limit 300 / current
# 436, and its CLI splats `**extra` from `--entry-json` with no allowlist, so
# recording a new key costs zero lines there. The figure was carried over from
# the anchor instead of measured — the exact failure this run's spec §0 was
# written to catch.
#
# Consequently F5c now RECORDS `prior_source` (references/F5c.md), so the
# option becomes available once the window fills, and the flip-rate this change
# causes becomes measurable instead of merely asserted.
# See 2026-07-31-it5-classification-calibration.md §1.
_PRIOR_CEILING = COMPLEXITY_ORDER.index("small")


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
    middle on even counts (conservative), clamped to at most "small".

    `prior` is the EFFECTIVE level — already capped. Callers report it as
    `signals.history_prior`, so that signal names the level actually used,
    never the raw median it was derived from.
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
        # Canonical summaries have exactly one extension. Secondary-extension
        # siblings (`.plan.json`, `.test-results.json`, future sidecars) are not
        # finalized history entries even if their schemas later gain date and
        # complexity fields.
        if "." in path.stem:
            continue
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
