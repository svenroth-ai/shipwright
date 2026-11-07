"""Content-only splitter for the unsplit/split event-log fixture pair (S0).

Splits ONE legacy event log into per-run drop files by CONTENT alone: the key is
``adr_id`` else ``session`` else ``_legacy`` (design 10.2: the replay splitter
never guesses the live writer's key rule). Records keep their relative order
inside each file. Used by S1 (WebUI) and S2 (``read_events`` contract) to prove
renders are byte-identical on the unsplit baseline vs the split log.
"""

from __future__ import annotations

import json
from pathlib import Path

DROPS_DIR = "shipwright_events.d"
LEGACY_NAME = "shipwright_events.jsonl"
FIXED_WT8 = "00000000"
FIXED_NONCE = "00000000"


def content_key(event: dict) -> str:
    for field in ("adr_id", "session"):
        val = event.get(field)
        if isinstance(val, str) and val:
            return "".join(c if c.isalnum() or c in "._-" else "-" for c in val).lstrip(".")[:80] or "_legacy"
    return "_legacy"


def split_log(unsplit: Path, out_root: Path) -> list[Path]:
    """Write ``out_root/shipwright_events.d/<key>--00000000--00000000.jsonl`` files."""
    groups: dict[str, list[str]] = {}
    for raw in unsplit.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            groups.setdefault(content_key(json.loads(raw)), []).append(raw)
    folder = out_root / DROPS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for key in sorted(groups):
        path = folder / f"{key}--{FIXED_WT8}--{FIXED_NONCE}.jsonl"
        path.write_text("\n".join(groups[key]) + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written
