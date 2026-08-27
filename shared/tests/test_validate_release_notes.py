"""Tests for `validate_release_notes.py` — the mechanical sanitize-and-
validate gate in front of publishing an LLM-condensed release body.

Every check independently, plus the neutralization behavior that makes the
sanitized output (not just a pass/fail verdict) the thing the caller must
actually publish (Round 2 finding, both external reviewers).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from tools import validate_release_notes as vrn  # noqa: E402

FOOTER = vrn.expected_footer("1.2.3", "https://github.com/acme/widgets/blob/main/CHANGELOG.md#123", None)
FOOTER_WITH_COMPARE = vrn.expected_footer(
    "1.2.3",
    "https://github.com/acme/widgets/blob/main/CHANGELOG.md#123",
    "https://github.com/acme/widgets/compare/v1.2.2...v1.2.3",
)


def test_happy_path():
    body = "## Highlights\n\nThis release adds a widget.\n\n## Features\n\n- A new widget.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok
    assert "Full changelog for v1.2.3" in result.sanitized_body


def test_empty_body_fails():
    result = vrn.validate("", "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert result.reason == "body is empty"


def test_oversized_body_fails(monkeypatch):
    monkeypatch.setattr(vrn, "MAX_RELEASE_BODY_BYTES", 50)
    body = "## Highlights\n\n" + ("word " * 100)
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "exceeds" in result.reason


def test_bad_heading_fails():
    body = "## Not A Real Section\n\n- item\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "not in the allowed vocabulary" in result.reason


def test_missing_version_string_fails():
    footer_no_version = "Full changelog: https://github.com/acme/widgets/blob/main/CHANGELOG.md#x\n"
    body = "## Highlights\n\nSomething shipped.\n"
    result = vrn.validate(body, "9.9.9", footer=footer_no_version, repo_identity="acme/widgets")
    assert not result.ok
    assert "version string" in result.reason


def test_first_release_no_compare_link_passes():
    body = "## Highlights\n\nFirst release.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok


def test_normal_release_footer_carries_compare_link():
    body = "## Highlights\n\nAnother release.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER_WITH_COMPARE, repo_identity="acme/widgets")
    assert result.ok
    assert "Compare with the previous release" in result.sanitized_body


@pytest.mark.parametrize(
    "snippet",
    [
        "![beacon](https://evil.example/x.png)",
        "<https://evil.example>",
        '<img src="https://evil.example/x.png">',
        '<a href="https://evil.example">click</a>',
        "visit https://evil.example now",
    ],
)
def test_rejects_unsafe_url_forms(snippet):
    body = f"## Highlights\n\n{snippet}\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok


def test_rejects_external_link_host():
    body = "## Highlights\n\nSee [details](https://attacker.example/phish).\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "disallowed host" in result.reason


def test_allows_own_repo_link():
    body = "## Highlights\n\nSee [the issue](https://github.com/acme/widgets/issues/1).\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok


def test_neutralizes_mention():
    body = "## Fixed\n\n- Reported by @someuser, thanks!\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok
    assert "`@someuser`" in result.sanitized_body


def test_neutralizes_issue_ref():
    body = "## Fixed\n\n- Closes #42.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok
    assert "`#42`" in result.sanitized_body


def test_neutralizes_mention_without_breaking_an_existing_code_span():
    """External code-review finding: naively wrapping @user in fresh
    backticks closed the existing inline code span early, leaving the
    mention live outside it. An @mention already inside a code span is
    already inert (GitHub never renders it as a live link there) and must
    be left untouched — not re-wrapped in a way that escapes the span."""
    body = "## Fixed\n\n- `reported by @someuser` in the logs.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok
    assert "- `reported by @someuser` in the logs." in result.sanitized_body


def test_neutralizes_a_mention_that_sits_right_next_to_a_code_span():
    """A mention OUTSIDE a code span must still be neutralized even when a
    code span appears elsewhere on the same line."""
    body = "## Fixed\n\n- Reported by @someuser, see `the_fix()`.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok
    assert "`@someuser`" in result.sanitized_body
    assert "`the_fix()`" in result.sanitized_body


def test_rejects_link_to_a_repo_whose_name_merely_starts_with_ours():
    """External code-review finding: a raw prefix check on the allowed host
    accepted 'acme/widgets-archive' for repo_identity 'acme/widgets'."""
    body = "## Highlights\n\nSee [details](https://github.com/acme/widgets-archive/issues/1).\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "disallowed host" in result.reason


def test_rejects_emoji():
    body = "## Highlights\n\nShipped a new widget \U0001F389.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "emoji" in result.reason


def test_rejects_a_heading_with_no_content():
    body = "## Highlights\n\n## Fixed\n\n- A real fix.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "no content" in result.reason


def test_rejects_an_empty_last_heading_even_with_the_footer_appended():
    """Code-reviewer finding: the empty-section check must scope to `body`
    alone, not `body + footer` — otherwise the footer's own non-empty link
    text masks a genuinely empty LAST section."""
    body = "## Highlights\n\nSomething shipped.\n\n## Security\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "no content" in result.reason


@pytest.mark.parametrize(
    "heading_line",
    [
        "# Highlights",
        "### Highlights",
        "#### Highlights",
    ],
)
def test_rejects_a_non_h2_atx_heading(heading_line):
    """Doubt-reviewer finding: the vocabulary/empty-section gate scanned only
    exact '## ' lines, so a single '#' or '###'+ heading — still a real,
    GitHub-rendered heading per CommonMark/GFM — could carry unauthorized
    text past validation untouched."""
    body = f"## Highlights\n\nReal content.\n\n{heading_line}\n\nSneaky attacker text.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "is not an H2" in result.reason


def test_rejects_an_indented_h2_heading_outside_the_vocabulary():
    """A 1-3-space-indented '## ' line is still a real ATX H2 per
    CommonMark/GFM, so it must be checked against ALLOWED_HEADINGS like any
    other H2 — not silently skipped because it isn't an exact '## ' line."""
    body = "## Highlights\n\nReal content.\n\n  ## Not In Vocab\n\nSneaky attacker text.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert not result.ok
    assert "not in the allowed vocabulary" in result.reason


