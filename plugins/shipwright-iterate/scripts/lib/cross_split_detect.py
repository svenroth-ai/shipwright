"""Cross-split detection for the Stage 1 complexity classifier."""

import json
import re
from pathlib import Path

from risk_taxonomy import RISK_TAXONOMY


def detect_cross_split(
    message: str, sync_config_path: str | None
) -> dict | None:
    """Check if change spans multiple planning splits."""
    if not sync_config_path:
        return None
    try:
        # WP8/F24: utf-8-sig (BOM-tolerant) — non-ASCII FR titles otherwise crash on cp1252.
        config = json.loads(Path(sync_config_path).read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    msg_lower = message.lower()
    splits_hit = set()
    for mapping in config.get("mappings", []):
        pattern = mapping.get("pattern", "")
        parts = re.findall(r"\w+", pattern)
        for part in parts:
            if part.lower() in msg_lower and len(part) > 3:
                for fr in mapping.get("frs", []):
                    # FR format: FR-NN.XX — extract split number
                    m = re.match(r"FR-(\d+)\.", fr)
                    if m:
                        splits_hit.add(m.group(1))
                break

    if len(splits_hit) >= 2:
        flag_def = RISK_TAXONOMY["cross_split"]
        return {
            "flag": "cross_split",
            "min_complexity": flag_def["min_complexity"],
            "enforces": flag_def["enforces"],
            "splits": sorted(splits_hit),
        }
    return None
