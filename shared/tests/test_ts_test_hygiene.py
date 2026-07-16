"""Unit tests for shared/scripts/ts_test_hygiene.py (traceability G6, TT4).

Pins the contract: skip/focus forms flagged unannotated (AC1); future
quarantine passes / expired fails (AC2); the lexer does NOT false-match a skip
in a comment/string (binding); diff-scoping keeps introduced/edited (AC3).
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest

from ts_test_hygiene import (  # noqa: E402
    TsFinding,
    added_lines_from_diff,
    filter_to_changed,
    is_ts_test_file,
    scan_ts_source,
    scan_ts_test_files,
)

TODAY = date(2026, 7, 15)
SPEC = Path("e2e/login.spec.ts")


def _scan(source: str) -> list[TsFinding]:
    return scan_ts_source(SPEC, textwrap.dedent(source), today=TODAY)


def _patterns(source: str) -> set[str]:
    return {f.pattern for f in _scan(source)}


# --- AC1: every skip form without quarantine is flagged ---


@pytest.mark.parametrize(
    "call",
    [
        "test.skip('a', () => {})",
        "describe.skip('a', () => {})",
        "test.fixme('a', () => {})",
        "xit('a', () => {})",
        "xdescribe('a', () => {})",
    ],
)
def test_skip_form_without_quarantine_is_flagged(call: str) -> None:
    findings = _scan(call + "\n")
    assert [f.pattern for f in findings] == ["js.skip.no_quarantine"]


@pytest.mark.parametrize(
    "call",
    [
        "test.only('a', () => {})",
        "fit('a', () => {})",
        "fdescribe('a', () => {})",
    ],
)
def test_focus_form_is_unconditional_fail(call: str) -> None:
    findings = _scan(call + "\n")
    assert [f.pattern for f in findings] == ["js.only"]


def test_only_is_not_quarantineable_even_with_annotation() -> None:
    # A quarantine block above a .only must NOT suppress it (binding).
    src = """\
        // @quarantine
        // reason: whatever
        // owner: @svroch
        // ticket: SHIP-1
        // expires: 2099-01-01
        test.only('a', () => {})
    """
    assert _patterns(src) == {"js.only"}


def test_clean_spec_has_no_findings() -> None:
    src = """\
        import { test, expect } from '@playwright/test';
        test('logs in', async ({ page }) => {
          await page.goto('/');
          expect(page.url()).toContain('/');
        });
    """
    assert _scan(src) == []


# --- AC2: quarantine metadata + expiry ---


def test_valid_future_quarantine_passes() -> None:
    src = """\
        // @quarantine
        // reason: flaky under CI parallelism
        // owner: @svroch
        // ticket: SHIP-123
        // expires: 2026-12-31
        test.skip('logs in with SSO', () => {})
    """
    assert _scan(src) == []


def test_expired_quarantine_fails() -> None:
    src = """\
        // @quarantine
        // reason: flaky under CI parallelism
        // owner: @svroch
        // ticket: SHIP-123
        // expires: 2020-01-01
        test.skip('logs in with SSO', () => {})
    """
    findings = _scan(src)
    assert [f.pattern for f in findings] == ["js.skip.expired"]
    assert "expired 2020-01-01" in findings[0].reason


def test_expires_today_is_not_expired() -> None:
    src = f"""\
        // @quarantine
        // reason: r
        // owner: o
        // ticket: t
        // expires: {TODAY.isoformat()}
        test.skip('a', () => {{}})
    """
    assert _scan(src) == []


@pytest.mark.parametrize(
    "expires",
    ["2099-13-01", "2099-1-1"],
)
def test_malformed_expires_is_treated_as_missing(expires: str) -> None:
    src = f"""\
        // @quarantine
        // reason: r
        // owner: o
        // ticket: t
        // expires: {expires}
        test.skip('a', () => {{}})
    """
    assert _patterns(src) == {"js.skip.no_quarantine"}


@pytest.mark.parametrize("drop", ["reason", "owner", "ticket", "expires"])
def test_missing_field_fails(drop: str) -> None:
    lines = [
        "// @quarantine",
        "// reason: r",
        "// owner: o",
        "// ticket: t",
        "// expires: 2099-01-01",
    ]
    kept = [ln for ln in lines if not ln.startswith(f"// {drop}:")]
    src = "\n".join(kept) + "\ntest.skip('a', () => {})\n"
    findings = scan_ts_source(SPEC, src, today=TODAY)
    assert [f.pattern for f in findings] == ["js.skip.no_quarantine"]
    assert drop in findings[0].reason


def test_block_comment_quarantine_form_passes() -> None:
    src = """\
        /* @quarantine
         * reason: upstream driver bug
         * owner: @svroch
         * ticket: SHIP-9
         * expires: 2026-09-01
         */
        it.skip('renders', () => {})
    """
    assert _scan(src) == []


def test_quarantine_must_be_immediately_above() -> None:
    """A blank line between the block and the skip breaks the association."""
    src = """\
        // @quarantine
        // reason: r
        // owner: o
        // ticket: t
        // expires: 2099-01-01

        test.skip('a', () => {})
    """
    assert _patterns(src) == {"js.skip.no_quarantine"}


# --- binding: comment/string/template awareness (no naive-regex matches) ---


@pytest.mark.parametrize(
    "decoy",
    [
        "// test.only('nope', () => {})",
        "// test.skip('nope')",
        "/* test.only('x', () => {}) */",
        "const s = 'test.only(x)';",
        "const s = `run test.only(x)`;",
    ],
)
def test_skip_or_only_in_comment_or_string_is_not_flagged(decoy: str) -> None:
    assert _scan(decoy + "\ntest('a', () => {})\n") == []


def test_multiline_template_preserves_line_numbers() -> None:
    src = "const s = `line1\nline2`;\ntest.only('real', () => {})\n"
    findings = scan_ts_source(SPEC, src, today=TODAY)
    assert [(f.pattern, f.line) for f in findings] == [("js.only", 3)]


@pytest.mark.parametrize(
    "call", ["test . skip('a', () => {})", "test\n.only('a', () => {})"]
)
def test_whitespace_around_member_access_does_not_bypass(call: str) -> None:
    # Valid JS spacing (``test . skip`` / ``test\n.only``) must still be caught.
    assert _scan(call + "\n") != []


# --- AC3: diff-scoping ---


def test_filter_keeps_finding_on_changed_line() -> None:
    findings = _scan("test.only('a', () => {})\n")
    kept = filter_to_changed(findings, {SPEC: {1}})
    assert len(kept) == 1


def test_filter_drops_untouched_preexisting_skip() -> None:
    findings = _scan("test.skip('legacy', () => {})\n")
    kept = filter_to_changed(findings, {SPEC: {99}})
    assert kept == []


def test_filter_expired_triggered_by_editing_quarantine_block() -> None:
    src = """\
        // @quarantine
        // reason: r
        // owner: o
        // ticket: t
        // expires: 2020-01-01
        test.skip('a', () => {})
    """
    findings = _scan(src)
    kept = filter_to_changed(findings, {SPEC: {5}})  # edit expires line, not skip
    assert [f.pattern for f in kept] == ["js.skip.expired"]


def test_filter_error_finding_always_survives(tmp_path: Path) -> None:
    missing = tmp_path / "gone.spec.ts"
    findings = scan_ts_test_files([missing], today=TODAY)
    assert [f.pattern for f in findings] == ["missing_file"]
    assert filter_to_changed(findings, {}) == findings


def test_no_quarantine_scope_covers_comment_block_above() -> None:
    findings = _scan("// stale note\ntest.skip('a', () => {})\n")
    assert filter_to_changed(findings, {SPEC: {1}})  # touched only the comment
    assert filter_to_changed(findings, {SPEC: {99}}) == []  # untouched


@pytest.mark.parametrize(
    "diff,expected",
    [
        ("@@ -0,0 +1,3 @@\n+a\n+b\n+c\n", {1, 2, 3}),
        ("@@ -3 +3 @@ ctx\n-a\n+b\n", {3}),
        ("@@ -5,2 +5,0 @@\n-a\n-b\n", set()),  # non-quarantine deletion: no straddle
        ("@@ -5,1 +4,0 @@\n-// expires: 2020-01-01\n", {5, 4}),  # quarantine del
    ],
)
def test_added_lines_from_diff(diff: str, expected: set[int]) -> None:
    assert added_lines_from_diff(diff) == expected


# --- helpers + batch reader ---


@pytest.mark.parametrize(
    "path,expected",
    [
        (Path("login.spec.ts"), True),
        (Path("login.test.tsx"), True),
        (Path("e2e/checkout.e2e.ts"), True),  # custom testMatch name + e2e/ dir
        (Path("tests/util.ts"), True),  # under tests/ dir
        (Path("helpers.ts"), False),  # bare non-test ts
        (Path("test_thing.py"), False),
    ],
)
def test_is_ts_test_file(path: Path, expected: bool) -> None:
    assert is_ts_test_file(path) is expected


def test_scan_ts_test_files_reads_from_disk(tmp_path: Path) -> None:
    spec = tmp_path / "a.spec.ts"
    spec.write_text("test.only('x', () => {})\n", encoding="utf-8")
    findings = scan_ts_test_files([spec], today=TODAY)
    assert [f.pattern for f in findings] == ["js.only"]
