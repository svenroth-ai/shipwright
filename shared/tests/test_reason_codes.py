"""The shared closed reason-code vocabulary and its three consumers."""

from __future__ import annotations

import pytest

from lib.reason_codes import REASON_CODES, family_codes, reason_code_error
from lib.review_entry_checks import REVIEW_FAMILY
from tools.verifiers.iterate_checks import UNTESTABLE_REASON_CODES


@pytest.mark.covers("FR-01.11")
def test_vocabulary_is_closed_and_frozen():
    for name, codes in REASON_CODES.items():
        assert isinstance(codes, frozenset) and codes, name
    with pytest.raises(TypeError):
        REASON_CODES["new_family"] = frozenset({"x"})  # type: ignore[index]


@pytest.mark.covers("FR-01.11")
def test_untestable_family_is_the_set_the_iterate_checks_export():
    assert UNTESTABLE_REASON_CODES == REASON_CODES["untestable"]
    assert "requires-prod-credential" in UNTESTABLE_REASON_CODES


@pytest.mark.covers("FR-01.11")
def test_review_family_carries_the_codes_the_campaign_names():
    assert {"unavailable", "trivial-auto"} <= family_codes(REVIEW_FAMILY)


@pytest.mark.covers("FR-01.11")
def test_families_do_not_share_codes_by_accident():
    seen: dict[str, str] = {}
    for name, codes in REASON_CODES.items():
        for code in codes:
            assert code not in seen, f"{code!r} is in both {seen[code]} and {name}"
            seen[code] = name


@pytest.mark.covers("FR-01.11")
def test_error_for_member_non_member_unknown_family_and_non_string():
    assert reason_code_error("test_exemption", "fixture-or-helper") is None
    assert "closed test_exemption vocabulary" in reason_code_error("test_exemption", "because i said so")
    assert "unknown reason-code family" in reason_code_error("nope", "x")
    assert reason_code_error("test_exemption", None) is not None
    assert reason_code_error("test_exemption", ["fixture-or-helper"]) is not None
