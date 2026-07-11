#!/usr/bin/env python3
"""Brief-intake for /shipwright-adopt (K2d).

The WebUI "improve existing code" door (concept §2.1) can hand
``/shipwright-adopt`` the same pre-delivered *brief* the Intent Wizard hands
``/shipwright-run`` (K2c): description (free text) + users / persistence /
run_location coded answers. This module maps that brief onto ADOPT's Step-C
interview so onboarding asks ONLY what the auto-scan (Layer 1) cannot infer —
"detection over questions".

Key asymmetry vs. run: adopt onboards an EXISTING repo, so profile / scope /
stack are DETECTED from the code, never taken from the brief. The one thing the
scan cannot reliably infer is the *product intent* — what the app is FOR. That
is exactly the brief's free-text ``description``. So a brief pre-fills the
Step-C product-description confirmation (``enrichment.product_description``) and
nothing else; profile + scope stay scan/interview-driven regardless.

No brief -> nothing changes: ``adopt_intake(None)`` reports ``has_brief`` False
and an empty ``brief_prefilled`` list, so Step C runs exactly as today (AC3).

Reuse is via the shared helper ``shared/scripts/lib/brief_intake.py`` loaded
with the pollution-free ``spec_from_file_location`` loader (ADR-045) — a plain
``from lib import brief_intake`` would pin the ``lib`` namespace to
``shared/scripts/lib`` and shadow the adopt plugin's own ``lib/`` for the rest
of a cross-plugin pytest session. CLI: ``--brief <path|payload>``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional, Union

# Step-C prompts adopt DETECTS from the codebase (Layer 1) — never from a brief.
# A brief can only ever REMOVE the product-description confirmation, never add a
# question, so these stay in `scan_gated` no matter what the brief carries.
_SCAN_GATED_PROMPTS = ["profile", "scope"]

# The single Step-C prompt a brief can pre-answer: the product description.
_PRODUCT_DESCRIPTION = "product_description"


def _load_brief_intake() -> ModuleType:
    """Load ``shared/scripts/lib/brief_intake.py`` without polluting ``lib``."""
    repo_root = Path(__file__).resolve().parents[4]
    file_path = repo_root / "shared" / "scripts" / "lib" / "brief_intake.py"
    sentinel = "_shipwright_adopt_brief_intake"
    if sentinel in sys.modules:
        return sys.modules[sentinel]
    spec = importlib.util.spec_from_file_location(sentinel, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules ONLY after exec_module succeeds. brief_intake.py
    # has no circular imports, so pre-registration is unnecessary — and pre-
    # registering would poison the cache: a raising exec_module would leave a
    # half-initialised module memoized under the sentinel, so every later call
    # returns the broken module instead of re-raising.
    spec.loader.exec_module(module)
    sys.modules[sentinel] = module
    return module


def adopt_intake(source: Optional[Union[str, dict]]) -> dict:
    """Map a brief onto adopt's Step-C interview.

    ``source`` is a brief dict, an inline JSON/text payload, a file path
    (optionally ``@``-prefixed), or None. Returns:

    - ``has_brief``: whether a usable brief was supplied.
    - ``product_description``: the brief's free-text intent, or None. When
      present, adopt uses it as ``enrichment.product_description`` and skips the
      Step-C product-description confirmation.
    - ``brief_prefilled``: Step-C prompts the brief answers (``[]`` or
      ``["product_description"]``) — do NOT ask these.
    - ``scan_gated``: prompts that stay driven by the Layer-1 scan / interview
      (``profile``, ``scope``) — a brief never pre-answers or adds these.
    """
    bi = _load_brief_intake()
    result = bi.intake(source)

    has_brief = bool(result.get("has_brief"))
    brief = result.get("brief") or {}
    # The shared brief_intake.normalize_brief already collapses a blank /
    # whitespace-only description to None, so brief["description"] is either a
    # non-empty string or None here — no extra strip needed.
    product_description = brief.get("description") if has_brief else None

    brief_prefilled = [_PRODUCT_DESCRIPTION] if product_description else []

    return {
        "has_brief": has_brief,
        "product_description": product_description,
        "brief_prefilled": brief_prefilled,
        "scan_gated": list(_SCAN_GATED_PROMPTS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Brief-intake for /shipwright-adopt")
    parser.add_argument(
        "--brief",
        default=None,
        help="Brief file path (optionally @-prefixed) or inline JSON/text payload",
    )
    parser.add_argument(
        "--project-root", help="Project root (unused; accepted for parity)"
    )
    args = parser.parse_args()

    print(json.dumps(adopt_intake(args.brief), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
