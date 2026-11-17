"""The oracle: FR-01.09's acceptance criteria as checks that share no code with the tools they judge.

Each function re-states one AC (the wording of ``.shipwright/planning/01-adopted/spec.md`` FR-01.09) over what a
scenario left behind - commit messages, ``CHANGELOG.md`` text, git state, the stub's log - and raises
``AssertionError`` naming the AC. None of them imports ``git_utils`` or an aggregator: the version rule is
written out again here, so a bug the tool shares with its own test cannot hide.
"""

from __future__ import annotations

import re
from typing import Sequence

_HEADER = re.compile(r"^(?P<type>[A-Za-z]+)(?:\([^)]*\))?(?P<bang>!)?:\s")
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.M)
_SECTION = re.compile(r"^## \[(?P<version>[^\]]+)\]", re.M)


def expected_version(last_tag: str | None, messages: Sequence[str], breaking_drops: int = 0) -> str:
    """AC04: a break raises the first number, a new capability the second, anything else the third; before
    the first stable release a break raises the second instead; no release at all starts at 0.1.0.
    ``breaking_drops`` counts recorded entries (not commits) that mark a break."""
    if not last_tag:
        return "0.1.0"
    major, minor, patch = (int(n) for n in last_tag.lstrip("v").split("."))
    parsed = [_HEADER.match(m.splitlines()[0]) if m.strip() else None for m in messages]
    breaking = breaking_drops > 0 or any(
        (p is not None and p.group("bang")) or _BREAKING_FOOTER.search("\n".join(m.splitlines()[1:]))
        for p, m in zip(parsed, messages))
    feature = any(p is not None and p.group("type") == "feat" for p in parsed)
    if breaking:
        return f"0.{minor + 1}.0" if major == 0 else f"{major + 1}.0.0"
    return f"{major}.{minor + 1}.0" if feature else f"{major}.{minor}.{patch + 1}"


def sections(changelog: str) -> list[tuple[str, str]]:
    """The ``## [version]`` sections of a changelog, as ``(version, text)`` in file order."""
    marks = list(_SECTION.finditer(changelog))
    ends = [m.start() for m in marks[1:]] + [len(changelog)]
    return [(m.group("version"), changelog[m.start():end]) for m, end in zip(marks, ends)]


def groups(section: str) -> dict[str, list[str]]:
    """``### Heading`` -> its bullets (text after ``- ``), for one section."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in section.splitlines():
        if line.startswith("### "):
            current = line[4:].strip()
            found[current] = []
        elif current and line.startswith("- "):
            found[current].append(line[2:].strip())
    return found


def check_ac02_grouped(section: str, expected: dict[str, Sequence[str]]) -> None:
    """AC02: each entry sits under the kind of change it was, as a readable bullet (not a raw commit line)."""
    got = groups(section)
    for kind, bullets in expected.items():
        assert got.get(kind) == list(bullets), f"AC02: {kind} holds {got.get(kind)!r}, expected {list(bullets)!r}"
    assert not re.search(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b", section), "AC02: a raw commit hash leaked into the release note"


def check_ac04_version(got: str | None, last_tag: str | None, messages: Sequence[str], breaking_drops: int = 0) -> None:
    want = expected_version(last_tag, messages, breaking_drops)
    assert got == want, f"AC04: proposed {got!r}, the rule gives {want!r} (last tag {last_tag!r})"


def check_ac06_placement(before: str, after: str, version: str) -> None:
    """AC06: the new section goes above the most recent released one; the title and older entries are intact."""
    old, new = sections(before), sections(after)
    assert [v for v, _ in new][:1] == [version], f"AC06: {version} is not the first section: {[v for v, _ in new]}"
    assert new[1:] == old, "AC06: older sections changed or were reordered"
    assert after.splitlines()[0] == before.splitlines()[0] == "# Changelog", "AC06: the title moved or changed"


def check_ac07_once(changelog: str, version: str) -> None:
    """AC07: one version appears exactly once."""
    count = [v for v, _ in sections(changelog)].count(version)
    assert count == 1, f"AC07: {version} appears {count} times"


def check_ac11_not_published(stub_state: dict, tag_on_remote: bool, pr_open: bool) -> None:
    """AC11: while the request is open nothing is out. The replay of today's prose does NOT satisfy this on a
    feature branch in guided mode (finding D2): a scenario that records it says so instead of calling this."""
    assert not (pr_open and (tag_on_remote or stub_state.get("releases"))), "AC11: published before the PR was merged"
