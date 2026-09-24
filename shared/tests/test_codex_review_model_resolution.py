"""`lib/codex_review_model_resolution.py` — the Codex reviewer-model
precedence chain (iterate-2026-09-19-codex-reviewer-session-override).

Precedence: explicit `model` argument > this role's session env var
(`SHIPWRIGHT_CODEX_REVIEW_MODEL` / `SHIPWRIGHT_CODEX_PLAN_REVIEW_MODEL`) >
`shipwright_model_config.json`'s `codex_review`/`codex_plan_review` key >
the caller-supplied hardcoded default. `load_model_config` is stubbed
throughout so these stay pure unit tests with no git subprocess call.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import codex_review_model_resolution as resolution  # noqa: E402

DEFAULT = "gpt-6-sol"


def _stub_config(monkeypatch: pytest.MonkeyPatch, config: dict) -> None:
    monkeypatch.setattr(resolution, "load_model_config", lambda root: config)


def test_explicit_model_wins_over_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch, {"codex_review": "gpt-5.6-terra"})
    monkeypatch.setenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", "gpt-5.6-luna")

    model, source = resolution.resolve_codex_review_model("code", tmp_path, "gpt-6-astra", DEFAULT)

    assert model == "gpt-6-astra"
    assert source == "the explicit model= argument"


def test_env_var_wins_over_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch, {"codex_review": "gpt-5.6-terra"})
    monkeypatch.setenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", "gpt-5.6-luna")

    model, source = resolution.resolve_codex_review_model("code", tmp_path, None, DEFAULT)

    assert model == "gpt-5.6-luna"
    assert source == "the SHIPWRIGHT_CODEX_REVIEW_MODEL environment variable"


def test_plan_review_role_reads_its_own_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `SHIPWRIGHT_CODEX_REVIEW_MODEL` override must not leak into
    `plan_review`'s resolution -- same independence the persisted
    `codex_plan_review` config key already has from `codex_review`."""
    _stub_config(monkeypatch, {})
    monkeypatch.setenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("SHIPWRIGHT_CODEX_PLAN_REVIEW_MODEL", "gpt-6-astra")

    model, source = resolution.resolve_codex_review_model("plan_review", tmp_path, None, DEFAULT)

    assert model == "gpt-6-astra"
    assert source == "the SHIPWRIGHT_CODEX_PLAN_REVIEW_MODEL environment variable"


def test_project_config_wins_over_hardcoded_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch, {"codex_review": "gpt-5.6-terra"})
    monkeypatch.delenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", raising=False)

    model, source = resolution.resolve_codex_review_model("code", tmp_path, None, DEFAULT)

    assert model == "gpt-5.6-terra"
    assert source == "shipwright_model_config.json's 'codex_review' key"


def test_hardcoded_default_when_nothing_else_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch, {})
    monkeypatch.delenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", raising=False)

    model, source = resolution.resolve_codex_review_model("code", tmp_path, None, DEFAULT)

    assert model == DEFAULT
    assert source == "the hardcoded default"


def test_blank_env_var_is_treated_as_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whitespace-only env var must fall through to project config, not be
    used verbatim (which would only ever fail the downstream allowlist)."""
    _stub_config(monkeypatch, {"codex_review": "gpt-5.6-terra"})
    monkeypatch.setenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", "   ")

    model, source = resolution.resolve_codex_review_model("code", tmp_path, None, DEFAULT)

    assert model == "gpt-5.6-terra"
    assert source == "shipwright_model_config.json's 'codex_review' key"


def test_env_var_surrounding_whitespace_is_trimmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_config(monkeypatch, {})
    monkeypatch.setenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", " gpt-5.6-terra ")

    model, _source = resolution.resolve_codex_review_model("code", tmp_path, None, DEFAULT)

    assert model == "gpt-5.6-terra"


@pytest.mark.parametrize("role", ["spec", "code", "doubt"])
def test_review_roles_share_the_same_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    _stub_config(monkeypatch, {})
    monkeypatch.setenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", "gpt-5.6-luna")

    model, _source = resolution.resolve_codex_review_model(role, tmp_path, None, DEFAULT)

    assert model == "gpt-5.6-luna"


def test_role_tables_stay_in_sync_with_role_schemas() -> None:
    assert resolution.ROLE_TO_CODEX_CONFIG_KEY.keys() == resolution.ROLE_SCHEMAS.keys()
    assert resolution.ROLE_TO_CODEX_ENV_VAR.keys() == resolution.ROLE_SCHEMAS.keys()


def test_role_missing_from_either_table_raises() -> None:
    """Regression for the drift class `review_via_codex.py` originally
    guarded against for its own (now-moved) role->config-key table: a role
    present in `ROLE_SCHEMAS` but missing from either table here must fail
    loudly, not with a `KeyError` deep inside resolution."""
    role_keys = resolution.ROLE_SCHEMAS.keys() | {"new_role"}

    with pytest.raises(RuntimeError, match="ROLE_TO_CODEX_CONFIG_KEY"):
        resolution._check_role_tables_complete(
            role_keys, resolution.ROLE_TO_CODEX_CONFIG_KEY.keys(), resolution.ROLE_TO_CODEX_ENV_VAR.keys())


def test_matching_tables_do_not_raise() -> None:
    resolution._check_role_tables_complete(
        resolution.ROLE_SCHEMAS.keys(), resolution.ROLE_TO_CODEX_CONFIG_KEY.keys(),
        resolution.ROLE_TO_CODEX_ENV_VAR.keys())
