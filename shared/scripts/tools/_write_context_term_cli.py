"""CLI argument-resolution helpers for ``write_context_term.py`` — split out
the moment the combined file crossed the 300-LOC bloat-baseline threshold
(same precedent as ``_backfill_ac_provenance_apply.py``). Private (leading
underscore) and stays that way, unlike the promoted ``context_md_format.py``
(doubt-reviewer D4, P4.1 Stage-3 review) — nothing but ``write_context_term.py``
itself ever calls this.

Owns the ``--payload-file`` JSON contract that is the SANCTIONED way to pass
free text from an interview (P4.1 final review, GitHub required-check
finding): substituting free interview text directly into a shell-quoted
``--term '<value>'`` breaks out of the quoting the instant the value itself
contains a single quote, and the rest of the string is then interpreted as
shell syntax. A ``--payload-file`` is written with the Write tool — never a
shell command — so no shell ever parses the free text at all; there is no
quote-breakout surface to defend against.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


class PayloadError(ValueError):
    """A malformed ``--payload-file``, or CLI args that don't resolve to a
    complete term — reported like any other rejected input."""


def build_arg_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--payload-file", default="",
                         help="JSON file with term/definition/avoid/clear_avoid/"
                              "project_name/summary — the sanctioned way to pass "
                              "free text from an interview (see module docstring); "
                              "mutually exclusive with the flags below")
    _legacy_warning = (
        "legacy flag for trusted, non-shell-composed values only — never "
        "substitute free interview text here (a single quote breaks the "
        "shell quoting); use --payload-file for that"
    )
    parser.add_argument("--term", default=None, help=_legacy_warning)
    parser.add_argument("--definition", default=None, help=_legacy_warning)
    parser.add_argument("--avoid", default=None, help=_legacy_warning)
    parser.add_argument("--clear-avoid", action="store_true",
                         help="delete an existing --avoid line (omitting --avoid keeps it)")
    parser.add_argument("--project-name", default="", help="only used if CONTEXT.md is new")
    parser.add_argument("--summary", default="", help="only used if CONTEXT.md is new")
    parser.add_argument("--context-path", default="", help="explicit path override")
    parser.add_argument("--lock-timeout", type=float, default=5.0)
    return parser


def load_payload_file(path: str) -> dict[str, object]:
    """Read+validate a ``--payload-file`` JSON document."""
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
    if "term" not in payload or "definition" not in payload:
        raise PayloadError(f"--payload-file {path} must include 'term' and 'definition'")
    avoid = payload.get("avoid")
    # A JSON `true`/`false` is a Python `bool`, which is itself an `int`
    # subclass — `isinstance(x, bool)` still correctly rejects a plain `1`/
    # `0`/other int, since those are NOT instances of `bool` even though
    # `bool` IS an instance of `int`. `clear_avoid` defaults to `False` when
    # omitted (unchanged), but a PRESENT-and-wrong-typed value (e.g. a
    # non-empty string, which `bool(...)` used to silently coerce to
    # `True`) is now rejected outright rather than coerced.
    clear_avoid = payload.get("clear_avoid", False)
    if not isinstance(clear_avoid, bool):
        raise PayloadError(
            f"--payload-file {path}: 'clear_avoid' must be a JSON boolean "
            f"(true/false), not {clear_avoid!r}"
        )
    fields: dict[str, object] = {
        "term": payload["term"],
        "definition": payload["definition"],
        "avoid": avoid,
        "clear_avoid": clear_avoid,
        "project_name": payload.get("project_name") or "",
        "summary": payload.get("summary") or "",
    }
    str_fields = ("term", "definition", "project_name", "summary")
    if any(not isinstance(fields[k], str) for k in str_fields) or (
        avoid is not None and not isinstance(avoid, str)
    ):
        raise PayloadError(
            f"--payload-file {path}: 'term'/'definition'/'project_name'/'summary' "
            "must be strings, and 'avoid' must be a string or null"
        )
    return fields


def resolve_fields(args: argparse.Namespace) -> dict[str, object]:
    """The single decision point: ``--payload-file`` XOR the ``--term``/...
    flags. Raises :class:`PayloadError` on any invalid combination or a
    missing required field."""
    cli_fields_given = any([
        args.term is not None, args.definition is not None, args.avoid is not None,
        args.clear_avoid, args.project_name, args.summary,
    ])
    if args.payload_file and cli_fields_given:
        raise PayloadError(
            "--payload-file cannot be combined with --term/--definition/"
            "--avoid/--clear-avoid/--project-name/--summary"
        )
    if args.payload_file:
        return load_payload_file(args.payload_file)
    if args.term is None or args.definition is None:
        raise PayloadError(
            "--term and --definition are required unless --payload-file is given"
        )
    return {
        "term": args.term, "definition": args.definition, "avoid": args.avoid,
        "clear_avoid": args.clear_avoid, "project_name": args.project_name,
        "summary": args.summary,
    }
