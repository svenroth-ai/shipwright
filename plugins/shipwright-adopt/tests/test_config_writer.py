"""Unit tests for config_writer.write_all."""

import json
from pathlib import Path

from lib.config_writer import write_all, write_iterate_config


def test_writes_all_configs_in_order(tmp_path: Path) -> None:
    paths = write_all(
        tmp_path,
        scope="full_app",
        profile="supabase-nextjs",
        split_name="01-adopted",
        plugin_version="0.1.0",
        dev_url="http://localhost:3000",
        test_cmd="npx vitest run",
        commit_sha="abc123",
        features_inferred=7,
        nested_excluded=["webui"],
        fr_count=7,
        qr_count=2,
    )
    # Run config must be last
    assert paths[-1].name == "shipwright_run_config.json"
    # All 7 files exist (project/plan/build/iterate/compliance/sync/run)
    for p in paths:
        assert p.exists()
    # iterate config sits between build and compliance, before run
    written_names = [p.name for p in paths]
    assert "shipwright_iterate_config.json" in written_names
    assert written_names.index("shipwright_iterate_config.json") < written_names.index(
        "shipwright_run_config.json"
    )
    # Validate JSON shapes
    run_config = json.loads((tmp_path / "shipwright_run_config.json").read_text())
    assert run_config["status"] == "complete"
    assert run_config["current_step"] is None
    assert run_config["completed_steps"] == ["project", "plan", "build", "test"]
    assert run_config["adoption"]["features_inferred"] == 7
    assert run_config["adoption"]["nested_excluded"] == ["webui"]
    assert run_config["phase_history"]["test"][0]["outcome"] == "adopted-skipped"
    assert run_config["phase_history"]["build"][0]["outcome"] == "adopted"

    # Iterate-history file-per-iterate refactor: fresh adopted projects
    # start with the new store + a migration-state stamp that tells the
    # append tool no first-touch migration is needed.
    assert run_config["iterate_history"] == []
    assert run_config["_iterate_migration_state"] == "complete"
    assert run_config["_iterate_migration_quarantined_count"] == 0

    iterates_dir = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    assert iterates_dir.is_dir()
    assert (iterates_dir / ".gitkeep").exists()
    assert (iterates_dir / "_quarantine" / ".gitkeep").exists()
    assert (iterates_dir / "_meta" / ".gitkeep").exists()

    # CHANGELOG-unreleased.d/ carries one .gitkeep per Keep-a-Changelog
    # category so a fresh clone tracks the structure without a first drop.
    for category in ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"):
        gitkeep = tmp_path / "CHANGELOG-unreleased.d" / category / ".gitkeep"
        assert gitkeep.exists(), f"missing .gitkeep in {category}"

    project_config = json.loads((tmp_path / "shipwright_project_config.json").read_text())
    assert project_config["splits"][0]["name"] == "01-adopted"
    assert project_config["requirements"]["fr_count"] == 7

    build_config = json.loads((tmp_path / "shipwright_build_config.json").read_text())
    assert build_config["status"] == "adopted"
    assert build_config["sections"][0]["name"] == "adopted-baseline"
    assert build_config["sections"][0]["commit"] == "abc123"


def test_no_sync_skips_sync_config(tmp_path: Path) -> None:
    paths = write_all(
        tmp_path,
        scope="library", profile="generic", split_name="01-adopted",
        plugin_version="0.1.0", dev_url=None, test_cmd=None, commit_sha=None,
        features_inferred=0, nested_excluded=[],
        fr_count=0, qr_count=0, write_sync=False,
    )
    sync = tmp_path / "shipwright_sync_config.json"
    assert not sync.exists()
    # Still the 6 mandatory configs (project + plan + build + iterate + compliance + run)
    assert len(paths) == 6


