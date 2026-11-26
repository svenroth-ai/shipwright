"""``release.py pr-body``: the release PR's body as a file, so ``gh pr create --body-file`` gets real newlines (Q10, D15).

The prose passed ``--body "## Changelog\\n\\n{entry}"``: inside bash double quotes ``\\n`` stays two characters, so the PR
showed a literal ``\\n``, and ``{entry}`` was never defined. The text stays what the skill said (operator re-scope
2026-11-25: title and body unchanged): ``## Changelog``, a blank line, then the entry, which is defined here as this
version's section of ``CHANGELOG.md`` (the same text the replay used: the section the aggregation rendered). The file goes
next to the run state in the checkout's git directory, so it never dirties the tree and is never committed. A version with
no section in ``CHANGELOG.md`` (or with more than one) is refused: an empty or ambiguous body would be a guess.
"""

from __future__ import annotations

from typing import Any

from . import release_runstate
from .release_runner import Recorder

HEADER = "## Changelog"
FILE_NAME = "release_pr_body.md"


def section_text(changelog: str, version: str) -> tuple[str | None, int]:
    """This version's section (heading included, outer blank lines stripped) and how many sections claim the version."""
    from ._shared_sections import load_changelog_sections  # on use: importing the CLI loads no non-release lib module

    sections = load_changelog_sections()
    lines = changelog.replace("\r\n", "\n").splitlines(keepends=True)
    starts = sections.section_starts(lines, version)
    if len(starts) != 1:
        return None, len(starts)
    return "".join(lines[starts[0]:sections.section_end(lines, starts[0])]).strip("\n"), 1


def body_for(section: str) -> str:
    return f"{HEADER}\n\n{section}\n"


def pr_body(rec: Recorder, *, version: str) -> tuple[int, dict[str, Any]]:
    root = rec.cwd
    try:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        changelog = ""
    section, count = section_text(changelog, version)
    if section is None:
        reason = "section_missing" if count == 0 else "section_ambiguous"
        return 1, {"status": "refused", "reason": reason, "version": version, "sections": count, "commands": rec.as_json()}
    target = release_runstate.state_path(root).with_name(FILE_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body_for(section), encoding="utf-8", newline="\n")
    return 0, {"status": "ok", "version": version, "body_file": str(target), "title": f"Release v{version}", "commands": rec.as_json()}
