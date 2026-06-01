"""Unit tests for shared/scripts/test_hygiene.py.

Pins the public API contract: is_ci, import_or_fail_in_ci,
skip_or_fail_on_missing_binary, scan_for_silent_skip_without_ci_guard.

External-review-driven specifications:
- #G1: suppression markers use tokenize (comments preserved), not AST alone.
- #G2 + #O1: scope topology (same FunctionDef body), not "±5 lines" geometry.
- #O5: suppression marker semantics — same-line OR previous-line comment.
- #O6: no hardcoded file exclusion; rely on the explicit marker.
- #O9: capture pre-refactor message shape via exception-text assertions.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from test_hygiene import (  # noqa: E402
    Finding,
    import_or_fail_in_ci,
    is_ci,
    scan_for_silent_skip_without_ci_guard,
    skip_or_fail_on_missing_binary,
)


# ---------------------------------------------------------------------------
# is_ci()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("", False),
        ("yes", False),
        ("on", False),
    ],
)
def test_is_ci_with_env_value(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    """is_ci() must accept exactly the canonical truthy values."""
    monkeypatch.setenv("CI", value)
    assert is_ci() is expected


def test_is_ci_with_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_ci() must return False when CI is not in the environment at all."""
    monkeypatch.delenv("CI", raising=False)
    assert is_ci() is False


# ---------------------------------------------------------------------------
# import_or_fail_in_ci()
# ---------------------------------------------------------------------------


def test_import_or_fail_in_ci_local_dev_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI unset → pytest.skip with plugin-session hint."""
    monkeypatch.delenv("CI", raising=False)
    exc = ImportError("test cross-plugin pollution")
    with pytest.raises(pytest.skip.Exception) as excinfo:
        import_or_fail_in_ci("shipwright-foo", exc)
    msg = str(excinfo.value)
    assert "cross-plugin sys.path pollution" in msg
    # Plugin-session hint MUST name the owning plugin
    assert "cd plugins/shipwright-foo" in msg
    assert "uv run pytest tests/" in msg


def test_import_or_fail_in_ci_ci_mode_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI=true → pytest.fail with plugin-session hint."""
    monkeypatch.setenv("CI", "true")
    exc = ModuleNotFoundError("scripts.lib.foo")
    with pytest.raises(pytest.fail.Exception) as excinfo:
        import_or_fail_in_ci("shipwright-bar", exc)
    msg = str(excinfo.value)
    assert "cross-plugin sys.path pollution" in msg
    assert "shipwright-bar" in msg
    assert "cd plugins/shipwright-bar" in msg
    # Message must reference the import error type/text for debuggability
    assert "scripts.lib.foo" in msg


# ---------------------------------------------------------------------------
# skip_or_fail_on_missing_binary()
# ---------------------------------------------------------------------------


def test_skip_or_fail_on_missing_binary_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Binary on PATH → no-op (function returns without raising)."""
    import shutil

    monkeypatch.setattr(
        shutil, "which", lambda b: "/usr/bin/foo" if b == "foo" else None
    )
    skip_or_fail_on_missing_binary("foo", "irrelevant hint")


def test_skip_or_fail_on_missing_binary_local_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Binary missing + CI unset → pytest.skip with install hint."""
    import shutil

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(shutil, "which", lambda b: None)
    with pytest.raises(pytest.skip.Exception) as excinfo:
        skip_or_fail_on_missing_binary("missingbin", "winget install foo")
    msg = str(excinfo.value)
    assert "missingbin not on PATH" in msg
    assert "winget install foo" in msg


def test_skip_or_fail_on_missing_binary_ci_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Binary missing + CI=true → pytest.fail with install hint."""
    import shutil

    monkeypatch.setenv("CI", "1")
    monkeypatch.setattr(shutil, "which", lambda b: None)
    with pytest.raises(pytest.fail.Exception) as excinfo:
        skip_or_fail_on_missing_binary(
            "missingbin", "actions/setup-foo@v1"
        )
    msg = str(excinfo.value)
    assert "missingbin not on PATH" in msg
    assert "actions/setup-foo@v1" in msg


# ---------------------------------------------------------------------------
# scan_for_silent_skip_without_ci_guard() — AST + tokenize hybrid
# ---------------------------------------------------------------------------


def _write_test(tmp_path: Path, name: str, body: str) -> Path:
    """Write a fixture .py file under tmp_path and return its Path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


