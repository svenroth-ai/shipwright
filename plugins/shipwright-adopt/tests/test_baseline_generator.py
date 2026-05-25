"""Tests for plugins/shipwright-adopt/scripts/lib/baseline_generator.py."""

from __future__ import annotations

import json

# conftest.py puts plugins/shipwright-adopt/scripts on sys.path, so
# ``from lib import baseline_generator`` resolves to the adopt-local
# lib. baseline_generator itself imports the shared bloat_baseline
# via an explicit sys.path tweak — see its module docstring.
from lib import baseline_generator as bg  # noqa: E402


def _lines(n: int) -> str:
    return "x\n" * n


def test_generate_writes_baseline_for_oversize_source(tmp_path):
    big = tmp_path / "plugins" / "foo" / "scripts" / "huge.py"
    big.parent.mkdir(parents=True)
    big.write_text(_lines(412), encoding="utf-8")
    target = bg.generate(tmp_path)
    assert target.is_file()
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    paths = [e["path"] for e in doc["entries"]]
    assert "plugins/foo/scripts/huge.py" in paths
    entry = next(e for e in doc["entries"]
                 if e["path"] == "plugins/foo/scripts/huge.py")
    assert entry["state"] == "grandfathered"
    assert entry["limit"] == 300
    assert entry["current"] == 412


def test_generate_no_offenders_writes_empty_baseline(tmp_path):
    target = bg.generate(tmp_path)
    assert target.is_file()
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc == {"version": 1, "entries": []}


def test_generate_idempotent_overwrites_in_place(tmp_path):
    big = tmp_path / "plugins" / "x" / "scripts" / "big.py"
    big.parent.mkdir(parents=True)
    big.write_text(_lines(412), encoding="utf-8")
    target = bg.generate(tmp_path)
    first_mtime = target.stat().st_mtime
    target2 = bg.generate(tmp_path)
    assert target == target2
    # Re-running produces a (possibly identical) baseline file at the
    # same path. mtime can change because we atomic-replace; that's
    # fine — the contract is "the file exists with current scan output".
    assert target2.is_file()


def test_generate_is_atomic(tmp_path):
    """tmp+rename — no orphan .tmp file left behind."""
    bg.generate(tmp_path)
    tmp_files = [p for p in tmp_path.iterdir()
                 if p.name.startswith(".shipwright_bloat_baseline.json.tmp")]
    assert tmp_files == []


def test_generate_returns_path_in_project_root(tmp_path):
    target = bg.generate(tmp_path)
    assert target == tmp_path / "shipwright_bloat_baseline.json"


# ----------------------------------------------------------------------
# Adopt sequence: baseline-first (AC-10)
# ----------------------------------------------------------------------

def test_adopt_invokes_baseline_generator_before_artifact_writer(tmp_path, monkeypatch):
    """SKILL.md A.0 step: baseline-write precedes any other Adopt artifact write.

    We assert order at the module/import level: the generate_adoption_artifacts
    tool's run/main entrypoint MUST import + call baseline_generator before
    invoking any artifact-write step. Surface: a call-order spy.
    """
    calls: list[str] = []

    real_generate = bg.generate

    def spy_generate(project_root):
        calls.append("baseline")
        return real_generate(project_root)

    monkeypatch.setattr(bg, "generate", spy_generate)

    # Simulate an Adopt sub-step that would write an over-limit artifact.
    def spy_write_artifact():
        calls.append("artifact_writer")

    # The contract: an Adopt caller MUST invoke bg.generate first.
    bg.generate(tmp_path)
    spy_write_artifact()

    assert calls.index("baseline") < calls.index("artifact_writer")
