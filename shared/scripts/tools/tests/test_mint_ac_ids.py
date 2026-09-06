"""CLI-level tests for ``mint_ac_ids.py`` -- invoked as a real subprocess
(the way an operator or a later sub-iterate actually runs it), not imported,
so the test also exercises argument parsing and the on-disk read/write path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "mint_ac_ids.py"

_SPEC = (
    "### FR-09.01 — Example\n\n"
    "- (E) Given a thing, when it happens, then it holds.\n"
    "- (E) Given a second thing, when it happens, then it holds too.\n"
)


def _run(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_TOOL), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_dry_run_reports_assignments_without_writing(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC, encoding="utf-8")
    registry = tmp_path / "shipwright_ac_registry.json"

    payload = _run("--spec-file", str(spec), "--registry-file", str(registry))

    assert payload["written"] is False
    assert payload["assigned"] == [
        {"fr_id": "FR-09.01", "ac_id": "AC01"},
        {"fr_id": "FR-09.01", "ac_id": "AC02"},
    ]
    assert spec.read_text(encoding="utf-8") == _SPEC  # untouched
    assert not registry.exists()  # untouched


def test_write_applies_the_mint_and_persists_the_registry(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC, encoding="utf-8")
    registry = tmp_path / "shipwright_ac_registry.json"

    payload = _run("--spec-file", str(spec), "--registry-file", str(registry), "--write")

    assert payload["written"] is True
    written = spec.read_text(encoding="utf-8")
    assert "[AC01] Given a thing" in written
    assert "[AC02] Given a second thing" in written
    assert json.loads(registry.read_text(encoding="utf-8")) == {"FR-09.01": 2}


def test_a_second_write_is_idempotent_and_never_renumbers(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC, encoding="utf-8")
    registry = tmp_path / "shipwright_ac_registry.json"

    _run("--spec-file", str(spec), "--registry-file", str(registry), "--write")
    once = spec.read_text(encoding="utf-8")

    payload = _run("--spec-file", str(spec), "--registry-file", str(registry), "--write")

    assert payload["assigned"] == []
    assert spec.read_text(encoding="utf-8") == once
    assert json.loads(registry.read_text(encoding="utf-8")) == {"FR-09.01": 2}


def test_a_duplicate_marker_document_exits_non_zero_not_zero(tmp_path):
    """GLM low #4: nothing previously proved the CLI FAILS loudly on a
    document ``ac_identity.mint`` itself rejects -- a future broad
    ``except Exception: ...; return 0`` around the mint call would pass every
    other test in this file while silently exiting clean on a real error."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "### FR-09.02 — Example\n\n"
        "- (E) [AC01] Given a first thing, when it happens, then it holds.\n"
        "- (E) [AC01] Given a second thing, when it happens, then it holds too.\n",
        encoding="utf-8",
    )
    registry = tmp_path / "shipwright_ac_registry.json"

    proc = subprocess.run(
        [sys.executable, str(_TOOL), "--spec-file", str(spec), "--registry-file", str(registry)],
        capture_output=True, text=True, encoding="utf-8",
    )

    assert proc.returncode != 0
    assert "DuplicateAcIdError" in proc.stderr or "AC01" in proc.stderr


def test_a_non_integer_registry_value_exits_non_zero_not_a_bare_traceback_deep_in_mint(tmp_path):
    """GLM low #5: a hand-edited registry value like ``"2"`` used to survive
    ``json.loads`` and die opaquely inside ``mint()``'s ``+ 1``; the CLI now
    validates the registry shape itself and fails loudly, at the boundary."""
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC, encoding="utf-8")
    registry = tmp_path / "shipwright_ac_registry.json"
    registry.write_text(json.dumps({"FR-09.01": "2"}), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(_TOOL), "--spec-file", str(spec), "--registry-file", str(registry)],
        capture_output=True, text=True, encoding="utf-8",
    )

    assert proc.returncode != 0
    assert "FR-09.01" in proc.stderr


def test_a_negative_registry_value_exits_non_zero_not_a_hand_typed_ac00(tmp_path):
    """External code review, 2026-09-06 round 2: `{"FR-09.01": -1}` would
    otherwise flow straight into `mint()`'s `+ 1` and mint `[AC00]` -- a
    marker `parse_marker` itself rejects as "can only be hand-typed", so the
    tool would poison its own next run. Caught here, at the boundary."""
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC, encoding="utf-8")
    registry = tmp_path / "shipwright_ac_registry.json"
    registry.write_text(json.dumps({"FR-09.01": -1}), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(_TOOL), "--spec-file", str(spec), "--registry-file", str(registry)],
        capture_output=True, text=True, encoding="utf-8",
    )

    assert proc.returncode != 0
    assert "FR-09.01" in proc.stderr


def test_write_creates_the_registry_file_even_when_the_spec_has_no_bullets(tmp_path):
    """GLM low #5, second half: the help text promises the registry is
    'created on first --write if absent'; that used to be false whenever
    ``result.registry == registry`` (e.g. a spec with no criterion bullets at
    all), since the write was conditional on a change."""
    spec = tmp_path / "spec.md"
    spec.write_text("### FR-09.03 — Example\n\nNo bullets here.\n", encoding="utf-8")
    registry = tmp_path / "shipwright_ac_registry.json"

    payload = _run("--spec-file", str(spec), "--registry-file", str(registry), "--write")

    assert payload["assigned"] == []
    assert registry.exists()
    assert json.loads(registry.read_text(encoding="utf-8")) == {}
