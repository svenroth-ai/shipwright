"""In-process (non-subprocess) coverage for
``_write_context_term_cli.py``'s ``build_arg_parser`` / ``load_payload_file``
/ ``resolve_fields``.

Sibling of ``test_write_context_term_direct.py`` — see that file's module
docstring for why direct (in-process) calls are needed alongside the
existing ``subprocess``-based CLI tests: this module's coverage is otherwise
invisible to the diff-coverage gate, since the CLI is exercised only through
a separate ``sys.executable`` child process elsewhere in this suite.
"""

from __future__ import annotations

import json

import pytest

from tools import _write_context_term_cli as cli_module
from tools._write_context_term_cli import (
    PayloadError,
    build_arg_parser,
    load_payload_file,
    resolve_fields,
)


# ---------------------------------------------------------------------------
# build_arg_parser()
# ---------------------------------------------------------------------------

def test_build_arg_parser_defaults():
    parser = build_arg_parser("a description")
    args = parser.parse_args(["--project-root", "."])
    assert args.project_root == "."
    assert args.payload_file == ""
    assert args.term is None
    assert args.definition is None
    assert args.avoid is None
    assert args.clear_avoid is False
    assert args.project_name == ""
    assert args.summary == ""
    assert args.context_path == ""
    assert args.lock_timeout == 5.0


def test_build_arg_parser_parses_every_flag():
    parser = build_arg_parser("a description")
    args = parser.parse_args([
        "--project-root", "proj",
        "--term", "Order",
        "--definition", "def",
        "--avoid", "avoid text",
        "--clear-avoid",
        "--project-name", "Acme",
        "--summary", "sum",
        "--context-path", "/tmp/CONTEXT.md",
        "--lock-timeout", "1.5",
    ])
    assert args.term == "Order"
    assert args.definition == "def"
    assert args.avoid == "avoid text"
    assert args.clear_avoid is True
    assert args.project_name == "Acme"
    assert args.summary == "sum"
    assert args.context_path == "/tmp/CONTEXT.md"
    assert args.lock_timeout == 1.5


# ---------------------------------------------------------------------------
# load_payload_file()
# ---------------------------------------------------------------------------

def test_load_payload_file_happy_path(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({
            "term": "Order",
            "definition": "a confirmed purchase.",
            "avoid": "cart.",
            "clear_avoid": False,
            "project_name": "Acme",
            "summary": "an order tool.",
        }),
        encoding="utf-8",
    )
    fields = load_payload_file(str(payload_path))
    assert fields == {
        "term": "Order",
        "definition": "a confirmed purchase.",
        "avoid": "cart.",
        "clear_avoid": False,
        "project_name": "Acme",
        "summary": "an order tool.",
    }


def test_load_payload_file_defaults_optional_fields(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": "a confirmed purchase."}),
        encoding="utf-8",
    )
    fields = load_payload_file(str(payload_path))
    assert fields["avoid"] is None
    assert fields["clear_avoid"] is False
    assert fields["project_name"] == ""
    assert fields["summary"] == ""


def test_load_payload_file_missing_path_raises(tmp_path):
    with pytest.raises(PayloadError, match="cannot read --payload-file"):
        load_payload_file(str(tmp_path / "does-not-exist.json"))


def test_load_payload_file_invalid_json_raises(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(PayloadError, match="not valid JSON"):
        load_payload_file(str(payload_path))


def test_load_payload_file_non_object_raises(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('["a", "b"]', encoding="utf-8")
    with pytest.raises(PayloadError, match="must contain a JSON object"):
        load_payload_file(str(payload_path))


def test_load_payload_file_missing_required_field_raises(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"term": "Order"}), encoding="utf-8")
    with pytest.raises(PayloadError, match="must include 'term' and 'definition'"):
        load_payload_file(str(payload_path))


def test_load_payload_file_non_string_field_raises(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": 12345}), encoding="utf-8"
    )
    with pytest.raises(PayloadError, match="must be strings"):
        load_payload_file(str(payload_path))


def test_load_payload_file_non_string_avoid_raises(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": "x", "avoid": 42}), encoding="utf-8"
    )
    with pytest.raises(PayloadError, match="must be strings"):
        load_payload_file(str(payload_path))


def test_load_payload_file_non_boolean_clear_avoid_raises(tmp_path):
    """A truthy-but-not-boolean ``clear_avoid`` (e.g. a non-empty string)
    must be rejected outright, not silently coerced to ``True`` via
    ``bool(...)`` — a malformed payload should fail loudly, never change
    behavior unexpectedly."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": "x", "clear_avoid": "false"}),
        encoding="utf-8",
    )
    with pytest.raises(PayloadError, match="'clear_avoid' must be a JSON boolean"):
        load_payload_file(str(payload_path))


def test_load_payload_file_clear_avoid_true_still_accepted(tmp_path):
    """A genuine JSON boolean must still work — the stricter check must not
    reject the legitimate value it was already accepting."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": "x", "clear_avoid": True}),
        encoding="utf-8",
    )
    fields = load_payload_file(str(payload_path))
    assert fields["clear_avoid"] is True


# ---------------------------------------------------------------------------
# resolve_fields()
# ---------------------------------------------------------------------------

def test_resolve_fields_from_payload_file(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": "a confirmed purchase."}),
        encoding="utf-8",
    )
    parser = build_arg_parser("d")
    args = parser.parse_args(["--project-root", ".", "--payload-file", str(payload_path)])
    fields = resolve_fields(args)
    assert fields["term"] == "Order"
    assert fields["definition"] == "a confirmed purchase."


def test_resolve_fields_from_cli_flags():
    parser = build_arg_parser("d")
    args = parser.parse_args([
        "--project-root", ".",
        "--term", "Order",
        "--definition", "a confirmed purchase.",
        "--avoid", "cart.",
    ])
    fields = resolve_fields(args)
    assert fields == {
        "term": "Order",
        "definition": "a confirmed purchase.",
        "avoid": "cart.",
        "clear_avoid": False,
        "project_name": "",
        "summary": "",
    }


def test_resolve_fields_missing_term_and_definition_raises():
    parser = build_arg_parser("d")
    args = parser.parse_args(["--project-root", "."])
    with pytest.raises(PayloadError, match="--term and --definition are required"):
        resolve_fields(args)


def test_resolve_fields_payload_file_combined_with_cli_flags_raises(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": "a confirmed purchase."}),
        encoding="utf-8",
    )
    parser = build_arg_parser("d")
    args = parser.parse_args([
        "--project-root", ".",
        "--payload-file", str(payload_path),
        "--term", "Cancellation",
    ])
    with pytest.raises(PayloadError, match="cannot be combined"):
        resolve_fields(args)


def test_resolve_fields_payload_file_combined_with_clear_avoid_raises(tmp_path):
    """``cli_fields_given`` also trips on the boolean/store-true flag, not
    just the string ones — covers the ``args.clear_avoid`` arm of the
    ``any([...])`` check."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"term": "Order", "definition": "a confirmed purchase."}),
        encoding="utf-8",
    )
    parser = build_arg_parser("d")
    args = parser.parse_args([
        "--project-root", ".",
        "--payload-file", str(payload_path),
        "--clear-avoid",
    ])
    with pytest.raises(PayloadError, match="cannot be combined"):
        resolve_fields(args)


def test_cli_module_reference_is_the_same_object_used_by_write_context_term():
    """Sanity check that this file is exercising the exact functions
    write_context_term.py imports (not a stale/shadowed copy)."""
    assert cli_module.build_arg_parser is build_arg_parser
    assert cli_module.resolve_fields is resolve_fields
