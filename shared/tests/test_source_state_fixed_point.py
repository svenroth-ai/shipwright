"""The stamp names a fixed point instead of pretending to be live.

Subject: the ``base=`` and ``release=`` tokens
(iterate-2026-07-31-derived-docs-at-release, AC-9 / AC-9b). Sibling to
``test_source_state.py``, which owns the pre-existing three-token contract; this
file owns the pair that arrived with the compliance-evidence refresh, so neither
file has to carry two subjects.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from source_state import (  # noqa: E402
    SHORT_SHA_LEN,
    SourceState,
    banner_line,
    from_block,
    parse_banner_line,
    strip_banner,
    to_block,
)

RUN = "iterate-2026-07-31-derived-docs-at-release"
BASE = "dcf85f874e8e528e9961f3d4d615a8a7c8dfee4b"
COMMIT = "a3e625fc" + "0" * 32
RELEASE = "v0.5.2"


# --- AC-9: absent by default -------------------------------------------------


def test_absent_renders_exactly_as_before():
    """The load-bearing compatibility claim. Every producer that is not a shipped
    refresh leaves both unresolved, so its banner is byte-identical to the one it
    rendered before these tokens existed — no document goes dirty for nothing."""
    assert banner_line(SourceState(run_id=RUN)) == f"Source-State: run={RUN}"
    assert banner_line(SourceState(run_id=RUN, commit=COMMIT, dirty=False)) == (
        f"Source-State: run={RUN} commit={COMMIT[:SHORT_SHA_LEN]} clean"
    )


def test_a_pre_refresh_block_reads_both_as_unresolved():
    state = from_block({"run_id": RUN, "commit": COMMIT, "dirty": False})
    assert state.base is None
    assert state.release is None


# --- AC-9: the round trip ----------------------------------------------------


def test_the_banner_round_trips_the_fixed_point():
    state = SourceState(run_id=RUN, commit=COMMIT, dirty=False,
                        base=BASE, release=RELEASE)
    assert parse_banner_line(banner_line(state)) == state.abbreviated()


def test_the_block_round_trips_the_fixed_point_at_full_length():
    state = SourceState(run_id=RUN, base=BASE, release=RELEASE)
    block = to_block(state)
    # The JSON side keeps the FULL sha — that is the side a gate compares.
    assert block["base"] == BASE
    assert block["release"] == RELEASE
    assert from_block(block) == state


def test_base_is_abbreviated_in_the_banner_but_release_never_is():
    """Half a SHA still identifies the commit. Half a version number is a
    different version."""
    line = banner_line(SourceState(run_id=RUN, base=BASE, release="v10.11.12"))
    assert f"base={BASE[:SHORT_SHA_LEN]}" in line
    assert BASE not in line
    assert "release=v10.11.12" in line


def test_abbreviated_shortens_base_alongside_commit():
    state = SourceState(commit=COMMIT, base=BASE, release=RELEASE).abbreviated()
    assert state.commit == COMMIT[:SHORT_SHA_LEN]
    assert state.base == BASE[:SHORT_SHA_LEN]
    assert state.release == RELEASE


# --- AC-9: validated, never sanitised ----------------------------------------


def test_a_non_sha_base_is_dropped_not_rendered():
    assert "base=" not in banner_line(SourceState(run_id=RUN, base="not-a-sha"))
    assert to_block(SourceState(base="not-a-sha"))["base"] is None


def test_a_release_with_whitespace_is_dropped_not_truncated():
    """Whitespace would split into a second banner token — the forged-token shape
    ``safe_run_id`` exists to refuse. Dropped whole, never trimmed into something
    that looks legitimate."""
    line = banner_line(SourceState(run_id=RUN, release="v1 clean"))
    assert "release=" not in line
    assert line == f"Source-State: run={RUN}"


def test_an_unsubstituted_placeholder_release_is_refused():
    assert "release=" not in banner_line(SourceState(run_id=RUN, release="{version}"))


def test_a_release_value_cannot_forge_a_commit_or_status_token():
    """A release is one whitespace-free token, so its VALUE can never begin a new
    one. ``release=commit=dead...`` parses back as a release, not as a commit."""
    line = banner_line(SourceState(run_id=RUN, release="commit=deadbeefcafe"))
    parsed = parse_banner_line(line)
    assert parsed.commit is None
    assert parsed.release == "commit=deadbeefcafe"
    assert parsed.dirty is None


def test_the_banner_is_still_exactly_one_line_with_every_token_set():
    line = banner_line(SourceState(run_id=RUN, commit=COMMIT, dirty=True,
                                   base=BASE, release=RELEASE))
    assert "\n" not in line
    assert line.count("Source-State:") == 1


def test_strip_banner_still_removes_the_whole_line():
    """The Group E staleness compare strips this line. Adding tokens to it must
    not leak a moving value into the snapshot diff."""
    doc = f"# RTM\n\nGenerated: x\n{banner_line(SourceState(run_id=RUN, base=BASE))}\n\nbody\n"
    assert BASE[:SHORT_SHA_LEN] not in strip_banner(doc)
    assert "body" in strip_banner(doc)
