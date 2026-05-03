"""Tests for shared.scripts.validate_env module."""

import json

import pytest

from shared.scripts.validate_env import init_env_file, parse_env_file, validate


@pytest.fixture
def profile_dir(tmp_path):
    """Create a temporary profile directory with a test profile."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    profile = {
        "name": "test-profile",
        "required_env_vars": {
            "build": [
                {"name": "NEXT_PUBLIC_SUPABASE_URL", "description": "Supabase project URL"},
                {"name": "NEXT_PUBLIC_SUPABASE_ANON_KEY", "description": "Supabase anonymous key"},
            ],
            "deploy": [
                {"name": "JELASTIC_TOKEN", "description": "Jelastic API token"},
                {"name": "SUPABASE_ACCESS_TOKEN", "description": "Supabase CLI token", "optional": True},
            ],
        },
    }
    (profiles / "test-profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return profiles


@pytest.fixture
def project_root(tmp_path):
    """Create a temporary project root with run config."""
    root = tmp_path / "project"
    root.mkdir()
    run_config = {"profile": "test-profile"}
    (root / "shipwright_run_config.json").write_text(json.dumps(run_config), encoding="utf-8")
    return root


class TestParseEnvFile:
    def test_simple_vars(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_quoted_values(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text('KEY="hello world"\nKEY2=\'single\'\n', encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"KEY": "hello world", "KEY2": "single"}

    def test_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text("# comment\n\nKEY=val\n  # indented comment\n", encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"KEY": "val"}

    def test_nonexistent_file(self, tmp_path):
        result = parse_env_file(tmp_path / "missing")
        assert result == {}

    def test_no_equals(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text("INVALID_LINE\nKEY=val\n", encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"KEY": "val"}


class TestValidateBuild:
    def test_all_vars_present(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text(
            "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n"
            "NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGci...\n",
            encoding="utf-8",
        )
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is False
        assert len(result["found"]) == 2
        assert result["missing"] == []
        assert result["env_file_exists"] is True

    def test_missing_vars(self, project_root, profile_dir):
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is False
        assert result["skipped"] is False
        assert len(result["missing"]) == 2
        assert result["missing"][0]["name"] == "NEXT_PUBLIC_SUPABASE_URL"
        assert result["env_file_exists"] is False

    def test_partial_vars(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text("NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n", encoding="utf-8")
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is False
        assert len(result["found"]) == 1
        assert len(result["missing"]) == 1
        assert result["missing"][0]["name"] == "NEXT_PUBLIC_SUPABASE_ANON_KEY"

    def test_vars_from_os_environ(self, project_root, profile_dir, monkeypatch):
        monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "eyJhbGci...")
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is True
        assert len(result["found"]) == 2


class TestValidateDeploy:
    def test_required_deploy_var_present(self, project_root, profile_dir, monkeypatch):
        monkeypatch.setenv("JELASTIC_TOKEN", "abc123")
        result = validate(project_root, "deploy", profile_dir)
        assert result["success"] is True
        assert "JELASTIC_TOKEN" in result["found"]
        assert len(result["optional_missing"]) == 1
        assert result["optional_missing"][0]["name"] == "SUPABASE_ACCESS_TOKEN"

    def test_missing_required_deploy_var(self, project_root, profile_dir, monkeypatch):
        monkeypatch.delenv("JELASTIC_TOKEN", raising=False)
        result = validate(project_root, "deploy", profile_dir)
        assert result["success"] is False
        assert len(result["missing"]) == 1
        assert result["missing"][0]["name"] == "JELASTIC_TOKEN"

    def test_all_deploy_vars_present(self, project_root, profile_dir, monkeypatch):
        monkeypatch.setenv("JELASTIC_TOKEN", "abc123")
        monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "sbp_token")
        result = validate(project_root, "deploy", profile_dir)
        assert result["success"] is True
        assert result["optional_missing"] == []
        assert len(result["found"]) == 2


class TestSkipConditions:
    def test_no_run_config(self, tmp_path, profile_dir):
        project = tmp_path / "empty_project"
        project.mkdir()
        result = validate(project, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is True
        assert "No shipwright_run_config.json" in result["skip_reason"]

    def test_no_profile_in_config(self, tmp_path, profile_dir):
        project = tmp_path / "no_profile"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
        result = validate(project, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is True
        assert "No profile set" in result["skip_reason"]

    def test_missing_profile_file(self, tmp_path, profile_dir):
        project = tmp_path / "bad_profile"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "nonexistent"}), encoding="utf-8"
        )
        result = validate(project, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is True
        assert "not found" in result["skip_reason"]

    def test_no_required_env_vars_for_phase(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "empty.json").write_text(json.dumps({"name": "empty"}), encoding="utf-8")
        project = tmp_path / "proj"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "empty"}), encoding="utf-8"
        )
        result = validate(project, "build", profiles)
        assert result["success"] is True
        assert result["skipped"] is True


class TestInitEnvFile:
    def test_creates_env_local_when_missing(self, project_root, profile_dir):
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "created"
        assert result["profile"] == "test-profile"
        assert "NEXT_PUBLIC_SUPABASE_URL" in result["vars"]
        assert "NEXT_PUBLIC_SUPABASE_ANON_KEY" in result["vars"]

        env_file = project_root / ".env.local"
        assert env_file.exists()
        content = env_file.read_text(encoding="utf-8")
        assert "# NEXT_PUBLIC_SUPABASE_URL=" in content
        assert "# NEXT_PUBLIC_SUPABASE_ANON_KEY=" in content
        assert "Supabase project URL" in content
        assert "Profile: test-profile" in content

    def test_appends_missing_vars_to_existing_file(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text(
            "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n",
            encoding="utf-8",
        )
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "updated"
        assert result["added"] == ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]

        content = env_file.read_text(encoding="utf-8")
        assert "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co" in content
        assert "# NEXT_PUBLIC_SUPABASE_ANON_KEY=" in content

    def test_idempotent_when_all_vars_present(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text(
            "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n"
            "NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGci...\n",
            encoding="utf-8",
        )
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "unchanged"

    def test_idempotent_with_commented_vars(self, project_root, profile_dir):
        """Already-commented placeholders count as present."""
        env_file = project_root / ".env.local"
        env_file.write_text(
            "# NEXT_PUBLIC_SUPABASE_URL=        # Supabase project URL\n"
            "# NEXT_PUBLIC_SUPABASE_ANON_KEY=   # Supabase anonymous key\n",
            encoding="utf-8",
        )
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "unchanged"

    def test_creates_for_deploy_phase(self, project_root, profile_dir):
        # Pre-existing test was named ``test_skips_deploy_phase`` and expected
        # ``action=skipped``. That dated to before deploy-phase scaffolding
        # landed (commit 2ae53b4, 2026-03-30); the function has supported deploy
        # vars ever since but the test was never updated. Iterate
        # iterate-2026-05-03-adopt-env-local-scaffold corrects the assertion.
        result = init_env_file(project_root, "deploy", profile_dir)
        assert result["action"] == "created"
        assert "JELASTIC_TOKEN" in result["vars"]

    def test_skips_without_run_config(self, tmp_path, profile_dir):
        project = tmp_path / "empty"
        project.mkdir()
        result = init_env_file(project, "build", profile_dir)
        assert result["action"] == "skipped"

    def test_skips_without_profile(self, tmp_path, profile_dir):
        project = tmp_path / "no_profile"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
        result = init_env_file(project, "build", profile_dir)
        assert result["action"] == "skipped"


# -----------------------------------------------------------------------------
# Iterate 2026-05-03: framework-vars merge + .gitignore hard-stop +
# rich return contract. Tracked under iterate-2026-05-03-adopt-env-local-scaffold.
# -----------------------------------------------------------------------------


class TestFrameworkVarsMerge:
    """`include_framework=True` appends the framework-level LLM review keys
    (OPENROUTER / GEMINI / OPENAI) after profile vars, deduped by name."""

    @pytest.fixture
    def empty_profile_dir(self, tmp_path):
        profiles = tmp_path / "empty_profiles"
        profiles.mkdir()
        (profiles / "empty.json").write_text(
            json.dumps({"name": "empty", "required_env_vars": {
                "build": [], "deploy": [], "plugin": [],
            }}),
            encoding="utf-8",
        )
        return profiles

    @pytest.fixture
    def empty_project(self, tmp_path):
        proj = tmp_path / "empty_project"
        proj.mkdir()
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "empty"}), encoding="utf-8",
        )
        return proj

    def test_framework_vars_added_when_profile_empty(self, empty_project, empty_profile_dir):
        result = init_env_file(
            empty_project, "all", empty_profile_dir, include_framework=True,
        )
        assert result["action"] == "created"
        env_text = (empty_project / ".env.local").read_text(encoding="utf-8")
        assert "OPENROUTER_API_KEY" in env_text
        assert "GEMINI_API_KEY" in env_text
        assert "OPENAI_API_KEY" in env_text
        # Order: OPENROUTER first, then GEMINI, then OPENAI.
        i_or = env_text.index("OPENROUTER_API_KEY")
        i_g = env_text.index("GEMINI_API_KEY")
        i_o = env_text.index("OPENAI_API_KEY")
        assert i_or < i_g < i_o
        # Section label
        assert "Framework / External Review" in env_text

    def test_framework_vars_off_by_default(self, empty_project, empty_profile_dir):
        """include_framework defaults to False to preserve global phase=all
        semantics for the pre-existing `validate_env.py --init` CLI users."""
        result = init_env_file(empty_project, "all", empty_profile_dir)
        # Profile is empty AND framework merge is off → nothing to write
        assert result["action"] == "skipped"
        assert not (empty_project / ".env.local").exists()

    def test_framework_dedup_when_profile_already_lists_key(
        self, tmp_path,
    ):
        """If the profile already has OPENROUTER_API_KEY, framework's copy is
        suppressed and the profile's description wins."""
        profiles = tmp_path / "p"
        profiles.mkdir()
        (profiles / "with_or.json").write_text(json.dumps({
            "name": "with_or",
            "required_env_vars": {
                "build": [],
                "deploy": [],
                "plugin": [
                    {"name": "OPENROUTER_API_KEY",
                     "description": "Profile-specific OpenRouter description (must win)",
                     "optional": True},
                ],
            },
        }), encoding="utf-8")
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "with_or"}), encoding="utf-8",
        )
        init_env_file(proj, "all", profiles, include_framework=True)
        env_text = (proj / ".env.local").read_text(encoding="utf-8")
        # OPENROUTER appears exactly once, with the profile's description.
        assert env_text.count("OPENROUTER_API_KEY") == 1
        assert "Profile-specific OpenRouter description" in env_text
        # Framework GEMINI / OPENAI are still present (not in profile).
        assert "GEMINI_API_KEY" in env_text
        assert "OPENAI_API_KEY" in env_text

    def test_dedup_first_occurrence_wins_within_profile(self, tmp_path):
        """Same key in build AND plugin → first occurrence (build) wins."""
        profiles = tmp_path / "p"
        profiles.mkdir()
        (profiles / "dup.json").write_text(json.dumps({
            "name": "dup",
            "required_env_vars": {
                "build": [
                    {"name": "DUPLICATED_KEY", "description": "build-side first"},
                ],
                "deploy": [],
                "plugin": [
                    {"name": "DUPLICATED_KEY", "description": "plugin-side second"},
                ],
            },
        }), encoding="utf-8")
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "dup"}), encoding="utf-8",
        )
        init_env_file(proj, "all", profiles, include_framework=False)
        env_text = (proj / ".env.local").read_text(encoding="utf-8")
        assert env_text.count("DUPLICATED_KEY=") == 1
        assert "build-side first" in env_text
        assert "plugin-side second" not in env_text


