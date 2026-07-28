#!/usr/bin/env python3
"""Per-source SARIF file writing for the scan CLI.

Extracted from ``scan.py`` (which sits at its bloat baseline) so the CLI can
carry the coverage manifest without ratcheting. Behaviour is unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from sarif_writer import to_sarif  # noqa: E402

# Scanners with a known SARIF capability — emit one .sarif file per source
# even on clean scans so `upload-sarif` doesn't fail on an empty directory.
SARIF_DEFAULT_SOURCES: tuple[str, ...] = ("semgrep", "trivy", "gitleaks")


def write_sarif_outputs(findings: list[dict[str, Any]], sarif_dir: Path) -> None:
    """Write one SARIF 2.1.0 file per scanner source.

    Always writes a placeholder for every source in `SARIF_DEFAULT_SOURCES`
    (semgrep, trivy, gitleaks) — even on clean scans — so that
    `github/codeql-action/upload-sarif@v3` doesn't fail on an empty directory.
    Additional sources discovered in `findings` get their own file too.
    """
    sarif_dir.mkdir(parents=True, exist_ok=True)

    by_source: dict[str, list[dict[str, Any]]] = {s: [] for s in SARIF_DEFAULT_SOURCES}
    for f in findings:
        if not isinstance(f, dict):
            continue
        src = (f.get("source") or "unknown").strip().lower() or "unknown"
        by_source.setdefault(src, []).append(f)

    for source, group in by_source.items():
        doc = to_sarif(group, source=source)
        out_path = sarif_dir / f"{source}.sarif"
        out_path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
