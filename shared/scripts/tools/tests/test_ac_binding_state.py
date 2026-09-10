"""``_ac_binding_state.read_binding_state`` — the pure reader both P3.7 feeder
checks share (SPEC §8 E2). No git here: this reader is state-only, so a fixture
is ``{spec_path: text}`` + a manifest dict, exactly what both CLIs hand it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from verifiers._ac_binding_state import ReadError, read_binding_state, spec_path_by_fr  # noqa: E402

SPEC_PATH = "docs/spec.md"
SPEC = """# Spec

## 2. Functional Requirements

### FR-01.01: Widgets

- [AC01] The widget must fizz.
- [AC02] The widget must buzz.

### FR-01.02: Gadgets

- [AC03] The gadget must whirr.
"""


def _manifest(*, acs_by_fr: dict[str, dict[str, dict]] | None = None,
              status: str = "active") -> dict:
    acs_by_fr = acs_by_fr or {}
    return {
        "requirements": {
            f"ns::{fr}": {
                "id": fr, "status": status, "spec_path": SPEC_PATH,
                "acs": acs_by_fr.get(fr, {}),
            }
            for fr in ("FR-01.01", "FR-01.02")
        },
    }


def _bound_link(test="tests/test_widget.py::test_fizz", executed="pass") -> dict:
    return {"tests": {"unit": [
        {"id": test, "layer": "unit", "status": "enabled", "executed": executed},
    ]}}


def test_every_minted_ac_with_no_link_is_unbound():
    manifest = _manifest()
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert state.minted == {("FR-01.01", "AC01"), ("FR-01.01", "AC02"), ("FR-01.02", "AC03")}
    assert state.unbound == state.minted
    assert state.bound == set()
    assert state.orphaned == set()
    assert state.warnings == []


def test_a_link_moves_its_ac_from_unbound_to_bound():
    manifest = _manifest(acs_by_fr={"FR-01.01": {"AC01": _bound_link()}})
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert state.bound == {("FR-01.01", "AC01")}
    assert state.unbound == {("FR-01.01", "AC02"), ("FR-01.02", "AC03")}


def test_a_link_bound_to_a_no_longer_minted_ac_is_orphaned():
    """Arm 1: outright deletion / id rotation — a manifest binding under an AC
    id the current spec no longer mints (SPEC §8 E2(b) shapes ii/iii)."""
    manifest = _manifest(acs_by_fr={"FR-01.01": {"AC99": _bound_link()}})
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert state.orphaned == {("FR-01.01", "AC99")}
    # AC99 never being minted means it contributes nothing to `minted`/`bound`/`unbound`.
    assert ("FR-01.01", "AC99") not in state.minted


def test_a_suffix_dropped_binding_is_unbound_not_orphaned():
    """The two-PR sequence's PR1 (SPEC §8 E2(b) shape i): the manifest simply
    carries no `acs` entry at all for AC01 once the `@covers` tag loses its
    suffix -- indistinguishable, at THIS reader, from an AC that was never
    bound. Confirms `_ac_binding_regression` exists for a reason: arm 1 alone
    cannot see this."""
    manifest = _manifest()  # no acs entries at all -- the post-dodge state
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert ("FR-01.01", "AC01") in state.unbound
    assert state.orphaned == set()


def test_an_unreadable_spec_path_raises_readerror_not_excludes(capsys):
    """External code review (openai, HIGH): an EARLIER version of this reader
    excluded a `None` (genuine read fault) spec path with a warning, which
    made feeder (b)'s HARD orphan check fail OPEN on exactly the case it
    exists to catch (a spec that could not be read still has stale bindings
    that need judging, not skipping). Now raises -- both CLIs map this to
    an infra_fault (exit 2), matching P3.6's own HEAD-side convention."""
    with pytest.raises(ReadError, match=SPEC_PATH):
        read_binding_state({SPEC_PATH: None}, _manifest())


def test_a_genuinely_absent_spec_path_proceeds_as_zero_criteria_with_a_warning():
    """The OTHER half of the three-way fix: `""` (genuinely absent, e.g. the
    spec file was deleted at head) is NOT the same as `None` (could not be
    read) -- it proceeds as zero minted criteria, so any AC the manifest
    still binds under that FR correctly reads as ORPHANED rather than being
    silently excluded. Matches `_keystone_ac_digest.ac_change_set`'s own
    precedent (named path resolves to no content -> proceed + warn)."""
    manifest = _manifest(acs_by_fr={"FR-01.01": {"AC01": _bound_link()}})
    state = read_binding_state({SPEC_PATH: ""}, manifest)
    assert state.minted == set()
    assert state.orphaned == {("FR-01.01", "AC01")}
    assert len(state.warnings) == 2  # one per FR sharing this spec_path
    assert all(SPEC_PATH in w for w in state.warnings)


def test_untrustworthy_markers_raise_readerror():
    """Duplicate `[AC01]` markers under the same FR -- `ac_identity.read_all`
    raises `DuplicateAcIdError`; this reader maps it to `ReadError`, matching
    `_keystone_criteria.ac_criteria_digests`'s own HEAD-side treatment."""
    bad_spec = SPEC.replace(
        "- [AC02] The widget must buzz.", "- [AC01] The widget must buzz twice.")
    with pytest.raises(ReadError, match="FR-01.01"):
        read_binding_state({SPEC_PATH: bad_spec}, _manifest())