def test_allows_a_relative_in_page_anchor_link():
    """A link starting with '#' is a relative in-page anchor, always allowed
    — it never reaches the host allowlist check at all."""
    body = "## Highlights\n\nSee [the details below](#more-details).\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok


def test_main_reports_missing_body_file(tmp_path: Path, capsys):
    rc = vrn.main([
        "--body-file", str(tmp_path / "missing.md"),
        "--version", "1.2.3",
        "--changelog-anchor-url", "https://github.com/acme/widgets/blob/v1.2.3/CHANGELOG.md",
        "--out-file", str(tmp_path / "out.md"),
        "--project-root", str(tmp_path),
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "body file not found" in payload["reason"]


def test_main_writes_sanitized_body_on_success(tmp_path: Path, capsys):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/widgets.git"],
        cwd=tmp_path, check=True,
    )
    body_file = tmp_path / "body.md"
    body_file.write_text("## Highlights\n\nSomething shipped in 1.2.3.\n", encoding="utf-8")
    out_file = tmp_path / "out.md"

    rc = vrn.main([
        "--body-file", str(body_file),
        "--version", "1.2.3",
        "--changelog-anchor-url", "https://github.com/acme/widgets/blob/v1.2.3/CHANGELOG.md",
        "--out-file", str(out_file),
        "--project-root", str(tmp_path),
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert out_file.is_file()
    assert "Highlights" in out_file.read_text(encoding="utf-8")


def test_main_does_not_write_out_file_on_failure(tmp_path: Path, capsys):
    body_file = tmp_path / "body.md"
    body_file.write_text("## Not A Real Section\n\nbad heading\n", encoding="utf-8")
    out_file = tmp_path / "out.md"

    rc = vrn.main([
        "--body-file", str(body_file),
        "--version", "1.2.3",
        "--changelog-anchor-url", "https://github.com/acme/widgets/blob/v1.2.3/CHANGELOG.md",
        "--out-file", str(out_file),
        "--project-root", str(tmp_path),
    ])

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert not out_file.exists()


def test_allows_an_indented_h2_heading_inside_the_vocabulary():
    """An indented '## ' heading using an allowed name is legitimate and
    must still pass — indentation alone is not the bypass, an unchecked
    heading level was."""
    body = "## Highlights\n\nSome real content.\n\n  ## Fixed\n\n- A real fix.\n"
    result = vrn.validate(body, "1.2.3", footer=FOOTER, repo_identity="acme/widgets")
    assert result.ok
