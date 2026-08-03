"""Upgrade coverage for immutable-evidence Git attributes."""

from lib import gitattributes_union as gu


def test_merge_into_upgrades_partial_exact_byte_rule():
    existing = gu.load_fragment().replace(" -text -diff", " -text")

    text, changed = gu.merge_into(existing)

    assert changed is True
    assert f"{gu.NON_TEXT_PATHS[0]} -text -diff" in text
    assert gu.missing_managed_paths(text) == []
