"""The oracle: FR-01.09's acceptance criteria as checks that share no code with the tools they judge.

Each function re-states one AC (the wording of ``.shipwright/planning/01-adopted/spec.md`` FR-01.09) over what a
scenario left behind - commit messages, ``CHANGELOG.md`` text, git state, the stub's log - and raises
``AssertionError`` naming the AC. None of them imports ``git_utils`` or an aggregator: the version rule is
written out again here, so a bug the tool shares with its own test cannot hide.
"""

from __future__ import annotations

import re
from typing import Callable, Mapping, Sequence

FR = "FR-01.09"
JUDGES: set[str] = set()  # every AC some oracle function judges (read by the P8c coverage check)
ASSERTED: set[str] = set()  # the ACs the oracle has judged since the last ``ASSERTED.clear()`` (scenario_core checks it)


def asserts(*acs: str) -> Callable:
    """Mark an oracle function as the judge of ``acs``: a scenario that names an AC must reach one of these."""
    JUDGES.update(f"{FR}/{ac}" for ac in acs)

    def mark(fn: Callable) -> Callable:
        def run(*args, **kwargs):
            result = fn(*args, **kwargs)
            ASSERTED.update(f"{FR}/{ac}" for ac in acs)
            return result
        run.__name__, run.__doc__ = fn.__name__, fn.__doc__
        return run
    return mark

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


