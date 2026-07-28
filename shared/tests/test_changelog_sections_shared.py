"""``changelog_sections`` is ONE implementation, reached from both writers.

Two writers splice sections into a ``CHANGELOG.md``: the plugin's
``update_changelog`` and the release-time ``aggregate_changelog``. They used to
carry separate structural predicates, and the two already disagreed — on a
lowercase ``## [unreleased]`` and on where a link-reference footer ends a
block. Neither lost content, so nothing had failed yet; adding replace logic as
a third copy is the drift ``conventions.md:50`` records.

The module lives at ``shared/scripts/`` **top level**, not under ``lib/``, per
ADR-045: every plugin ships its own ``scripts/lib`` package, so a shared helper
under ``lib/`` would bind ``sys.modules['lib']`` to whichever got there first.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# APPEND, not insert(0): `shared/tests/tools/` would shadow the
# `shared/scripts/tools` package the conftest puts on the path.
sys.path.append(str(Path(__file__).resolve().parent))
from _changelog_release_fixtures import (  # noqa: E402
    PRIOR_RELEASE,
    changelog_text,
    seed,
    seed_drops,
)

import changelog_sections  # noqa: E402
from changelog_sections import (  # noqa: E402
    insertion_index,
    section_end,
    section_starts,
)
from changelog_splice import insert_section  # noqa: E402
from tools.aggregate_changelog import aggregate  # noqa: E402


_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# AC1 / AC2 — one implementation, and only one
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_the_module_lives_at_shared_scripts_top_level() -> None:
    """ADR-045: a cross-plugin helper must NOT sit under a `lib/` package."""
    location = Path(changelog_sections.__file__).resolve()
    assert location == _REPO_ROOT / "shared" / "scripts" / "changelog_sections.py"
    assert location.parent.name != "lib", (
        "under lib/ this would collide with every plugin's own lib package"
    )


@pytest.mark.covers("FR-01.09")
def test_no_plugin_local_copy_survives() -> None:
    """AC1 — a leftover copy would silently shadow the shared one for the
    plugin writer while the aggregator used the shared module."""
    stale = (
        _REPO_ROOT
        / "plugins"
        / "shipwright-changelog"
        / "scripts"
        / "lib"
        / "changelog_sections.py"
    )
    assert not stale.exists(), f"delete the superseded copy at {stale}"


@pytest.mark.covers("FR-01.09")
def test_aggregator_has_no_second_insertion_predicate() -> None:
    """AC2 — `_find_structural_insertion_line` was the aggregator's own copy of
    `insertion_index`. Removing the duplicate is the point of the extraction."""
    from tools import aggregate_changelog

    assert not hasattr(aggregate_changelog, "_find_structural_insertion_line"), (
        "the aggregator must take its insertion point from changelog_sections"
    )


@pytest.mark.covers("FR-01.09")
def test_aggregator_carries_no_section_heading_pattern_of_its_own() -> None:
    """AC2 — the aggregator must USE the shared module, not merely have dropped
    its own copy: it holds no `##`-heading pattern of its own to drift.

    The scan covers any regex construction on a line mentioning `##`, not only
    `re.compile`. The narrower filter missed a surviving inline `re.search` for
    `^##\\s+\\[Unreleased\\]` in `_warn_if_legacy_unreleased_has_bullets`,
    which was case-SENSITIVE where the shared `insertion_index` lowercases — so
    a history spelling it `## [unreleased]` got the correct insertion point and
    NO split-brain warning. That reader now goes through `unreleased_start`.
    """
    from tools import aggregate_changelog

    source = Path(aggregate_changelog.__file__).read_text(encoding="utf-8")
    assert "from changelog_sections import" in source
    assert "from changelog_splice import" in source

    heading_patterns = [
        line.strip()
        for line in source.splitlines()
        if "##" in line
        and ("re.compile" in line or "re.search" in line or "re.findall" in line)
    ]
    assert heading_patterns == [], (
        "a section-heading pattern here re-creates the drift the extraction "
        f"removes: {heading_patterns}"
    )


# ---------------------------------------------------------------------------
# AC13 — the plugin writer resolves the SHARED module at import time
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_plugin_writer_resolves_changelog_sections_from_shared() -> None:
    """AC13 — asserted in a CLEAN SUBPROCESS.

    The ADR-045 `lib` collision is bidirectional within one pytest session: a
    shared-side test that imports a plugin module in-process binds
    ``sys.modules['lib']`` and makes the result order-dependent
    (``conventions.md:88``). A subprocess with only the plugin's ``scripts`` on
    ``sys.path`` reproduces how the plugin is actually loaded.
    """
    plugin_scripts = (
        _REPO_ROOT / "plugins" / "shipwright-changelog" / "scripts"
    )
    program = (
        "import sys, json;"
        f"sys.path.insert(0, {str(plugin_scripts)!r});"
        "from lib import changelog;"
        # Resolved through the writer's own loader, exactly as `update_changelog`
        # does at call time (the predicates are bound lazily, so there is no
        # module attribute to inspect until something asks for one).
        "mod = changelog.load_changelog_sections();"
        "print(json.dumps({'file': mod.__file__, 'name': mod.__name__}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=60,
    )
    assert completed.returncode == 0, (
        f"the plugin writer failed to import its section predicates:\n"
        f"{completed.stderr}"
    )

    import json

    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    resolved = Path(payload["file"]).resolve()
    assert resolved == _REPO_ROOT / "shared" / "scripts" / "changelog_sections.py", (
        f"the plugin writer resolved {resolved}, not the shared implementation"
    )


# ---------------------------------------------------------------------------
# The predicates themselves — edge cases that used to live in the aggregator's
# suite against its own copy.
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.09")
def test_insertion_index_handles_degenerate_files() -> None:
    """Moved from `test_changelog_aggregation.py`, where it pinned the now
    deleted `_find_structural_insertion_line`."""
    assert insertion_index([]) == 0
    assert insertion_index(["# Changelog", ""]) == 2


@pytest.mark.covers("FR-01.09")
def test_lowercase_unreleased_is_not_treated_as_a_release() -> None:
    """One of the two divergences between the old copies: the aggregator read
    `## [unreleased]` as a released version and inserted ABOVE it."""
    lines = ["# Changelog\n", "\n", "## [unreleased]\n", "\n", "- pending\n"]
    assert insertion_index(lines) == len(lines), (
        "a new release belongs below the Unreleased block, whatever its casing"
    )


@pytest.mark.covers("FR-01.09")
def test_section_end_stops_before_a_link_reference_footer() -> None:
    """The other divergence, and what AC10 rests on: a footer is not part of
    the section above it, so a replaced span must not swallow it."""
    lines = [
        "## [0.3.0] - 2026-04-23\n",
        "\n",
        "### Added\n",
        "\n",
        "- a bullet\n",
        "\n",
        "[0.3.0]: https://example.test/v0.3.0\n",
    ]
    end = section_end(lines, 0)
    assert end == 6, "the span must stop at the footer, not run to EOF"
    assert "".join(lines[end:]).strip().startswith("[0.3.0]:")


@pytest.mark.covers("FR-01.09")
def test_new_release_lands_above_prose_trailing_an_unreleased_block() -> None:
    """A third divergence between the retired copies, pinned rather than left
    to be rediscovered.

    The aggregator's own arm scanned forward to the next `## [` heading, so a
    new section landed BELOW any prose trailing the `[Unreleased]` block. The
    shared `section_end` stops at the first non-body line, so it lands above —
    which is right for the canonical Keep-a-Changelog link footer, and means
    prose documenting `[Unreleased]` keeps annotating `[Unreleased]` rather
    than silently becoming part of the new release.
    """
    lines = [
        "# Changelog\n",
        "\n",
        "## [Unreleased]\n",
        "\n",
        "- pending one\n",
        "\n",
        "See CONTRIBUTING.md for how to add entries.\n",
    ]
    at = insertion_index(lines)
    assert "".join(lines[:at]).endswith("- pending one\n")
    assert "".join(lines[at:]).strip() == "See CONTRIBUTING.md for how to add entries."


@pytest.mark.covers("FR-01.09")
def test_insert_terminates_an_unterminated_last_line() -> None:
    """Appending to a file whose last line has no newline must not weld the
    heading onto it (`# Changelog## [0.3.0]`). The sibling writer in
    `changelog.update_changelog` has always guarded this; the retired
    aggregator-local copy did not, and this is now the ONE implementation."""
    out = insert_section("# Changelog", "## [0.3.0] - 2026-04-23\n\n- x\n")

    assert "# Changelog## [0.3.0]" not in out
    assert out.splitlines()[0] == "# Changelog"
    assert "## [0.3.0] - 2026-04-23" in out


@pytest.mark.covers("FR-01.09")
def test_section_starts_finds_every_claim_on_a_version() -> None:
    """AC6 rests on counting, not on finding the first."""
    lines = [
        "## [0.3.0] - 2026-04-23\n",
        "- a\n",
        "## [0.3.0] - 2026-04-23\n",
        "- b\n",
        "## [0.2.0] - 2026-04-01\n",
    ]
    assert section_starts(lines, "0.3.0") == [0, 2]
    assert section_starts(lines, "0.2.0") == [4]
    assert section_starts(lines, "9.9.9") == []


# ---------------------------------------------------------------------------
# The legacy-[Unreleased] warning now uses the shared predicate
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    seed(tmp_path)
    return tmp_path


@pytest.mark.covers("FR-01.09")
def test_lowercase_unreleased_bullets_are_still_reported(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The aggregator's own regex for this warning was case-SENSITIVE, where
    the shared insertion predicate lowercases. So a history spelling it
    `## [unreleased]` got the correct insertion point and NO split-brain
    warning — the operator was never told the legacy bullets were being left
    behind. Both now go through `unreleased_start`."""
    seed(
        project,
        "## [unreleased]\n\n### Added\n\n- an orphan legacy entry\n\n" + PRIOR_RELEASE,
    )
    seed_drops(project, [("iterate-2026-04-23-a", "Added", "new bullet")])

    result = aggregate(project, "0.3.0", release_date="2026-04-23")

    assert result["legacy_unreleased_bullets"] == 1
    assert "legacy [Unreleased]" in capsys.readouterr().err
    # ... and the legacy bullet is still there, untouched.
    assert "an orphan legacy entry" in changelog_text(project)
