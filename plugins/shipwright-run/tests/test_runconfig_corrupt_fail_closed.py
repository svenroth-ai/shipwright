"""An UNUSABLE run config must stop anything that would advance or change a run,
and must never be overwritten.

Measured before the fix, against a truncated config recording
``standalone: false`` and ``mode: single_session``:

* ``_read_standalone_flag`` -> ``True``, so the phase gate was skipped, a
  ``force=True`` with no reason was accepted, and no ``validation_overrides[]``
  entry was written. FR-01.01's evidence rule stopped applying precisely in the
  degraded state where evidence matters.
* ``get_next_step`` -> ``"no config found, start from beginning"``.
* ``_load_or_bootstrap`` then atomically replaced the file, discarding
  ``runId`` / ``mode`` / ``phase_tasks`` / ``completed_steps`` /
  ``validation_overrides``.

Recorded as Rejected under ADR-114 pending a decision about what a corrupt config
should do to a run. The decision — fail closed where it can change a run, stay
tolerant where it only displays — and the four doors it closes are in
``.shipwright/planning/iterate/iterate-2026-08-05-standalone-flag-corrupt-config.md``.

The read boundary is covered by ``test_runconfig_corrupt_reader.py``, the CLI
exit codes and recovery by ``test_runconfig_corrupt_cli.py``, and the strict-read
inventory by ``test_runconfig_corrupt_chokepoints.py``.
"""
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
# The shared shapes module lives beside this file; pytest's import mode here does
# not put the test dir on sys.path, so say so explicitly.
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import orchestrator  # noqa: E402,F401 — installs the ``orchestrator`` shim namespace
from orchestrator_pkg import step_planning  # noqa: E402
from orchestrator_pkg.config_io import RunConfigUnreadable  # noqa: E402
from orchestrator_pkg.constants import CONFIG_NAME  # noqa: E402
from runconfig_corrupt_shapes import (  # noqa: E402
    CANARY_MARKER,
    UNUSABLE_CONTENT,
    truncated,
    write,
)


# --------------------------------------------------------------------------- #
# AC4 — the standalone flag is a real bool, and fails SAFE
# --------------------------------------------------------------------------- #

def test_absent_config_still_reads_standalone(tmp_path):
    assert step_planning._read_standalone_flag(tmp_path) is True


@pytest.mark.parametrize("name", sorted(UNUSABLE_CONTENT))
def test_standalone_flag_refuses_rather_than_demoting(tmp_path, name):
    """THE REPORTED BUG. A config that cannot be used must not be answered for."""
    write(tmp_path, UNUSABLE_CONTENT[name])
    with pytest.raises(RunConfigUnreadable):
        step_planning._read_standalone_flag(tmp_path)


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("true", True),
        ("false", False),
        ('"false"', False),   # a truthy STRING — used to read as standalone
        ('"no"', False),
        ('"true"', False),    # not the literal bool: fail safe, run the gate
        ("0", False),
        ("1", False),
        ("null", False),
        ('""', False),
    ],
)
def test_standalone_is_only_the_literal_true(tmp_path, literal, expected):
    """The semantic door. The function is annotated ``-> bool`` but returned
    ``config.get("standalone", False)`` raw, so ``"false"`` was truthy."""
    write(tmp_path, '{"standalone": %s, "pipeline": ["plan"]}' % literal)
    assert step_planning._read_standalone_flag(tmp_path) is expected


def test_present_empty_object_is_not_standalone(tmp_path):
    """The truthiness door at the flag: ``{}`` records no ``standalone``, so the
    gate must RUN."""
    write(tmp_path, "{}")
    assert step_planning._read_standalone_flag(tmp_path) is False


def test_standalone_flag_still_mirrors_load_or_bootstrap(tmp_path):
    """The invariant the pre-existing suite pins, re-asserted across the fix."""
    assert step_planning._read_standalone_flag(tmp_path) is (
        step_planning._load_or_bootstrap(tmp_path, "plan").get("standalone", False)
    )
    write(tmp_path, '{"standalone": true}')
    assert step_planning._read_standalone_flag(tmp_path) is True
    write(tmp_path, '{"standalone": false}')
    assert step_planning._read_standalone_flag(tmp_path) is False