class TestExportPrefixParsing:
    def test_export_prefix_recognized_as_present(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "export FOO=bar\n  export BAZ=qux\n",
            encoding="utf-8",
        )
        result = parse_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_export_prefix_in_idempotence_check(self, tmp_path):
        """init_env_file must treat `export OPENROUTER_API_KEY=...` as present."""
        profiles = tmp_path / "p"
        profiles.mkdir()
        (profiles / "empty.json").write_text(json.dumps({
            "name": "empty",
            "required_env_vars": {"build": [], "deploy": [], "plugin": []},
        }), encoding="utf-8")
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "empty"}), encoding="utf-8",
        )
        env_file = proj / ".env.local"
        # User pre-populated with POSIX-style export
        env_file.write_text(
            "export OPENROUTER_API_KEY=sk-or-real-1\n"
            "export GEMINI_API_KEY=AIza-real-2\n"
            "export OPENAI_API_KEY=sk-real-3\n",
            encoding="utf-8",
        )
        # Need to also pre-create .gitignore so we don't change file structure
        (proj / ".gitignore").write_text(".env.local\n", encoding="utf-8")
        result = init_env_file(proj, "all", profiles, include_framework=True)
        assert result["action"] == "unchanged"
        # File preserved byte-for-byte
        assert env_file.read_text(encoding="utf-8") == (
            "export OPENROUTER_API_KEY=sk-or-real-1\n"
            "export GEMINI_API_KEY=AIza-real-2\n"
            "export OPENAI_API_KEY=sk-real-3\n"
        )


