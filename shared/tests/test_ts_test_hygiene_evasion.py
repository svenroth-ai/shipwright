"""Evasion/hardening tests for ts_test_hygiene.py (TT4 doubt-review follow-up).

Pins the gate-defeating holes the adversarial review found — chained
modifiers, regex-literal lexing, conditional-skip exemption, the `\\b` global
anchor, the widened file gate, the expiry cap, quarantine-aware deletion
straddle, and `test.todo`. Threat model = FORGOTTEN skips + common idiomatic
forms, not adversarial obfuscation.
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest

from _ts_lexer import lex
from ts_test_hygiene import scan_ts_source

TODAY = date(2026, 7, 15)
SPEC = Path("e2e/login.spec.ts")


def _patterns(src: str) -> set[str]:
    return {f.pattern for f in scan_ts_source(SPEC, textwrap.dedent(src), today=TODAY)}


# --- MUST-FIX 1: chained modifiers must not evade ---


@pytest.mark.parametrize(
    "call,pattern",
    [
        ("test.only.each([[1]])('x', () => {})", "js.only"),
        ("test.concurrent.only('x', () => {})", "js.only"),
        ("test.skip.each([[1]])('x', () => {})", "js.skip.no_quarantine"),
        ("it.concurrent.skip('x', () => {})", "js.skip.no_quarantine"),
    ],
)
def test_chained_modifiers_are_flagged(call: str, pattern: str) -> None:
    assert _patterns(call + "\n") == {pattern}


# --- MUST-FIX 2: regex-literal lexing ---


def test_backtick_in_regex_does_not_swallow_skip_below() -> None:
    # doubt O3: a lone backtick in a regex must not open a template to EOF.
    src = "const B = /`/;\ntest.skip('x', () => {})\n"
    assert scan_ts_source(SPEC, src, today=TODAY)[0].pattern == "js.skip.no_quarantine"


def test_regex_literal_is_not_scanned_as_code() -> None:
    # code-review: /test.only(/ is a regex body, not a focused test.
    assert _patterns("const re = /test.only(/;\ntest('ok', () => {})\n") == set()


def test_unterminated_template_is_a_loud_finding() -> None:
    # Fail-loud: an unterminated template blanks to EOF, so signal it.
    findings = scan_ts_source(SPEC, "const s = `unclosed\ntest.skip('x', fn)\n", today=TODAY)
    assert [f.pattern for f in findings] == ["could_not_lex"]


def test_lex_records_unterminated_string() -> None:
    result = lex("const s = 'unclosed\n")
    assert result.unterminated and result.unterminated[0][1] == "string"


# --- MUST-FIX 3: conditional / in-body skip is exempt ---


@pytest.mark.parametrize(
    "call",
    [
        "test.skip(browserName === 'webkit', 'reason')",
        "test.fixme(isMobile, 'flaky on mobile')",
        "test.skip()",
    ],
)
def test_conditional_skip_is_exempt(call: str) -> None:
    assert _patterns(call + "\n") == set()


def test_declaration_skip_is_still_flagged() -> None:
    assert _patterns("test.skip('logs in', () => {})\n") == {"js.skip.no_quarantine"}


# --- MUST-FIX 4: global \b anchor must not match after a dot ---


@pytest.mark.parametrize(
    "call", ["chart.fit(data)", "obj.xit(spec)", "helper.xfail(x)"]
)
def test_dotted_global_lookalikes_are_not_flagged(call: str) -> None:
    assert _patterns(call + "\n") == set()


def test_standalone_global_focus_is_flagged() -> None:
    assert _patterns("fit('only me', () => {})\n") == {"js.only"}


# --- SHOULD-FIX 6: far-future expiry is a rubber-stamp ---


def test_far_future_expiry_fails() -> None:
    src = """\
        // @quarantine
        // reason: r
        // owner: o
        // ticket: t
        // expires: 2099-12-31
        test.skip('a', () => {})
    """
    assert _patterns(src) == {"js.skip.expiry_too_far"}


# --- SHOULD-FIX 9: test.todo is a silent non-run ---


def test_todo_is_flagged() -> None:
    assert _patterns("test.todo('implement SSO later')\n") == {"js.skip.no_quarantine"}
