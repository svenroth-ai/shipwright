"""Resolver gaps found by S1's review cascade, fixed in S2 (D1 / D4).

* A dangling ``.shipwright/profiles`` (or dangling ``.shipwright``) link is a BROKEN
  source, not an absent one: resolution fails, it never falls through to a lower source.
* ``NaN`` / ``Infinity`` are not JSON.
* ``SHIPWRIGHT_USER_PROFILES_DIR`` that is set but unusable is reported by ``list``.

Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py for the FR note).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_resolver as pr  # noqa: E402
from shared.tests.profile_test_fixtures import proj_dir, write_profile  # noqa: E402
from shared.tests.profile_test_fixtures import profile_project, profile_user_dir  # noqa: E402,F401  (module-local fixtures: "project", "user_dir")

pytestmark = pytest.mark.covers("FR-01.06")


def _dangling_dir_link(link: Path, tmp_path: Path) -> None:
    """Make ``link`` a directory link whose target no longer exists (skip without the privilege)."""
    target = tmp_path / f"gone-{link.name}"
    target.mkdir()
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("cannot create symlinks here")
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, text=True)
        if done.returncode != 0:
            pytest.skip("cannot create a junction here")
    target.rmdir()
    assert os.path.lexists(link) and not os.path.exists(link)


def test_dangling_project_profiles_dir_fails_instead_of_falling_through(project, tmp_path):
    _dangling_dir_link(proj_dir(project), tmp_path)
    with pytest.raises(pr.ProfileInvalid, match="dangling") as exc:
        pr.resolve_profile("vite-hono", project)  # a bundled name: must NOT silently win
    assert exc.value.kind == "invalid" and exc.value.exit_code == 3
    with pytest.raises(pr.ProfileInvalid, match="dangling"):
        pr.resolve_profile("generic", project)


def test_dangling_dot_shipwright_fails_too(project, tmp_path):
    _dangling_dir_link(project / ".shipwright", tmp_path)
    with pytest.raises(pr.ProfileInvalid, match="dangling"):
        pr.resolve_profile("vite-hono", project)


def test_list_warns_about_a_dangling_project_dir_and_still_lists_bundled(project, tmp_path):
    _dangling_dir_link(proj_dir(project), tmp_path)
    out = pr.list_profiles(project)
    assert any("dangling" in w for w in out["warnings"])
    assert "vite-hono" in {r["name"] for r in out["profiles"]}


def test_dangling_user_dir_is_absent_for_resolve_and_a_warning_in_list(project, user_dir, tmp_path):
    user_dir.rmdir()
    _dangling_dir_link(user_dir, tmp_path)
    assert pr.resolve_profile("vite-hono", project).source == "bundled"
    assert any("dangling" in w for w in pr.list_profiles(project)["warnings"])


def test_existing_dir_and_absent_dir_are_not_dangling(project):
    assert pr.dangling(str(project)) is False
    assert pr.dangling(str(project / "nope" / "deeper")) is False


@pytest.mark.parametrize("body", ['{"name": "p", "x": NaN}', '{"name": "p", "x": Infinity}',
                                  '{"name": "p", "x": -Infinity}'])
def test_nan_and_infinity_are_not_json(project, body):
    d = proj_dir(project)
    d.mkdir(parents=True)
    (d / "p.json").write_text(body, encoding="utf-8")
    with pytest.raises(pr.ProfileInvalid, match="not valid JSON"):
        pr.resolve_profile("p", project)


def test_list_reports_a_user_dir_variable_that_is_set_but_ignored(project, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_USER_PROFILES_DIR", "relative/profiles")
    assert pr.user_dir() is None
    assert any("ignored" in w for w in pr.list_profiles(project)["warnings"])


def test_list_is_quiet_about_the_variable_when_it_is_usable(project):
    assert not any("ignored" in w for w in pr.list_profiles(project)["warnings"])


@pytest.mark.skipif(os.name != "nt", reason="drive-less rooted paths are a Windows notion")
def test_drive_less_rooted_user_dir_is_ignored_on_windows(monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_USER_PROFILES_DIR", "\\profiles")  # current drive of the cwd
    assert pr.user_dir() is None


def test_list_row_uses_the_one_resolved_path_for_a_linked_profile(project, tmp_path):
    """``_row`` validates through the resolved path (no second, divergent resolution)."""
    write_profile(tmp_path / "elsewhere", "linked")
    d = proj_dir(project)
    d.mkdir(parents=True)
    try:
        os.symlink(tmp_path / "elsewhere" / "linked.json", d / "linked.json")
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks here")
    row = next(r for r in pr.list_profiles(project)["profiles"] if r["name"] == "linked")
    assert row["valid"] is False and "outside" in row["error"]
