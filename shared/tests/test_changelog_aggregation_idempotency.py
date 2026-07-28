"""Re-running a release writes the version once.

`/shipwright-changelog` SKILL.md Step 4 makes ``aggregate_changelog.py`` the
writer the release path invokes. Its atomic write happens BEFORE the unlink
loop, so an interruption in that window leaves the drop files on disk — and
before this suite existed, a re-run inserted a **second** ``## [x.y.z]``.

This module covers the arms that CONVERGE. The arms that REFUSE — where
replacing would destroy released history — live in
``test_changelog_aggregation_refusal.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# APPEND, not insert(0): `shared/tests/tools/` would shadow the
# `shared/scripts/tools` package the conftest puts on the path, and the
# fixtures module imports `tools.aggregate_changelog`.
sys.path.append(str(Path(__file__).resolve().parent))
from _changelog_release_fixtures import (
    changelog_text,
    drop_texts,
    interrupt_after_write,
    pending,
    seed,
    seed_drops,
)
from changelog_splice import apply_section
from tools.aggregate_changelog import CHANGELOG_NAME, aggregate


@pytest.fixture
def project(tmp_path: Path) -> Path:
    seed(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# AC3 — the version appears exactly once
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_rerun_after_interrupted_release_writes_the_version_once(project: Path) -> None:
    """AC3 — same release date: run 2 leaves the file byte-identical to run 1."""
    seed_drops(project, pending())
    interrupt_after_write(project, "0.3.0", "2026-04-23")
    after_run_1 = changelog_text(project)
    assert after_run_1.count("## [0.3.0]") == 1

    aggregate(project, "0.3.0", release_date="2026-04-23")

    after_run_2 = changelog_text(project)
    assert after_run_2.count("## [0.3.0]") == 1, (
        "a re-run must replace the recorded section, not append a second one"
    )
    assert after_run_2 == after_run_1, "the converging re-run must not churn bytes"
    for bullet in ("first bullet", "second bullet", "third bullet"):
        assert bullet in after_run_2
    # The neighbouring release is untouched.
    assert "## [0.2.0] - 2026-04-01" in after_run_2
    assert "- old bullet" in after_run_2


@pytest.mark.covers("FR-01.09")
def test_rerun_resumed_on_a_later_date_still_writes_the_version_once(
    project: Path,
) -> None:
    """AC3 — ``release_date`` defaults to today, so a release resumed the next
    morning renders a different heading for identical content. Comparing the
    heading would refuse the very scenario this fix exists for."""
    seed_drops(project, pending())
    interrupt_after_write(project, "0.3.0", "2026-04-23")

    aggregate(project, "0.3.0", release_date="2026-04-24")

    text = changelog_text(project)
    assert text.count("## [0.3.0]") == 1
    assert "## [0.3.0] - 2026-04-24" in text, "the replace adopts the new heading"
    assert "2026-04-23" not in text, "the superseded heading must not linger"
    for bullet in ("first bullet", "second bullet", "third bullet"):
        assert bullet in text


@pytest.mark.covers("FR-01.09")
def test_trailing_whitespace_in_the_recorded_section_still_converges(
    project: Path,
) -> None:
    """AC3 — the comparison tolerates FORMATTING, not content.

    `normalize_body` exists so an editor that stripped or added trailing
    spaces cannot read as "the operator changed the release" and trigger the
    refusal. Without it this comparison is byte-for-byte and this release
    falsely refuses.
    """
    seed(
        project,
        "## [0.3.0] - 2026-04-23\n\n### Added\n\n- first bullet   \n\n"
        + "## [0.2.0] - 2026-04-01\n\n### Added\n\n- old bullet\n",
    )
    seed_drops(project, [("iterate-2026-04-23-a", "Added", "first bullet")])

    result = aggregate(project, "0.3.0", release_date="2026-04-23")

    assert result["section_action"] == "replaced", (
        "trailing whitespace is formatting; it must not be read as a conflict"
    )
    text = changelog_text(project)
    assert text.count("## [0.3.0]") == 1
    assert "first bullet" in text
    assert drop_texts(project) == set(), "it must converge, not refuse"


@pytest.mark.covers("FR-01.09")
def test_crlf_recorded_section_matches_an_lf_rendered_one() -> None:
    """AC3 — differing line endings are formatting, not a disagreement.

    A CONTRACT test for the shared `apply_section`, not a claim about the
    aggregator: `aggregate` reads with `read_text`, whose universal-newline
    translation folds CRLF to LF before `apply_section` ever sees it, so the
    aggregator cannot reach this state. The function is shared, and the next
    caller may read bytes — this pins the guarantee for them.
    """
    changelog = (
        "# Changelog\r\n\r\n"
        "## [0.3.0] - 2026-04-23\r\n\r\n### Added\r\n\r\n- a\r\n"
    )
    rendered = "## [0.3.0] - 2026-04-23\n\n### Added\n\n- a\n"

    new_text, action = apply_section(changelog, "0.3.0", rendered, "CHANGELOG.md")

    # `replaced`, not `unchanged`: the bodies MATCH (so no refusal) but the
    # rewritten section carries LF, so the bytes genuinely change.
    assert action == "replaced"
    assert new_text.count("## [0.3.0]") == 1
    assert "- a" in new_text


@pytest.mark.covers("FR-01.09")
def test_a_multi_line_bullet_still_converges() -> None:
    """AC3/AC4 — both sides of the comparison must be measured with the same
    ruler.

    A drop file may hold a multi-line bullet: `write_changelog_drop` only
    strips it. The recorded side is bounded by `section_end`, so if the
    rendered side were compared unbounded, a continuation line that
    `continues_section` rejects would make the two differ forever — and the
    interrupted release this whole change exists to fix would refuse
    permanently, blaming a hand edit that never happened.
    """
    rendered = (
        "## [0.3.0] - 2026-04-23\n\n### Added\n\n"
        "- renamed --old to --new\nBREAKING: --old is gone\n"
    )
    changelog = "# Changelog\n\n" + rendered

    _new_text, action = apply_section(changelog, "0.3.0", rendered, "CHANGELOG.md")

    assert action in ("unchanged", "replaced"), (
        "a section identical to what the entries render must never refuse"
    )


# ---------------------------------------------------------------------------
# AC4 — convergence means the release ends up clean
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_converging_rerun_consumes_the_drop_files(project: Path) -> None:
    """AC4 — after the re-run the release is clean, so a third run is a plain
    no-op rather than another recovery."""
    seed_drops(project, pending())
    interrupt_after_write(project, "0.3.0", "2026-04-23")
    assert drop_texts(project), "precondition: the interrupted run left drops"

    aggregate(project, "0.3.0", release_date="2026-04-23")

    assert drop_texts(project) == set(), "the converging re-run must consume the drops"
    before_third = changelog_text(project)
    result = aggregate(project, "0.3.0", release_date="2026-04-23")
    assert result["section_action"] == "none"
    assert changelog_text(project) == before_third


# ---------------------------------------------------------------------------
# AC11 — the result names what happened, and `changelog_updated` means bytes
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_converging_rerun_reports_unchanged_without_writing(project: Path) -> None:
    """AC11 — a re-run that finds the file already saying exactly this writes
    nothing, and still converges by consuming the drops."""
    seed_drops(project, pending())
    interrupt_after_write(project, "0.3.0", "2026-04-23")
    bytes_before = (project / CHANGELOG_NAME).read_bytes()

    result = aggregate(project, "0.3.0", release_date="2026-04-23")

    assert result["section_action"] == "unchanged"
    assert result["changelog_updated"] is False
    # Bytes, not mtime: a coarse filesystem clock lets an mtime comparison
    # PASS through a rewrite, which is the thing being ruled out.
    assert (project / CHANGELOG_NAME).read_bytes() == bytes_before
    assert drop_texts(project) == set(), "consuming the drops is NOT skipped"


@pytest.mark.covers("FR-01.09")
def test_first_release_reports_inserted(project: Path) -> None:
    """AC11 — the ordinary path still inserts, and still says so."""
    seed_drops(project, pending())
    result = aggregate(project, "0.3.0", release_date="2026-04-23")
    assert result["section_action"] == "inserted"
    assert result["changelog_updated"] is True


@pytest.mark.covers("FR-01.09")
def test_replacing_changed_content_reports_replaced(project: Path) -> None:
    """AC11 — a replace that changes bytes is `replaced`, not `unchanged`."""
    seed_drops(project, pending())
    interrupt_after_write(project, "0.3.0", "2026-04-23")

    result = aggregate(project, "0.3.0", release_date="2026-04-24")

    assert result["section_action"] == "replaced"
    assert result["changelog_updated"] is True


# ---------------------------------------------------------------------------
# AC12 — re-running a COMPLETED release
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_rerunning_a_completed_release_is_a_clean_noop(project: Path) -> None:
    """AC12 — section recorded, no drops left. This must never reach a refusal
    arm: a successful release has to stay re-runnable."""
    seed_drops(project, pending())
    aggregate(project, "0.3.0", release_date="2026-04-23")
    before = changelog_text(project)

    result = aggregate(project, "0.3.0", release_date="2026-04-23")

    assert result["section_action"] == "none"
    assert result["changelog_updated"] is False
    assert result["section_written"] == ""
    assert changelog_text(project) == before


# ---------------------------------------------------------------------------
# AC10 — a replaced span is bounded by what the section owns
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_replace_preserves_trailing_prose_and_link_footer(project: Path) -> None:
    """AC10 — the canonical Keep-a-Changelog link footer sits below the last
    section. Ending a replaced span at "next heading or EOF" would delete it."""
    seed(
        project,
        "## [0.3.0] - 2026-04-23\n\n### Added\n\n- first bullet\n\n"
        "Thanks to everyone who contributed.\n\n"
        "[0.3.0]: https://example.test/compare/v0.2.0...v0.3.0\n"
        "[0.2.0]: https://example.test/releases/v0.2.0\n",
    )
    seed_drops(project, [("iterate-2026-04-23-a", "Added", "first bullet")])

    aggregate(project, "0.3.0", release_date="2026-04-24")

    text = changelog_text(project)
    assert text.count("## [0.3.0]") == 1
    # Present exactly once and still BELOW the section — the footer must be
    # neither deleted, nor duplicated, nor hoisted above the release it annotates.
    assert text.count("Thanks to everyone who contributed.") == 1
    assert text.count("[0.3.0]: https://example.test/compare/v0.2.0...v0.3.0") == 1
    assert text.count("[0.2.0]: https://example.test/releases/v0.2.0") == 1
    assert text.index("## [0.3.0]") < text.index("Thanks to everyone")
    assert text.index("Thanks to everyone") < text.index("[0.3.0]: https")
