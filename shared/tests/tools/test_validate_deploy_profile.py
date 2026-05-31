"""Tests for shared.scripts.lib.deploy_profile_validator + the CLI wrapper.

Library-level tests use validate() directly (fast, in-process).
CLI-level tests are kept sparing — happy path + handful of error paths via
in-process main() with patched argv. One subprocess test covers
end-to-end-ness (the script is reachable as a uv entry point).
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.scripts.lib.deploy_profile_validator import (  # noqa: E402
    validate,
)
from shared.scripts.tools import validate_deploy_profile as cli_module  # noqa: E402

SCHEMA_PATH = REPO_ROOT / "shared" / "profiles" / "deploy-profile.schema.json"
PROFILES_DIR = REPO_ROOT / "shared" / "profiles" / "deploy"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def jelastic_profile() -> dict:
    return json.loads((PROFILES_DIR / "jelastic.json").read_text(encoding="utf-8"))


@pytest.fixture
def vercel_profile() -> dict:
    return json.loads((PROFILES_DIR / "vercel.json").read_text(encoding="utf-8"))


@pytest.fixture
def compose_profile() -> dict:
    return json.loads((PROFILES_DIR / "compose-vps.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Library-level tests (fast, in-process)                                       #
# --------------------------------------------------------------------------- #


class TestRealProfilesAreValid:
    """AC-12 (a): all three real profiles pass via validate() directly."""

    def test_jelastic_valid(self, jelastic_profile, schema):
        assert validate(jelastic_profile, schema) == []

    def test_vercel_valid(self, vercel_profile, schema):
        assert validate(vercel_profile, schema) == []

    def test_compose_valid(self, compose_profile, schema):
        assert validate(compose_profile, schema) == []


class TestStructuralViolations:
    """JSON-Schema-level errors."""

    def test_missing_required_field(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        del broken["target_id"]
        errors = validate(broken, schema)
        assert any("target_id" in e.message for e in errors), errors

    def test_additional_property_at_root(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["unknown_field"] = "should fail"
        errors = validate(broken, schema)
        assert any("unknown_field" in e.message or "Additional" in e.message for e in errors)

    def test_env_var_name_violates_regex(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["auth"]["required_env_vars"][0]["name"] = "lowercase_name"
        errors = validate(broken, schema)
        assert errors, "expected regex violation"

    def test_empty_string_in_required_string_field(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["description"] = ""
        errors = validate(broken, schema)
        assert any("minLength" in e.message or "description" in (e.json_pointer or "")
                   for e in errors)

    def test_migrations_supported_false_with_strategy_fields_fails(self, vercel_profile, schema):
        broken = copy.deepcopy(vercel_profile)
        broken["migrations"] = {"supported": False, "dev_strategy": "auto-apply"}
        errors = validate(broken, schema)
        assert errors, "expected if/then violation when supported=false carries strategy fields"

    def test_extra_environment_via_pattern_properties_passes(self, jelastic_profile, schema):
        """environments.staging is allowed via patternProperties."""
        extended = copy.deepcopy(jelastic_profile)
        extended["environments"]["staging"] = {
            "url_pattern": "staging-{project}.jpc.infomaniak.com",
            "confirmation": "user",
        }
        assert validate(extended, schema) == []

    def test_environment_name_with_uppercase_rejected(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["environments"]["Staging"] = {
            "url_pattern": "staging.example.com",
            "confirmation": "user",
        }
        errors = validate(broken, schema)
        assert errors, "PascalCase env-name should be rejected by patternProperties + additionalProperties:false"

    def test_dollar_schema_field_accepted(self, jelastic_profile, schema):
        """`$schema` at profile root must NOT be flagged as unknown."""
        # Real profiles already have $schema; just ensure modifying it is OK
        modified = copy.deepcopy(jelastic_profile)
        modified["$schema"] = "../deploy-profile.schema.json"
        assert validate(modified, schema) == []

    def test_known_gaps_field_accepted(self, vercel_profile, schema):
        """known_gaps is optional but real Vercel stub uses it — must validate."""
        # Vercel profile already declares known_gaps; ensure removing it still passes
        without_gaps = copy.deepcopy(vercel_profile)
        del without_gaps["known_gaps"]
        assert validate(without_gaps, schema) == []


class TestSemanticViolations:
    """Cross-field invariants enforced by validator's semantic-check layer."""

    def test_shipped_with_null_client_fails(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["client"] = None
        errors = validate(broken, schema)
        assert any("shipped profiles must declare a non-null client" in e.message
                   or "client" in (e.json_pointer or "") for e in errors)

    def test_shipped_with_documented_confidence_fails(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["confidence"] = "documented"
        errors = validate(broken, schema)
        assert any("verified" in e.message for e in errors)

    def test_stub_with_verified_confidence_fails(self, vercel_profile, schema):
        broken = copy.deepcopy(vercel_profile)
        broken["confidence"] = "verified"
        errors = validate(broken, schema)
        assert any("verified" in e.message and "stub" in e.message
                   for e in errors)

    def test_stub_with_non_null_client_fails(self, vercel_profile, schema):
        broken = copy.deepcopy(vercel_profile)
        broken["client"] = {"entrypoint": "x.py", "runner": "python"}
        errors = validate(broken, schema)
        assert errors, "stub with non-null client must fail (allOf rule)"

    def test_filename_target_id_mismatch_fails(self, tmp_path, jelastic_profile, schema):
        wrong_path = tmp_path / "wrongname.json"
        wrong_path.write_text(json.dumps(jelastic_profile))
        errors = validate(jelastic_profile, schema, profile_path=wrong_path)
        assert any("filename stem" in e.message for e in errors)

    def test_duplicate_target_id_in_all_mode_fails(self, tmp_path, jelastic_profile, schema):
        seen: set[str] = set()
        first_path = tmp_path / "jelastic.json"
        first_path.write_text(json.dumps(jelastic_profile))
        errors_first = validate(jelastic_profile, schema, profile_path=first_path,
                                known_target_ids=seen)
        assert errors_first == []
        # Second profile with the same target_id but a different filename
        second_profile = copy.deepcopy(jelastic_profile)
        second_path = tmp_path / "jelastic-copy.json"
        second_path.write_text(json.dumps(second_profile))
        errors_second = validate(second_profile, schema, profile_path=second_path,
                                 known_target_ids=seen)
        # Will fail filename mismatch AND duplicate target_id; we only need duplicate flag
        assert any("duplicate target_id" in e.message for e in errors_second)

    def test_duplicate_env_var_within_required_list_fails(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["auth"]["required_env_vars"].append(
            {"name": "JELASTIC_TOKEN", "description": "duplicate"}
        )
        errors = validate(broken, schema)
        assert any("duplicate env-var name" in e.message for e in errors)

    def test_duplicate_env_var_across_required_and_optional_fails(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["auth"]["optional_env_vars"].append(
            {"name": "JELASTIC_TOKEN", "description": "duplicate"}
        )
        errors = validate(broken, schema)
        assert any("duplicate env-var name" in e.message for e in errors)

    def test_absolute_client_entrypoint_fails(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["client"]["entrypoint"] = "/absolute/path/client.py"
        errors = validate(broken, schema)
        assert any("absolute" in e.message for e in errors)

    def test_windows_absolute_client_entrypoint_fails(self, jelastic_profile, schema):
        """Windows-style drive-letter paths must also be rejected as absolute."""
        broken = copy.deepcopy(jelastic_profile)
        broken["client"]["entrypoint"] = "C:\\windows\\absolute\\client.py"
        errors = validate(broken, schema)
        assert any("absolute" in e.message for e in errors)

    def test_backslash_root_client_entrypoint_fails(self, jelastic_profile, schema):
        """Bare-backslash leading paths (e.g. \\share) must also be rejected."""
        broken = copy.deepcopy(jelastic_profile)
        broken["client"]["entrypoint"] = "\\share\\path\\client.py"
        errors = validate(broken, schema)
        assert any("absolute" in e.message for e in errors)

    def test_traversal_in_client_entrypoint_fails(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["client"]["entrypoint"] = "../escape/client.py"
        errors = validate(broken, schema)
        assert any(".." in e.message or "traversal" in e.message for e in errors)

    def test_strict_with_valid_path_passes(self, jelastic_profile, schema):
        """The shipped Jelastic profile's entrypoint exists in the real repo."""
        errors = validate(
            jelastic_profile,
            schema,
            strict=True,
            repo_root=REPO_ROOT,
        )
        assert errors == []

    def test_strict_with_bogus_path_fails(self, jelastic_profile, schema):
        broken = copy.deepcopy(jelastic_profile)
        broken["client"]["entrypoint"] = "plugins/non-existent/client.py"
        errors = validate(broken, schema, strict=True, repo_root=REPO_ROOT)
        assert any("does not resolve to a file" in e.message for e in errors)


# --------------------------------------------------------------------------- #
# CLI-level tests (in-process main(), sparing)                                 #
# --------------------------------------------------------------------------- #


class TestCLIInProcess:
    """Run the CLI's main() directly with patched argv to avoid subprocess overhead."""

    def test_all_happy_path(self, capsys):
        rc = cli_module.main(["--all"])
        out = capsys.readouterr()
        assert rc == 0, out
        assert "All profiles valid." in out.out

    def test_profile_happy_path(self, capsys):
        rc = cli_module.main(["--profile", str(PROFILES_DIR / "jelastic.json")])
        out = capsys.readouterr()
        assert rc == 0, out

    def test_profile_and_all_combined_is_usage_error(self):
        with pytest.raises(SystemExit) as exc_info:
            cli_module.main(["--profile", "x.json", "--all"])
        assert exc_info.value.code == 2

    def test_neither_profile_nor_all(self):
        with pytest.raises(SystemExit) as exc_info:
            cli_module.main([])
        assert exc_info.value.code == 2

    def test_nonexistent_profile_exits_1(self, capsys, tmp_path):
        rc = cli_module.main(["--profile", str(tmp_path / "missing.json")])
        out = capsys.readouterr()
        assert rc == 1
        assert "profile not found" in out.err

    def test_malformed_json_exits_1(self, capsys, tmp_path):
        bad = tmp_path / "broken.json"
        bad.write_text("{not valid json")
        rc = cli_module.main(["--profile", str(bad)])
        out = capsys.readouterr()
        assert rc == 1
        assert "malformed JSON" in out.err

    def test_empty_profiles_dir_exits_0(self, capsys, tmp_path):
        empty_dir = tmp_path / "empty-deploy"
        empty_dir.mkdir()
        rc = cli_module.main(["--all", "--profiles-dir", str(empty_dir)])
        out = capsys.readouterr()
        assert rc == 0
        assert "no profile files" in out.err

    def test_strict_passes_against_real_repo(self, capsys):
        rc = cli_module.main(["--all", "--strict"])
        out = capsys.readouterr()
        assert rc == 0, out

    def test_skips_dot_files_and_schema_files(self, capsys, tmp_path):
        """--all is non-recursive, skips hidden + *.schema.json."""
        d = tmp_path / "isolated"
        d.mkdir()
        # Place one valid profile + decoys
        valid = json.loads((PROFILES_DIR / "vercel.json").read_text(encoding="utf-8"))
        (d / "vercel.json").write_text(json.dumps(valid))
        (d / ".hidden.json").write_text("{}")
        (d / "fake.schema.json").write_text("{}")
        sub = d / "sub"
        sub.mkdir()
        (sub / "nested.json").write_text("{}")
        rc = cli_module.main(["--all", "--profiles-dir", str(d)])
        out = capsys.readouterr()
        assert rc == 0, out


# --------------------------------------------------------------------------- #
# Subprocess test (one — ensures the script is reachable as a CLI entrypoint)  #
# --------------------------------------------------------------------------- #


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    uv_bin = shutil.which("uv")
    if uv_bin is None:
        pytest.skip("uv not available")
    return subprocess.run(
        [uv_bin, "run", "shared/scripts/tools/validate_deploy_profile.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.slow
def test_subprocess_all_exits_zero():
    result = _run_cli(["--all"])
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    assert "All profiles valid." in result.stdout


@pytest.mark.slow
def test_subprocess_malformed_json_exits_one(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not valid json")
    result = _run_cli(["--profile", str(bad)])
    assert result.returncode == 1, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    assert "malformed JSON" in result.stderr


@pytest.mark.slow
def test_subprocess_nonexistent_path_exits_one(tmp_path):
    missing = tmp_path / "absent.json"
    result = _run_cli(["--profile", str(missing)])
    assert result.returncode == 1, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    assert "profile not found" in result.stderr


@pytest.mark.slow
def test_subprocess_profile_and_all_combined_exits_two():
    result = _run_cli(["--profile", "x.json", "--all"])
    assert result.returncode == 2, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    # argparse usage error message
    assert "not allowed with" in result.stderr or "usage" in result.stderr.lower()
