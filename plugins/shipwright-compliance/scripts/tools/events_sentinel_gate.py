"""Release-evidence gate (issue 978, S7): load ``shared/scripts/lib/events_sentinel.py`` by FILE location.

A ``sys.path`` insert of ``shared/scripts`` would shadow this plugin's own ``lib`` package
(see ``collectors/_lib_loader.py``), so the stdlib-only sentinel is loaded without touching it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def evidence_refusal(project_root: Path, producer: str) -> dict | None:
    """The refusal record when the repo's events layout is unsupported, else ``None``."""
    path = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib" / "events_sentinel.py"
    spec = importlib.util.spec_from_file_location("_shipwright_events_sentinel", path)
    if spec is None or spec.loader is None or not path.is_file():
        return {"status": "refused_events_sentinel_missing", "producer": producer,
                "error": f"events-layout sentinel not found at {path}; broken install, refusing to produce evidence"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evidence_refusal(project_root, producer)
