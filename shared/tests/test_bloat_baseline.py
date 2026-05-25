"""Tests for shared/scripts/lib/bloat_baseline.py.

Single producer for the bloat-allowlist schema + classification logic.
Consumed by Phase-0 inventory, /shipwright-adopt's baseline_generator,
and the bloat_gate_on_stop hook. Tests cover classification, per-
filetype limit selection, scan, atomic load, path normalization, and
fail-open behaviour on malformed input.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import bloat_baseline as bb  # noqa: E402


# ---------------------------------------------------------------------
# classify_md
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "rel,expected",
    [
        ("plugins/shipwright-build/skills/build/SKILL.md", "runtime-prompt"),
        ("plugins/shipwright-iterate/skills/iterate/SKILL.md", "runtime-prompt"),
        ("CLAUDE.md", "runtime-prompt"),
        ("plugins/shipwright-build/agents/code-reviewer.md", "runtime-prompt"),
        ("shared/prompts/code_reviewer.md", "runtime-prompt"),
        # Backslash variant — Windows path
        (r"plugins\shipwright-build\agents\code-reviewer.md", "runtime-prompt"),
        # Plain docs / non-runtime
        ("docs/guide.md", "doc"),
        ("docs/hooks-and-pipeline.md", "doc"),
        ("README.md", "doc"),
        (".shipwright/agent_docs/conventions.md", "doc"),
        # Non-markdown
        ("plugins/shipwright-iterate/scripts/foo.py", None),
        ("foo.json", None),
    ],
)
def test_classify_md(rel, expected):
    assert bb.classify_md(rel) == expected


# ---------------------------------------------------------------------
# limit_for
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "rel,expected",
    [
        # Runtime-prompts -> 400
        ("plugins/shipwright-build/skills/build/SKILL.md", 400),
        ("CLAUDE.md", 400),
        ("plugins/shipwright-build/agents/code-reviewer.md", 400),
        # Source -> 300
        ("plugins/foo/scripts/bar.py", 300),
        ("plugins/foo/scripts/bar.ts", 300),
        ("plugins/foo/scripts/bar.tsx", 300),
        ("plugins/foo/scripts/bar.js", 300),
        ("plugins/foo/scripts/bar.jsx", 300),
        # Test files -> still source (300) — campaign §4.1
        ("plugins/foo/tests/test_bar.py", 300),
        ("client/src/foo.test.ts", 300),
        ("client/src/foo.spec.tsx", 300),
        # Plain docs -> None (caller skips)
        ("docs/guide.md", None),
        # Non-source, non-runtime -> None
        ("foo.json", None),
        ("foo.lock", None),
    ],
)
def test_limit_for(rel, expected):
    assert bb.limit_for(rel) == expected


# ---------------------------------------------------------------------
# should_skip
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "rel,expected",
    [
        # Skipped: lock files, vendored, generated, migrations, plain docs
        ("package-lock.json", True),
        ("node_modules/foo/bar.js", True),
        ("dist/foo.js", True),
        ("build/foo.js", True),
        ("supabase/migrations/001_init.sql", True),
        ("foo.min.js", True),
        ("docs/guide.md", True),
        ("README.md", True),
        # NOT skipped: runtime prompts, source, tests
        ("plugins/shipwright-build/skills/build/SKILL.md", False),
        ("CLAUDE.md", False),
        ("plugins/foo/agents/x.md", False),
        ("plugins/foo/scripts/bar.py", False),
        ("plugins/foo/tests/test_bar.py", False),
    ],
)
def test_should_skip(rel, expected):
    assert bb.should_skip(rel) == expected


# ---------------------------------------------------------------------
# normalize_path
# ---------------------------------------------------------------------

def test_normalize_path_separator():
    assert bb.normalize_path("plugins\\foo\\bar.py") == "plugins/foo/bar.py"
    assert bb.normalize_path("plugins/foo/bar.py") == "plugins/foo/bar.py"


def test_normalize_path_idempotent():
    once = bb.normalize_path("plugins\\foo\\bar.py")
    twice = bb.normalize_path(once)
    assert once == twice


def test_normalize_path_strips_leading_dot_slash():
    assert bb.normalize_path("./plugins/foo.py") == "plugins/foo.py"


# ---------------------------------------------------------------------
# scan() — walks project root, emits one entry per oversize tracked file
# ---------------------------------------------------------------------

def _write_lines(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n" * n, encoding="utf-8")


def test_scan_finds_oversize_source(tmp_path):
    _write_lines(tmp_path / "plugins" / "foo" / "scripts" / "big.py", 401)
    _write_lines(tmp_path / "plugins" / "foo" / "scripts" / "tiny.py", 10)
    entries = bb.scan(tmp_path)
    paths = {e["path"] for e in entries}
    assert "plugins/foo/scripts/big.py" in paths
    assert "plugins/foo/scripts/tiny.py" not in paths


def test_scan_finds_oversize_runtime_prompt(tmp_path):
    _write_lines(
        tmp_path / "plugins" / "shipwright-build" / "skills" / "build" / "SKILL.md",
        500,
    )
    entries = bb.scan(tmp_path)
    paths = {e["path"] for e in entries}
    assert "plugins/shipwright-build/skills/build/SKILL.md" in paths


def test_scan_does_not_grandfather_runtime_under_limit(tmp_path):
    _write_lines(
        tmp_path / "plugins" / "shipwright-build" / "skills" / "build" / "SKILL.md",
        350,  # under 400 — should not appear
    )
    entries = bb.scan(tmp_path)
    assert entries == []


def test_scan_skips_plain_markdown(tmp_path):
    _write_lines(tmp_path / "docs" / "guide.md", 5000)
    assert bb.scan(tmp_path) == []


def test_scan_skips_node_modules(tmp_path):
    _write_lines(tmp_path / "node_modules" / "foo" / "bar.js", 5000)
    assert bb.scan(tmp_path) == []


def test_scan_skips_dist_and_build(tmp_path):
    _write_lines(tmp_path / "dist" / "foo.js", 1000)
    _write_lines(tmp_path / "build" / "foo.js", 1000)
    assert bb.scan(tmp_path) == []


def test_scan_entry_shape(tmp_path):
    _write_lines(tmp_path / "plugins" / "foo" / "scripts" / "big.py", 412)
    entries = bb.scan(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert e["path"] == "plugins/foo/scripts/big.py"
    assert e["limit"] == 300
    assert e["current"] == 412
    assert e["state"] == "grandfathered"
    assert e["adr"] is None


def test_scan_normalizes_path_separator_on_windows(tmp_path):
    _write_lines(tmp_path / "plugins" / "foo" / "scripts" / "big.py", 401)
    entries = bb.scan(tmp_path)
    assert all("\\" not in e["path"] for e in entries)


# ---------------------------------------------------------------------
# load() — reads shipwright_bloat_baseline.json, fail-open on errors
# ---------------------------------------------------------------------

def test_load_returns_none_when_missing(tmp_path):
    assert bb.load(tmp_path) is None


def test_load_returns_doc_when_present(tmp_path):
    doc = {
        "version": 1,
        "entries": [
            {"path": "foo.py", "limit": 300, "current": 410,
             "state": "grandfathered", "adr": None},
        ],
    }
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps(doc), encoding="utf-8",
    )
    loaded = bb.load(tmp_path)
    assert loaded is not None
    assert loaded["version"] == 1
    assert loaded["entries"][0]["path"] == "foo.py"


def test_load_fail_open_on_malformed_json(tmp_path, capsys):
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        "{not valid json", encoding="utf-8",
    )
    assert bb.load(tmp_path) is None
    err = capsys.readouterr().err
    assert "bloat_baseline" in err.lower() or "malformed" in err.lower()


def test_load_fail_open_on_non_list_entries(tmp_path, capsys):
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": {"oops": "dict"}}),
        encoding="utf-8",
    )
    assert bb.load(tmp_path) is None
    err = capsys.readouterr().err
    assert err.strip() != ""


def test_load_normalises_path_separators(tmp_path):
    """Baseline path written with backslashes is normalised on load."""
    doc = {
        "version": 1,
        "entries": [
            {"path": r"plugins\foo\bar.py", "limit": 300, "current": 400,
             "state": "grandfathered", "adr": None},
        ],
    }
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps(doc), encoding="utf-8",
    )
    loaded = bb.load(tmp_path)
    assert loaded is not None
    assert loaded["entries"][0]["path"] == "plugins/foo/bar.py"


# ---------------------------------------------------------------------
# Schema-contract round-trip: scan -> file -> load -> match
# ---------------------------------------------------------------------

def test_round_trip_scan_write_load_match(tmp_path):
    _write_lines(tmp_path / "plugins" / "foo" / "scripts" / "big.py", 412)
    _write_lines(
        tmp_path / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md",
        450,
    )
    entries = bb.scan(tmp_path)
    doc = {"version": 1, "entries": entries}
    bb.write_baseline(tmp_path, doc)
    loaded = bb.load(tmp_path)
    assert loaded is not None
    loaded_paths = sorted(e["path"] for e in loaded["entries"])
    assert loaded_paths == sorted(e["path"] for e in entries)


def test_write_baseline_is_atomic(tmp_path):
    """tmp+rename ensures readers never see a partial file."""
    doc = {"version": 1, "entries": []}
    bb.write_baseline(tmp_path, doc)
    target = tmp_path / "shipwright_bloat_baseline.json"
    assert target.exists()
    # Atomic write must leave no orphan tmp file.
    assert not any(
        p.name.startswith("shipwright_bloat_baseline.json.tmp")
        for p in tmp_path.iterdir()
    )


def test_marker_ttl_seconds_constant_is_one_hour():
    assert bb.MARKER_TTL_SECONDS == 3600
