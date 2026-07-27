"""What the durable record is allowed to claim — scope bookkeeping + validation.

Two ways this feature can lie, both covered here:

1. **Scope.** A partial ``--only`` run must never be readable as a whole-project
   cross-check, and must never erase the date of the last one that was.
2. **Trust.** The record lives in a tracked, hand-editable config and its values
   are interpolated into compliance documents. A damaged record must read as
   *unknown* (never as "never run", which asserts something the project cannot
   know), and no unvalidated value may reach markdown.

Writing durability is covered by ``test_audit_disclosure.py``; rendering by
``test_audit_disclosure_render.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lib.audit_disclosure import (
    ABSENT,
    CONFIG_FILE,
    INVALID,
    LAST_AUDIT_KEY,
    LAST_FULL_AUDIT_KEY,
    VALID,
    load_audit_freshness,
    read_last_audit,
    record_audit_run,
)


def _write_config(root: Path, payload: dict) -> Path:
    path = root / CONFIG_FILE
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _full_block(ran_at="2026-07-01T00:00:00+00:00", **over) -> dict:
    block = {
        "ran_at": ran_at,
        "verdict": "pass",
        "scope": "full",
        "checks": {"total": 5, "pass": 5, "fail": 0, "skip": 0},
    }
    block.update(over)
    return block


@pytest.fixture
def bare_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


class TestScopeBookkeeping:
    """AC-5 — "when was the WHOLE project last checked?" stays answerable."""

    def test_a_full_run_also_refreshes_the_last_full_record(self, bare_root: Path):
        record_audit_run(bare_root, statuses=["pass"], any_fail=False)
        doc = json.loads((bare_root / CONFIG_FILE).read_text(encoding="utf-8"))
        assert doc[LAST_FULL_AUDIT_KEY] == doc[LAST_AUDIT_KEY]

    def test_a_partial_run_never_erases_the_last_full_check(self, bare_root: Path):
        """Otherwise a Friday ``--only A`` deletes Thursday's whole-project run."""
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False,
            ran_at="2026-07-01T00:00:00+00:00",
        )
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False, scope="A,B",
            ran_at="2026-07-25T00:00:00+00:00",
        )
        freshness = load_audit_freshness(bare_root)
        assert freshness.latest.scope == "A,B"
        assert freshness.latest_full.ran_at == "2026-07-01T00:00:00+00:00"

    def test_a_partial_run_promotes_a_pre_upgrade_full_record(
        self, bare_root: Path,
    ):
        """Upgrade path: a config predating ``last_full_audit`` must not lose it.

        Such a config holds its full run only under ``last_audit``; the first
        partial run after the upgrade overwrites that slot, so the full record
        has to be promoted first or the project silently reads "never fully run".
        """
        _write_config(bare_root, {LAST_AUDIT_KEY: _full_block()})
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False, scope="A,B",
            ran_at="2026-07-25T00:00:00+00:00",
        )
        freshness = load_audit_freshness(bare_root)
        assert freshness.latest.scope == "A,B"
        assert freshness.latest_full is not None
        assert freshness.latest_full.ran_at == "2026-07-01T00:00:00+00:00"

    def test_a_partial_run_does_not_promote_a_prior_partial_record(
        self, bare_root: Path,
    ):
        _write_config(bare_root, {LAST_AUDIT_KEY: _full_block(scope="C")})
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False, scope="A,B",
        )
        assert load_audit_freshness(bare_root).latest_full is None

    def test_a_full_run_after_a_partial_one_becomes_the_full_record(
        self, bare_root: Path,
    ):
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False, scope="A",
            ran_at="2026-07-01T00:00:00+00:00",
        )
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False,
            ran_at="2026-07-25T00:00:00+00:00",
        )
        freshness = load_audit_freshness(bare_root)
        assert freshness.latest.is_full
        assert freshness.latest_full.ran_at == "2026-07-25T00:00:00+00:00"


