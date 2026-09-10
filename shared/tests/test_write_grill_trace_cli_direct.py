"""In-process (non-subprocess) coverage for
``_write_grill_trace_cli.py``'s ``build_arg_parser`` / ``load_payload_file``.

Sibling of ``test_write_grill_trace_direct.py`` — see that file's module
docstring for why direct (in-process) calls are needed alongside the
existing ``subprocess``-based CLI tests: this module's coverage is otherwise
invisible to the diff-coverage gate, since the CLI is exercised only through
a separate ``sys.executable`` child process elsewhere in this suite.
Precedent: ``test_write_context_term_cli_direct.py`` (P4.1's identical fix).
"""

from __future__ import annotations

import json

import pytest

from tools import _write_grill_trace_cli as cli_module
from tools._write_grill_trace_cli import (
    PayloadError,
    build_arg_parser,
    load_payload_file,
)


# ---------------------------------------------------------------------------
# build_arg_parser()
# ---------------------------------------------------------------------------

def test_build_arg_parser_defaults():
    parser = build_arg_parser("a description")
    args = parser.parse_args(["--project-root", ".", "--payload-file", "payload.json"])
    assert args.project_root == "."
    assert args.planning_dir == ""
    assert args.payload_file == "payload.json"
    assert args.lock_timeout == 5.0


def test_build_arg_parser_parses_every_flag():
    parser = build_arg_parser("a description")
    args = parser.parse_args([
        "--project-root", "proj",
        "--planning-dir", "alt-planning",
        "--payload-file", "payload.json",
        "--lock-timeout", "1.5",
    ])
    assert args.project_root == "proj"
    assert args.planning_dir == "alt-planning"
    assert args.payload_file == "payload.json"
    assert args.lock_timeout == 1.5


def test_build_arg_parser_requires_payload_file():
    parser = build_arg_parser("a description")
    with pytest.raises(SystemExit):
        parser.parse_args(["--project-root", "."])


# ---------------------------------------------------------------------------
# load_payload_file()
# ---------------------------------------------------------------------------

def test_load_payload_file_happy_path(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"requirement_key": "login-rate-limit", "surface": "project"}),
        encoding="utf-8",
    )
    fields = load_payload_file(str(payload_path))
    assert fields == {"requirement_key": "login-rate-limit", "surface": "project"}


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


def test_load_payload_file_top_level_scalar_raises(tmp_path):
    """A bare JSON scalar (not even a list) hits the same non-dict branch."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("42", encoding="utf-8")
    with pytest.raises(PayloadError, match="must contain a JSON object"):
        load_payload_file(str(payload_path))


def test_cli_module_reference_is_the_same_object_used_by_write_grill_trace():
    """Sanity check that this file is exercising the exact functions
    write_grill_trace.py imports (not a stale/shadowed copy)."""
    assert cli_module.build_arg_parser is build_arg_parser
    assert cli_module.load_payload_file is load_payload_file