class TestRichReturnContract:
    @pytest.fixture
    def fw_profile_dir(self, tmp_path):
        profiles = tmp_path / "p"
        profiles.mkdir()
        (profiles / "empty.json").write_text(json.dumps({
            "name": "empty",
            "required_env_vars": {"build": [], "deploy": [], "plugin": []},
        }), encoding="utf-8")
        return profiles

    @pytest.fixture
    def fw_project(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "empty"}), encoding="utf-8",
        )
        return proj

    def test_rich_keys_on_created(self, fw_project, fw_profile_dir):
        result = init_env_file(
            fw_project, "all", fw_profile_dir, include_framework=True,
        )
        assert result["action"] == "created"
        assert "missing_keys" in result
        assert set(result["missing_keys"]) == {
            "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
        }
        assert result["framework_keys"] == [
            "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
        ]
        assert "path" in result

    def test_missing_keys_reflects_final_state_on_unchanged(
        self, fw_project, fw_profile_dir,
    ):
        """A second run on a file with all keys still commented (placeholders)
        must report all three as missing, not zero. Action is 'unchanged'
        because no rewrite happened — but Step H still needs to prompt the
        user."""
        # First run creates the file with three commented placeholders.
        init_env_file(fw_project, "all", fw_profile_dir, include_framework=True)
        # Second run: file unchanged, but all three values are still empty.
        result = init_env_file(
            fw_project, "all", fw_profile_dir, include_framework=True,
        )
        assert result["action"] == "unchanged"
        assert set(result["missing_keys"]) == {
            "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
        }

    def test_missing_keys_excludes_filled_values(
        self, fw_project, fw_profile_dir,
    ):
        """If user has filled OPENROUTER_API_KEY, missing_keys lists the
        other two."""
        env_file = fw_project / ".env.local"
        env_file.write_text(
            "OPENROUTER_API_KEY=sk-or-real-value\n"
            "# GEMINI_API_KEY=        # placeholder\n"
            "# OPENAI_API_KEY=        # placeholder\n",
            encoding="utf-8",
        )
        # Pre-create gitignore so action stays 'unchanged'.
        (fw_project / ".gitignore").write_text(".env.local\n", encoding="utf-8")
        result = init_env_file(
            fw_project, "all", fw_profile_dir, include_framework=True,
        )
        assert result["action"] == "unchanged"
        assert "OPENROUTER_API_KEY" not in result["missing_keys"]
        assert "GEMINI_API_KEY" in result["missing_keys"]
        assert "OPENAI_API_KEY" in result["missing_keys"]


