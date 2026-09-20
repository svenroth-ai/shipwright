"""Compatibility CLI and import entry point for shared journey coverage."""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from shared_lib_loader import load_shared_lib  # noqa: E402

_shared = load_shared_lib("journey_coverage", prefer_private=True)
Journey = _shared.Journey
check_journey_coverage = _shared.check_journey_coverage
parse_journeys = _shared.parse_journeys
plan_files = _shared.plan_files
slugify = _shared.slugify
spec_files = _shared.spec_files

__all__ = [
    "Journey", "check_journey_coverage", "parse_journeys", "plan_files", "slugify", "spec_files",
]

if __name__ == "__main__":
    sys.exit(_shared.main())
