"""Consensus tests for the canonical Shipwright-project predicate.

iterate-2026-06-12-canonical-project-predicate: every hook that decides the
greenfield/foreign boundary ("is this directory a Shipwright-managed project?")
MUST delegate to ``lib.project_root.is_shipwright_project`` so a tree carrying
any single marker is classified IDENTICALLY everywhere. Before consolidation the
five sites used four different marker sets (run-only / run+build / 5-config /
5-config+agent_docs), so an ``agent_docs``-only or ``project_config``-only tree
was a project to some hooks and foreign to others.

conftest.py puts ``shared/scripts`` on ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hooks import aggregate_triage_on_stop, generate_handoff_on_stop, track_tool_calls
from lib import drift_anchor
from lib import phase_quality as pq
from lib.project_root import _is_shipwright_project, is_shipwright_project, resolve_project_root


# Every predicate that gates a hook on "is this a Shipwright project?".
# Signature: ``(Path) -> bool``. They must all be the canonical predicate
# (directly or via a thin delegating wrapper). ``drift_anchor`` is the F7 drift
# guard (PR #200): it delegates to ``project_root._is_shipwright_project`` (the
# alias), so on the normal path it agrees with the canonical boundary too.
PREDICATES = {
    "project_root": is_shipwright_project,
    "project_root._is_shipwright_project (alias)": _is_shipwright_project,
    "phase_quality": pq.is_shipwright_project,
    "track_tool_calls": track_tool_calls._is_shipwright_project,
    "aggregate_triage_on_stop": aggregate_triage_on_stop.is_shipwright_project,
    "generate_handoff_on_stop": generate_handoff_on_stop.is_shipwright_project,
    "drift_anchor": drift_anchor.is_shipwright_project,
}


def _touch(path: Path, name: str) -> None:
    (path / name).write_text("{}", encoding="utf-8")


def _mk_agent_docs(path: Path) -> None:
    (path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)


# (id, setup_fn, canonical verdict) — the single boundary every hook must share.
SCENARIOS = [
    ("empty", lambda p: None, False),
    ("run_config", lambda p: _touch(p, "shipwright_run_config.json"), True),
    ("project_config", lambda p: _touch(p, "shipwright_project_config.json"), True),
    ("plan_config", lambda p: _touch(p, "shipwright_plan_config.json"), True),
    ("build_config", lambda p: _touch(p, "shipwright_build_config.json"), True),
    ("events_jsonl", lambda p: _touch(p, "shipwright_events.jsonl"), True),
    ("agent_docs_dir", _mk_agent_docs, True),
    ("foreign_only", lambda p: _touch(p, "package.json"), False),
]


@pytest.mark.parametrize(
    "label,setup,expected",
    [pytest.param(s[0], s[1], s[2], id=s[0]) for s in SCENARIOS],
)
def test_all_predicates_agree(tmp_path: Path, label, setup, expected):
    """Every hook predicate returns the IDENTICAL verdict for each marker shape,
    and that verdict equals the canonical (broad) boundary."""
    setup(tmp_path)
    results = {name: bool(fn(tmp_path)) for name, fn in PREDICATES.items()}
    assert all(v == expected for v in results.values()), (
        f"[{label}] predicates disagree — expected {expected} everywhere, got {results}"
    )


# ---------------------------------------------------------------------------
# Canonical semantics + fail-closed contract
# ---------------------------------------------------------------------------


def test_canonical_detects_agent_docs_dir(tmp_path: Path):
    _mk_agent_docs(tmp_path)
    assert is_shipwright_project(tmp_path) is True


def test_canonical_fail_closed_agent_docs_is_a_file(tmp_path: Path):
    """``.shipwright/agent_docs`` as a FILE (not a directory) is NOT a project."""
    (tmp_path / ".shipwright").mkdir()
    (tmp_path / ".shipwright" / "agent_docs").write_text("x", encoding="utf-8")
    assert is_shipwright_project(tmp_path) is False


def test_canonical_fail_closed_missing_path(tmp_path: Path):
    assert is_shipwright_project(tmp_path / "does_not_exist") is False


def test_canonical_returns_real_bool(tmp_path: Path):
    _touch(tmp_path, "shipwright_run_config.json")
    # identity check — callers/tests rely on a genuine bool, not a truthy object
    assert is_shipwright_project(tmp_path) is True


# ---------------------------------------------------------------------------
# resolve_project_root tie-break (config-bearing sibling wins over agent_docs-only)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)


def test_resolver_detects_agent_docs_only_subdir(tmp_path: Path, monkeypatch):
    sub = tmp_path / "app"
    (sub / ".shipwright" / "agent_docs").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert resolve_project_root() == sub


def test_resolver_prefers_config_sibling_over_agent_docs_only(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "real"
    cfg.mkdir()
    _touch(cfg, "shipwright_run_config.json")
    stray = tmp_path / "stray"
    (stray / ".shipwright" / "agent_docs").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    # config-bearing sibling wins; a stray agent_docs dir must NOT turn a clean
    # resolution into a multi-candidate ValueError.
    assert resolve_project_root() == cfg


def test_resolver_multiple_config_subdirs_still_raises(tmp_path: Path, monkeypatch):
    for n in ("a", "b"):
        d = tmp_path / n
        d.mkdir()
        _touch(d, "shipwright_run_config.json")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="Multiple Shipwright projects"):
        resolve_project_root()


# ---------------------------------------------------------------------------
# Back-compat: the historical private name is a thin alias of the canonical one
# (external importers — e.g. the drift-anchor F7 guard — import the `_` name).
# ---------------------------------------------------------------------------


def test_private_alias_is_the_canonical_predicate():
    assert _is_shipwright_project is is_shipwright_project


# ---------------------------------------------------------------------------
# Degraded-import fallbacks — each hook preserves ITS OWN pre-consolidation
# behaviour when the canonical import is unavailable (defensive, ~unreachable in
# the real runtime but contractually pinned).
# ---------------------------------------------------------------------------


@pytest.fixture
def _force_canonical_import_failure(monkeypatch):
    """Make ``from lib.project_root import is_shipwright_project`` raise
    ImportError inside the hooks (None in sys.modules => ImportError)."""
    monkeypatch.setitem(sys.modules, "lib.project_root", None)


def test_track_tool_calls_fallback_preserves_run_plus_build(
    tmp_path: Path, _force_canonical_import_failure
):
    """track_tool_calls keeps a lazy import + fallback (it is a high-frequency
    PostToolUse hook). Degraded fallback = its prior markers (run OR build),
    NOT narrower. (aggregate_triage / generate_handoff import the canonical at
    module top — no per-call fallback — so they have no degraded path to pin.)"""
    build_only = tmp_path / "build"
    build_only.mkdir()
    _touch(build_only, "shipwright_build_config.json")
    assert track_tool_calls._is_shipwright_project(build_only) is True

    docs_only = tmp_path / "docs"
    (docs_only / ".shipwright" / "agent_docs").mkdir(parents=True)
    # prior behaviour never keyed on agent_docs → stays False on the degraded path
    assert track_tool_calls._is_shipwright_project(docs_only) is False

    assert track_tool_calls._is_shipwright_project(tmp_path / "empty") is False
