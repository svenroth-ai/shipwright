"""Tests for ``_is_safe_split_name`` (``_project_gate_manifest.py``).

Split out of ``test_project_gate_no_empty_split.py`` (shared bloat gate,
300-line limit; req3-06-enforcement-mono sub-iterate e2, round 7) — that
file already carries ``check_no_empty_split``'s manifest-parsing and
missing/unreadable-spec regression tests, so the name-safety predicate
gets its own file rather than pushing the parent past the limit again.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.verifiers._project_gate_manifest import _is_safe_split_name  # noqa: E402


def test_is_safe_split_name_rejects_windows_drive_and_root_relative_names():
    """External code review (round 6, low+medium, both reviewers
    independently): ``is_absolute()`` alone misses Windows DRIVE-relative
    (``"C:foo"``) and ROOT-relative (``"\\\\outside"``) names — neither
    counts as absolute to pathlib (it requires BOTH drive and root), but
    either re-anchors ``planning_dir / name`` away from the planning tree."""
    assert _is_safe_split_name("C:foo") is False
    assert _is_safe_split_name("\\outside\\spec") is False
    assert _is_safe_split_name("01-a") is True


def test_is_safe_split_name_rejects_backslash_traversal_on_any_host_os():
    """Required Tier-3 PR review (PR #729): the ``..``/``.`` segment check
    used to parse ``name`` with the host-native ``Path``, so a backslash
    traversal name stayed one literal part on POSIX (backslash isn't a
    separator there) and was judged safe — but the name is committed data
    later joined by whichever OS reads the manifest, where backslash IS a
    separator. Must be rejected regardless of which OS runs this check."""
    assert _is_safe_split_name("foo\\..\\..\\escape") is False
