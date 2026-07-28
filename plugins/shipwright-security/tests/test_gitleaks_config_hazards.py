"""Hazards in extend-mode, from the external review of the mini-plan.

Both reviewers (gemini + gpt) independently raised the same HIGH finding:
gitleaks aborts on a config that sets both ``extend.useDefault`` and
``extend.path``, so extending the project's file means the plugin can no longer
force the built-in ruleset on. A project ``.gitleaks.toml`` authored purely to
hold an ``[allowlist]`` therefore scans with almost no secret rules.

The host workflow already behaves that way (same file, no ``--config``), so
extending does not introduce the divergence — it makes a pre-existing hole
visible. Which is this card's whole thesis: a class scanned with no rules is
unexamined, not clean, and must say so.

Also covers the TOML-serialization finding: escaping only backslash and quote
is not enough for an arbitrary absolute path.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from gitleaks_config import render_config  # noqa: E402
from gitleaks_inspect import (  # noqa: E402
    PROJECT_CONFIG_NAME,
    class_degradations,
    inspect_project_config,
    project_config_warning,
)


def _write(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / PROJECT_CONFIG_NAME
    cfg.write_text(body, encoding="utf-8")
    return cfg


@pytest.mark.covers("FR-01.07")
class TestInspectProjectConfig:
    def test_detects_usedefault(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "[extend]\nuseDefault = true\n")
        assert inspect_project_config(str(cfg))["extends_default"] is True

    def test_detects_own_rules(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, '[[rules]]\nid = "x"\nregex = "y"\n')
        assert inspect_project_config(str(cfg))["defines_rules"] is True

    def test_detects_a_chained_extend(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, '[extend]\npath = "other.toml"\n')
        assert inspect_project_config(str(cfg))["extends_other"] is True

    def test_allowlist_only_config_brings_no_rules(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "[allowlist]\npaths = ['x']\n")
        info = inspect_project_config(str(cfg))
        assert info["parsed"] is True
        assert info["extends_default"] is False
        assert info["defines_rules"] is False

    def test_unparseable_config_reports_not_parsed(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "this is not = = toml\n")
        assert inspect_project_config(str(cfg))["parsed"] is False

    def test_missing_file_reports_not_parsed(self, tmp_path: Path) -> None:
        assert inspect_project_config(str(tmp_path / "nope.toml"))["parsed"] is False


@pytest.mark.covers("FR-01.07")
class TestProjectConfigWarning:
    def test_allowlist_only_config_is_named_loudly(self, tmp_path: Path) -> None:
        """The HIGH review finding: this scan looked for almost nothing, and
        silence here is exactly the false-clean signal the card exists to kill."""
        _write(tmp_path, "[allowlist]\npaths = ['x']\n")
        warning = project_config_warning(str(tmp_path))
        assert warning is not None
        assert "useDefault" in warning

    def test_config_extending_the_defaults_is_silent(self, tmp_path: Path) -> None:
        _write(tmp_path, "[extend]\nuseDefault = true\n[allowlist]\npaths = ['x']\n")
        assert project_config_warning(str(tmp_path)) is None

    def test_config_with_its_own_rules_is_silent(self, tmp_path: Path) -> None:
        _write(tmp_path, '[[rules]]\nid = "x"\nregex = "y"\n')
        assert project_config_warning(str(tmp_path)) is None

    def test_unparseable_config_is_named(self, tmp_path: Path) -> None:
        _write(tmp_path, "= = =\n")
        assert "could not be parsed" in (project_config_warning(str(tmp_path)) or "")

    def test_no_project_config_is_silent(self, tmp_path: Path) -> None:
        assert project_config_warning(str(tmp_path)) is None

    def test_degradations_target_the_secrets_class(self, tmp_path: Path) -> None:
        _write(tmp_path, "[allowlist]\npaths = ['x']\n")
        assert set(class_degradations(str(tmp_path))) == {"secrets"}

    def test_no_degradation_when_nothing_to_say(self, tmp_path: Path) -> None:
        assert class_degradations(str(tmp_path)) == {}


@pytest.mark.covers("FR-01.07")
class TestTomlPathSerialization:
    @pytest.mark.parametrize(
        "raw",
        [
            r"C:\repo\.gitleaks.toml",
            "/home/user/my repo/.gitleaks.toml",
            '/tmp/we"ird/.gitleaks.toml',
            "/tmp/tab\there/.gitleaks.toml",
            "/tmp/nl\nhere/.gitleaks.toml",
            "/tmp/cr\rhere/.gitleaks.toml",
            "/tmp/bell\x07here/.gitleaks.toml",
            "/tmp/ünïcode/.gitleaks.toml",
        ],
    )
    def test_path_round_trips_through_toml_exactly(self, raw: str) -> None:
        """A partially-escaped path either fails to parse or silently points
        somewhere else — and for a scanner config, "somewhere else" means
        scanning under rules nobody chose."""
        parsed = tomllib.loads(render_config((), raw))
        assert parsed["extend"]["path"] == raw

    def test_generated_config_stays_valid_toml_with_a_hostile_path(self) -> None:
        body = render_config(("node_modules",), '/a\\b"c\n/.gitleaks.toml')
        parsed = tomllib.loads(body)
        assert parsed["allowlist"]["paths"]
