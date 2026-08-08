"""Platform-independent trust-decision constants for _windows_acl.py.

Split out so this logic can be exercised -- and regressions against it
guarded -- in the required Linux gate (ci.yml). _windows_acl.py itself
imports `ctypes.wintypes` at module level, which is Windows-only (raises
ValueError on POSIX, since the 'v' VARIANT_BOOL field type it registers is
only supported under MS_WIN32 builds of _ctypes) -- so nothing that needs
to import cleanly on Linux can live in that module.
"""

from __future__ import annotations

_TRUSTED_SYSTEM_SIDS = {
    "S-1-3-0",       # creator-owner inheritance placeholder
    "S-1-3-4",       # owner-rights principal
    "S-1-5-18",      # LocalSystem
    "S-1-5-32-544",  # built-in Administrators
}
# Owner-trust is a NARROWER set than _TRUSTED_SYSTEM_SIDS above: S-1-3-0 and
# S-1-3-4 are ACE-only inheritance placeholders (they appear inside an ACE's
# SID field to mean "the future owner" / "the current owner", never as an
# object's actual, resolved owner returned by GetNamedSecurityInfoW), so
# including them in an owner comparison would be meaningless, not merely
# imprecise -- trg-eed74a42 external plan review, both reviewers.
_TRUSTED_OWNER_SIDS = {
    "S-1-5-18",      # LocalSystem
    "S-1-5-32-544",  # built-in Administrators
}


def _owner_is_trusted(owner_sid: str, current_sid: str) -> bool:
    """The owner is safe to trust: the current user, or one of the two
    system principals in _TRUSTED_OWNER_SIDS that can realistically own a
    real filesystem object (LocalSystem, built-in Administrators) -- a
    deliberately narrower set than _TRUSTED_SYSTEM_SIDS, which also carries
    two ACE-only placeholder SIDs that can never be a resolved owner.
    Windows commonly provisions per-user profile directories (e.g.
    LOCALAPPDATA on ephemeral, admin-provisioned CI runners) with an owner
    of BUILTIN\\Administrators rather than the specific user SID, even when
    that user is itself an administrator (trg-eed74a42). The widening is
    safe because of who can *become* the owner, not because the owner was
    already trusted some other way: absent SeRestorePrivilege, a process
    can only set an object's owner to a SID present in its own token, so a
    non-administrator caller cannot forge Administrators or LocalSystem
    ownership on a path it creates -- an adversary able to reach this
    branch is already a local administrator, who can defeat this whole
    check via SeTakeOwnershipPrivilege regardless of what this function
    decides (code review, iterate-2026-08-07-windows-ci-perf: the earlier
    "already accepted as an ACE grantee, so owner grants nothing new"
    argument was incorrect -- the owner check ran BEFORE the ACE loop and
    rejected this exact shape, which is the bug being fixed here; owner
    identity also carries implicit WRITE_DAC/WRITE_OWNER that no ACE
    entry represents, so the two are not equivalent capabilities). The
    ACE-danger loop's own trust of S-1-3-4 (OWNER RIGHTS) is unaffected in
    mechanism but now resolves against a possibly-Administrators owner
    instead of always the current user -- deliberately unreviewed here
    (Out of Scope: "any other _windows_acl.py hardening"), safe under the
    same admin-only-adversary reasoning above. Consistent also with
    _host_resource_locking.py's POSIX branch, which already accepts uid 0
    (root) as owner alongside the current user."""
    return owner_sid == current_sid or owner_sid in _TRUSTED_OWNER_SIDS
