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
