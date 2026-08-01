r"""The hyphen guard: a hyphen CONTINUING a word makes a reference non-bare.

`plugins/shipwright-compliance/tests/x.py` names a real plugin directory, not the
legacy `compliance/` artifact dir, but the Layer-1 canon patterns reported it as
one for months — their negative lookbehind covered word chars, `/`, `.` and `\`
but nothing for the hyphen. iterate-2026-08-01-canon-lookbehind-hyphen added a
second lookbehind, `(?<!\w-)`, to the two separator patterns of each migration.

Deliberately NOT the wider `[-\w/.\\]`: that would also suppress `-planning/` at
line start, which is a real legacy reference. ADR-080 rejected this fix on the
grounds that a hyphen-preceded path could be legitimate legacy (`pre-planning/`);
the answer is that `pre-planning` is a DIFFERENT directory from `planning`, so a
substring match was never a path reference — see the run's decision drop.

Split out of test_path_canon_windows.py (Layer 7, cross-platform coverage) in the
same change: the guard is its own subject, and the Windows module was over the
300-line budget with it inline.
"""
from __future__ import annotations

import re

import pytest

from lib.artifact_migrations import ARTIFACT_MIGRATIONS

_LOOKBEHIND_CLASS = re.compile(r"\(\?<!\[([^\]]*)\]\)")

# The guard that makes a hyphen continuing a word suppress the match.
_HYPHEN_GUARD = r"(?<!\w-)"

# Only migrations the lint actually scans. A `pending` entry is documented as a
# Layer-1 no-op (see artifact_migrations.py's registration steps), so holding one
# to the pattern shape would make registration fail before the migration is live.
_ACTIVE = [m for m in ARTIFACT_MIGRATIONS if m["status"] in ("in_progress", "migrated")]


def _lookbehind_classes(pattern: str) -> list[str]:
    """Bodies of every negative-lookbehind character class in *pattern*."""
    return _LOOKBEHIND_CLASS.findall(pattern)


def _is_separator_pattern(pattern: str) -> bool:
    """True for the two patterns that anchor on a trailing path separator."""
    return pattern.endswith("/") or pattern.endswith("\\\\")


@pytest.mark.parametrize("migration", _ACTIVE, ids=lambda m: m["name"])
def test_hyphen_suffixed_dirname_is_not_a_legacy_reference(migration):
    """A directory whose name merely ENDS in the legacy dirname after a hyphen
    is a structurally legitimate path, never a bare legacy reference.

    What makes such a reference non-bare is a hyphen that CONTINUES a word —
    every ``shipwright-*`` plugin dir has one. That is why the fix is a separate
    ``(?<!\\w-)`` lookbehind rather than a ``-`` member in the class alongside
    ``\\w / . \\``: a class member would also suppress ``-planning/`` at line
    start, which is a real legacy reference and must stay caught (see
    ``test_bare_legacy_reference_still_matches``, samples 5 and 6).
    Before iterate-2026-08-01-canon-lookbehind-hyphen the guard was absent and
    ``plugins/shipwright-compliance/tests/x.py`` was reported as a legacy path.
    """
    legacy = migration["legacy_dirname"]
    patterns = [re.compile(p) for p in migration["old_path_patterns"]]
    for sample in (
        f"plugins/shipwright-{legacy}/tests/x.py",
        f"shipwright-{legacy}/tests",
        f"plugins\\shipwright-{legacy}\\tests\\x.py",
        f"skill-{legacy}/report.md",
    ):
        hits = [p.pattern for p in patterns if p.search(sample)]
        assert not hits, (
            f"Migration `{migration['name']}` false-positives on `{sample}` "
            f"via {hits} — the legacy dirname is hyphen-suffixed onto a longer "
            f"name here, so this is a real path, not a legacy reference."
        )


@pytest.mark.parametrize("migration", _ACTIVE, ids=lambda m: m["name"])
def test_bare_legacy_reference_still_matches(migration):
    """Positive control for the hyphen fix: narrowing the lookbehind must not
    cost any real detection. A BARE legacy reference still matches, on both
    separators, at line start and mid-line."""
    legacy = migration["legacy_dirname"]
    patterns = [re.compile(p) for p in migration["old_path_patterns"]]
    for sample in (
        f"{legacy}/spec.md",
        f"{legacy}\\spec.md",
        f'path = "{legacy}/spec.md"',
        f"path = '{legacy}\\spec.md'",
        # A hyphen that starts a token is NOT a word continuing into one, so it
        # must still be caught: a diff removal line, an unspaced list marker.
        # This is what `(?<!\w-)` buys over putting `-` in the class outright.
        f"-{legacy}/spec.md",
        f"- {legacy}/spec.md",
    ):
        assert any(p.search(sample) for p in patterns), (
            f"Migration `{migration['name']}` MISSES the bare legacy reference "
            f"`{sample}` — the lookbehind has been narrowed too far."
        )