class TestValuesReachingADocument:
    """Nothing unvalidated may be interpolated into compliance evidence."""

    def test_non_integer_check_counts_are_dropped(self, bare_root: Path):
        _write_config(
            bare_root,
            {LAST_AUDIT_KEY: _full_block(
                checks={"total": 5, "pass": "0\n## Injected", "fail": -3},
            )},
        )
        assert load_audit_freshness(bare_root).latest.checks == {"total": 5}

    def test_a_hostile_scope_value_is_stripped_before_it_is_stored(
        self, bare_root: Path,
    ):
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False,
            scope="A](http://evil)`x`\n# heading",
        )
        assert read_last_audit(bare_root)["scope"] == "Ahttpevilxheading"

    def test_a_hostile_scope_value_is_stripped_on_read(self, bare_root: Path):
        """Defence in depth: the file can be edited after the writer ran."""
        _write_config(
            bare_root, {LAST_AUDIT_KEY: _full_block(scope="A **bold** ](x)")},
        )
        assert load_audit_freshness(bare_root).latest.scope == "Aboldx"

    def test_no_temp_file_is_left_behind(self, bare_root: Path):
        record_audit_run(bare_root, statuses=["pass"], any_fail=False)
        assert not list(bare_root.glob("*.tmp"))


class TestLoadAuditFreshness:
    """AC-7 — degrade honestly. "Absent" and "damaged" are different claims."""

    def test_no_config_at_all_is_absent(self, bare_root: Path):
        assert load_audit_freshness(bare_root).status == ABSENT

    def test_config_without_the_key_is_absent(self, bare_root: Path):
        _write_config(bare_root, {"enforcement": {}})
        assert load_audit_freshness(bare_root).status == ABSENT

    def test_null_record_is_absent(self, bare_root: Path):
        _write_config(bare_root, {LAST_AUDIT_KEY: None})
        assert load_audit_freshness(bare_root).status == ABSENT

    @pytest.mark.parametrize(
        "payload",
        [
            {LAST_AUDIT_KEY: "2026-07-20"},               # scalar, not an object
            {LAST_AUDIT_KEY: {}},                         # no ran_at
            {LAST_AUDIT_KEY: {"verdict": "pass"}},        # ran_at missing
            {LAST_AUDIT_KEY: {"ran_at": ""}},             # ran_at empty
            {LAST_AUDIT_KEY: {"ran_at": "not-a-date", "verdict": "pass"}},
            {LAST_AUDIT_KEY: {"ran_at": "2026-07-20T00:00:00+00:00",
                              "verdict": "probably fine"}},
        ],
    )
    def test_damaged_records_are_invalid_not_absent(
        self, bare_root: Path, payload: dict,
    ):
        _write_config(bare_root, payload)
        freshness = load_audit_freshness(bare_root)
        assert freshness.status == INVALID
        assert freshness.latest is None

    def test_non_object_config_root_is_invalid(self, bare_root: Path):
        (bare_root / CONFIG_FILE).write_text("[]", encoding="utf-8")
        assert load_audit_freshness(bare_root).status == INVALID

    def test_unparseable_config_is_invalid(self, bare_root: Path):
        (bare_root / CONFIG_FILE).write_text("{oops", encoding="utf-8")
        assert load_audit_freshness(bare_root).status == INVALID

    def test_a_well_formed_record_is_valid(self, bare_root: Path):
        record_audit_run(bare_root, statuses=["pass"], any_fail=False)
        freshness = load_audit_freshness(bare_root)
        assert freshness.status == VALID
        assert freshness.latest.is_full

    def test_read_last_audit_returns_none_for_every_unusable_state(
        self, bare_root: Path,
    ):
        assert read_last_audit(bare_root) is None
        (bare_root / CONFIG_FILE).write_text("{oops", encoding="utf-8")
        assert read_last_audit(bare_root) is None
