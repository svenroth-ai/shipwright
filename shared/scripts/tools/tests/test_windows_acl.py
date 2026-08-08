"""Native Windows ACL/ownership proofs, split out of test_host_resource_locking.py
(bloat gate, iterate-2026-08-07-windows-ci-perf) -- mirrors the source-side
split between _windows_acl.py and _windows_acl_trust.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.lib import _host_resource_locking as locking
from scripts.lib import host_resource_lease as lease


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL proof")
def test_owner_sid_of_reports_the_current_users_own_sid_on_a_normal_directory(tmp_path):
    """owner_sid_of() needs no privilege to CALL -- only takeown /A needs
    privilege to REASSIGN ownership -- so this covers its body (F0 diff-
    coverage gate) without the takeown test's admin-privilege dependency.
    A directory this process just created is owned by the current user;
    owner_sid_of() and _current_sid() must agree."""
    from scripts.lib import _windows_acl

    owned = tmp_path / "self-owned"
    owned.mkdir()
    advapi, kernel = _windows_acl._apis()
    assert _windows_acl.owner_sid_of(owned) == _windows_acl._current_sid(advapi, kernel)


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL proof")
def test_owner_sid_of_raises_on_a_path_that_does_not_exist(tmp_path):
    from scripts.lib import _windows_acl

    with pytest.raises(OSError, match="GetNamedSecurityInfoW failed"):
        _windows_acl.owner_sid_of(tmp_path / "does-not-exist")


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL proof")
def test_windows_private_root_rejects_world_writable_acl(tmp_path):
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    granted = subprocess.run(
        ["icacls", str(unsafe), "/grant", "*S-1-1-0:(OI)(CI)M"],
        capture_output=True, text=True, errors="replace", check=False,
    )
    assert granted.returncode == 0, granted.stdout + granted.stderr
    try:
        with pytest.raises(lease.HostLeaseError, match="not private"):
            locking._safe_dir(unsafe / "nested", trusted_parent=tmp_path)
    finally:
        subprocess.run(
            ["icacls", str(unsafe), "/remove:g", "*S-1-1-0"],
            capture_output=True, check=False,
        )


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL proof")
def test_windows_private_file_rejects_world_writable_acl(tmp_path):
    unsafe = tmp_path / "unsafe.state.json"
    unsafe.write_text("{}", encoding="utf-8")
    granted = subprocess.run(
        ["icacls", str(unsafe), "/grant", "*S-1-1-0:M"],
        capture_output=True, text=True, errors="replace", check=False,
    )
    assert granted.returncode == 0, granted.stdout + granted.stderr
    try:
        with pytest.raises(lease.HostLeaseError, match="file is not private"):
            locking._safe_file(unsafe)
    finally:
        subprocess.run(
            ["icacls", str(unsafe), "/remove:g", "*S-1-1-0"],
            capture_output=True, check=False,
        )


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL proof")
def test_windows_acl_rejects_every_unparsed_ace_type():
    from scripts.lib import _windows_acl

    assert _windows_acl._ace_type_is_supported(0)
    assert _windows_acl._ace_type_is_supported(1)
    assert all(not _windows_acl._ace_type_is_supported(value)
               for value in range(2, 256))


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL proof")
def test_windows_private_root_accepts_administrators_owned_directory(tmp_path):
    """GitHub-hosted windows-latest provisions LOCALAPPDATA under the
    runneradmin profile with an owner of BUILTIN\\Administrators, not
    runneradmin's own user SID -- trg-eed74a42, root-caused during
    iterate-2026-08-07-windows-ci-perf. `takeown /A` reproduces that exact
    ownership shape for real (the same primitive this repo's own
    windows-tests.yml already uses to take the WSL bash.exe stub)."""
    owned = tmp_path / "admin-owned"
    owned.mkdir()
    # Reset inheritance before the ownership assertion: RUNNER_TEMP's own DACL
    # is not something this repo controls, and a dangerous inherited ACE would
    # fail this test via the ACE-danger loop, misattributed to the owner check
    # this test exists to prove -- code review, iterate-2026-08-07-windows-ci-perf.
    reset = subprocess.run(
        ["icacls", str(owned), "/inheritance:r",
         "/grant:r", f"{os.environ.get('USERNAME', 'CURRENT')}:(OI)(CI)F"],
        capture_output=True, text=True, errors="replace", check=False,
    )
    assert reset.returncode == 0, reset.stdout + reset.stderr
    taken = subprocess.run(
        ["takeown", "/F", str(owned), "/A"],
        capture_output=True, text=True, errors="replace", check=False,
    )
    if taken.returncode != 0:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            raise AssertionError(
                "could not reassign ownership to Administrators on the CI "
                f"runner -- this test IS the proof AC5/AC7 require: {taken.stderr.strip()}"
            )
        pytest.skip(
            "current account cannot reassign ownership to Administrators "
            f"(needs runneradmin-equivalent privilege): {taken.stderr.strip()}"
        )
    try:
        from scripts.lib import _windows_acl
        observed_owner = _windows_acl.owner_sid_of(owned)
        assert observed_owner == "S-1-5-32-544", (
            f"takeown /A was expected to set the owner to built-in "
            f"Administrators (S-1-5-32-544), observed {observed_owner!r} instead"
        )
        private, reason = _windows_acl.path_acl_is_private(owned)
        assert private, reason
    finally:
        subprocess.run(
            ["takeown", "/F", str(owned)],
            capture_output=True, text=True, errors="replace", check=False,
        )


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL proof")
def test_windows_private_root_rejects_a_spoofed_foreign_current_user(monkeypatch, tmp_path):
    """AC6 at the actual function boundary, not just the pure helper: a
    directory this test process owns must still be REJECTED by
    path_acl_is_private() once _current_sid is made to disagree with the
    real owner and the observed owner is not in _TRUSTED_OWNER_SIDS either.
    Without this, deleting the owner check outright -- the exact "remove it
    for Windows entirely" move the mini-plan's alternatives section rejects
    as dangerous -- would leave every other test in this file green, since
    none of them drive path_acl_is_private's reject branch. Code review,
    iterate-2026-08-07-windows-ci-perf."""
    from scripts.lib import _windows_acl

    root = tmp_path / "not-actually-yours"
    root.mkdir()
    monkeypatch.setattr(_windows_acl, "_current_sid",
                         lambda advapi, kernel: "S-1-5-21-1-2-3-1000")
    private, reason = _windows_acl.path_acl_is_private(root)
    assert not private
    assert "neither the current user" in reason


def test_owner_trust_rejects_a_genuinely_foreign_owner_sid():
    """Guards against over-widening the Administrators-owner fix: an owner
    SID that is neither the current user nor a trusted system principal
    must still be rejected. Pure string comparison, platform-independent by
    design -- this is the regression guard for `_TRUSTED_OWNER_SIDS`
    widening, and it must run in the REQUIRED Linux gate (ci.yml), not only
    in the advisory windows-tests.yml job. Imports _windows_acl_trust
    directly, NOT _windows_acl -- the latter imports ctypes.wintypes at
    module level, which raises ValueError on POSIX (the 'v' VARIANT_BOOL
    field type it registers is Windows-only), so importing it here would
    make this test error on every Linux run instead of running. Named for
    the unit actually under test (_owner_is_trusted), not path_acl_is_private
    -- see the sibling win32-gated test above for that function-level proof."""
    from scripts.lib import _windows_acl_trust

    assert not _windows_acl_trust._owner_is_trusted(
        "S-1-5-21-1-2-3-1001", "S-1-5-21-1-2-3-1000")


def test_owner_trust_accepts_a_trusted_system_principal():
    """Positive counterpart to the rejection test above: an owner SID that
    IS a trusted system principal (e.g. BUILTIN\\Administrators, the shape
    GitHub-hosted windows-latest uses for the runneradmin profile) is
    accepted even though it differs from the current user's own SID. Pure
    string comparison, platform-independent, runs in the required gate --
    imports _windows_acl_trust directly, see the sibling test above."""
    from scripts.lib import _windows_acl_trust

    assert _windows_acl_trust._owner_is_trusted("S-1-5-32-544", "S-1-5-21-1-2-3-1000")


def test_windows_acl_module_still_imports_the_trust_helper_from_its_sibling():
    """Platform-independent wiring pin: _windows_acl.py is unimportable on
    Linux (ctypes.wintypes), so nothing in the required ci.yml gate would
    otherwise notice if a rename broke its import of _windows_acl_trust --
    the break would surface only in the advisory windows-tests.yml job.
    Source-text check, not an import, so it runs everywhere. Code review,
    iterate-2026-08-07-windows-ci-perf."""
    source = (Path(__file__).resolve().parents[3] / "scripts" / "lib"
              / "_windows_acl.py").read_text(encoding="utf-8")
    assert "from scripts.lib._windows_acl_trust import" in source
    assert "_owner_is_trusted(" in source