@asserts("AC02")
def check_ac02_grouped(section: str, expected: dict[str, Sequence[str]]) -> None:
    """AC02: each entry sits under the kind of change it was, as a readable bullet (not a raw commit line)."""
    got = groups(section)
    for kind, bullets in expected.items():
        assert got.get(kind) == list(bullets), f"AC02: {kind} holds {got.get(kind)!r}, expected {list(bullets)!r}"
    assert not re.search(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b", section), "AC02: a raw commit hash leaked into the release note"


@asserts("AC04")
def check_ac04_version(got: str | None, last_tag: str | None, messages: Sequence[str], breaking_drops: int = 0) -> None:
    want = expected_version(last_tag, messages, breaking_drops)
    assert got == want, f"AC04: proposed {got!r}, the rule gives {want!r} (last tag {last_tag!r})"


@asserts("AC06")
def check_ac06_placement(before: str, after: str, version: str) -> None:
    """AC06: the new section goes above the most recent released one; the title and older entries are intact."""
    old, new = sections(before), sections(after)
    assert [v for v, _ in new][:1] == [version], f"AC06: {version} is not the first section: {[v for v, _ in new]}"
    assert new[1:] == old, "AC06: older sections changed or were reordered"
    assert after.splitlines()[0] == before.splitlines()[0] == "# Changelog", "AC06: the title moved or changed"


@asserts("AC07")
def check_ac07_once(changelog: str, version: str) -> None:
    """AC07: one version appears exactly once."""
    count = [v for v, _ in sections(changelog)].count(version)
    assert count == 1, f"AC07: {version} appears {count} times"


@asserts("AC11")
def check_ac11_not_published(stub_state: dict, tag_on_remote: bool, pr_open: bool) -> None:
    """AC11: while the request is open nothing is out. The replay of today's prose does NOT satisfy this on a
    feature branch in guided mode (finding D2): a scenario that records it says so instead of calling this."""
    assert not (pr_open and (tag_on_remote or stub_state.get("releases"))), "AC11: published before the PR was merged"


def expect_ac11_violated_today(stub_state: dict, tag_on_remote: bool, pr_open: bool) -> None:
    """Finding D2, judged by AC11's own predicate: a guided or driven run leaves the request open AND has pushed the tag
    and the release page. Raises when AC11 would hold, so a fix of the skill turns the scenario red on purpose."""
    try:
        check_ac11_not_published(stub_state, tag_on_remote, pr_open)
    except AssertionError:
        ASSERTED.add(f"{FR}/AC11")
        return
    raise AssertionError("AC11 holds here: finding D2 no longer reproduces (the scenario must be re-recorded)")


@asserts("AC01")
def check_ac01(note: str, tag_made: bool, request_open: bool, *, outcome: str) -> None:
    """AC01: a release note, a version marking and an open request. ``outcome`` says which of today's results this is:
    ``prepared`` (all three), ``no_request`` (note and tag, no request: a release made on ``main`` or a request that
    could not be opened) or ``stopped`` (the release ended before the marking and before any request)."""
    assert outcome in ("prepared", "no_request", "stopped"), outcome
    if outcome == "stopped":
        assert not tag_made and not request_open, f"AC01: stopped but tag={tag_made} request={request_open}"
        return
    readable = bool(note.strip()) and "### " in note and not re.search(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b", note)
    assert readable and tag_made, f"AC01: note readable={readable}, tag={tag_made}"
    assert request_open == (outcome == "prepared"), f"AC01: request open={request_open}, outcome {outcome}"


@asserts("AC03")
def check_ac03_stops(said: str, words: Sequence[str], wrote_nothing: bool, tag_made: bool) -> None:
    """AC03: nothing recorded since the last release: it says so and stops, no empty release, no marking."""
    assert all(w in said.lower() for w in words), f"AC03: the message {said!r} lacks {list(words)}"
    assert wrote_nothing and not tag_made, "AC03: an empty release was written or marked"


@asserts("AC05")
def check_ac05_numbered(log_before: str, log_after: str, drops_before: int, drops_left: int) -> None:
    """AC05: the decision records get their sequential numbers at release: one continuing run, each exactly once."""
    number = lambda text: [int(n) for n in re.findall(r"^### ADR-(\d+)", text, re.M)]  # noqa: E731
    before, after = number(log_before), number(log_after)
    last = max(before, default=0)
    assert after[:len(before)] == before, "AC05: numbers already given changed"
    assert after[len(before):] == list(range(last + 1, last + 1 + drops_before)), f"AC05: new numbers {after[len(before):]}"
    assert len(set(after)) == len(after) and drops_left == 0, "AC05: a number was used twice or a drop was left behind"


def _refusal(before: Mapping, after: Mapping, stderr: str, words: Sequence[str]) -> None:
    assert before == after, "a refused run changed something on disk"
    assert all(w in stderr.lower() for w in words), f"the refusal {stderr!r} lacks {list(words)}"


@asserts("AC07")
def check_ac07_refused(before: Mapping, after: Mapping, stderr: str, words: Sequence[str]) -> None:
    """AC07: two sections claiming one version stop the write; it says so and changes nothing (content digests)."""
    _refusal(before, after, stderr, words)


@asserts("AC08")
def check_ac08_refused(before: Mapping, after: Mapping, stderr: str, words: Sequence[str]) -> None:
    """AC08: a section that no longer matches the pending entries, or carries a withdrawn marking, stops the write,
    says which, and leaves the history and every pending entry untouched."""
    _refusal(before, after, stderr, words)


@asserts("AC09")
def check_ac09_named(stderr: str, bullets: Sequence[str], changelog: str, version: str) -> None:
    """AC09: each old-style entry is named back, not folded into the new section and not lost."""
    assert "WARNING" in stderr and all(b in stderr for b in bullets), f"AC09: not named back: {stderr!r}"
    new = dict(sections(changelog))[version]
    assert not any(b in new for b in bullets) and all(changelog.count(f"- {b}") == 1 for b in bullets), "AC09: folded or lost"


@asserts("AC10")
def check_ac10_unchanged(before: Mapping, after: Mapping, shown: str, bullets: Sequence[str]) -> None:
    """AC10: the preview shows the whole result and changes nothing on disk (no file added, changed or deleted)."""
    assert before == after, "AC10: the preview changed the disk"
    assert '"section_written"' in shown and all(b in shown for b in bullets), "AC10: the preview did not show the result"


@asserts("AC12")
def check_ac12_manifests(committed: Mapping[str, str | None], version: str, tag_made: bool) -> None:
    """AC12: the release commit carries the new version in every declared manifest before the tag; a manifest still at
    the previous version stops the release (no tag). ``committed`` is each manifest's version as the commit holds it."""
    stale = sorted(p for p, v in committed.items() if v != version)
    assert tag_made != bool(stale), f"AC12: tag={tag_made} while these manifests are not at {version}: {stale}"


@asserts("AC13")
def check_ac13_nested(parsed: Mapping, version: str) -> None:
    """AC13: a version written in more than one place of one manifest is written in all of them together."""
    names = [parsed.get("version")] + [entry.get("version") for entry in parsed.get("plugins", [])]
    assert len(names) > 1 and all(n == version for n in names), f"AC13: {names} (want {version} everywhere)"


@asserts("AC14")
def check_ac14_page(releases: Mapping, version: str, slug: str) -> None:
    """AC14: the page exists for the marking, with a readable summary; its title and the link to the full record at the
    tag are built from the recorded facts, not left to the condensing step."""
    page = releases.get(f"v{version}")
    assert page is not None and page["notes"].strip(), f"AC14: no release page for v{version}"
    assert f"https://github.com/{slug}/blob/v{version}/CHANGELOG.md" in page["notes"], "AC14: the link to the full record is missing"
    assert page["title"] == f"v{version}", page["title"]


@asserts("AC14")
def check_ac14_unchecked_not_published(releases: Mapping, version: str, reason: str) -> None:
    """AC14: a summary that fails the fixed shape is never published."""
    assert f"v{version}" not in releases and reason.startswith("notes_failed_validation"), f"AC14: {reason!r}, {list(releases)}"


@asserts("AC15")
def check_ac15_page_failed(releases: Mapping, version: str, tag_made: bool, reported: str) -> None:
    """AC15: a release page that could not be created leaves the release as it was, and is reported, not dropped."""
    assert tag_made and f"v{version}" not in releases and reported in ("failed", "skipped"), f"AC15: tag={tag_made} {reported!r}"


@asserts("AC15")
def check_ac15_no_backfill(releases: Mapping, create_calls: Sequence[Sequence[str]], older_tags: Sequence[str]) -> None:
    """AC15: an earlier version's page is not created retroactively."""
    made = {argv[2] for argv in create_calls if len(argv) > 2}
    assert not made & set(older_tags) and not set(releases) & set(older_tags), f"AC15: back-filled {made | set(releases)}"


def check_tag_on_release_commit(tag_subject: str, version: str) -> None:
    """Step 6 invariant: the tag marks the release commit itself (not its parent, not the event commit)."""
    assert tag_subject == f"chore(release): v{version}", f"the tag v{version} marks {tag_subject!r}, not the release commit"


def check_drops_consumed(pending: Sequence[str]) -> None:
    """Step 4 invariant: the pending entries the aggregation folded are gone, or the next release counts them twice."""
    assert not pending, f"pending entries were not consumed by the aggregation: {list(pending)}"


def check_release_commit_paths(changed: Sequence[str], unrelated: Sequence[str]) -> None:
    """Step 6 invariant: the release commit holds what the release changed and nothing a person happened to have staged."""
    leaked = sorted(set(changed) & set(unrelated))
    assert not leaked, f"the release commit swept in unrelated paths: {leaked}"
    assert "CHANGELOG.md" in changed, "the release commit does not hold CHANGELOG.md"
