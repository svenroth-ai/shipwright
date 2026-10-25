"""Does the applied Brief package account for a changed upload? (campaign brief-driven-run, B3a)

``design_gate_extras.uploads_preserved`` treats git as the historical record: a committed upload must never
show as modified. After a package change the documented recovery re-applies the NEW package, so an upload
of the same name legitimately differs from its committed bytes. It is accounted for ONLY when the applied
marker holds the hash run_config recorded AND the upload equals the package's current mockup (the package
hash's own CRLF rule). Stdlib only, no sibling import: this loads both as ``lib.*`` and as a top-level
module (ADR-045).
"""

from __future__ import annotations

import json
from pathlib import Path

_SNIFF_BYTES = 8000  # = brief_package_manifest._SNIFF_BYTES (pinned by a test)


def _norm(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n") if 0 not in raw[:_SNIFF_BYTES] else raw


def accounted_by_applied_package(project_root: Path, upload: Path) -> bool:
    root = Path(project_root)
    try:
        cfg = json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8-sig"))
        recorded = cfg["brief_package"]["package_sha256"]
        applied = json.loads((root / ".shipwright" / "designs" / "brief-package-applied.json").read_text(encoding="utf-8"))
        mockup = (root / str(cfg["brief_dir"]) / "mockups" / upload.name).resolve()
        if applied.get("package_sha256") != recorded or not mockup.is_relative_to(root.resolve()):
            return False
        return _norm(upload.read_bytes()) == _norm(mockup.read_bytes())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
