"""Unit tests for lib.model_tier_config — the per-role Claude model tier resolver.

Precedence: flag > project config > unset. Unset and the literal "inherit"
resolve to the same value. See
.shipwright/planning/iterate/2026-08-07-agent-model-tiers.md.
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

from lib.model_tier_config import (  # noqa: E402
    ModelTierConfigError,
    agent_model_param,
    load_model_config,
    resolve_model_tier,
)


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


def test_unset_resolves_to_inherit_with_source_unset(repo: Path) -> None:
    resolved, source = resolve_model_tier("review", repo)
    assert resolved == "inherit"
    assert source == "unset"


def test_flag_wins_over_project_config(repo: Path) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"review": "sonnet"}), encoding="utf-8",
    )
    resolved, source = resolve_model_tier("review", repo, flag_value="opus")
    assert resolved == "opus"
    assert source == "flag"


def test_project_config_wins_over_unset(repo: Path) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"finalization": "opus"}), encoding="utf-8",
    )
    resolved, source = resolve_model_tier("finalization", repo)
    assert resolved == "opus"
    assert source == "project_config"


def test_explicit_inherit_flag_is_source_flag_not_unset(repo: Path) -> None:
    """`inherit` is an explicit way to say the same thing as leaving it unset —
    but the SOURCE must still say it was an explicit flag, for the Planned Run
    Summary to print "explicitly set to inherit" vs "never configured"."""
    resolved, source = resolve_model_tier("review", repo, flag_value="inherit")
    assert resolved == "inherit"
    assert source == "flag"


def test_plan_review_role_resolves_independently_of_review(repo: Path) -> None:
    """plan_review is its own role — a project pinning `review` to a cheaper
    tier must not silently drag the plan reviewer down with it."""
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"review": "sonnet", "plan_review": "opus"}), encoding="utf-8",
    )
    review_resolved, _ = resolve_model_tier("review", repo)
    plan_review_resolved, plan_review_source = resolve_model_tier("plan_review", repo)
    assert review_resolved == "sonnet"
    assert plan_review_resolved == "opus"
    assert plan_review_source == "project_config"


def test_plan_review_invalid_flag_warns_with_hyphenated_flag_name(repo: Path, capsys) -> None:
    resolve_model_tier("plan_review", repo, flag_value="gpt5")
    err = capsys.readouterr().err
    assert "--plan-review-model" in err
    assert "--plan_review-model" not in err
    assert "is not a valid tier" in err


def test_floors_round_trip_plan_review(repo: Path) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"floors": {"plan_review": "opus"}}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert config["floors"] == {"plan_review": "opus"}


def test_agent_model_param_omits_for_inherit() -> None:
    assert agent_model_param("inherit") is None


def test_agent_model_param_passes_through_explicit_tier() -> None:
    assert agent_model_param("opus") == "opus"


def test_unknown_role_raises() -> None:
    with pytest.raises(ModelTierConfigError):
        resolve_model_tier("not-a-role", Path("."))


def test_invalid_flag_value_ignored_falls_back_to_config(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"review": "opus"}), encoding="utf-8",
    )
    resolved, source = resolve_model_tier("review", repo, flag_value="gpt5")
    assert resolved == "opus"
    assert source == "project_config"
    assert "gpt5" in capsys.readouterr().err


def test_malformed_config_fails_soft_to_empty(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text("{not json", encoding="utf-8")
    resolved, source = resolve_model_tier("review", repo)
    assert resolved == "inherit"
    assert source == "unset"
    assert "malformed" in capsys.readouterr().err


def test_config_not_a_json_object_fails_soft(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text("[1, 2, 3]", encoding="utf-8")
    result = load_model_config(repo)
    assert result == {}
    assert "not a JSON object" in capsys.readouterr().err


def test_invalid_config_tier_value_dropped_not_raised(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"review": "'; rm -rf /"}), encoding="utf-8",
    )
    resolved, source = resolve_model_tier("review", repo)
    assert resolved == "inherit"
    assert source == "unset"
    err = capsys.readouterr().err
    assert "invalid tier" in err


def test_hostile_config_value_never_echoed_into_resolved_output(repo: Path, capsys) -> None:
    """A hostile string in the config must never reach the resolved value that
    flows into an Agent-tool model= argument or a rendered CLI flag — and the
    warning that DOES echo it (to stderr, for operator debugging) must be
    length-capped, since stderr lands in the same tool output a driving LLM
    reads verbatim."""
    hostile = '"; cat /etc/passwd #' * 20  # long enough to exercise the cap
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"review": hostile}), encoding="utf-8",
    )
    resolved, _source = resolve_model_tier("review", repo)
    assert resolved == "inherit"
    assert hostile not in resolved
    err = capsys.readouterr().err
    assert hostile not in err
    assert "(truncated)" in err


def test_floors_round_trip(repo: Path) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"floors": {"review": "opus"}}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert config["floors"] == {"review": "opus"}


def test_floors_invalid_value_dropped(repo: Path, capsys) -> None:
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"floors": {"review": "inherit"}}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert "review" not in config.get("floors", {})
    assert "invalid tier" in capsys.readouterr().err


def test_missing_config_file_returns_empty(repo: Path) -> None:
    assert load_model_config(repo) == {}


def test_undecodable_config_bytes_fail_soft_to_empty(repo: Path, capsys) -> None:
    """Not just malformed JSON — bytes that are not valid UTF-8 at all (e.g. a
    file saved as UTF-16) must fail soft too, not raise UnicodeDecodeError."""
    (repo / "shipwright_model_config.json").write_bytes(b"\xff\xfe\x00\x01")

    assert load_model_config(repo) == {}
    assert "unreadable" in capsys.readouterr().err


def test_plan_review_boundary_probe_round_trip(repo: Path) -> None:
    """Boundary Probe (touches_io_boundary): the new `plan_review` key
    round-trips whole through load_model_config -> resolve_model_tier ->
    agent_model_param, exactly like the pre-existing three roles."""
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"plan_review": "opus"}), encoding="utf-8",
    )
    config = load_model_config(repo)
    assert config["plan_review"] == "opus"
    resolved, source = resolve_model_tier("plan_review", repo, _config=config)
    assert (resolved, source) == ("opus", "project_config")
    assert agent_model_param(resolved) == "opus"


def test_shipped_root_config_round_trips_through_resolver(repo: Path) -> None:
    """Round-trip the actual bytes of the repo's own `shipwright_model_config.json`
    (not a re-typed fixture) through the resolver in an isolated repo — so this
    proves the committed artifact itself, independent of `load_model_config`'s
    main-repo-root resolution (which would otherwise read whatever a
    developer's main checkout locally holds instead of this branch's file).
    Pins `review: opus` — the value this repo intends, distinct from the
    `plan_review` role, which stays independently configurable per
    iterate-2026-08-08-plan-reviewer-configurable."""
    source_path = Path(__file__).resolve().parents[2] / "shipwright_model_config.json"
    raw = source_path.read_text(encoding="utf-8")
    config_dict = json.loads(raw)
    assert config_dict["review"] == "opus"
    assert config_dict["finalization"] == "sonnet"
    assert config_dict["execution"] == "sonnet"
    assert config_dict["plan_review"] == "opus"
    assert config_dict["floors"] == {"review": "sonnet"}

    (repo / "shipwright_model_config.json").write_text(raw, encoding="utf-8")

    assert resolve_model_tier("review", repo) == ("opus", "project_config")
    assert resolve_model_tier("finalization", repo) == ("sonnet", "project_config")
    assert resolve_model_tier("execution", repo) == ("sonnet", "project_config")
    assert resolve_model_tier("plan_review", repo) == ("opus", "project_config")


def test_resolves_from_main_repo_root_not_worktree_cwd(repo: Path) -> None:
    """A linked worktree must read the config the operator set at the MAIN
    repo root, not silently see an empty/different one from its own tree —
    the same rule durable artifacts already follow (main-root resolver)."""
    (repo / "shipwright_model_config.json").write_text(
        json.dumps({"review": "opus"}), encoding="utf-8",
    )
    subprocess.run(
        ["git", "worktree", "add", "-b", "wt-branch", str(repo / ".worktrees" / "wt")],
        cwd=repo, check=True, capture_output=True,
    )
    worktree_root = repo / ".worktrees" / "wt"
    resolved, source = resolve_model_tier("review", worktree_root)
    assert resolved == "opus"
    assert source == "project_config"


def _schema_errors(instance: dict) -> list[str]:
    import jsonschema

    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "model_config.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(instance)]


def test_schema_accepts_plan_review_key() -> None:
    assert _schema_errors({"plan_review": "opus"}) == []
    assert _schema_errors({"review": "sonnet", "plan_review": "inherit"}) == []


def test_schema_rejects_unknown_role_key() -> None:
    errors = _schema_errors({"plan_review": "opus", "not_a_role": "opus"})
    assert errors, "an unrecognized top-level role key must be rejected"


def test_schema_rejects_plan_review_with_invalid_tier() -> None:
    errors = _schema_errors({"plan_review": "gpt-5"})
    assert errors, "plan_review must be constrained to the same Tier enum as the other roles"
