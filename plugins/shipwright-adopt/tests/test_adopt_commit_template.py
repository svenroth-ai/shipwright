"""Tests for the adopt Step H commit template (iterate-2026-05-23).

Step H creates a single ``chore(shipwright): adopt repository ...`` commit.
Post-iterate-2026-05-23 the commit body MUST carry a
``Run-ID: adopt-<YYYY-MM-DD>-<repo-name>`` trailer so the snapshot
audit (``find_snapshot_commit``) recognizes it as a compliance baseline.

The template-builder helper lives at
``plugins/shipwright-adopt/scripts/lib/adopt_commit_template.py``
(NEW in this iterate). Pure-function: given project root + adoption
metadata, returns the commit message string.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))


RUN_ID_REGEX = re.compile(
    r"^Run-ID: adopt-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$",
    re.MULTILINE,
)


def test_template_includes_run_id_trailer(tmp_path):
    """The template must contain a ``Run-ID: adopt-...`` line."""
    from lib.adopt_commit_template import build_adopt_commit_message

    msg = build_adopt_commit_message(
        project_root=tmp_path / "myrepo",
        profile="python-cli",
        scope="full_app",
        inferred_fr_count=12,
    )
    assert RUN_ID_REGEX.search(msg), (
        f"Run-ID trailer missing or malformed.\n---\n{msg}\n---"
    )


def test_template_subject_unchanged():
    """Subject line stays ``chore(shipwright): adopt repository into Shipwright SDLC``."""
    from lib.adopt_commit_template import build_adopt_commit_message

    msg = build_adopt_commit_message(
        project_root=Path("/tmp/repo"),
        profile="python-cli",
        scope="full_app",
        inferred_fr_count=5,
    )
    first_line = msg.splitlines()[0]
    assert first_line == "chore(shipwright): adopt repository into Shipwright SDLC"


def test_run_id_format_derives_from_repo_name():
    """Run-ID's repo segment = lowercased basename of project_root."""
    from lib.adopt_commit_template import build_adopt_commit_message

    msg = build_adopt_commit_message(
        project_root=Path("/tmp/MyRepo-XYZ"),
        profile="python-cli",
        scope="full_app",
        inferred_fr_count=5,
    )
    # The Run-ID segment after the date is the kebab-cased lowercase basename.
    match = RUN_ID_REGEX.search(msg)
    assert match is not None
    line = match.group(0)
    # Last hyphen-separated tokens after the date should reflect the repo name.
    assert "myrepo-xyz" in line, f"unexpected repo segment in {line!r}"


def test_run_id_handles_whitespace_and_specials_in_repo_name():
    """Special chars in repo name are sanitized to kebab-safe form."""
    from lib.adopt_commit_template import build_adopt_commit_message

    msg = build_adopt_commit_message(
        project_root=Path("/tmp/My Repo!@#"),
        profile="python-cli",
        scope="full_app",
        inferred_fr_count=5,
    )
    match = RUN_ID_REGEX.search(msg)
    assert match is not None, (
        f"Run-ID regex did not match a sanitized version: {msg!r}"
    )


def test_template_includes_profile_and_scope_in_body():
    """Body preserves the existing profile/scope phrasing."""
    from lib.adopt_commit_template import build_adopt_commit_message

    msg = build_adopt_commit_message(
        project_root=Path("/tmp/repo"),
        profile="python-cli",
        scope="full_app",
        inferred_fr_count=12,
    )
    assert "profile=python-cli" in msg
    assert "scope=full_app" in msg
    assert "12 functional requirements" in msg or "Inferred 12" in msg


def test_template_is_deterministic_for_same_date(monkeypatch):
    """Same inputs + same UTC date → byte-identical message (no wall-clock drift)."""
    from datetime import datetime, timezone

    from lib import adopt_commit_template
    from lib.adopt_commit_template import build_adopt_commit_message

    fixed = datetime(2026, 5, 23, tzinfo=timezone.utc)
    monkeypatch.setattr(adopt_commit_template, "_utc_today", lambda: fixed)

    a = build_adopt_commit_message(
        project_root=Path("/tmp/repo"),
        profile="python-cli",
        scope="full_app",
        inferred_fr_count=5,
    )
    b = build_adopt_commit_message(
        project_root=Path("/tmp/repo"),
        profile="python-cli",
        scope="full_app",
        inferred_fr_count=5,
    )
    assert a == b