class TestGitignoreHardStop:
    """If `_ensure_gitignore` raises, init_env_file MUST return action=skipped
    with reason=gitignore_enforcement_failed and NOT write `.env.local`."""

    @pytest.fixture
    def fw_profile_dir(self, tmp_path):
        profiles = tmp_path / "p"
        profiles.mkdir()
        (profiles / "empty.json").write_text(json.dumps({
            "name": "empty",
            "required_env_vars": {"build": [], "deploy": [], "plugin": []},
        }), encoding="utf-8")
        return profiles

    @pytest.fixture
    def fw_project(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "empty"}), encoding="utf-8",
        )
        return proj

    def test_gitignore_failure_aborts_env_local(
        self, fw_project, fw_profile_dir, monkeypatch,
    ):
        from shared.scripts import validate_env

        def explode(_root):
            raise OSError("simulated permission denied on .gitignore")

        monkeypatch.setattr(validate_env, "_ensure_gitignore", explode)
        result = init_env_file(
            fw_project, "all", fw_profile_dir, include_framework=True,
        )
        assert result["action"] == "skipped"
        assert result["reason"] == "gitignore_enforcement_failed"
        assert "permission denied" in result["error"].lower()
        # Crucially: .env.local was NOT written despite an "all" phase request.
        assert not (fw_project / ".env.local").exists()


