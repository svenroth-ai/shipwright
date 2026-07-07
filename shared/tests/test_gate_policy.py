"""Resolver / mode-resolution / dry-run / doc-generation tests (SS2).

The catalog-integrity + validator coverage lives in ``test_gate_catalog.py``.
``shared/tests/conftest.py`` puts ``shared/scripts`` on sys.path, so the
mechanism imports as ``lib.gate_policy``.
"""
from __future__ import annotations

import json

import pytest

from lib.gate_policy import (
    COVERED_PHASES,
    DEFAULT_RUN_MODE,
    INTERACTIVE,
    POLICIES,
    SINGLE_SESSION,
    effective_mode,
    load_catalog,
    read_run_config_mode,
    render_catalog_markdown,
    resolve_gate_policy,
)


# --------------------------------------------------------------------------- #
# Resolver — multi_session inert, single_session per-gate
# --------------------------------------------------------------------------- #

def test_multi_session_is_inert_for_every_gate():
    """Under multi_session every gate resolves to 'interactive' (today's behaviour)."""
    catalog = load_catalog()
    for gid in catalog["gates"]:
        r = resolve_gate_policy(gid, mode="multi_session", catalog=catalog)
        assert r["effective_policy"] == INTERACTIVE
        assert r["should_stop"] is True
        assert r["default_answer"] is None  # no default applied when asking a human


def test_unknown_mode_is_inert():
    """A typo/unknown mode is treated as NOT single_session (fail-safe)."""
    r = resolve_gate_policy("project.interview", mode="typo_session")
    assert r["effective_policy"] == INTERACTIVE


def test_single_session_auto_default_proceeds():
    r = resolve_gate_policy("project.interview", mode=SINGLE_SESSION)
    assert r["effective_policy"] == "auto-default"
    assert r["should_stop"] is False
    assert r["default_answer"]  # non-empty


def test_single_session_orchestrator_approve_stops():
    r = resolve_gate_policy("design.preview-approval", mode=SINGLE_SESSION)
    assert r["effective_policy"] == "orchestrator-approve"
    assert r["should_stop"] is True
    assert r["default_answer"] is None


def test_single_session_hard_stop_stops():
    r = resolve_gate_policy("deploy.prod-deploy-confirm", mode=SINGLE_SESSION)
    assert r["effective_policy"] == "hard-stop"
    assert r["should_stop"] is True
    assert r["constitution"] is True


def test_resolver_unknown_gate_raises():
    with pytest.raises(KeyError):
        resolve_gate_policy("project.does-not-exist", mode=SINGLE_SESSION)


def test_resolver_never_auto_answers_a_constitution_gate():
    """Defense-in-depth: no constitution gate ever resolves to a proceed."""
    catalog = load_catalog()
    for gid, g in catalog["gates"].items():
        if g["constitution"]:
            r = resolve_gate_policy(gid, mode=SINGLE_SESSION, catalog=catalog)
            assert r["should_stop"] is True
            assert r["default_answer"] is None


# --------------------------------------------------------------------------- #
# Per-phase dry-run (AC: "dry-run test per phase")
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("phase", list(COVERED_PHASES))
def test_dry_run_per_phase(phase):
    """Resolve every gate of a phase under single_session; the honoring contract
    holds: auto-default proceeds with a default, everything else stops and never
    carries a default."""
    catalog = load_catalog()
    phase_gates = {gid: g for gid, g in catalog["gates"].items() if g["phase"] == phase}
    assert phase_gates, f"phase {phase} has no gates"
    for gid in phase_gates:
        r = resolve_gate_policy(gid, mode=SINGLE_SESSION, catalog=catalog)
        assert r["phase"] == phase
        if r["effective_policy"] == "auto-default":
            assert r["should_stop"] is False
            assert r["default_answer"]
        else:
            assert r["effective_policy"] in ("orchestrator-approve", "hard-stop")
            assert r["should_stop"] is True
            assert r["default_answer"] is None


# --------------------------------------------------------------------------- #
# Mode resolution + run_config round-trip (Boundary Probe / touches_io_boundary)
# --------------------------------------------------------------------------- #

def test_mode_precedence_explicit_wins():
    assert effective_mode(explicit=SINGLE_SESSION, env=None, project_root=None) == SINGLE_SESSION
    assert effective_mode(explicit="multi_session", env=SINGLE_SESSION, project_root=None) == "multi_session"


def test_mode_precedence_env_over_config(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"mode": "multi_session"}), encoding="utf-8"
    )
    assert effective_mode(explicit=None, env=SINGLE_SESSION, project_root=tmp_path) == SINGLE_SESSION


def test_mode_default_when_nothing_set(tmp_path):
    assert effective_mode(explicit=None, env=None, project_root=tmp_path) == DEFAULT_RUN_MODE
    assert effective_mode(explicit=None, env=None, project_root=None) == DEFAULT_RUN_MODE


@pytest.mark.parametrize("mode", ["single_session", "multi_session"])
def test_run_config_mode_round_trip(tmp_path, mode):
    """Boundary Probe: a mode written to run_config reads back identically, and
    the resolver's effective_policy honours it end-to-end."""
    cfg = tmp_path / "shipwright_run_config.json"
    cfg.write_text(json.dumps({"schemaVersion": 2, "mode": mode}), encoding="utf-8")
    assert read_run_config_mode(tmp_path) == mode
    resolved = effective_mode(explicit=None, env=None, project_root=tmp_path)
    assert resolved == mode
    r = resolve_gate_policy("project.interview", mode=resolved)
    if mode == SINGLE_SESSION:
        assert r["effective_policy"] == "auto-default"
    else:
        assert r["effective_policy"] == INTERACTIVE


def test_read_run_config_mode_missing_or_modeless(tmp_path):
    assert read_run_config_mode(tmp_path) == DEFAULT_RUN_MODE  # no config
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"schemaVersion": 2}), encoding="utf-8"
    )
    assert read_run_config_mode(tmp_path) == DEFAULT_RUN_MODE  # mode-less legacy


def test_read_run_config_mode_survives_corrupt_json(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    assert read_run_config_mode(tmp_path) == DEFAULT_RUN_MODE


# --------------------------------------------------------------------------- #
# Doc generation
# --------------------------------------------------------------------------- #

def test_render_markdown_mentions_every_gate():
    catalog = load_catalog()
    md = render_catalog_markdown(catalog)
    for gid in catalog["gates"]:
        assert gid in md, f"{gid} missing from generated doc"
    for policy in POLICIES:
        assert policy in md


def test_render_markdown_is_deterministic():
    assert render_catalog_markdown(load_catalog()) == render_catalog_markdown(load_catalog())


def test_render_markdown_is_pure_ascii():
    """The doc must be ASCII so it round-trips through any shell redirect
    (incl. PowerShell's UTF-16 default) — the committed regen relies on it."""
    md = render_catalog_markdown(load_catalog())
    non_ascii = [c for c in md if ord(c) > 127]
    assert not non_ascii, f"render leaked non-ASCII chars: {sorted(set(non_ascii))}"
