"""Normalize externally-authored text before it is recorded or printed."""

from __future__ import annotations

import re

# C0 and C1 controls, except ordinary whitespace handled by ``split`` below.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def sanitize(text: str) -> str:
    """Strip control characters and collapse whitespace runs."""
    return " ".join(_CONTROL_CHARS.sub("", text).split())


__all__ = ["sanitize"]
