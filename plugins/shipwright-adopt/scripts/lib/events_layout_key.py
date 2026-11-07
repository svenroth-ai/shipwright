"""The ``events_layout`` entry adopt writes into ``shipwright_sync_config.json`` (issue 978, S7).

Adopt writes the key EXPLICITLY (``legacy``; "absent = legacy" stays valid forever) but:

* an existing value is kept as is -- including a falsy or unknown one: the key is never removed or
  overwritten here (an unknown value is the layout sentinel's business, not adopt's);
* ``legacy`` is never written over live drop files (``shipwright_events.d/*.jsonl``): with the key absent
  the layout sentinel refuses a legacy write there, and an explicit ``legacy`` would switch that off.
  In that case no entry is returned.

Stdlib only (a deliberate small duplicate of ``shared/scripts/lib/events_sentinel``, ADR-045).
"""

from __future__ import annotations

import json
from pathlib import Path


def layout_entry(project_root: Path, config_path: Path) -> dict:
    """``{"events_layout": value}`` to merge into the new sync config, or ``{}``."""
    try:
        prior = json.loads(config_path.read_text(encoding="utf-8-sig")).get("events_layout")
    except (OSError, ValueError, AttributeError):
        prior = None
    if prior is not None:
        return {"events_layout": prior}
    if any((project_root / "shipwright_events.d").glob("*.jsonl")):
        return {}
    return {"events_layout": "legacy"}
