"""Reviewer Bloat-Checklist parity drift-protection (Campaign A.review).

Two reviewer subagent prompts must carry an IDENTICAL ``## Bloat Checklist``
section + attribution footer:

- ``plugins/shipwright-build/agents/code-reviewer.md``
- ``plugins/shipwright-iterate/agents/sub-iterate-runner.md``

The two prompts have very different file-local context around the section,
so the parity test extracts ONLY the section body between explicit start
and end markers (per external-review Gemini #3 / OpenAI #7+#8).

Section boundaries:
- start: line containing ``## Bloat Checklist`` (exact heading)
- end: the literal line ``<!-- /Bloat Checklist -->`` immediately
  preceding the section's attribution sub-footer (so attribution +
  external-reference links are also covered by the parity check)

This file lives in ``shared/tests/`` rather than under a single plugin's
test dir because it reaches into two different plugins. Per
external-review OpenAI #6 this is the natural home — a plugin-scoped
``pytest plugins/foo/tests/`` would otherwise miss the cross-plugin
parity invariant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

REVIEWER_FILES = (
    REPO_ROOT / "plugins" / "shipwright-build" / "agents" / "code-reviewer.md",
    REPO_ROOT / "plugins" / "shipwright-iterate" / "agents"
        / "sub-iterate-runner.md",
)

SECTION_START_HEADING = "## Bloat Checklist"
SECTION_END_MARKER = "<!-- /Bloat Checklist -->"


def _extract_section(path: Path) -> str:
    """Return the body between ``## Bloat Checklist`` and the closing marker.

    Raises ``AssertionError`` if either delimiter is missing — that IS
    the drift-protection invariant.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    start = None
    for i, line in enumerate(lines):
        if line.strip() == SECTION_START_HEADING:
            start = i
            break
    assert start is not None, (
        f"{path}: missing '{SECTION_START_HEADING}' heading"
    )

    end = None
    for i in range(start + 1, len(lines)):
        if lines[i].strip() == SECTION_END_MARKER:
            end = i
            break
    assert end is not None, (
        f"{path}: missing '{SECTION_END_MARKER}' end delimiter "
        f"(must follow the attribution footer)"
    )

    # Include start heading + end marker so any diff in either marker
    # is also caught.
    return "\n".join(lines[start:end + 1])


# ---------------------------------------------------------------------------
# Existence: section present in BOTH files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", REVIEWER_FILES)
def test_bloat_checklist_section_present(path: Path):
    text = path.read_text(encoding="utf-8")
    assert SECTION_START_HEADING in text, \
        f"{path}: '{SECTION_START_HEADING}' heading missing"
    assert SECTION_END_MARKER in text, \
        f"{path}: '{SECTION_END_MARKER}' end-delimiter missing"


# ---------------------------------------------------------------------------
# Parity: byte-identical section bodies across both files
# ---------------------------------------------------------------------------


def test_bloat_checklist_byte_identical_between_reviewers():
    bodies = [_extract_section(p) for p in REVIEWER_FILES]
    a, b = bodies[0], bodies[1]
    assert a == b, (
        "Bloat Checklist sections drifted between "
        f"{REVIEWER_FILES[0].name} and {REVIEWER_FILES[1].name}.\n"
        "Both reviewer files MUST carry verbatim-identical content."
    )


# ---------------------------------------------------------------------------
# Attribution footer present (verbatim-citation invariant)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", REVIEWER_FILES)
def test_attribution_links_to_source_repos(path: Path):
    section = _extract_section(path)
    # External-review OpenAI #11: record exact upstream source.
    assert "multica-ai/andrej-karpathy-skills" in section, \
        f"{path}: Karpathy attribution link missing"
    assert "addyosmani/agent-skills" in section, \
        f"{path}: Osmani attribution link missing"
    # MIT license attribution required for both.
    assert "MIT" in section, f"{path}: MIT license attribution missing"
