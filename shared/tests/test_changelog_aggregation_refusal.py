"""When replacing would destroy released history, the aggregator stops.

The fix for the duplicate-section bug is not "always replace". The unlink loop
is not atomic either: if it deletes some drops and then dies, the recorded
section holds more bullets than the surviving drops render, and an
unconditional replace would delete released history — strictly worse than the
duplicate it was meant to fix, because a duplicate loses nothing.

Every test asserts that BOTH the changelog bytes and the pending drop set come
through a refusal untouched. A refusal that consumed the drops would leave the
operator with nothing to re-run.
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
    DUPLICATE_SECTIONS,
    PRIOR_RELEASE,
    changelog_text,
    drop_texts,
    interrupt_after_write,
    pending,
    seed,
    seed_drops,
)
from tools.aggregate_changelog import AggregatorError, CHANGELOG_NAME, aggregate
from tools.aggregate_changelog import main as agg_main


@pytest.fixture
def project(tmp_path: Path) -> Path:
    seed(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# AC5 — the partial-unlink refusal (the arm that prevents silent data loss)
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_partial_unlink_refuses_instead_of_deleting_released_bullets(
    project: Path,
) -> None:
    """AC5 — the unlink loop consumed two of three drops and died. The recorded
    section holds three bullets; the surviving drop renders one. Replacing
    would delete two bullets of released history."""
    seed_drops(project, pending())
    interrupt_after_write(project, "0.3.0", "2026-04-23")
    for path in (project / "CHANGELOG-unreleased.d").rglob("*.md"):
        if "third bullet" not in path.read_text(encoding="utf-8"):
            path.unlink()

    before_text = changelog_text(project)
    before_drops = drop_texts(project)
    assert before_drops == {"third bullet"}, "precondition: a partial unlink"

    with pytest.raises(AggregatorError) as excinfo:
        aggregate(project, "0.3.0", release_date="2026-04-23")

    message = str(excinfo.value)
    assert "0.3.0" in message, "the refusal must name the version"
    assert CHANGELOG_NAME in message, "the refusal must name the file"
    # The CAUSE, not just the subject. Both arms name the file and the version,
    # so asserting only those would pass on an implementation that raised the
    # duplicate-section message here.
    assert "not what the pending entries say" in message
    assert "interrupted partway" in message

    assert changelog_text(project) == before_text, "a refusal must not touch the file"
    assert drop_texts(project) == before_drops, "a refusal must not consume drops"
    # The bullets that an unconditional replace would have destroyed are intact.
    for bullet in ("first bullet", "second bullet", "third bullet"):
        assert bullet in changelog_text(project)


@pytest.mark.covers("FR-01.09")
def test_hand_edited_section_refuses(project: Path) -> None:
    """AC5 — the same arm protects an operator edit. The recorded section is
    not what the drops say, and which one is right is not knowable here."""
    seed(
        project,
        "## [0.3.0] - 2026-04-23\n\n### Added\n\n- hand written by the operator\n\n"
        + PRIOR_RELEASE,
    )
    seed_drops(project, [("iterate-2026-04-23-x", "Added", "generated bullet")])
    before_text = changelog_text(project)

    with pytest.raises(AggregatorError, match="not what the pending entries say"):
        aggregate(project, "0.3.0", release_date="2026-04-23")

    assert changelog_text(project) == before_text
    assert drop_texts(project) == {"generated bullet"}
    assert "hand written by the operator" in changelog_text(project)


# ---------------------------------------------------------------------------
# AC5 — a heading carrying more than a version and a date
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_yanked_marker_on_the_heading_refuses(project: Path) -> None:
    """A replace rewrites the whole heading line, so anything the renderer does
    not reproduce is discarded. Keep-a-Changelog puts the yank marker there;
    silently dropping it makes a withdrawn release read as a normal one."""
    seed(
        project,
        "## [0.3.0] - 2026-04-23 [YANKED]\n\n### Added\n\n- first bullet\n\n"
        + PRIOR_RELEASE,
    )
    seed_drops(project, [("iterate-2026-04-23-a", "Added", "first bullet")])
    before_text = changelog_text(project)

    with pytest.raises(AggregatorError, match="YANKED"):
        aggregate(project, "0.3.0", release_date="2026-04-24")

    assert changelog_text(project) == before_text
    assert "[YANKED]" in changelog_text(project)
    assert drop_texts(project) == {"first bullet"}


@pytest.mark.covers("FR-01.09")
def test_aggregating_the_unreleased_block_refuses(project: Path) -> None:
    """`entry_version` has always refused to write an `[Unreleased]` section,
    because replacing it discards entries that were never released. The
    aggregator takes its version from argv, so the same guard has to live in
    the splice."""
    seed_drops(project, [("iterate-2026-04-23-a", "Added", "first bullet")])

    with pytest.raises(AggregatorError, match="(?i)unreleased"):
        aggregate(project, "Unreleased", release_date="2026-04-23")

    assert drop_texts(project) == {"first bullet"}


# ---------------------------------------------------------------------------
# AC6 — more than one section claims the version
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_duplicate_sections_refuse_with_the_count(project: Path) -> None:
    """AC6 — wreckage from the old bug. Which section is authoritative is not
    knowable, so stop rather than write a third."""
    seed(project, DUPLICATE_SECTIONS)
    seed_drops(project, [("iterate-2026-04-23-y", "Added", "third copy")])
    before_text = changelog_text(project)

    with pytest.raises(AggregatorError) as excinfo:
        aggregate(project, "0.3.0", release_date="2026-04-23")

    message = str(excinfo.value)
    # "2 sections", not bare "2": `message` embeds the absolute tmp_path, and a
    # pytest tmp path routinely contains a literal '2', so `"2" in message`
    # passes whether or not the count is reported at all.
    assert "2 sections" in message, "the refusal must report how many it found"
    assert "0.3.0" in message
    assert "refusing to guess which one to replace" in message, (
        "the cause must distinguish this arm from the content-mismatch one"
    )

    assert changelog_text(project) == before_text
    assert drop_texts(project) == {"third copy"}
    assert changelog_text(project).count("## [0.3.0]") == 2, "no third was written"


# ---------------------------------------------------------------------------
# AC8 — --dry-run touches nothing, and still refuses what would be refused
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_dry_run_reports_the_replace_without_writing_or_unlinking(
    project: Path,
) -> None:
    """AC8 — a preview of a replace changes neither the file nor the drops."""
    seed_drops(project, pending())
    interrupt_after_write(project, "0.3.0", "2026-04-23")
    before_text = changelog_text(project)
    before_drops = drop_texts(project)

    result = aggregate(project, "0.3.0", release_date="2026-04-24", dry_run=True)

    assert result["section_action"] == "replaced"
    assert result["changelog_updated"] is False
    assert changelog_text(project) == before_text
    assert drop_texts(project) == before_drops


@pytest.mark.covers("FR-01.09")
def test_dry_run_still_refuses_a_state_that_would_be_refused(project: Path) -> None:
    """AC8 — a refusal is a refusal under --dry-run too. Reporting it as a
    successful preview would tell the operator the release is safe to run."""
    seed(project, DUPLICATE_SECTIONS)
    seed_drops(project, [("iterate-2026-04-23-y", "Added", "third copy")])

    before_text = changelog_text(project)
    with pytest.raises(AggregatorError, match="2 sections"):
        aggregate(project, "0.3.0", release_date="2026-04-23", dry_run=True)
    assert changelog_text(project) == before_text
    assert drop_texts(project) == {"third copy"}


@pytest.mark.covers("FR-01.09")
def test_dry_run_cli_also_exits_nonzero_on_a_refusal(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC8 — through `main()`, not just the library: a preview that reported
    success would tell release CI the run is safe to repeat."""
    seed(project, DUPLICATE_SECTIONS)
    seed_drops(project, [("iterate-2026-04-23-y", "Added", "third copy")])

    rc = agg_main([
        "--project-root", str(project),
        "--version", "0.3.0",
        "--release-date", "2026-04-23",
        "--dry-run",
    ])

    assert rc != 0
    assert "2 sections" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# AC7 — both refusals reach the operator through the CLI
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_cli_exits_nonzero_on_duplicate_sections(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC7 — release CI must fail, not warn."""
    seed(project, DUPLICATE_SECTIONS)
    seed_drops(project, [("iterate-2026-04-23-y", "Added", "third copy")])

    rc = agg_main([
        "--project-root", str(project),
        "--version", "0.3.0",
        "--release-date", "2026-04-23",
    ])

    assert rc != 0
    assert "0.3.0" in capsys.readouterr().err


@pytest.mark.covers("FR-01.09")
def test_cli_exits_nonzero_on_content_mismatch(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC7 — the partial-unlink arm reaches the operator the same way."""
    seed(
        project,
        "## [0.3.0] - 2026-04-23\n\n### Added\n\n- what was released\n\n"
        + PRIOR_RELEASE,
    )
    seed_drops(project, [("iterate-2026-04-23-z", "Added", "what is pending")])

    rc = agg_main([
        "--project-root", str(project),
        "--version", "0.3.0",
        "--release-date", "2026-04-23",
    ])

    assert rc != 0
    err = capsys.readouterr().err
    assert "0.3.0" in err
    assert CHANGELOG_NAME in err, "the message must name the file to look at"
    assert "not what the pending entries say" in err
    # The one string an operator must read to reconcile by hand travels through
    # a pipe. A non-ASCII character in it arrives as mojibake on a Windows
    # console, or kills a UTF-8 decode outright.
    err.encode("ascii")