def test_scan_detects_bare_pytest_skip(tmp_path: Path) -> None:
    """A test that calls pytest.skip without an enclosing CI-gated branch
    must surface as a finding."""
    src = _write_test(
        tmp_path,
        "test_bare_skip.py",
        """
        import pytest

        def test_something():
            pytest.skip("scanner is missing")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, Finding)
    assert f.file == src
    assert "pytest.skip" in f.pattern.lower()


def test_scan_detects_skipif_decorator(tmp_path: Path) -> None:
    """@pytest.mark.skipif is ALWAYS flagged — decorator runs at collection
    time and can't carry a CI-gated branch structurally. The rule is
    'convert to body-level gate' (per AC-3 of PR #26 + ADR-044).
    """
    src = _write_test(
        tmp_path,
        "test_skipif.py",
        """
        import pytest
        import shutil

        @pytest.mark.skipif(not shutil.which("foo"), reason="foo missing")
        def test_something():
            assert True
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1
    assert "skipif" in findings[0].pattern.lower()


def test_scan_accepts_ci_gated_skip_via_is_ci_helper(tmp_path: Path) -> None:
    """A skip site preceded by `if is_ci(): pytest.fail(...)` in the same
    FunctionDef body is NOT a finding. Uses AST scope topology (same
    function), NOT line-counting (external-review #O1 + #G2).
    """
    src = _write_test(
        tmp_path,
        "test_guarded.py",
        """
        import pytest
        from test_hygiene import is_ci

        def test_something():
            if is_ci():
                pytest.fail("foo missing in CI — install via setup-foo@v1")
            pytest.skip("foo missing locally")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert findings == []


def test_scan_accepts_inverted_branch(tmp_path: Path) -> None:
    """Inverted-branch form `if not is_ci(): pytest.skip; pytest.fail` is
    semantically equivalent and must also pass (external-review #O4)."""
    src = _write_test(
        tmp_path,
        "test_inverted.py",
        """
        import pytest
        from test_hygiene import is_ci

        def test_something():
            if not is_ci():
                pytest.skip("foo missing locally")
            pytest.fail("foo missing in CI — install via setup-foo@v1")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert findings == []


def test_scan_rejects_bare_skip_and_fail_without_ci_guard(
    tmp_path: Path,
) -> None:
    """A function that calls BOTH pytest.skip AND pytest.fail without an
    enclosing CI-guard `if` is NOT a CI-gated pattern — it's just an
    unguarded test bailing out two different ways. Must be flagged.

    Regression for code-review HIGH-1: the prior implementation's
    fallback loop admitted ANY scope-level pytest.fail as proof of
    a CI gate, which would whitewash this case.
    """
    src = _write_test(
        tmp_path,
        "test_unguarded.py",
        """
        import pytest

        def test_something():
            pytest.skip("foo missing")
            pytest.fail("never reached, but the scanner used to accept this")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1, (
        "Without a CI-guard `if`, the bare skip must be flagged regardless "
        "of any scope-level pytest.fail. Got: " + repr(findings)
    )


def test_scan_rejects_distant_pytest_fail(tmp_path: Path) -> None:
    """A pytest.fail in a DIFFERENT function does NOT satisfy the CI gate
    (external-review #O1 — scope topology, not line proximity).
    """
    src = _write_test(
        tmp_path,
        "test_distant.py",
        """
        import pytest
        from test_hygiene import is_ci

        def helper_that_fails_in_ci():
            if is_ci():
                pytest.fail("not the same function")

        def test_something():
            pytest.skip("foo missing")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1
    assert findings[0].file == src


def test_scan_respects_allow_silent_skip_marker_same_line(
    tmp_path: Path,
) -> None:
    """`# test-hygiene: allow-silent-skip` on the same line as the offending
    statement suppresses the finding (external-review #O5).
    """
    src = _write_test(
        tmp_path,
        "test_marker_same_line.py",
        """
        import pytest

        def test_something():
            pytest.skip("intentional fixture")  # test-hygiene: allow-silent-skip — fixture
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert findings == []


def test_scan_respects_allow_silent_skip_marker_previous_line(
    tmp_path: Path,
) -> None:
    """`# test-hygiene: allow-silent-skip` on the line ABOVE the offending
    statement also suppresses the finding.
    """
    src = _write_test(
        tmp_path,
        "test_marker_prev_line.py",
        """
        import pytest

        def test_something():
            # test-hygiene: allow-silent-skip — fixture rationale
            pytest.skip("intentional fixture")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert findings == []


def test_scan_respects_allow_silent_skip_marker_above_comment_block(
    tmp_path: Path,
) -> None:
    """A marker placed at the top of a contiguous comment block immediately
    above the offending statement DOES suppress the finding. Natural
    Python pattern for multi-line rationale.
    """
    src = _write_test(
        tmp_path,
        "test_marker_block.py",
        """
        import pytest

        def test_something():
            # test-hygiene: allow-silent-skip — rationale starts here
            # and continues on this line and the next; the contiguous
            # comment block immediately above the skip is one logical unit.
            pytest.skip("intentional fixture with multi-line rationale")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert findings == []


def test_scan_marker_on_unrelated_line_does_not_suppress(
    tmp_path: Path,
) -> None:
    """A marker comment on an unrelated line (not same and not previous)
    does NOT suppress a finding three lines below."""
    src = _write_test(
        tmp_path,
        "test_unrelated_marker.py",
        """
        import pytest
        # test-hygiene: allow-silent-skip — wrong location

        def test_something():
            x = 1
            pytest.skip("not suppressed by far-away marker")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1


def test_scan_handles_syntax_error_gracefully(tmp_path: Path) -> None:
    """A file with a Python SyntaxError must NOT crash the scanner; emit
    a Finding with a clear `pattern` describing the parse failure
    (external-review #O10)."""
    src = _write_test(
        tmp_path,
        "test_syntax_error.py",
        """
        import pytest

        def test_broken(:
            pytest.skip("never parsed")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1
    assert "syntax" in findings[0].pattern.lower()


def test_scan_handles_missing_file_gracefully(tmp_path: Path) -> None:
    """A non-existent file must NOT crash; report as a Finding."""
    missing = tmp_path / "does_not_exist.py"
    findings = scan_for_silent_skip_without_ci_guard([missing])
    # Either a finding or empty + warning is acceptable — we just must not crash.
    # We pick "finding" semantics here so callers see the issue.
    assert all(isinstance(f, Finding) for f in findings)


def test_scan_no_findings_on_clean_file(tmp_path: Path) -> None:
    """A test file with no pytest.skip / pytest.mark.skipif must produce
    zero findings."""
    src = _write_test(
        tmp_path,
        "test_clean.py",
        """
        import pytest

        def test_something():
            assert 1 + 1 == 2
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert findings == []


def test_scan_module_level_pytest_skip_with_ci_gate(tmp_path: Path) -> None:
    """Module-level skip guarded by `if is_ci(): pytest.fail()` immediately
    above must NOT be flagged. Mirrors the canonical
    `test_path_helpers_template_vitest.py` pattern from PR #26.
    """
    src = _write_test(
        tmp_path,
        "test_module_level_ok.py",
        """
        import pytest
        import shutil
        from test_hygiene import is_ci

        if shutil.which("npx") is None:
            msg = "npx not on PATH"
            if is_ci():
                pytest.fail(msg, pytrace=False)
            pytest.skip(msg, allow_module_level=True)
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert findings == []


def test_scan_module_level_bare_skip_is_flagged(tmp_path: Path) -> None:
    """Module-level skip with NO CI gate is flagged."""
    src = _write_test(
        tmp_path,
        "test_module_level_bad.py",
        """
        import pytest
        import shutil

        if shutil.which("npx") is None:
            pytest.skip("npx missing", allow_module_level=True)
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1


def test_scan_returns_finding_dataclass_with_line(tmp_path: Path) -> None:
    """Finding must carry file + line + pattern + reason; line points to
    the offending pytest.skip/skipif call site."""
    src = _write_test(
        tmp_path,
        "test_line_info.py",
        """
        import pytest

        def test_one():
            assert True

        def test_two():
            pytest.skip("missing tool")
        """,
    )
    findings = scan_for_silent_skip_without_ci_guard([src])
    assert len(findings) == 1
    f = findings[0]
    # The pytest.skip call is on the last line of the file; line numbers
    # are 1-indexed.
    assert f.line >= 5
    assert f.reason  # non-empty