# --------------------------------------------------------------------------- #
# AC5 — bootstrap is for ABSENT only; an unusable config is never overwritten
# --------------------------------------------------------------------------- #

def test_bootstrap_fires_only_when_the_file_is_absent(tmp_path):
    config = step_planning._load_or_bootstrap(tmp_path, "plan")
    assert config["standalone"] is True
    assert config["current_step"] == "plan"


def test_present_empty_object_is_returned_not_bootstrapped(tmp_path):
    """Presence, not truthiness: ``{}`` is a real config and comes back as-is."""
    write(tmp_path, "{}")
    config = step_planning._load_or_bootstrap(tmp_path, "plan")
    assert config == {}


def test_present_empty_object_reaches_the_gate_instead_of_skipping_it(
    tmp_path, monkeypatch,
):
    """The one behaviour change on a USABLE config, end-to-end (Stage-3 review).

    ``{}`` used to read as standalone, so ``update_step`` skipped the phase gate
    and completed the step. It is now not-standalone, so the gate RUNS, finds
    ask-level issues on a project with no artifacts, and parks the run at
    ``needs_validation`` for a person to decide — recoverable with
    ``--force --force-reason``. Failing toward asking is the intent; asserted
    here because it is a real change and was otherwise covered only at the
    helpers, never through ``update_step``.
    """
    monkeypatch.setattr(step_planning, "_run_compliance_update", lambda root, phase: None)
    write(tmp_path, "{}")

    result = step_planning.update_step(tmp_path, "plan", "complete")

    assert result["status"] == "needs_validation"
    assert result["validation_issues"], "the gate ran and its findings were recorded"
    assert "plan" not in (result.get("completed_steps") or []), (
        "a phase must not bank as complete while the gate is unanswered"
    )


@pytest.mark.parametrize("name", sorted(UNUSABLE_CONTENT))
def test_refuses_to_bootstrap_over_an_unusable_config(tmp_path, name):
    write(tmp_path, UNUSABLE_CONTENT[name])
    with pytest.raises(RunConfigUnreadable):
        step_planning._load_or_bootstrap(tmp_path, "plan")


@pytest.mark.parametrize("name", sorted(UNUSABLE_CONTENT))
def test_the_unusable_file_survives_byte_for_byte(tmp_path, name):
    """THE ANTI-DATA-LOSS GUARANTEE. Not 'assert it raised' — assert the bytes
    that could still be hand-repaired survived."""
    path = write(tmp_path, UNUSABLE_CONTENT[name])
    before = path.read_bytes()

    with pytest.raises(RunConfigUnreadable):
        step_planning.update_step(tmp_path, "plan", "complete")

    assert path.read_bytes() == before, "the only copy of the damaged config was overwritten"


def test_a_non_utf8_config_also_survives_byte_for_byte(tmp_path):
    """``UNUSABLE_CONTENT`` is text-only, so ``decode`` would otherwise never
    reach the anti-data-loss assertion (Stage-1 review)."""
    path = tmp_path / CONFIG_NAME
    path.write_bytes(b'{"standalone": fa\xff\xfelse}')
    before = path.read_bytes()

    with pytest.raises(RunConfigUnreadable):
        step_planning.update_step(tmp_path, "plan", "complete")

    assert path.read_bytes() == before


# --------------------------------------------------------------------------- #
# AC6 — update_step refuses for EVERY status, before doing anything
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", ["complete", "in_progress", "failed"])
def test_update_step_refuses_on_every_status(tmp_path, status):
    path = write(tmp_path, truncated())
    before = path.read_bytes()
    with pytest.raises(RunConfigUnreadable):
        step_planning.update_step(tmp_path, "plan", status)
    assert path.read_bytes() == before


def test_never_spawns_compliance_on_a_doomed_path(tmp_path, monkeypatch):
    """Up to a 30 s subprocess; a doomed run must not pay for it. Patched by
    MODULE OBJECT (ADR-045), not by dotted string."""
    calls = []
    monkeypatch.setattr(step_planning, "_run_compliance_update",
                        lambda root, phase: calls.append(phase))
    write(tmp_path, truncated())
    with pytest.raises(RunConfigUnreadable):
        step_planning.update_step(tmp_path, "plan", "complete")
    assert calls == []