def test_iterate_config_written_with_documented_schema(tmp_path: Path) -> None:
    """write_all must emit shipwright_iterate_config.json with the schema
    documented in iteration-reviews.md (external_review.feedback_iterations
    + external_code_review.enabled). Defaults are conservative:
    feedback_iterations=0 (matches plan-config opt-out), code-review
    cascade enabled=true (cascade runs, user can flip off).
    """
    write_all(
        tmp_path,
        scope="full_app", profile="supabase-nextjs", split_name="01-adopted",
        plugin_version="0.1.0", dev_url=None, test_cmd=None, commit_sha=None,
        features_inferred=0, nested_excluded=[],
        fr_count=0, qr_count=0,
    )
    iterate_path = tmp_path / "shipwright_iterate_config.json"
    assert iterate_path.exists(), "shipwright_iterate_config.json must be written by adopt"

    iterate = json.loads(iterate_path.read_text(encoding="utf-8"))

    # Schema: external_review.feedback_iterations (controls plan/iterate-mode review)
    assert "external_review" in iterate
    assert iterate["external_review"]["feedback_iterations"] == 0

    # Schema: external_code_review.enabled (controls code-review cascade — independent gate)
    assert "external_code_review" in iterate
    assert iterate["external_code_review"]["enabled"] is True

    # Provenance marker so tooling can tell adopt-seeded configs apart from
    # /shipwright-iterate hand-edited ones.
    assert iterate.get("seeded_by_adopt") is True
    assert "updated_at" in iterate


def test_iterate_config_round_trip_producer_consumer(tmp_path: Path) -> None:
    """Boundary Probe: producer (write_iterate_config) -> file on disk ->
    consumer (json.loads) round-trip. Asserts the file is valid JSON, the
    documented keys round-trip without mutation, and all values keep their
    types (boolean stays boolean, int stays int, ISO string stays string).
    """
    iterate_path = write_iterate_config(tmp_path)
    raw = iterate_path.read_text(encoding="utf-8")

    # Produce -> file on disk -> consumer parse
    parsed = json.loads(raw)

    # Round-trip identity: re-serialize, re-parse, deep-equal
    re_serialized = json.dumps(parsed, indent=2) + "\n"
    re_parsed = json.loads(re_serialized)
    assert re_parsed == parsed

    # Type fidelity (the root of most boundary bugs):
    assert isinstance(parsed["external_review"]["feedback_iterations"], int)
    assert isinstance(parsed["external_code_review"]["enabled"], bool)
    assert isinstance(parsed["seeded_by_adopt"], bool)
    assert isinstance(parsed["updated_at"], str)

    # No accidental BOM or trailing junk
    assert not raw.startswith("﻿"), "config must be UTF-8 without BOM"
    assert raw.endswith("\n"), "config must terminate with a single newline"


def test_iterate_config_idempotent_overwrite(tmp_path: Path) -> None:
    """Calling write_iterate_config twice produces the same shape with a
    refreshed updated_at. No accidental schema drift between writes.
    """
    p1 = write_iterate_config(tmp_path)
    first = json.loads(p1.read_text(encoding="utf-8"))

    p2 = write_iterate_config(tmp_path)
    second = json.loads(p2.read_text(encoding="utf-8"))

    assert p1 == p2
    # Same keys + types, only updated_at may differ
    assert set(first.keys()) == set(second.keys())
    assert first["external_review"] == second["external_review"]
    assert first["external_code_review"] == second["external_code_review"]
    assert first["seeded_by_adopt"] == second["seeded_by_adopt"]


def test_custom_completed_steps(tmp_path: Path) -> None:
    write_all(
        tmp_path,
        scope="full_app", profile="supabase-nextjs", split_name="01-adopted",
        plugin_version="0.1.0", dev_url=None, test_cmd=None, commit_sha=None,
        features_inferred=3, nested_excluded=[],
        fr_count=3, qr_count=0,
        completed_steps=["project", "plan", "build"],  # no test
    )
    run_config = json.loads((tmp_path / "shipwright_run_config.json").read_text())
    assert run_config["completed_steps"] == ["project", "plan", "build"]
    assert "test" not in run_config["phase_history"]
