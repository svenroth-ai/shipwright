"""Unit tests for lib.model_tier_config's `fable` tier and `codex_review`/
`codex_plan_review` keys — split from `test_model_tier_config.py` to stay
under the 300-line source cap (iterate-2026-09-18-codex-review-tier-config).

`fable` is a real Claude alias the Agent tool already accepts (confirmed
live, this run) — `TIERS` must not stay stale on it the way it was.
`codex_review`/`codex_plan_review` are a separate, non-Claude axis (a Codex
model slug string) read through the same config reader, never checked
against `TIERS`. See `.shipwright/planning/iterate/2026-09-18-codex-review-tier-config.md`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.model_tier_config import load_model_config, resolve_model_tier  # noqa: E402


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


def test_fable_is_a_valid_flag_tier(repo: Path) -> None:
    resolved, source = resolve_model_tier("review", repo, flag_value="fable")
    assert resolved == "fable"
    assert source == "flag"


def test_fable_wins_from_project_config(repo: Path) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"plan_review": "fable"}), encoding="utf-8",
    )
    resolved, source = resolve_model_tier("plan_review", repo)
    assert resolved == "fable"
    assert source == "project_config"


def test_fable_is_unranked_like_inherit() -> None:
    """No capability ordering relative to opus/sonnet/haiku has been
    established for fable -- it must stay floor-exempt, not guessed at."""
    from lib.model_tier_config import RANK, RANKED_TIERS

    assert "fable" not in RANKED_TIERS
    assert "fable" not in RANK


def test_codex_review_key_round_trips_with_no_spurious_warning(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": "gpt-5.6-terra"}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert config["codex_review"] == "gpt-5.6-terra"
    assert "unrecognized key" not in capsys.readouterr().err


def test_codex_plan_review_key_round_trips_with_no_spurious_warning(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"codex_plan_review": "gpt-6-astra"}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert config["codex_plan_review"] == "gpt-6-astra"
    assert "unrecognized key" not in capsys.readouterr().err


def test_codex_review_key_non_string_dropped_not_raised(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": ["not", "a", "string"]}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert "codex_review" not in config
    assert "invalid" in capsys.readouterr().err


def test_codex_review_key_empty_string_dropped_with_warning(repo: Path, capsys) -> None:
    """An empty/whitespace-only value must warn and be dropped here — the
    caller (`review_via_codex.py`) treats a falsy `configured_model` as
    "unset" and silently falls back to the hardcoded default, so a silent
    pass-through here would make an explicit-but-empty config value take
    effect with no warning at all (code-reviewer MEDIUM, 2026-09-18)."""
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": "  "}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert "codex_review" not in config
    assert "invalid" in capsys.readouterr().err


def test_codex_review_key_surrounding_whitespace_is_trimmed(repo: Path) -> None:
    """A padded slug must be stored trimmed, not passed through verbatim --
    otherwise it fails the downstream allowlist over a whitespace typo
    instead of being usable (external code review, LOW, 2026-09-18)."""
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": " gpt-5.6-terra "}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert config["codex_review"] == "gpt-5.6-terra"


def test_genuinely_unknown_top_level_key_still_warns(repo: Path, capsys) -> None:
    """Widening the unknown-key allowlist for the two new Codex keys must not
    silently widen it for everything else -- a real typo must still warn."""
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"reviews": "opus"}), encoding="utf-8",
    )
    load_model_config(repo)
    assert "unrecognized key" in capsys.readouterr().err


def _schema_errors(instance: dict) -> list[str]:
    import jsonschema

    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "model_config.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(instance)]


def test_schema_accepts_fable_tier() -> None:
    assert _schema_errors({"review": "fable"}) == []


def test_schema_rejects_fable_as_a_floor() -> None:
    errors = _schema_errors({"floors": {"review": "fable"}})
    assert errors, "fable is unranked — it must not be a legal floors value"


def test_schema_accepts_codex_keys() -> None:
    assert _schema_errors({"codex_review": "gpt-5.6-sol", "codex_plan_review": "gpt-6-astra"}) == []


def test_schema_rejects_non_string_codex_key() -> None:
    errors = _schema_errors({"codex_review": 5})
    assert errors, "codex_review must be a string"