def test_a_bound_ac_with_a_failed_or_skipped_link_is_still_bound_not_unbound():
    """External plan review (glm, low): "bound" is TAG-derived (does a link
    exist), never execution-derived (did it pass) -- greenness is P3.6's own
    gate's question. A failed or skipped link still counts as a binding."""
    manifest = _manifest(acs_by_fr={
        "FR-01.01": {
            "AC01": _bound_link(executed="fail"),
            "AC02": {"tests": {"unit": [
                {"id": "t::x", "layer": "unit", "status": "skipped", "executed": "not_run"},
            ]}},
        },
    })
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert state.bound == {("FR-01.01", "AC01"), ("FR-01.01", "AC02")}
    assert state.unbound == {("FR-01.02", "AC03")}


def test_a_retired_requirement_contributes_nothing():
    manifest = _manifest(status="retired", acs_by_fr={"FR-01.01": {"AC99": _bound_link()}})
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert state.minted == set() and state.orphaned == set()


def test_spec_path_by_fr_is_scoped_to_active_requirements():
    manifest = _manifest(status="retired")
    assert spec_path_by_fr(manifest) == {}


def test_an_active_fr_with_no_spec_path_is_warned_not_silently_excluded():
    """Stage-2 code review, medium: an active FR with no `spec_path` recorded
    at all (`spec_path_by_fr` never enters it into `spec_text_by_path`, so it
    has no read outcome to react to) is excluded from BOTH feeders -- its
    minted ACs never enter `unbound` (feeder a), and any binding it still
    carries never enters the orphan check (feeder b) -- and that exclusion
    must be a WARNING naming both consequences, not a silent drop that would
    read as a clean pass to either gate."""
    manifest = {
        "requirements": {
            "ns::FR-01.01": {
                "id": "FR-01.01", "status": "active", "spec_path": SPEC_PATH,
                "acs": {"AC01": _bound_link()},
            },
            "ns::FR-01.02": {"id": "FR-01.02", "status": "active", "acs": {"AC03": _bound_link()}},
            "ns::FR-01.03": {"id": "FR-01.03", "status": "active", "acs": {}},
        },
    }
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert not any(fr == "FR-01.02" for fr, _ac in (state.minted | state.unbound | state.orphaned))
    assert not any(fr == "FR-01.03" for fr, _ac in (state.minted | state.unbound | state.orphaned))
    warned_frs = {w.split(":")[0] for w in state.warnings}
    assert "FR-01.02" in warned_frs and "FR-01.03" in warned_frs
    assert any("FR-01.02" in w and "1 AC binding" in w for w in state.warnings)
    assert any("FR-01.03" in w and "0 AC binding" in w for w in state.warnings)


def test_a_display_id_collision_is_warned_not_falsely_orphaned():
    """Stage-3 doubt review, HIGH: two active nodes sharing a display id but
    naming DIFFERENT spec_paths make `spec_path_by_fr`'s plain dict pick ONE
    path arbitrarily (last write wins) -- an AC minted only in the LOSING
    document, with a binding, would otherwise false-orphan on this hard,
    unbaselined gate. The same ambiguity is already routed ADVISORY
    everywhere else the family checks for it
    (`_layer_coverage_core.collision_display_ids`); this reader picks the
    SAME resolution (exclude + warn), not a stricter one, since failing
    closed would block every PR touching any PRE-EXISTING collision."""
    second_path = "docs/spec2.md"
    second_spec_text = (
        "# Spec 2\n\n## 2. Functional Requirements\n\n### FR-01.01: Widgets (dup)\n\n"
        "- [AC02] A criterion minted only in the second, colliding document.\n"
    )
    manifest = {
        "requirements": {
            "ns::FR-01.01-a": {
                "id": "FR-01.01", "status": "active", "spec_path": SPEC_PATH,
                "acs": {"AC01": _bound_link()},
            },
            "ns::FR-01.01-b": {
                "id": "FR-01.01", "status": "active", "spec_path": second_path,
                "acs": {},
            },
        },
    }
    state = read_binding_state({SPEC_PATH: SPEC, second_path: second_spec_text}, manifest)
    assert state.orphaned == set()
    assert not any(fr == "FR-01.01" for fr, _ac in (state.minted | state.unbound))
    assert any("FR-01.01" in w and "collides" in w for w in state.warnings)


def test_a_non_string_id_is_warned_not_silently_excluded():
    """Stage-3 doubt review, low: the third instance of the same silent-
    exclusion class -- an active node whose `id` is not a string falls
    through every string-keyed branch; it must warn like its two siblings
    (missing spec_path, display-id collision), not skip silently."""
    manifest = {"requirements": {"ns::x": {"id": 123, "status": "active", "acs": {"AC01": {}}}}}
    state = read_binding_state({}, manifest)
    assert state.orphaned == set() and state.minted == set()
    assert any("123" in w for w in state.warnings)


def test_orphaned_keys_on_link_count_not_node_presence():
    """Stage-2 code review, low: `bound`/`unbound` key on `links_for`'s COUNT
    (its own stated convention, not the `acs` node's presence), so `orphaned`
    must too -- an `acs[ac_id]` node with an empty `tests` map is not a real
    binding and must not false-BLOCK the gate."""
    manifest = _manifest(acs_by_fr={
        "FR-01.01": {"AC99": {"tests": {"unit": []}}},  # node present, zero links
    })
    state = read_binding_state({SPEC_PATH: SPEC}, manifest)
    assert state.orphaned == set()
