"""Tests for sync_release_manifests.py's ``sync()`` orchestration — no-op,
write, multi-manifest, preflight failures, dry-run, and mid-sequence
rollback. Config/path/parsing primitives are covered directly against
lib.manifest_sync_core in shared/scripts/tests/test_manifest_sync_core.py.
Git-integration scenarios (staging, verify-commit, dirty-check) live in
test_sync_release_manifests_git.py, which needs a real repo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools.sync_release_manifests import main, sync, verify_commit  # noqa: E402


def _write_config(root: Path, entries: list[dict] | None) -> None:
    body = {} if entries is None else {"published_manifests": entries}
    (root / "shipwright_changelog_config.json").write_text(json.dumps(body), encoding="utf-8")


def _write_manifest(path: Path, extra: dict | None = None, version: str = "0.1.0") -> None:
    body = {"name": "pkg", "version": version, **(extra or {})}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def test_sync_no_config_is_ok_noop(tmp_path):
    result = sync(tmp_path, "1.0.0", dry_run=False, stage=False)
    assert result == {
        "status": "ok", "version": "1.0.0", "manifests": [],
        "note": "no published manifests declared",
    }


def test_sync_no_config_with_stage_reports_empty_pathspec(tmp_path):
    """Step 6 reads manifest_pathspec unconditionally when --stage was
    passed; a no-manifests project must return [] rather than omit the
    key, or a caller that expects the documented field errors instead of
    seeing a clean no-op."""
    result = sync(tmp_path, "1.0.0", dry_run=False, stage=True)
    assert result["manifest_pathspec"] == []


def test_sync_one_manifest_write(tmp_path):
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(tmp_path / "package.json", version="0.1.0")

    result = sync(tmp_path, "0.2.0", dry_run=False, stage=False)

    assert result["status"] == "ok"
    assert result["manifests"] == [
        {"path": "package.json", "format": "package_json", "changed": True, "reformatted": False}
    ]
    assert json.loads((tmp_path / "package.json").read_text())["version"] == "0.2.0"


def test_sync_several_manifests_mixed_initial_versions(tmp_path):
    _write_config(
        tmp_path,
        [
            {"path": "a/package.json", "format": "package_json"},
            {"path": "b/package.json", "format": "package_json"},
        ],
    )
    _write_manifest(tmp_path / "a" / "package.json", version="0.1.0")
    _write_manifest(tmp_path / "b" / "package.json", version="0.5.0")  # already current

    result = sync(tmp_path, "0.5.0", dry_run=False, stage=False)

    assert result["status"] == "ok"
    by_path = {m["path"]: m for m in result["manifests"]}
    assert by_path["a/package.json"]["changed"] is True
    assert by_path["b/package.json"]["changed"] is False
    assert json.loads((tmp_path / "a" / "package.json").read_text())["version"] == "0.5.0"


def test_sync_idempotent_rerun_no_write(tmp_path):
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    manifest = tmp_path / "package.json"
    _write_manifest(manifest, version="0.5.0")
    before_mtime = manifest.stat().st_mtime_ns

    result = sync(tmp_path, "0.5.0", dry_run=False, stage=False)

    assert result["manifests"][0]["changed"] is False
    assert manifest.stat().st_mtime_ns == before_mtime


def test_sync_missing_file_fails_closed(tmp_path):
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    result = sync(tmp_path, "1.0.0", dry_run=False, stage=False)
    assert result["status"] == "manifest_missing"
    assert result["path"] == "package.json"


def test_sync_unsupported_format_fails_closed(tmp_path):
    _write_config(tmp_path, [{"path": "Cargo.toml", "format": "cargo_toml"}])
    (tmp_path / "Cargo.toml").write_text("[package]\nversion = \"0.1.0\"\n", encoding="utf-8")
    result = sync(tmp_path, "1.0.0", dry_run=False, stage=False)
    assert result["status"] == "unsupported_format"


def test_sync_missing_version_field_fails_closed_disk_untouched(tmp_path):
    _write_config(
        tmp_path,
        [
            {"path": "a/package.json", "format": "package_json"},
            {"path": "b/package.json", "format": "package_json"},
        ],
    )
    _write_manifest(tmp_path / "a" / "package.json", version="0.1.0")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "package.json").write_text(json.dumps({"private": True}), encoding="utf-8")

    result = sync(tmp_path, "1.0.0", dry_run=False, stage=False)

    assert result["status"] == "missing_version_field"
    assert result["path"] == "b/package.json"
    # Two-phase: b failed preflight, so the write phase never started and a
    # (whose own preflight had already succeeded) was never touched.
    assert json.loads((tmp_path / "a" / "package.json").read_text())["version"] == "0.1.0"


def test_sync_invalid_version_argument_touches_nothing(tmp_path):
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(tmp_path / "package.json", version="0.1.0")
    result = sync(tmp_path, "v1.0.0", dry_run=False, stage=False)
    assert result["status"] == "invalid_version_argument"
    assert json.loads((tmp_path / "package.json").read_text())["version"] == "0.1.0"


def test_sync_dry_run_reports_without_writing(tmp_path):
    manifest = tmp_path / "package.json"
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(manifest, version="0.1.0")
    before = manifest.read_bytes()

    result = sync(tmp_path, "0.2.0", dry_run=True, stage=False)

    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert result["manifests"][0]["changed"] is True
    assert manifest.read_bytes() == before
    assert "manifest_pathspec" not in result  # --stage wasn't passed at all


def test_sync_dry_run_with_stage_reports_empty_pathspec(tmp_path):
    """--dry-run --stage together must not be the one combination where a
    caller reading the documented manifest_pathspec field gets a KeyError:
    the key is present whenever --stage was requested, dry-run or not."""
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(tmp_path / "package.json", version="0.1.0")

    result = sync(tmp_path, "0.2.0", dry_run=True, stage=True)

    assert result["status"] == "ok"
    assert result["manifest_pathspec"] == []  # nothing was actually staged


def test_sync_mid_sequence_write_failure_restores_earlier_manifests(tmp_path, monkeypatch):
    _write_config(
        tmp_path,
        [
            {"path": "a/package.json", "format": "package_json"},
            {"path": "b/package.json", "format": "package_json"},
        ],
    )
    _write_manifest(tmp_path / "a" / "package.json", version="0.1.0")
    _write_manifest(tmp_path / "b" / "package.json", version="0.1.0")

    import scripts.tools.sync_release_manifests as mod

    real_write = mod.durable_atomic_write
    calls = {"n": 0}

    def flaky_write(path, data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated disk failure")
        real_write(path, data)

    monkeypatch.setattr(mod, "durable_atomic_write", flaky_write)

    a_before = (tmp_path / "a" / "package.json").read_bytes()
    b_before = (tmp_path / "b" / "package.json").read_bytes()

    result = sync(tmp_path, "0.2.0", dry_run=False, stage=False)

    assert result["status"] == "write_failed"
    assert (tmp_path / "a" / "package.json").read_bytes() == a_before
    assert (tmp_path / "b" / "package.json").read_bytes() == b_before


def test_main_exits_zero_on_ok_and_writes_result_file(tmp_path, capsys):
    """The SKILL.md Step 6 `&&`-chain before `git tag` depends entirely on
    this process exit code — a 0/1 mismatch here would silently break the
    fail-closed gate regardless of what sync()/verify_commit() return."""
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(tmp_path / "package.json", version="0.1.0")
    result_file = tmp_path / "result.json"

    exit_code = main(
        ["--project-root", str(tmp_path), "--version", "0.2.0", "--result-file", str(result_file)]
    )

    assert exit_code == 0
    written = json.loads(result_file.read_text())
    assert written["status"] == "ok"
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "ok"


def test_main_exits_nonzero_on_failure(tmp_path, capsys):
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    # File never created -> manifest_missing.

    exit_code = main(["--project-root", str(tmp_path), "--version", "0.2.0"])

    assert exit_code == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "manifest_missing"


def test_main_verify_commit_requires_result_file(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        main(["--project-root", str(tmp_path), "--version", "0.2.0", "--verify-commit", "deadbeef"])
    assert exc_info.value.code == 2


def test_main_relative_result_file_resolves_against_project_root(tmp_path):
    """Doubt-reviewer D6: a relative --result-file must resolve against
    --project-root, not the process's CWD (which need not coincide)."""
    _write_config(tmp_path, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(tmp_path / "package.json", version="0.1.0")

    exit_code = main(
        ["--project-root", str(tmp_path), "--version", "0.2.0", "--result-file", "relative_result.json"]
    )

    assert exit_code == 0
    assert (tmp_path / "relative_result.json").is_file()


def test_verify_commit_rejects_non_dict_result_file(tmp_path):
    """Doubt-reviewer D3: a --result-file that parses as valid JSON but
    isn't an object (e.g. a bare list) must fail closed with well-formed
    JSON, not an AttributeError traceback from recorded.get(...)."""
    result_file = tmp_path / "result.json"
    result_file.write_text("[]", encoding="utf-8")
    result = verify_commit(tmp_path, "deadbeef", "0.2.0", result_file)
    assert result["status"] == "result_file_invalid"


def test_verify_commit_rejects_dry_run_result_file(tmp_path):
    """Doubt-reviewer D6: a --result-file recording a --dry-run sync must
    never be trusted to verify a real release — nothing was staged."""
    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({"status": "ok", "version": "0.2.0", "dry_run": True, "manifests": []}),
        encoding="utf-8",
    )
    result = verify_commit(tmp_path, "deadbeef", "0.2.0", result_file)
    assert result["status"] == "sync_incomplete"


def test_verify_commit_rejects_non_list_manifests_field(tmp_path):
    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({"status": "ok", "version": "0.2.0", "manifests": "not-a-list"}),
        encoding="utf-8",
    )
    result = verify_commit(tmp_path, "deadbeef", "0.2.0", result_file)
    assert result["status"] == "result_file_invalid"


def test_verify_commit_rejects_malformed_manifest_entry(tmp_path):
    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({"status": "ok", "version": "0.2.0", "manifests": [{"path": "package.json"}]}),
        encoding="utf-8",
    )
    result = verify_commit(tmp_path, "deadbeef", "0.2.0", result_file)
    assert result["status"] == "result_file_invalid"
