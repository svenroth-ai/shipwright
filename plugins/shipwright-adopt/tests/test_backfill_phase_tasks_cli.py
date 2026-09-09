"""CLI-level tests for ``scripts/tools/backfill_phase_tasks.py``.

AC1 (reads correctly after backfill) and AC2 (idempotent) are pinned at the
pure-function level in ``test_backfill_missing_phase_tasks.py``; this file
covers the I/O wrapper — reading/writing the real file on disk — and AC3:
verified against a REAL pre-existing adopted config, not only a synthetic
fixture. ``leadwright_run_config.json`` is a verbatim copy of the on-disk
``shipwright_run_config.json`` from a repo adopted 2026-05-29, well before
s2 (2026-09-09) started seeding ``phase_tasks[]`` -- exactly the gap this
sub-iterate closes, and the "known live case" the spec names.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

import tools.backfill_phase_tasks as backfill_cli
from tools.backfill_phase_tasks import RUN_CONFIG_NAME, run

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "backfill_phase_tasks"


def _copy_config(src_name: str, project_root: Path) -> Path:
    project_root.mkdir(parents=True, exist_ok=True)
    dest = project_root / RUN_CONFIG_NAME
    shutil.copyfile(_FIXTURES / src_name, dest)
    return dest


# ---------------------------------------------------------------------------
# Confidence Calibration boundary probes (touches_io_boundary, s2b): a
# shipwright_run_config.json is human-editable JSON. A BOM-prefixed file
# (Notepad-style save) was found by an empirical probe to raise
# JSONDecodeError instead of parsing -- fixed via utf-8-sig decoding.
# CRLF line endings and non-ASCII values round-tripped cleanly on first
# probe (JSON's own escaping/quoting handles both; unlike raw KEY=VALUE
# .env parsing, there is no hand-rolled line-splitting here) -- two
# consecutive clean probes, asymptote reached.
# ---------------------------------------------------------------------------


def test_a_bom_prefixed_config_is_read_not_rejected(tmp_path: Path) -> None:
    project = tmp_path / "leadwright"
    project.mkdir()
    fixture_bytes = (_FIXTURES / "leadwright_run_config.json").read_bytes()
    (project / RUN_CONFIG_NAME).write_bytes(b"\xef\xbb\xbf" + fixture_bytes)

    result = run(project, dry_run=True)

    assert result["applicable"] is True
    assert sorted(result["added_phases"]) == sorted(["project", "plan", "build", "test"])


def test_crlf_and_non_ascii_values_round_trip_cleanly(tmp_path: Path) -> None:
    project = tmp_path / "leadwright"
    project.mkdir()
    cfg = json.loads((_FIXTURES / "leadwright_run_config.json").read_text(encoding="utf-8"))
    non_ascii_scope = "Bibliothek fur Munchen -- umlaut probe: äöü—"
    cfg["scope"] = non_ascii_scope
    crlf_text = json.dumps(cfg, indent=2).replace("\n", "\r\n")
    (project / RUN_CONFIG_NAME).write_bytes(crlf_text.encode("utf-8"))

    run(project, dry_run=False)

    after = json.loads((project / RUN_CONFIG_NAME).read_text(encoding="utf-8"))
    assert after["scope"] == non_ascii_scope


def test_missing_config_raises(tmp_path: Path) -> None:
    empty = tmp_path / "no-config"
    empty.mkdir()
    with pytest.raises(SystemExit, match="does not exist"):
        run(empty, dry_run=False)


def test_corrupt_json_raises(tmp_path: Path) -> None:
    project = tmp_path / "corrupt"
    project.mkdir()
    (project / RUN_CONFIG_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="not valid JSON"):
        run(project, dry_run=False)


def test_a_non_adopted_config_is_reported_not_applicable(tmp_path: Path) -> None:
    project = tmp_path / "driven"
    project.mkdir()
    (project / RUN_CONFIG_NAME).write_text(
        json.dumps({"status": "in_progress", "completed_steps": ["project"]}),
        encoding="utf-8",
    )
    result = run(project, dry_run=False)
    assert result == {
        "success": True,
        "applicable": False,
        "reason": (
            "no usable 'adoption' object -- not a shipwright-adopt config "
            "(or it is malformed), nothing to backfill"
        ),
        "added_phases": [],
        "skipped_phases": [],
        "dry_run": False,
    }
    # Untouched on disk.
    assert "phase_tasks" not in json.loads((project / RUN_CONFIG_NAME).read_text())


# ---------------------------------------------------------------------------
# AC3: a real pre-existing adopted config.
# ---------------------------------------------------------------------------


def test_backfills_the_real_leadwright_config(tmp_path: Path) -> None:
    project = tmp_path / "leadwright"
    config_path = _copy_config("leadwright_run_config.json", project)
    before = json.loads(config_path.read_text(encoding="utf-8"))
    assert "phase_tasks" not in before, "fixture must reproduce the pre-s2 gap"

    result = run(project, dry_run=False)

    assert result["success"] is True
    assert result["applicable"] is True
    assert result["written"] is True
    assert sorted(result["added_phases"]) == sorted(["project", "plan", "build", "test"])
    assert result["skipped_phases"] == []

    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert {t["phase"] for t in after["phase_tasks"]} == {"project", "plan", "build", "test"}
    # Every other field survives byte-for-byte (only phase_tasks[] was added).
    for key, value in before.items():
        assert after[key] == value, f"backfill must not touch {key!r}"


def test_backfilling_the_real_leadwright_config_twice_is_a_no_op(tmp_path: Path) -> None:
    project = tmp_path / "leadwright"
    config_path = _copy_config("leadwright_run_config.json", project)

    first = run(project, dry_run=False)
    text_after_first = config_path.read_text(encoding="utf-8")
    mtime_after_first = config_path.stat().st_mtime_ns

    second = run(project, dry_run=False)
    text_after_second = config_path.read_text(encoding="utf-8")

    assert first["added_phases"] != []
    assert second["added_phases"] == []
    assert second["written"] is False
    assert text_after_second == text_after_first
    # The file must not even be touched (no rewrite), not merely
    # byte-identical after a rewrite -- proves "changes nothing" (AC2), not
    # just "converges".
    assert config_path.stat().st_mtime_ns == mtime_after_first


def test_a_second_run_never_calls_the_write_primitive_at_all(
    tmp_path: Path, monkeypatch
) -> None:
    """External code review, s2b: an mtime check alone can pass spuriously
    on coarse-mtime filesystems even if the implementation rewrites the
    file. This proves the structural guarantee directly -- ``run()``
    returns before ever reaching the actual write call when there is
    nothing to add. Monkeypatches ``durable_atomic_write`` (the primitive
    the doubt-review's lock fix switched writes to), not ``Path.write_text``
    -- the original version of this test targeted ``write_text``, which the
    code no longer calls on ANY run once that switch landed, making the
    monkeypatch never trigger either way (re-verification code review,
    s2b PR #701 gate)."""
    project = tmp_path / "leadwright"
    _copy_config("leadwright_run_config.json", project)

    run(project, dry_run=False)  # first run: real backfill, real write

    def _forbidden_write(*args, **kwargs):
        raise AssertionError("durable_atomic_write called during a no-op run")

    monkeypatch.setattr(backfill_cli, "durable_atomic_write", _forbidden_write)
    second = run(project, dry_run=False)  # second run: must not write
    assert second["written"] is False


def test_a_config_with_adoption_null_does_not_crash(tmp_path: Path) -> None:
    """External code review, s2b: ``"adoption": null`` passes a bare
    ``"adoption" in run_config`` guard but is not a usable object -- must
    resolve to 'not applicable', never an uncaught AttributeError."""
    project = tmp_path / "malformed"
    project.mkdir()
    (project / RUN_CONFIG_NAME).write_text(
        json.dumps({"completed_steps": ["project"], "adoption": None}),
        encoding="utf-8",
    )

    result = run(project, dry_run=False)

    assert result["applicable"] is False
    assert "phase_tasks" not in json.loads((project / RUN_CONFIG_NAME).read_text())


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    project = tmp_path / "leadwright"
    config_path = _copy_config("leadwright_run_config.json", project)

    result = run(project, dry_run=True)

    assert result["written"] is False
    assert sorted(result["added_phases"]) == sorted(["project", "plan", "build", "test"])
    assert "phase_tasks" not in json.loads(config_path.read_text(encoding="utf-8"))


def test_seeded_entries_use_the_original_adoption_timestamp(tmp_path: Path) -> None:
    """Backfilled entries should read as having happened at adoption time,
    not at backfill time -- the only honest timestamp available for work
    that predates this tool."""
    project = tmp_path / "leadwright"
    config_path = _copy_config("leadwright_run_config.json", project)

    run(project, dry_run=False)

    after = json.loads(config_path.read_text(encoding="utf-8"))
    for task in after["phase_tasks"]:
        assert task["createdAt"] == after["adoption"]["adopted_at"]
        assert task["completedAt"] == after["adoption"]["adopted_at"]


# ---------------------------------------------------------------------------
# Boundary Probe: the real leadwright config, backfilled, read by the real
# dashboard phase strip (mermaid.py, ADR-045 file-path load).
# ---------------------------------------------------------------------------


def _load_mermaid():
    repo_root = Path(__file__).resolve().parents[3]
    mod_path = (
        repo_root / "plugins" / "shipwright-compliance" / "scripts" / "lib" / "mermaid.py"
    )
    spec = importlib.util.spec_from_file_location("mermaid_leadwright_probe", mod_path)
    assert spec is not None and spec.loader is not None
    mermaid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mermaid)
    return mermaid


def test_backfilled_leadwright_config_renders_complete_not_pending(tmp_path: Path) -> None:
    project = tmp_path / "leadwright"
    config_path = _copy_config("leadwright_run_config.json", project)
    run(project, dry_run=False)
    after = json.loads(config_path.read_text(encoding="utf-8"))

    mermaid = _load_mermaid()
    for phase in ("project", "plan", "build", "test"):
        status = mermaid._get_phase_status(phase, "in_progress", {"run": after})
        assert status == "complete", (
            f"leadwright phase {phase!r} read as {status!r} after backfill"
        )