@pytest.mark.parametrize("migration", _ACTIVE, ids=lambda m: m["name"])
def test_canonical_shipwright_path_is_not_a_legacy_reference(migration):
    """The post-migration canonical form stays unmatched on both separators —
    the pre-existing ``/`` and ``\\`` members of the lookbehind class are what
    do this, and the hyphen fix must not disturb them."""
    legacy = migration["legacy_dirname"]
    patterns = [re.compile(p) for p in migration["old_path_patterns"]]
    for sample in (f".shipwright/{legacy}/x.md", f".shipwright\\{legacy}\\x.md"):
        hits = [p.pattern for p in patterns if p.search(sample)]
        assert not hits, (
            f"Migration `{migration['name']}` flags the CANONICAL path "
            f"`{sample}` via {hits}"
        )


@pytest.mark.parametrize("migration", _ACTIVE, ids=lambda m: m["name"])
def test_quoted_literal_patterns_are_unaffected_by_the_hyphen_fix(migration):
    """The hyphen belongs only in the two SEPARATOR patterns.

    In the quoted-literal patterns the lookbehind sits before the opening quote,
    where a preceding hyphen says nothing about the string's contents — and
    ``"shipwright-compliance"`` cannot match ``"compliance"`` anyway. This pins
    the untouched half behaviourally: the bare quoted literal still matches, and
    the hyphenated one still does not.
    """
    legacy = migration["legacy_dirname"]
    # Restrict to the quoted-literal half. Quantifying over ALL patterns would
    # let this pass if the quoted patterns were deleted and a separator pattern
    # later broadened to cover the sample — i.e. it could pass while the half it
    # names no longer exists.
    quoted = [re.compile(p) for p in migration["old_path_patterns"]
              if not _is_separator_pattern(p)]
    assert len(quoted) == 2, (
        f"Migration `{migration['name']}`: expected 2 quoted-literal patterns, "
        f"found {len(quoted)} — this test no longer covers the half it names"
    )
    for sample in (f'x = "{legacy}"', f"x = '{legacy}'"):
        assert any(p.search(sample) for p in quoted), (
            f"Migration `{migration['name']}` no longer flags the bare quoted "
            f"literal `{sample}` — the quoted patterns were not meant to change."
        )
    for sample in (f'x = "shipwright-{legacy}"', f"x = 'shipwright-{legacy}'"):
        assert not any(p.search(sample) for p in quoted), (
            f"Migration `{migration['name']}` flags `{sample}`"
        )


@pytest.mark.parametrize("migration", _ACTIVE, ids=lambda m: m["name"])
def test_only_separator_patterns_carry_the_hyphen_guard(migration):
    """Structural pin for a decision no behavioural test can reach.

    The guard belongs on the two SEPARATOR patterns only. Adding it to the
    quoted-literal patterns would be INERT — that lookbehind sits before the
    opening quote, and ``"shipwright-compliance"`` cannot match ``"compliance"``
    either way — so its presence or absence there is invisible to behaviour.
    That makes this the only place the decision can be pinned, and it is worth
    pinning: each lookbehind means something specific in its position, and a
    maintainer adding the guard "for consistency" should have to read why not.

    Also guards `_without_hyphen_guard` in the sibling manifest test, which
    silently returns None if the patterns stop carrying the guard substring.
    """
    for pattern in migration["old_path_patterns"]:
        guarded = _HYPHEN_GUARD in pattern
        assert guarded == _is_separator_pattern(pattern), (
            f"Migration `{migration['name']}`: pattern {pattern!r} "
            f"{'carries' if guarded else 'lacks'} the hyphen guard but is "
            f"{'a' if _is_separator_pattern(pattern) else 'not a'} separator "
            f"pattern. The guard goes on the separator patterns ONLY."
        )
        # Gemini (external plan review): a literal `-` at the END of a character
        # class is a time-bomb — appending a member silently turns it into a
        # range. The guard is its own lookbehind rather than a class member, so
        # this cannot arise today; the assertion keeps it that way if someone
        # later folds the hyphen back into a class.
        for body in _lookbehind_classes(pattern):
            assert not body.endswith("-"), (
                f"{pattern!r}: a lookbehind class ends in a bare `-`. Appending "
                f"a member would turn it into a range — put it first, or escape it."
            )


