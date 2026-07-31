"""The artifact-state stamp's SHAPE contract — both serializations round-trip.

Card ``trg-4d5b6a56`` (FR-01.10): a produced artifact must name which state of the
project it describes. ``shared/scripts/source_state.py`` owns that identifier's shape
for both producers (the test-results record and the compliance evidence documents), so
it is defined once — these cases pin the shape itself.

The round-trip cases are the deliberate Boundary Probe for this change: the diff-driven
``touches_io_boundary`` flag does NOT fire (it matches file paths and this diff is
``.py``-only), but two serialized formats gain a field, so producer→file→consumer is
proven rather than assumed.

Split from one 403-line module (bloat gate): git resolution lives in
``test_source_state_git.py``, and the untrusted-value/forgery regressions in
``test_source_state_untrusted.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from source_state import (  # noqa: E402
    BANNER_PREFIX,
    BANNER_STRIP_RE,
    UNKNOWN_RUN,
    SourceState,
    banner_line,
    from_block,
    parse_banner_line,
    safe_run_id,
    to_block,
)

RUN = "iterate-2026-07-27-artifact-state-stamping"
SHA = "ff88258795717661322e0d5cd5ccc5ff91efa17e"

# --------------------------------------------------------------------------
# AC1 / AC6 — the shape is one shape, and both serializations round-trip
# --------------------------------------------------------------------------


class TestBannerRoundTrip:
    def test_full_state_round_trips_to_its_abbreviated_form(self):
        state = SourceState(run_id=RUN, commit=SHA, dirty=False)
        parsed = parse_banner_line(banner_line(state))
        # The banner deliberately carries the ABBREVIATED commit (a 40-hex blob
        # in an operator-facing header is noise), so the exact round-trip target
        # is the abbreviated projection. Stated, not silently lossy.
        assert parsed == state.abbreviated()
        assert parsed.run_id == RUN
        assert parsed.commit == SHA[:12]

    def test_dirty_flag_round_trips(self):
        state = SourceState(run_id=RUN, commit=SHA, dirty=True)
        line = banner_line(state)
        assert parse_banner_line(line).dirty is True

    @pytest.mark.parametrize("dirty", [True, False, None])
    def test_all_three_dirty_states_survive_the_banner(self, dirty):
        # "clean" and "git could not answer" must not render identically — that
        # collapse is the honesty distinction this stamp exists to make, and the
        # first implementation got it wrong (caught here, not in review).
        line = banner_line(SourceState(run_id=RUN, dirty=dirty))
        assert parse_banner_line(line).dirty is dirty

    def test_clean_and_unknown_render_differently(self):
        assert banner_line(SourceState(run_id=RUN, dirty=False)) != banner_line(
            SourceState(run_id=RUN, dirty=None)
        )

    def test_empty_state_round_trips_as_unknown(self):
        line = banner_line(SourceState())
        assert f"run={UNKNOWN_RUN}" in line
        parsed = parse_banner_line(line)
        assert parsed.run_id is None
        assert parsed.commit is None

    def test_banner_is_a_single_line_and_prefixed(self):
        line = banner_line(SourceState(run_id=RUN, commit=SHA, dirty=True))
        assert "\n" not in line
        assert line.startswith(BANNER_PREFIX)

    def test_parse_returns_none_when_no_banner_present(self):
        assert parse_banner_line("# Doc\n\nGenerated: 2026-07-27\n\nbody\n") is None

    def test_parse_finds_the_banner_inside_a_document(self):
        doc = f"# RTM\n\nGenerated: x\n{banner_line(SourceState(run_id=RUN))}\n\nbody\n"
        assert parse_banner_line(doc).run_id == RUN


class TestBlockRoundTrip:
    def test_json_block_round_trips_exactly_including_full_sha(self):
        state = SourceState(run_id=RUN, commit=SHA, dirty=False)
        assert from_block(to_block(state)) == state
        # The JSON side keeps the FULL sha — that is the side a gate compares.
        assert to_block(state)["commit"] == SHA

    def test_block_keys_are_the_declared_five(self):
        # `base` and `release` joined the block with the compliance-evidence
        # refresh (iterate-2026-07-31-derived-docs-at-release). Additive: every
        # reader uses .get(), and a pre-refresh block reads them as unresolved.
        assert set(to_block(SourceState()).keys()) == {
            "run_id", "commit", "dirty", "base", "release",
        }

    def test_unresolved_fields_serialise_as_null_not_omitted(self):
        # AC7: absent must be visibly absent, never quietly dropped.
        block = to_block(SourceState())
        assert block == {"run_id": None, "commit": None, "dirty": None,
                         "base": None, "release": None}

    @pytest.mark.parametrize("junk", [
        None, [], "x", 7,
        {"run_id": 5, "commit": object(), "dirty": "yes"},
        {"run_id": "a b", "commit": "nothex", "dirty": 1},
    ])
    def test_from_block_yields_an_empty_state_not_a_half_trusted_one(self, junk):
        # Asserts the VALUES, not merely that nothing raised: the guarantee is "this
        # record says nothing about its state", so a partially-trusted field is the bug.
        assert from_block(junk) == SourceState(run_id=None, commit=None, dirty=None)

    def test_from_block_rejects_a_non_bool_dirty(self):
        assert from_block({"dirty": "true"}).dirty is None


# --------------------------------------------------------------------------
# AC7 / security — untrusted values are single-line tokens or nothing
# --------------------------------------------------------------------------


class TestRunIdSanitisation:
    @pytest.mark.parametrize("bad", [
        "run\nSource-State: run=forged",   # banner forgery via newline
        "run\r\nGenerated: fake",
        "run\twith-tab",
        "run\x00null",
        "   ",
        "",
        None,
        123,
    ])
    def test_unusable_values_become_none(self, bad):
        assert safe_run_id(bad) is None

    def test_a_forged_newline_cannot_produce_a_second_banner_line(self):
        line = banner_line(SourceState(run_id="run\nSource-State: run=forged"))
        assert line.count(BANNER_PREFIX) == 1
        assert "\n" not in line
        assert UNKNOWN_RUN in line

    def test_surrounding_whitespace_is_trimmed_not_rejected(self):
        assert safe_run_id(f"  {RUN}  ") == RUN


# --------------------------------------------------------------------------
# AC5 — the strip regex is anchored (must not eat document body or layout)
# --------------------------------------------------------------------------


class TestBannerStripRegex:
    def test_strips_an_anchored_banner_line(self):
        text = f"# RTM\nGenerated: x\n{banner_line(SourceState(run_id=RUN))}\nbody\n"
        assert BANNER_STRIP_RE.sub("", text) == "# RTM\nGenerated: x\nbody\n"

    def test_does_not_strip_a_mid_line_occurrence(self):
        # Mirrors the existing Generated:-line guarantee in test_audit_staleness.
        text = f"the {BANNER_PREFIX} token appears mid-line\n"
        assert BANNER_STRIP_RE.sub("", text) == text

    def test_does_not_consume_the_blank_line_below_the_header(self):
        text = f"{banner_line(SourceState(run_id=RUN))}\n\nbody\n"
        assert BANNER_STRIP_RE.sub("", text) == "\nbody\n"

    def test_crlf_document_keeps_its_layout(self):
        text = f"# RTM\r\n{banner_line(SourceState(run_id=RUN))}\r\n\r\nbody\r\n"
        out = BANNER_STRIP_RE.sub("", text)
        assert "run=" not in out
        assert out == "# RTM\r\n\r\nbody\r\n"

    def test_strips_every_occurrence(self):
        one = banner_line(SourceState(run_id=RUN))
        assert BANNER_STRIP_RE.sub("", f"{one}\nmid\n{one}\n") == "mid\n"


