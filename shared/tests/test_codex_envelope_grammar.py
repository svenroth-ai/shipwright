"""Tests for shared/scripts/lib/codex_envelope_grammar.py (R2 — M7).

``compose()``/``parse()`` are the one shared module for the first-prompt-
embedded closed grammar an armed Codex activation record is minted from.
``parse()`` must NEVER raise — its input is the raw first-prompt text of a
live Codex session, which is untrusted/attacker-influenceable (a pasted log
or README could contain stray text) — any malformed shape is ``None``, never
an exception. See the iterate spec's Design Notes for the full contract and
the exact wire format this test matrix is drawn from verbatim."""

from __future__ import annotations

import base64
import json

import pytest


def test_round_trip_with_args():
    from lib.codex_envelope_grammar import Envelope, compose, parse

    text = compose("shipwright-iterate:iterate", {"run_id": "iterate-2026-09-20-r2", "n": 3})
    envelope = parse(text)

    assert envelope == Envelope(
        skill_id="shipwright-iterate:iterate",
        args={"run_id": "iterate-2026-09-20-r2", "n": 3},
    )


def test_round_trip_with_empty_args():
    from lib.codex_envelope_grammar import Envelope, compose, parse

    text = compose("bare-skill-id", {})
    envelope = parse(text)

    assert envelope == Envelope(skill_id="bare-skill-id", args={})


def test_round_trip_embedded_in_larger_first_prompt():
    from lib.codex_envelope_grammar import Envelope, compose, parse

    marker = compose("shipwright-iterate:iterate", {"run_id": "r2"})
    text = f"Please start working. {marker} Thanks!"

    assert parse(text) == Envelope(skill_id="shipwright-iterate:iterate", args={"run_id": "r2"})


def test_no_marker_present_returns_none():
    from lib.codex_envelope_grammar import parse

    assert parse("just an ordinary first prompt, nothing special here") is None


def test_marker_split_across_line_break_returns_none():
    from lib.codex_envelope_grammar import compose, parse

    marker = compose("shipwright-iterate:iterate", {"run_id": "r2"})
    # Simulate a reflowed/line-wrapped paste: inject a newline mid-marker.
    midpoint = len(marker) // 2
    reflowed = marker[:midpoint] + "\n" + marker[midpoint:]

    assert parse(reflowed) is None


def test_two_markers_in_one_text_returns_none():
    from lib.codex_envelope_grammar import compose, parse

    marker = compose("shipwright-iterate:iterate", {"run_id": "r2"})
    text = f"{marker} some text in between {marker}"

    assert parse(text) is None


def test_marker_regex_rejects_out_of_charset_base64():
    # A charset-invalid args_b64 (contains "!") never even matches the
    # marker regex, so this exercises the "no match" branch of parse(),
    # not the base64-decode failure branch (that's the next test).
    from lib.codex_envelope_grammar import parse

    text = "[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=shipwright-iterate:iterate|args_b64=not!valid!base64]"

    assert parse(text) is None


def test_charset_valid_but_undecodable_base64_returns_none():
    # A single base64 character is charset-valid but an invalid length for
    # any padding — this is what actually drives the binascii.Error branch
    # in _b64_decode_args.
    from lib.codex_envelope_grammar import parse

    text = "[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=shipwright-iterate:iterate|args_b64=A]"

    assert parse(text) is None


def test_valid_base64_but_not_utf8_returns_none():
    from lib.codex_envelope_grammar import parse

    non_utf8 = base64.urlsafe_b64encode(bytes([0x80, 0x80, 0x80])).rstrip(b"=").decode("ascii")
    text = f"[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=shipwright-iterate:iterate|args_b64={non_utf8}]"

    assert parse(text) is None


def test_valid_base64_but_not_json_returns_none():
    from lib.codex_envelope_grammar import parse

    garbage = base64.urlsafe_b64encode(b"not json at all {{{").rstrip(b"=").decode("ascii")
    text = f"[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=shipwright-iterate:iterate|args_b64={garbage}]"

    assert parse(text) is None


def test_valid_json_but_not_an_object_returns_none():
    from lib.codex_envelope_grammar import parse

    not_an_object = base64.urlsafe_b64encode(json.dumps([1, 2, 3]).encode("utf-8")).rstrip(b"=").decode("ascii")
    text = f"[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=shipwright-iterate:iterate|args_b64={not_an_object}]"

    assert parse(text) is None


def test_compose_raises_on_invalid_skill_id():
    from lib.codex_envelope_grammar import compose

    with pytest.raises(ValueError):
        compose("has a space", {})


def test_compose_raises_on_empty_skill_id():
    from lib.codex_envelope_grammar import compose

    with pytest.raises(ValueError):
        compose("", {})


def test_compose_raises_on_trailing_newline_in_skill_id():
    # Regression: Python's `$` anchor (without re.MULTILINE) matches just
    # before a trailing newline, not strictly end-of-string — a naive
    # `^charset$` validation regex would let "ok\n" through even though
    # "\n" is outside the declared skill_id charset, silently producing a
    # marker that then fails to round-trip through parse() (which correctly
    # rejects embedded newlines). Must be anchored with \Z or use fullmatch.
    from lib.codex_envelope_grammar import compose

    with pytest.raises(ValueError):
        compose("shipwright-iterate:iterate\n", {})


def test_parse_never_raises_on_arbitrary_garbage():
    from lib.codex_envelope_grammar import parse

    # A grab-bag of adversarial-shaped inputs that must all degrade to None,
    # never an exception — this is the module's core safety contract.
    garbage_inputs = [
        "",
        "[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=|args_b64=]",
        "[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=ok|args_b64=" + "=" * 200 + "]",
        "SHIPWRIGHT-CODEX-ACTIVATE-v1 skill_id=ok args_b64=",
        "[shipwright-codex-activate-v1|skill_id=ok|args_b64=]",
        "\x00\x01[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=ok|args_b64=e30]\x02",
    ]
    for candidate in garbage_inputs:
        parse(candidate)  # must not raise
