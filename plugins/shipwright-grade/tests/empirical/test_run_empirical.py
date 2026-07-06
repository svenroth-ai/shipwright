"""Hermetic end-to-end tests for the empirical runner (DEFAULT suite / PR gate).

These build a synthetic git repo (conftest ``build_repo`` fixtures) and drive the
FULL record → replay → grade → assert → gallery path with **NO network** — so the
mechanism (and the ``run_empirical`` runner) is proven on every PR, while the
real-OSS calibration assertions live in ``test_empirical.py`` (``-m empirical``).

The band a synthetic repo earns is not hard-coded (a cold-repo grade is an
emergent value); the tests observe it and assert the runner's *pass path*, plus
the invariants that must hold regardless of the exact score: JSON round-trip
byte-stability, tier ordering, honest n/a on a no-signal repo, and the
strict-missing-fixture = FAIL rule.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

import run_empirical
from calibration import FixtureVersionError, grade_from_fixture, parse_band_set
from grade_inputs_projector import grade_context_captured
from record import RecordError, project_fixture
from replay import record as record_fixture
from replay import replay as replay_fixture
from repo_context import RepoContext
from resolve_target import resolve_target


def _target(repo: Path):
    return resolve_target(str(repo))


def _fixture(repo: Path, name: str, sha: str) -> dict:
    return project_fixture(_target(repo), name=name, sha=sha, allow_network=False)


def test_project_fixture_replays_to_identical_report(well_run_repo: Path):
    """The offline replay of a recorded fixture reproduces the live ReportModel
    byte-for-byte — the record/replay boundary is exact (touches_io_boundary).

    ``live`` is graded through the SAME (local-only) policy the recorder used, so
    the comparison isolates the record/replay round-trip, not a policy mismatch."""
    from git_exec import remote_url
    from network_policy import resolve_network_policy

    from gh_bridge import run_gh

    target = _target(well_run_repo)
    fixture = project_fixture(target, name="local/well-run", sha="b" * 40, allow_network=False)
    policy = resolve_network_policy(
        allow_network=False, allow_private=False,
        remote_url=remote_url(target.local_path), gh=run_gh)
    live = grade_context_captured(RepoContext(target), policy=policy).report
    # The recorder stamps the canonical repo name over the throwaway-checkout dir
    # name (so the gallery is titled correctly); the round-trip is otherwise exact.
    expected = dataclasses.replace(live, target_display="local/well-run")
    replayed = grade_from_fixture(json.loads(json.dumps(fixture)))  # through JSON
    assert dataclasses.asdict(replayed) == dataclasses.asdict(expected)


def test_fixture_json_round_trips_byte_stable(well_run_repo: Path, tmp_path: Path):
    key = "x/y@" + "c" * 40
    fixture = _fixture(well_run_repo, "x/y", "c" * 40)
    record_fixture(key, fixture, cache_dir=tmp_path)
    back = replay_fixture(key, cache_dir=tmp_path)
    assert back == json.loads(json.dumps(fixture))
    assert grade_from_fixture(back).grade in set("ABCDF")


def test_gh_audit_log_is_redacted(well_run_repo: Path):
    """A recorded fixture stores the gh audit trail without raw response bodies."""
    fixture = _fixture(well_run_repo, "x/y", "d" * 40)
    assert "gh_audit" in fixture
    for entry in fixture["gh_audit"]:
        assert set(entry) <= {"args", "ok", "error", "returncode", "stdout_len"}
        assert "stdout" not in entry  # never the raw body


def test_schema_version_mismatch_is_actionable(well_run_repo: Path):
    fixture = _fixture(well_run_repo, "x/y", "e" * 40)
    fixture["schema_version"] = 999
    with pytest.raises(FixtureVersionError):
        grade_from_fixture(fixture)


def test_no_signal_repo_grades_with_honest_na(no_tests_repo: Path):
    """A no-tests/no-CI repo is graded (never crashes) and its unmeasurable
    dimensions stay n/a — never a fake failing 0."""
    model = grade_from_fixture(_fixture(no_tests_repo, "edge/no-tests", "1" * 40))
    assert model.gradeable
    test_health = next(d for d in model.dimensions if d.key == "test_health")
    assert test_health.score is None  # present-not-executed → honest n/a


def test_ordering_holds_exemplary_over_poor(well_run_repo: Path, messy_repo: Path):
    """well-run (tests + CI + linked commits) must out-score the messy repo — the
    cross-tier ordering invariant the launch gate defends."""
    wr = grade_from_fixture(_fixture(well_run_repo, "ex", "a" * 40))
    ms = grade_from_fixture(_fixture(messy_repo, "po", "f" * 40))
    assert wr.score is not None and ms.score is not None
    assert wr.score > ms.score


def test_run_offline_pass_path_and_gallery(well_run_repo: Path, messy_repo: Path, tmp_path: Path):
    """The runner replays a tmp cache, asserts bands + ordering, writes the gallery."""
    cache = tmp_path / "cache"
    out = tmp_path / "gallery"
    # Observe each synthetic repo's own band, then assert the runner accepts it —
    # this exercises the pass path deterministically without guessing cold grades.
    specs = [(well_run_repo, "ex/repo", "a" * 40, "exemplary"),
             (messy_repo, "po/repo", "f" * 40, "poor")]
    entries = []
    for repo, name, sha, tier in specs:
        fixture = _fixture(repo, name, sha)
        record_fixture(f"{name}@{sha}", fixture, cache_dir=cache)
        band = grade_from_fixture(fixture).grade
        entries.append({"name": name, "pinned_sha": sha, "expected_band": band,
                        "tags": [tier], "url": f"https://github.com/{name}"})

    report = run_empirical.run(
        entries, refresh=False, strict=True, include_ci_only=False,
        out_dir=out, generated_at="2026-01-01 00:00 UTC", cache_dir=cache)
    assert report.ok, (report.failures, report.missing)
    assert len(report.rows) == 2
    assert (out / "index.html").is_file()
    assert (out / "ex_repo.html").is_file()


def test_run_strict_missing_fixture_fails(tmp_path: Path):
    """A pinned entry with no cache is a FAILURE in strict/CI (no green-but-empty
    gate), a loud skip otherwise."""
    entry = {"name": "no/fixture", "pinned_sha": "9" * 40, "expected_band": "A/B",
             "tags": ["exemplary"], "url": "https://github.com/no/fixture"}
    strict = run_empirical.run(
        [entry], refresh=False, strict=True, include_ci_only=False,
        out_dir=tmp_path / "g1", generated_at="t", cache_dir=tmp_path / "empty")
    assert not strict.ok and strict.missing

    lenient = run_empirical.run(
        [entry], refresh=False, strict=False, include_ci_only=False,
        out_dir=tmp_path / "g2", generated_at="t", cache_dir=tmp_path / "empty")
    assert lenient.ok and not lenient.missing


def test_run_edge_ungradeable_fails_the_gate(no_tests_repo: Path, tmp_path: Path, monkeypatch):
    """An edge (robustness-only) entry that regresses to ungradeable ('?') must FAIL
    the CLI gate too — not pass as a silent green 'robust' (parity with the pytest
    gate's test_edge_repo_grades_without_crash)."""
    cache = tmp_path / "cache"
    real = grade_from_fixture(_fixture(no_tests_repo, "edge/x", "3" * 40))
    ungradeable = dataclasses.replace(real, gradeable=False, grade="?", score=None)
    monkeypatch.setattr(run_empirical, "grade_from_fixture", lambda fx: ungradeable)
    record_fixture("edge/x@" + "3" * 40, {"schema_version": 1}, cache_dir=cache)
    entry = {"name": "edge/x", "pinned_sha": "3" * 40, "expected_band": None,
             "tags": ["edge"], "url": "https://github.com/edge/x"}

    report = run_empirical.run(
        [entry], refresh=False, strict=True, include_ci_only=False,
        out_dir=tmp_path / "g", generated_at="t", cache_dir=cache)
    assert not report.ok and report.failures  # ungradeable edge → FAIL, not 'robust'


def test_record_rejects_authoritative_target(well_run_repo: Path, monkeypatch):
    """An authoritative grade (grade_inputs is None) is rejected by the recorder —
    the empirical set expects external cold repos, not a .shipwright/-owning source.
    Monkeypatch the capture to the authoritative shape so the guard is tested
    deterministically without staging a full authoritative source."""
    import record as record_mod
    from grade_inputs_projector import GradeComputation

    authoritative = GradeComputation(report=None, grade_inputs=None, report_extras=None)
    monkeypatch.setattr(record_mod, "grade_context_captured", lambda *a, **k: authoritative)
    with pytest.raises(RecordError):
        project_fixture(_target(well_run_repo), name="auth/repo", sha="2" * 40, allow_network=False)


def test_parse_band_set_ranges():
    assert parse_band_set("A/B") == frozenset({"A", "B"})
    assert parse_band_set("A") == frozenset({"A"})
    assert parse_band_set(None) == frozenset()


def test_fetch_rejects_non_sha_before_network():
    """A non-40-hex pin is rejected up front (input validation, no network)."""
    from fetch import FetchError, open_target_at_sha

    with pytest.raises(FetchError):
        with open_target_at_sha("https://github.com/pallets/flask", "not-a-sha"):
            pass  # pragma: no cover - the context body never runs


def test_recording_gh_passes_through_input_and_redacts():
    from fetch import RecordingGh
    from gh_bridge import GhResult

    seen = {}

    def base(args, *, timeout=30, input_text=None):
        seen["input_text"] = input_text
        return GhResult(ok=True, stdout="secret-body")

    gh = RecordingGh(base)
    gh(["api", "x"], input_text="payload")
    assert seen["input_text"] == "payload"  # passthrough (not dropped)
    assert gh.log[0]["stdout_len"] == len("secret-body")
    assert "stdout" not in gh.log[0]  # body never recorded


def test_preflight_network_flags_missing_git(monkeypatch):
    import fetch

    monkeypatch.setattr(fetch.shutil, "which", lambda name: None)
    problems = fetch.preflight_network()
    assert any("git" in p for p in problems)


def test_preflight_network_flags_unauthenticated_gh(monkeypatch):
    import fetch
    from gh_bridge import GhResult

    monkeypatch.setattr(fetch.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(fetch, "run_gh", lambda *a, **k: GhResult(ok=False, error="auth"))
    problems = fetch.preflight_network()
    assert problems and any("authenticated" in p for p in problems)


def test_preflight_network_ready_when_git_gh_authed(monkeypatch):
    import fetch
    from gh_bridge import GhResult

    monkeypatch.setattr(fetch.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(fetch, "run_gh", lambda *a, **k: GhResult(ok=True))
    assert fetch.preflight_network() == []


def test_summary_table_renders_rows():
    from gallery import SummaryRow, summary_table

    rows = [SummaryRow("a/b", "F", "A/B", "FAIL", 19.9, "a/b"),
            SummaryRow("edge/x", "C", "", "robust", None, "edge/x")]
    out = summary_table(rows)
    assert "repo" in out and "a/b" in out and "n/a" in out  # n/a score cell


def test_main_offline_smoke_renders_selected_report(tmp_path: Path):
    """The CLI replays the committed flask fixture, reaches a verdict, and renders
    that repo's report into the gallery (not just an empty index)."""
    out = tmp_path / "g"
    rc = run_empirical.main(["--repos", "flask", "--out", str(out)])
    assert rc in (0, 1)  # a pass/fail verdict, not a usage error (2)
    assert (out / "index.html").is_file()
    assert (out / "pallets_flask.html").is_file()  # the selected repo's report
