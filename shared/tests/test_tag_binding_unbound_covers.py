"""Gate routing of an unbound covers comment (warning, never a finding) and the untagged-modified text."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from tools.verifiers._tag_binding_core import evaluate  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11/AC51")

UNBOUND = {"test": "", "raw": "app/unit/a.test.ts:3: // @covers FR-01.01", "reason": "unbound-covers-comment"}


def _manifest(**extra) -> dict:
    return {"requirements": {}, "orphans": [], "invalid_tags": [], "untagged_tests": [], **extra}


def test_unbound_covers_is_one_warning_and_no_finding():
    v = evaluate(_manifest(), _manifest(invalid_tags=[UNBOUND]), {"app/unit/a.test.ts"}, lambda p, s: "", [], set())
    assert v.findings == []
    assert len([w for w in v.warnings if "binds nothing" in w]) == 1


def test_unbound_covers_already_at_base_is_not_reported_again():
    v = evaluate(_manifest(invalid_tags=[UNBOUND]), _manifest(invalid_tags=[UNBOUND]), set(), lambda p, s: "", [], set())
    assert v.findings == [] and not [w for w in v.warnings if "binds nothing" in w]


def test_a_malformed_tag_is_still_a_finding():
    bad = {"test": "app/unit/a.test.ts::t", "raw": "@FR-1.3", "reason": "non_canonical_fr_id"}
    v = evaluate(_manifest(), _manifest(invalid_tags=[bad, UNBOUND]), set(), lambda p, s: "", [], set())
    assert [f[0] for f in v.findings] == ["invalid-tag"]


def test_untagged_modified_names_both_remedies_and_stays_a_stop():
    test = "tests/test_x.py::test_a"
    texts = {"base": "def test_a():\n    assert 1\n", "head": "def test_a():\n    assert 2\n"}
    m = _manifest(untagged_tests=[test])
    v = evaluate(m, m, {"tests/test_x.py"}, lambda p, side: texts[side], [], set())
    [(kind, _t, why)] = v.findings
    assert kind == "untagged-modified"
    assert "tag the test with the requirement it exercises" in why and "mint or extend a requirement" in why
    exempt = [{"kind": "test_exemption", "scope": test, "reason_code": "no-requirement"}]
    v = evaluate(m, m, {"tests/test_x.py"}, lambda p, side: texts[side], exempt, set())
    assert [f[0] for f in v.findings] == ["bad-exemption"]

