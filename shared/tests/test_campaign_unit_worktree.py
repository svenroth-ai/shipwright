"""Unit tests for lib.campaign_unit_worktree (campaign-dag-scheduler R2).

Covers the composite worktree identity, the guard-mode properties Work
Breakdown item 1 calls for (a directory merely starting with the same string
is still rejected; a recomputed-vs-stored path mismatch is rejected), the
security-hardening path-escape refusal, and the Windows path-length bound.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.campaign_unit_worktree import (
    CampaignUnitWorktreeError,
    WINDOWS_MAX_PATH,
    composite_worktree_name,
    git_admin_path,
    path_length_error,
    resolved_worktree_path,
)
from lib.worktree_location import worktree_location_error


# --- composite_worktree_name -------------------------------------------------


def test_composite_name_attempt_zero_has_no_suffix():
    assert composite_worktree_name("dag-scheduler", "R2") == "campaign-dag-scheduler--R2"


def test_composite_name_attempt_one_adds_suffix():
    assert composite_worktree_name("dag-scheduler", "R2", attempt=1) == "campaign-dag-scheduler--R2-a1"


def test_composite_name_rejects_invalid_campaign_slug():
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name("bad slug!", "R2")


def test_composite_name_rejects_invalid_unit_id():
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name("dag-scheduler", "R2/../etc")


def test_composite_name_rejects_a_unit_id_containing_the_reserved_separator():
    """`id_charset_ok` already rejects a literal '--' — verified here because
    a caller could otherwise forge a second separator and collide two
    different (slug, unit_id) pairs onto the same composite string."""
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name("dag-scheduler", "R2--R3")


def test_composite_name_rejects_non_int_attempt():
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name("dag-scheduler", "R2", attempt="1")  # type: ignore[arg-type]


def test_composite_name_rejects_negative_attempt():
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name("dag-scheduler", "R2", attempt=-1)


def test_composite_name_rejects_bool_attempt():
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name("dag-scheduler", "R2", attempt=True)  # type: ignore[arg-type]


@pytest.mark.parametrize("reserved", ["CON", "con", "Nul", "COM1", "lpt9"])
def test_composite_name_rejects_windows_reserved_unit_id(reserved):
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name("dag-scheduler", reserved)


@pytest.mark.parametrize("reserved", ["CON", "AUX", "PRN"])
def test_composite_name_rejects_windows_reserved_campaign_slug(reserved):
    with pytest.raises(CampaignUnitWorktreeError):
        composite_worktree_name(reserved, "R2")


def test_composite_name_allows_a_name_merely_containing_a_reserved_substring():
    """A reserved check is a whole-segment match, not a substring ban —
    'console' and 'comedy' are legitimate ids."""
    assert composite_worktree_name("console", "comedy") == "campaign-console--comedy"


# --- resolved_worktree_path ---------------------------------------------------


def test_resolved_worktree_path_lands_under_worktrees_dir(tmp_path):
    path = resolved_worktree_path(tmp_path, "dag-scheduler", "R2")
    assert path == (tmp_path / ".worktrees" / "campaign-dag-scheduler--R2").resolve()


def test_resolved_worktree_path_propagates_identity_errors(tmp_path):
    with pytest.raises(CampaignUnitWorktreeError):
        resolved_worktree_path(tmp_path, "bad slug!", "R2")


# --- path_length_error ---------------------------------------------------


def test_path_length_error_empty_for_a_short_path(tmp_path):
    assert path_length_error(tmp_path, "dag-scheduler", "R2") == ""


def test_path_length_error_names_slug_and_unit_id_when_too_long(tmp_path):
    long_slug = "s" * 40
    long_unit = "u" * 64
    error = path_length_error(tmp_path, long_slug, long_unit, max_path=50)
    assert error != ""
    assert long_slug in error
    assert long_unit in error


def test_path_length_error_respects_a_custom_max_path(tmp_path):
    # A path that fits under the real Windows bound but not under an
    # artificially tight one passed by the caller.
    error = path_length_error(tmp_path, "dag-scheduler", "R2", max_path=10)
    assert error != ""
    assert path_length_error(tmp_path, "dag-scheduler", "R2", max_path=WINDOWS_MAX_PATH) == ""


def test_git_admin_path_shares_the_composite_basename(tmp_path):
    admin = git_admin_path(tmp_path, "dag-scheduler", "R2")
    assert admin == (tmp_path / ".git" / "worktrees" / "campaign-dag-scheduler--R2").resolve()


def test_path_length_error_also_catches_an_overflowing_admin_path(tmp_path):
    """The real-world case this closes: a worktree path comfortably under
    max_path whose git ADMIN path (nested one level deeper under
    `.git/worktrees/`) is what actually overflows — reproduced here by
    pointing `main_root` at a path deep enough that only the (longer,
    because of the extra `.git/worktrees/` segment) admin path crosses a
    tight custom bound."""
    deep_root = tmp_path
    for i in range(3):
        deep_root = deep_root / f"seg{i}"
    deep_root.mkdir(parents=True)
    worktree_len = len(str(resolved_worktree_path(deep_root, "dag-scheduler", "R2")))
    admin_len = len(str(git_admin_path(deep_root, "dag-scheduler", "R2")))
    assert admin_len > worktree_len  # extra "worktrees" path segment
    error = path_length_error(deep_root, "dag-scheduler", "R2", max_path=worktree_len)
    assert error != ""
    assert "git administrative" in error


# --- guard-mode: composite identity through the existing location guard ------
#
# Work Breakdown item 1: "a directory merely starting with the same string is
# still rejected; recomputed-vs-stored path mismatch is rejected". The guard
# itself (lib.worktree_location.worktree_location_error) is untouched by R2 —
# these tests exercise it with the COMPOSITE slug shape this module mints,
# proving `expected_campaign_slug` already supports it with zero code change
# to the guard (call-site wiring only, per this module's own docstring).


def _add_campaign_worktree(work: Path, dirname: str) -> Path:
    wt = work / ".worktrees" / dirname
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(wt),
         "-b", f"iterate/{dirname}", "main"],
        capture_output=True, text=True, check=True,
    )
    return wt


def test_guard_accepts_the_exact_composite_worktree(git_origin_repo):
    work, _ = git_origin_repo
    name = composite_worktree_name("dag-scheduler", "R2")
    wt = _add_campaign_worktree(work, name)
    assert worktree_location_error(wt, expected_campaign_slug="dag-scheduler--R2") == ""


def test_guard_rejects_a_directory_merely_starting_with_the_same_string(git_origin_repo):
    """R2 vs R20 — a prefix collision the exact-directory-basename compare
    must still reject; this is exactly the shape a bare `attempt` string
    concatenation (rather than this module's `-a{n}` suffix rule) could
    otherwise create by accident."""
    work, _ = git_origin_repo
    exact = composite_worktree_name("dag-scheduler", "R2")
    prefixed = composite_worktree_name("dag-scheduler", "R20")
    assert exact != prefixed
    assert prefixed.startswith(exact)
    wt = _add_campaign_worktree(work, prefixed)
    error = worktree_location_error(wt, expected_campaign_slug="dag-scheduler--R2")
    assert error != ""


def test_guard_rejects_a_recomputed_path_mismatch(git_origin_repo):
    """The full resolved path is compared, not just the basename — a sibling
    directory nested one level deeper sharing the right name must still be
    rejected (mirrors test_worktree_location_error.py's existing nested-dir
    case, exercised here with the composite per-unit shape)."""
    work, _ = git_origin_repo
    name = composite_worktree_name("dag-scheduler", "R2")
    nested = work / ".worktrees" / "other" / name
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(nested),
         "-b", "iterate/nested-unit", "main"],
        capture_output=True, text=True, check=True,
    )
    error = worktree_location_error(nested, expected_campaign_slug="dag-scheduler--R2")
    assert error != ""


def test_guard_rejects_a_different_unit_within_the_same_campaign(git_origin_repo):
    work, _ = git_origin_repo
    wt = _add_campaign_worktree(work, composite_worktree_name("dag-scheduler", "R3"))
    error = worktree_location_error(wt, expected_campaign_slug="dag-scheduler--R2")
    assert error != ""
    assert "dag-scheduler--R2" in error
