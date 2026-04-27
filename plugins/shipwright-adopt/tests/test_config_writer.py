"""Unit tests for config_writer.write_all."""

import json
from pathlib import Path

from lib.config_writer import write_all


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
    # All 6 files exist
    for p in paths:
        assert p.exists()
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
    # Still the 5 mandatory configs
    assert len(paths) == 5


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
