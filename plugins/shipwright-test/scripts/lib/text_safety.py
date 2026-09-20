"""Compatibility entry point for the shared text-normalization helper."""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from shared_lib_loader import load_shared_lib  # noqa: E402

sanitize = load_shared_lib("text_safety", prefer_private=True).sanitize

__all__ = ["sanitize"]