class TestFrameworkOrderDriftProtection:
    """The hardcoded framework-key order in validate_env._SHIPWRIGHT_FRAMEWORK_VARS
    must mirror the fallback order in external_review_config.is_external_review_enabled
    so that the .env.local scaffold reflects what the runtime actually checks
    for. If a future edit to external_review_config.py reorders the fallback
    or adds another key, this test fails loud.
    """

    @staticmethod
    def _extract_runtime_fallback_keys() -> list[str]:
        """Parse external_review_config.py and return the ORDERED list of keys
        consulted in is_external_review_enabled().

        The reference implementation looks like::

            has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
            has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
            has_openai = bool(os.environ.get("OPENAI_API_KEY"))

        We extract every ``os.environ.get("KEY")`` argument inside the function
        body in source order, then dedupe while preserving first occurrence.
        ``GOOGLE_API_KEY`` appears as a Gemini alias and is intentionally
        excluded from the framework scaffold (only direct, primary keys
        are scaffolded), so we tolerate it in the runtime list.
        """
        import ast
        from pathlib import Path as _P

        from shared.scripts import validate_env

        external_review_path = (
            _P(validate_env.__file__).resolve().parent / "lib" / "external_review_config.py"
        )
        assert external_review_path.exists(), (
            "external_review_config.py path drifted — update this test"
        )
        tree = ast.parse(external_review_path.read_text(encoding="utf-8"))

        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "is_external_review_enabled":
                target = node
                break
        assert target is not None, "is_external_review_enabled() not found"

        # ast.walk's traversal order is unspecified, so collect calls with
        # their source positions and sort explicitly. (lineno, col_offset)
        # is a stable surrogate for "source order".
        positioned: list[tuple[int, int, str]] = []
        for node in ast.walk(target):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "environ"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                positioned.append((node.lineno, node.col_offset, node.args[0].value))
        positioned.sort()

        # Dedupe preserving first-seen order
        seen: set[str] = set()
        ordered: list[str] = []
        for _, _, k in positioned:
            if k not in seen:
                seen.add(k)
                ordered.append(k)
        return ordered

    def test_framework_keys_match_external_review_fallback_order(self):
        from shared.scripts import validate_env

        framework_names = [v["name"] for v in validate_env._SHIPWRIGHT_FRAMEWORK_VARS]
        assert framework_names == [
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
        ]

        runtime_keys = self._extract_runtime_fallback_keys()
        # Filter out Gemini aliases (GOOGLE_API_KEY) — only primary-name
        # keys are scaffolded, but the runtime accepts both. Locking the
        # alias here would block legitimate fallback additions.
        primary_runtime_keys = [k for k in runtime_keys if k != "GOOGLE_API_KEY"]

        # Order must match exactly. If a new primary key is added to the
        # runtime fallback, this test fails loud and the framework list
        # must be synced before merging.
        assert primary_runtime_keys == framework_names, (
            f"Framework key list out of sync with runtime fallback.\n"
            f"  validate_env._SHIPWRIGHT_FRAMEWORK_VARS: {framework_names}\n"
            f"  external_review_config.is_external_review_enabled(): {primary_runtime_keys}\n"
            f"Update _SHIPWRIGHT_FRAMEWORK_VARS to match (or update this test "
            f"if GOOGLE_API_KEY-style aliases were added)."
        )


class TestMissingKeysActiveBlankValues:
    """``_compute_missing_keys`` must treat actively-assigned blank values
    (``KEY=``, ``KEY=""``, ``KEY=''``) as missing. ``_is_placeholder`` already
    has empty-string semantics; this locks in the wiring through ``parse_env_file``.
    """

    @pytest.fixture
    def fw_profile_dir(self, tmp_path):
        profiles = tmp_path / "p"
        profiles.mkdir()
        (profiles / "empty.json").write_text(json.dumps({
            "name": "empty",
            "required_env_vars": {"build": [], "deploy": [], "plugin": []},
        }), encoding="utf-8")
        return profiles

    @pytest.fixture
    def fw_project(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "empty"}), encoding="utf-8",
        )
        (proj / ".gitignore").write_text(".env.local\n", encoding="utf-8")
        return proj

    def test_unquoted_blank_counts_as_missing(self, fw_project, fw_profile_dir):
        (fw_project / ".env.local").write_text(
            "OPENROUTER_API_KEY=\n"
            "GEMINI_API_KEY=AIza-real\n"
            "OPENAI_API_KEY=\n",
            encoding="utf-8",
        )
        result = init_env_file(
            fw_project, "all", fw_profile_dir, include_framework=True,
        )
        assert "OPENROUTER_API_KEY" in result["missing_keys"]
        assert "OPENAI_API_KEY" in result["missing_keys"]
        assert "GEMINI_API_KEY" not in result["missing_keys"]

    def test_quoted_blank_counts_as_missing(self, fw_project, fw_profile_dir):
        (fw_project / ".env.local").write_text(
            'OPENROUTER_API_KEY=""\n'
            "GEMINI_API_KEY=''\n"
            "OPENAI_API_KEY=AIza-real\n",
            encoding="utf-8",
        )
        result = init_env_file(
            fw_project, "all", fw_profile_dir, include_framework=True,
        )
        assert "OPENROUTER_API_KEY" in result["missing_keys"]
        assert "GEMINI_API_KEY" in result["missing_keys"]
        assert "OPENAI_API_KEY" not in result["missing_keys"]
