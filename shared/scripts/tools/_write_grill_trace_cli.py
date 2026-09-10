"""CLI argument-resolution for ``write_grill_trace.py`` — split out up front
(same precedent as ``_write_context_term_cli.py``). Private and stays that
way; nothing but ``write_grill_trace.py`` calls this.

Owns the ``--payload-file`` JSON contract — the ONLY sanctioned way to pass
free interview text into this tool (P4.1's precedent, carried over
verbatim): a hand-assembled ``--requirement-text '<value>'`` shell argument
breaks out of its quoting the instant the interview's own words contain a
single quote. The caller writes a small JSON file with the Write tool
(never a shell command) and this script's argv then never carries free
text at all.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


class PayloadError(ValueError):
    """A malformed ``--payload-file`` — reported like any other rejected input."""


def build_arg_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--planning-dir", default="",
                         help="override the planning dir (default: "
                              "<project-root>/.shipwright/planning)")
    parser.add_argument("--payload-file", required=True,
                         help="JSON file holding the full grill-trace record "
                              "(shared/grill-trace-format.md) — the sanctioned "
                              "way to pass free interview text; see module docstring")
    parser.add_argument("--lock-timeout", type=float, default=5.0)
    return parser


def load_payload_file(path: str) -> dict[str, object]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PayloadError(f"cannot read --payload-file {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PayloadError(f"--payload-file {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PayloadError(f"--payload-file {path} must contain a JSON object")
    return payload
