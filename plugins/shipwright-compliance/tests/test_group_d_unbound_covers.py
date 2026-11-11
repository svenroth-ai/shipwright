"""D-orphan words an unbound covers comment apart from a malformed tag and does not fail on it.

"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.audit import _group_d_traceability as gdt  # noqa: E402
from tests.test_group_d_traceability import _manifest  # noqa: E402

import pytest  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11/AC51")

UNBOUND = {"test": "", "raw": "a.test.ts:3: // @covers FR-01.01", "reason": "unbound-covers-comment"}
MALFORMED = {"test": "a.test.ts::t", "raw": "@FR-1.3", "reason": "non_canonical_fr_id"}


def test_only_an_unbound_covers_comment_does_not_fail_d_orphan():
    m = _manifest([])
    m["invalid_tags"] = [UNBOUND]
    status, _sev, detail, evidence, _cmd = gdt.check_orphan(m)
    assert status == "pass"
    assert "binding no declaration" in detail and "malformed" in detail
    assert evidence == [gdt.unbound_covers_line(UNBOUND)] and "[unbound_covers]" in evidence[0]


def test_a_malformed_tag_still_fails_and_is_counted_without_the_unbound_one():
    m = _manifest([])
    m["invalid_tags"] = [MALFORMED, UNBOUND]
    status, _sev, detail, evidence, _cmd = gdt.check_orphan(m)
    assert status == "fail" and "1 malformed @FR tag(s)" in detail
    assert any("[unbound_covers]" in e for e in evidence)