def test_a_reasonless_force_can_no_longer_slip_through(tmp_path):
    """The FR-01.01 hole. On a demoted run ``normalise_override_reason`` was never
    reached, so ``force=True`` with no reason was accepted and no
    ``validation_overrides[]`` entry was written."""
    write(tmp_path, truncated())
    with pytest.raises(RunConfigUnreadable):
        step_planning.update_step(tmp_path, "plan", "complete", force=True, force_reason=None)


def test_a_driven_run_is_not_restarted_from_the_beginning(tmp_path):
    """The end-to-end symptom: a truncated config recording two completed phases
    and ``mode: single_session`` came back as a fresh standalone run, and the
    file was replaced by a bootstrap that recorded ``standalone: true`` with an
    empty pipeline history."""
    path = write(tmp_path, truncated())
    with pytest.raises(RunConfigUnreadable):
        step_planning.update_step(tmp_path, "plan", "complete")

    survived = path.read_text(encoding="utf-8")
    # The run's identity is still on disk to be repaired from...
    assert '"runId"' in survived and '"single_session"' in survived
    # ...and it was NOT replaced by a synthesised standalone bootstrap.
    assert '"standalone": true' not in survived
    assert '"created_at"' not in survived


# --------------------------------------------------------------------------- #
# AC7 — get_next_step reports, and stops lying
# --------------------------------------------------------------------------- #

def test_no_longer_says_start_from_the_beginning(tmp_path):
    write(tmp_path, truncated())
    result = step_planning.get_next_step(tmp_path)
    assert result["blocked"] is True
    assert result["reason"] == "config_unreadable"
    assert result["next_step"] is None


def test_blocked_is_distinguishable_from_all_steps_complete(tmp_path):
    """Both carry ``next_step: None``. Only ``blocked`` tells them apart."""
    write(tmp_path, json.dumps(
        {"pipeline": ["plan"], "completed_steps": ["plan"], "standalone": True}))
    done = step_planning.get_next_step(tmp_path)
    assert done["next_step"] is None and not done.get("blocked")

    write(tmp_path, truncated())
    blocked = step_planning.get_next_step(tmp_path)
    assert blocked["next_step"] is None and blocked["blocked"] is True


def test_absent_config_still_starts_from_the_beginning(tmp_path):
    """Unchanged for the case that genuinely IS a fresh project."""
    result = step_planning.get_next_step(tmp_path)
    assert result["next_step"] == "project"
    assert not result.get("blocked")


def test_blocked_result_does_not_leak_file_content(tmp_path):
    """A library consumer serialises this itself, so it must use the same bounded
    formatter as the CLI payload."""
    write(tmp_path, '{"marker": "%s", ' % CANARY_MARKER)
    assert CANARY_MARKER not in json.dumps(step_planning.get_next_step(tmp_path))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"pipeline": null}', "project"),                              # falls back to PIPELINE_STEPS
        ('{"completed_steps": null, "pipeline": ["plan"]}', "plan"),    # own pipeline honoured
        ('{"pipeline": null, "completed_steps": null}', "project"),
    ],
)
def test_null_valued_fields_do_not_crash_the_reporter(tmp_path, payload, expected):
    """The FIFTH shape (Stage-3 review). An explicit null passes the shape gate —
    it IS a well-formed object — and then raised ``TypeError`` out of a function
    whose docstring promises not to crash, escaping both the
    ``RunConfigUnreadable`` handler and the CLI's. ``update_step`` already
    carried ``or PIPELINE_STEPS  # tolerate explicit null``, which is the
    evidence the shape occurs in the wild."""
    write(tmp_path, payload)
    result = step_planning.get_next_step(tmp_path)
    assert result["next_step"] == expected
    assert not result.get("blocked")


def test_get_next_step_does_not_raise(tmp_path):
    """It is a reporter. It must stop lying without becoming a crash site."""
    write(tmp_path, "null")
    assert step_planning.get_next_step(tmp_path)["blocked"] is True
