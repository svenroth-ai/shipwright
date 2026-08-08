"""Git-history backfill + per-entry provenance tests for event_context_index.

Split out of test_event_context.py (iterate-2026-08-07-events-context-backfill-keys)
once that file crossed the 300-line guideline — see
.shipwright/planning/iterate/2026-08-07-events-context-backfill-keys.md.
Coverage-envelope aggregate tests (coverage.fields.*, missing_work_completed)
moved out again into test_event_context_coverage_envelope.py
(iterate-2026-08-08-coverage-envelope-split) for the same reason.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.area_catalog import seed_brownfield  # noqa: E402
from lib.event_context_index import build_index, index_path, load_or_rebuild_index  # noqa: E402
from lib.event_context_query import query_events  # noqa: E402
from tests._event_context_fixtures import commit as _commit  # noqa: E402
from tests._event_context_fixtures import git as _git  # noqa: E402
from tests._event_context_fixtures import init_repo as _init_repo  # noqa: E402
from tests._event_context_fixtures import write_events as _write_events  # noqa: E402


def test_git_backfill_populates_commit_and_changed_files_with_derived_provenance(tmp_path: Path) -> None:
    (tmp_path / "src/auth").mkdir(parents=True)
    (tmp_path / "src/auth/login.py").write_text("", encoding="utf-8")
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    sha = _commit(tmp_path, "src/auth/login.py", "x",
                 "feat(auth): login\n\nRun-ID: run-backfill-me")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-backfill-me",
         "description": "no changed_files/commit on the event itself"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["commit"] == sha
    assert entry["changed_files"] == ["src/auth/login.py"]
    assert entry["area_ids"] == ["src"]
    assert entry["provenance"]["commit"] == "derived"
    assert entry["provenance"]["changed_files"] == "derived"
    assert entry["provenance"]["area_ids"] == "derived"
    assert "extraction" not in entry


def test_empty_diff_backfilled_commit_is_derived_not_unavailable(tmp_path: Path) -> None:
    """A matched, non-merge commit with an EMPTY diff must still mark
    changed_files "derived" (it is a computed fact -- this commit really did
    change nothing) rather than "unavailable", which the empty-list check
    alone (`if declared_raw_paths: ... elif backfill: ...`) already gets
    right structurally; this pins the case explicitly (external review
    openai finding, iterate-2026-08-07-events-context-backfill-keys)."""
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "--allow-empty", "-q", "-m",
         "chore: no-op\n\nRun-ID: run-empty-diff")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-empty-diff"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["changed_files"] == []
    assert entry["provenance"]["changed_files"] == "derived"


def test_changed_files_matching_zero_catalog_areas_is_derived_not_unavailable(tmp_path: Path) -> None:
    """Backfilled changed_files that match NO catalog area must still mark
    area_ids "derived" with an empty list, not "unavailable" -- the
    provenance rule keys off whether there WERE changed files, not whether
    any of them happened to match an area (external review openai finding,
    iterate-2026-08-07-events-context-backfill-keys)."""
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    (tmp_path / "unmapped").mkdir()
    (tmp_path / "unmapped/outside.py").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "unmapped/outside.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: outside\n\nRun-ID: run-no-area-match")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-no-area-match"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["changed_files"] == ["unmapped/outside.py"]
    assert entry["area_ids"] == []
    assert entry["provenance"]["area_ids"] == "derived"


def test_declared_commit_and_changed_files_are_untouched_by_backfill(tmp_path: Path) -> None:
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _commit(tmp_path, "other.py", "x", "feat: other\n\nRun-ID: run-declared")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-declared",
         "commit": "already-declared-sha", "changed_files": ["declared/path.py"]},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["commit"] == "already-declared-sha"
    assert entry["changed_files"] == ["declared/path.py"]
    assert entry["provenance"]["commit"] == "declared"
    assert entry["provenance"]["changed_files"] == "declared"


def test_no_matching_commit_resolves_unavailable_provenance(tmp_path: Path) -> None:
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _commit(tmp_path, "unrelated.py", "x", "chore: unrelated, no run id trailer")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-does-not-exist"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["commit"] == ""
    assert entry["changed_files"] == []
    assert entry["provenance"]["commit"] == "unavailable"
    assert entry["provenance"]["changed_files"] == "unavailable"
    assert entry["provenance"]["area_ids"] == "unavailable"


def test_merge_only_match_resolves_unavailable_not_derived(tmp_path: Path) -> None:
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "1", "chore: init")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _commit(tmp_path, "b.txt", "2", "feat: b")
    _git(tmp_path, "checkout", "-q", "main")
    _commit(tmp_path, "c.txt", "3", "feat: c")
    _git(tmp_path, "merge", "--no-ff", "-q", "feature",
        "-m", "Merge feature\n\nRun-ID: run-merge-only")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-merge-only"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["provenance"]["commit"] == "unavailable"
    assert entry["provenance"]["changed_files"] == "unavailable"


def test_backfilled_paths_flow_through_the_same_normalize_path_pipeline(tmp_path: Path) -> None:
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/ok.py").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "src/ok.py")
    _git(tmp_path, "commit", "-q", "-m", "feat: ok\n\nRun-ID: run-hostile-git")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-hostile-git"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    # git itself never emits a "../" path, so this pins the well-formed case;
    # what matters is that the backfilled raw path reaches the SAME
    # normalize_path() call declared paths already go through
    # (test_hostile_event_text_is_untrusted_redacted_and_bounded pins the
    # hostile-declared-path case in test_event_context.py) rather than a
    # second, unguarded inlet.
    assert entry["changed_files"] == ["src/ok.py"]


def test_boundary_probe_provenance_and_coverage_survive_the_json_round_trip(tmp_path: Path) -> None:
    """Affected Boundaries: build_index() writes JSON, load_or_rebuild_index()
    reads it back from the CACHE path (not a rebuild) — provenance/coverage
    must survive that write-then-read round trip byte-identically, since a
    JSON round trip is exactly where a boundary bug would surface (e.g. a
    set serialized with nondeterministic key order, or a field silently
    dropped by an incomplete schema)."""
    (tmp_path / "src/auth").mkdir(parents=True)
    (tmp_path / "src/auth/login.py").write_text("", encoding="utf-8")
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    sha = _commit(tmp_path, "src/auth/login.py", "x", "feat(auth): login\n\nRun-ID: run-probe")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-probe"},
    ])
    written = build_index(tmp_path)  # writes JSON to index_path(tmp_path)
    loaded, source = load_or_rebuild_index(tmp_path)  # reads it back
    assert source == "cache"
    assert loaded == written
    assert loaded["entries"][0]["commit"] == sha
    assert loaded["entries"][0]["provenance"] == written["entries"][0]["provenance"]
    assert loaded["coverage"] == written["coverage"]


def test_new_commit_landing_after_index_build_triggers_rebuild_not_stale_cache(tmp_path: Path) -> None:
    """A commit carrying a Run-ID: trailer can land AFTER build_index() ran and
    BEFORE any new event is appended (F5b writes work_completed before F6
    creates the commit). The event-log fingerprint alone would keep serving a
    stale 'unavailable' provenance forever; the git-state re-check added to
    load_or_rebuild_index (code review, iterate-2026-08-07-events-context-
    backfill-keys) must catch it instead."""
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "1", "chore: init, no run id yet")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-lands-later"},
    ])
    first = build_index(tmp_path)
    assert first["entries"][0]["provenance"]["commit"] == "unavailable"

    sha = _commit(tmp_path, "src/late.py", "x", "feat: late\n\nRun-ID: run-lands-later")

    loaded, source = load_or_rebuild_index(tmp_path)
    assert source == "rebuild"
    entry = loaded["entries"][0]
    assert entry["commit"] == sha
    assert entry["provenance"]["commit"] == "derived"


def test_stale_v1_cache_shape_is_rejected_and_rebuilt(tmp_path: Path) -> None:
    seed_brownfield(tmp_path)
    _write_events(tmp_path, [
        {"event_id": "old", "type": "work_completed", "commit": "abc123", "tree": "tree123",
         "changed_files": ["src/auth/login.py"],
         "affected_frs": ["FR-01.01"], "description": "Implemented auth"},
    ])
    (tmp_path / "src/auth").mkdir(parents=True)
    (tmp_path / "src/auth/login.py").write_text("", encoding="utf-8")
    built = build_index(tmp_path)
    stale = dict(built)
    stale["index_schema_version"] = 1
    for entry in stale["entries"]:
        entry.pop("provenance", None)
        entry["extraction"] = {"confidence": "low"}
    del stale["coverage"]
    index_path(tmp_path).write_text(json.dumps(stale), encoding="utf-8")
    result = query_events(tmp_path, run_id="stale-cache-check",
                          changed_files=["src/auth/login.py"])
    assert result["index"]["source"] == "rebuild"
