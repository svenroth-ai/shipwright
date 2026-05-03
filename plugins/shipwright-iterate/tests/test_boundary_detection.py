"""Unit tests for is_io_boundary_change helper in classify_complexity.

Sub-Iterate A — Boundary Tests Foundation (campaign iterate-skill-hardening).

Covers:
- Path-match positive cases for each `IO_BOUNDARY_FILE_PATTERNS` entry.
- Negative case: ordinary source/test files do NOT trigger the flag.
- Empty/None inputs are handled gracefully.
- Path normalization (Windows vs POSIX separators).
"""

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from classify_complexity import (  # noqa: E402
    IO_BOUNDARY_FILE_PATTERNS,
    is_io_boundary_change,
)


class TestIoBoundaryFilePatterns:
    """The pattern tuple itself must include the canonical anchors.

    Patterns are regexes — substring checks compare against the
    regex source (which contains escape backslashes), so the test
    keywords use the escaped form `\\.json` etc. to match.
    """

    def test_env_files_listed(self):
        # Env files are the motivating example (the env-iterate BOM bug).
        assert any("env" in p for p in IO_BOUNDARY_FILE_PATTERNS)

    def test_hooks_json_listed(self):
        assert any(r"hooks\.json" in p for p in IO_BOUNDARY_FILE_PATTERNS)

    def test_settings_json_listed(self):
        assert any(r"settings\.json" in p for p in IO_BOUNDARY_FILE_PATTERNS)

    def test_config_json_pattern_listed(self):
        # Generic _config.json wildcard must be present.
        assert any(r"_config\.json" in p for p in IO_BOUNDARY_FILE_PATTERNS)

    def test_state_json_pattern_listed(self):
        assert any(r"_state\.json" in p for p in IO_BOUNDARY_FILE_PATTERNS)


class TestIsIoBoundaryChangePositive:
    def test_dotenv_file(self):
        assert is_io_boundary_change([".env"]) is True

    def test_dotenv_local_file(self):
        assert is_io_boundary_change([".env.local"]) is True

    def test_hooks_json_anywhere(self):
        assert is_io_boundary_change(
            ["plugins/shipwright-iterate/hooks/hooks.json"]
        ) is True

    def test_settings_json(self):
        assert is_io_boundary_change([".claude/settings.json"]) is True

    def test_config_json_suffix(self):
        assert is_io_boundary_change(
            ["shipwright_run_config.json"]
        ) is True

    def test_state_json_suffix(self):
        assert is_io_boundary_change([".shipwright/loop_state.json"]) is True

    def test_windows_path_separators(self):
        # Path normalization: backslashes treated identically to forward slashes.
        assert is_io_boundary_change(
            ["plugins\\shipwright-iterate\\hooks\\hooks.json"]
        ) is True

    def test_mixed_changed_files(self):
        # One match in a list of many should still trigger.
        assert is_io_boundary_change([
            "src/components/Button.tsx",
            "src/utils/helper.ts",
            ".env.local",
            "README.md",
        ]) is True


class TestIsIoBoundaryChangeNegative:
    def test_ordinary_source_file(self):
        assert is_io_boundary_change(["src/components/Button.tsx"]) is False

    def test_ordinary_python_file(self):
        assert is_io_boundary_change(["scripts/lib/helpers.py"]) is False

    def test_markdown_file(self):
        assert is_io_boundary_change(["README.md"]) is False

    def test_random_json_without_suffix(self):
        # data.json is not a config / state / settings / hooks file.
        assert is_io_boundary_change(["data/data.json"]) is False

    def test_package_json_not_io_boundary(self):
        # package.json is a build-touching file (touches_build), not an
        # IO boundary in the producer/consumer sense.
        assert is_io_boundary_change(["package.json"]) is False

    def test_empty_list(self):
        assert is_io_boundary_change([]) is False

    def test_none_safe(self):
        # Implementation should treat None like an empty list, not crash.
        assert is_io_boundary_change(None) is False
