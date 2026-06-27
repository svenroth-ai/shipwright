"""Regression for CodeQL py/loop-variable-capture in the Group C/F fixtures.

``_passing_checks`` (in ``test_audit_groups_c_f``) builds ``{cid: lambda ...}`` in
a dict comprehension. Without binding ``cid=cid`` in the lambda signature every
value-lambda closes over the single loop variable and returns the LAST id —
silently making each fixture check report the wrong name. The existing Group C/F
tests do NOT catch this (they assert the group-derived ``check_id``, not
``_FakeCheck.name``), so this pins the fix directly. Kept in its own file to
avoid growing the already-oversize ``test_audit_groups_c_f`` module.
"""

from __future__ import annotations

from tests.test_audit_groups_c_f import _passing_checks


def test_each_fixture_check_binds_its_own_id() -> None:
    """Late-binding bug would make every check report 'gamma'."""
    checks = _passing_checks(["alpha", "beta", "gamma"])
    for cid, fn in checks.items():
        assert fn(None).name == cid
