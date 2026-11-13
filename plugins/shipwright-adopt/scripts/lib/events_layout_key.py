"""The ``events_layout`` entry adopt writes into ``shipwright_sync_config.json`` (issue 978, S7).

Adopt writes the key EXPLICITLY (``legacy``; "absent = legacy" stays valid forever) but:

* an existing value is kept as is -- including a falsy, unknown or JSON-``null`` one: the key is never removed or
  overwritten here (an unknown value is the layout sentinel's business, not adopt's; it reads an explicit ``null``
  as an unsupported declaration, so turning it into ``legacy`` would silently switch the refusal off);
* ``legacy`` is never written over live drop files (``.shipwright/events/drops/*.jsonl``): with the key absent
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
        cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        cfg = None
    if isinstance(cfg, dict) and "events_layout" in cfg:   # presence, not value: an explicit null is a declaration too
        return {"events_layout": cfg["events_layout"]}
    if any((project_root / ".shipwright/events/drops").glob("*.jsonl")):
        return {}
    return {"events_layout": "legacy"}
