"""Compatibility entry point for the shared journey-plan parser."""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from shared_lib_loader import load_shared_lib  # noqa: E402

_shared = load_shared_lib("journey_plan", prefer_private=True)
Journey = _shared.Journey
malformed_flow_headings = _shared.malformed_flow_headings
parse_journeys = _shared.parse_journeys
plan_files = _shared.plan_files
slugify = _shared.slugify
spec_files = _shared.spec_files

__all__ = ["Journey", "malformed_flow_headings", "parse_journeys", "plan_files", "slugify", "spec_files"]
