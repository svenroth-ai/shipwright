"""Empirical calibration launch gate — real OSS repos, opt-in (``-m empirical``).

Excluded from the hermetic default run and the PR gate (the grade plugin's
``addopts = -m 'not empirical'``); a dedicated CI job (network + gh) runs it and
it **gates the public launch** (G5). It REPLAYS recorded fixtures — fully offline
+ deterministic — and asserts grade **bands + relative ordering**, never exact
scores. The engine (``compute_grade``) runs on every replay, so this still catches
rubric regressions. Recording (``--refresh``) is the network path (see
``run_empirical.py`` + the CI launch-gate workflow).

Strict semantics (GPT #6): under CI a pinned entry with no recorded fixture is a
**failure**, not a green skip — a launch gate that silently passes on missing
coverage is worse than none. Locally it degrades to a loud skip.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

import replay  # noqa: E402
from calibration import (  # noqa: E402
    assert_band,
    assert_ordering,
    grade_from_fixture,
    result_for,
)

pytestmark = pytest.mark.empirical

_MANIFEST = Path(__file__).resolve().parent / "repos.yaml"


def _entries() -> list[dict]:
    return yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))["repos"]


def _calibration_entries() -> list[dict]:
    return [e for e in _entries() if e.get("expected_band")]


def _edge_entries() -> list[dict]:
    return [e for e in _entries() if not e.get("expected_band")]


def _strict() -> bool:
    return os.environ.get("CI", "").lower() in ("1", "true")


def _fixture_or_skip(entry: dict) -> dict:
    sha = str(entry["pinned_sha"])
    if not replay.is_pinned_sha(sha):
        pytest.fail(f"{entry['name']}: pinned_sha is not a real 40-hex SHA ({sha!r})")
    cached = replay.replay(f"{entry['name']}@{sha}")
    if cached is None:
        msg = (f"{entry['name']}: no recorded fixture — record it with "
               "`run_empirical.py --refresh`")
        if _strict():
            pytest.fail(msg)  # launch gate: missing coverage is a hard failure
        pytest.skip(msg)
    return cached


@pytest.mark.parametrize("entry", _calibration_entries(), ids=lambda e: e["name"])
def test_real_repo_grade_in_band(entry: dict):
    """Each calibration repo replays to a grade within its expected band."""
    model = grade_from_fixture(_fixture_or_skip(entry))
    assert_band(entry["name"], model, entry["expected_band"])


@pytest.mark.parametrize("entry", _edge_entries(), ids=lambda e: e["name"])
def test_edge_repo_grades_without_crash(entry: dict):
    """Edge cases (monorepo / no-tests / huge / polyglot / non-English) assert only
    ROBUSTNESS: the grader produces a gradeable verdict, never a crash."""
    model = grade_from_fixture(_fixture_or_skip(entry))
    assert model.gradeable


def test_calibration_ordering():
    """Across the calibration tiers, exemplary must out-score average out-score
    poor — the ordering invariant a per-repo band can miss (plan §14)."""
    results = []
    for entry in _calibration_entries():
        cached = replay.replay(f"{entry['name']}@{entry['pinned_sha']}")
        if cached is None:
            if _strict():
                pytest.fail(f"{entry['name']}: no fixture for the ordering check")
            pytest.skip("missing fixtures — record with `run_empirical.py --refresh`")
        results.append(result_for(entry["name"], grade_from_fixture(cached), entry))
    assert_ordering(results)
