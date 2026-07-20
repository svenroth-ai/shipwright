"""Unit tests for canonical FR-id sequence assignment (trg-c9669d6a).

Adopt numbers detected features/routes ``1..N`` and stamps each with a
requirement id. A naive ``f"FR-01.{n:02d}"`` silently emits the non-canonical
``FR-01.100`` past 99 detections; the canonical machine token is ``FR-GG.MM``
with exactly two digits per side (mirror of
``shared/scripts/lib/requirement_model.CANONICAL_FR_RE``). These tests pin the
group-rollover behaviour and that every emitted id is canonical.
"""

import re

import pytest

from lib.fr_id_sequence import canonical_fr_id

# Mirror of shared/scripts/lib/requirement_model.CANONICAL_FR_RE — the gate the
# generated ids must satisfy downstream (is_canonical_fr / namespace_for_id).
CANONICAL_FR_RE = re.compile(r"^FR-\d{2}\.\d{2}$")


def test_sub_100_sequence_is_unchanged() -> None:
    # Behaviour for the common case (<= 99 features) is byte-identical to the
    # old ``f"FR-01.{n:02d}"`` — this fix only touches the >99 tail.
    assert canonical_fr_id(1) == "FR-01.01"
    assert canonical_fr_id(9) == "FR-01.09"
    assert canonical_fr_id(10) == "FR-01.10"
    assert canonical_fr_id(99) == "FR-01.99"


def test_rolls_group_over_at_100_instead_of_emitting_fr_01_100() -> None:
    # The bug: past 99 the old code produced "FR-01.100" (three-digit minor),
    # which fails is_canonical_fr and blows up namespace_for_id downstream.
    assert canonical_fr_id(100) == "FR-02.01"
    assert canonical_fr_id(101) == "FR-02.02"
    assert canonical_fr_id(198) == "FR-02.99"
    assert canonical_fr_id(199) == "FR-03.01"


def test_every_id_up_to_the_ceiling_is_canonical() -> None:
    for n in range(1, 9802):
        fid = canonical_fr_id(n)
        assert CANONICAL_FR_RE.match(fid), f"{n} -> {fid} is non-canonical"


def test_non_positive_sequence_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_fr_id(0)
    with pytest.raises(ValueError):
        canonical_fr_id(-1)


def test_overflow_beyond_group_99_rejected() -> None:
    # 99 groups * 99 minors = 9801 is the last canonical id (FR-99.99).
    assert canonical_fr_id(9801) == "FR-99.99"
    with pytest.raises(ValueError):
        canonical_fr_id(9802)


def test_e2e_baseline_spec_ids_canonical_past_99() -> None:
    # Real call site: the e2e baseline generator numbers routes 1..N. With >99
    # routes every embedded FR id must still be canonical (rolled to FR-02.*).
    from lib.e2e_baseline_generator import render_baseline_spec

    routes = [
        {"url": f"/r{i}", "title": f"R{i}", "h1": "", "buttons": []}
        for i in range(120)
    ]
    spec = render_baseline_spec(routes)
    ids = re.findall(r"FR-\d+\.\d+", spec)
    assert ids, "no FR ids rendered"
    non_canonical = [i for i in ids if not CANONICAL_FR_RE.match(i)]
    assert not non_canonical, non_canonical
    assert "FR-02.01" in ids  # rolled over past FR-01.99
