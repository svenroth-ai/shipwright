"""``tools/backfill_ac_provenance.py``'s ``main()``-level snapshot/restore
guarantees: an orphan tag, an uncaught mid-batch write exception, and a
SILENTLY-reported write failure must all roll back every file the run
touched, not just the one that failed. Split out of
``test_backfill_ac_provenance_cli.py`` at the 300-LOC bloat-baseline
threshold (same precedent as that file's own ``_git.py`` /
``_apply_skips.py`` siblings) -- the pure-logic tests (conflict marking,
apply/validate, status accounting) stay in the sibling file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

_SPEC = importlib.util.spec_from_file_location(
    "backfill_ac_provenance_cli_rollback", _TOOLS / "backfill_ac_provenance.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[union-attr]


def _candidate(fr_id, ac_id, files, status="candidate"):
    return {"fr_id": fr_id, "ac_id": ac_id, "slug": f"iterate-{fr_id}-{ac_id}".lower(),
             "commit": "deadbeef", "status": status, "test_files": list(files)}


_UNTAGGED = '''"""A fixture test module."""
from __future__ import annotations


def test_one():
    assert True
'''

_BARE_TAGGED = '''"""A fixture test module with an existing bare tag."""
from __future__ import annotations

import pytest


@pytest.mark.covers("FR-01.01")
def test_one():
    assert True
'''

_MINTED_SPEC = (
    "### FR-01.01 — /shipwright-run\n\n"
    "- (E) [AC01] Given a described change, when the pipeline is run, then\n"
    "  the phases are carried out in order.\n"
)


def test_main_rolls_back_every_touched_file_when_an_orphan_tag_is_written(tmp_path, monkeypatch):
    """External plan review + external code review (P3.4, glm low / openai
    medium): a post-write orphan must not leave a half-applied tree behind a
    non-zero exit -- every file this run touched is restored byte-for-byte."""
    rel = "tests/test_untagged.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_UNTAGGED, encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("### FR-01.01 — /shipwright-run\n\nno minted ACs here.\n", encoding="utf-8")

    fake_report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel).read_text(encoding="utf-8") == _UNTAGGED  # restored, not left half-written


def test_main_rolls_back_a_successful_bare_tag_upgrade_when_a_sibling_insertion_write_fails(tmp_path, monkeypatch):
    """Tier-3 CI-gate re-review (P3.4 high): ``apply_writes`` can report a
    write failure for an insertion candidate AFTER a SIBLING candidate's
    bare-tag upgrade has already been written directly to disk in the same
    ``--write`` batch. ``main()`` must not report success -- the
    already-applied upgrade must be rolled back too, exactly like an orphan
    tag already triggers."""
    rel = "tests/test_bare.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_BARE_TAGGED, encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text(_MINTED_SPEC, encoding="utf-8")

    fake_report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    def fake_apply_upgrades(project_root, report):
        # Simulate the real sequence: THIS candidate's bare-tag upgrade is
        # written directly to disk, then a sibling insertion elsewhere in the
        # same batch fails -- exactly the ordering apply_upgrades itself uses.
        (project_root / rel).write_text(
            _BARE_TAGGED.replace('covers("FR-01.01")', 'covers("FR-01.01/AC01")'), encoding="utf-8")
        return {
            "upgraded_bare_tags": [{"file": rel, "fr_id": "FR-01.01", "ac_id": "AC01",
                                     "slug": "x", "commit": "deadbeef", "tags_upgraded": 1}],
            "inserted_new_tags": [], "skipped": [],
            "tags_upgraded_total": 1, "tags_inserted_total": 0,
            "write_failures_occurred": True,
        }
    monkeypatch.setattr(mod, "apply_upgrades", fake_apply_upgrades)

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel).read_text(encoding="utf-8") == _BARE_TAGGED  # rolled back, not left applied


def test_main_rolls_back_every_touched_file_when_a_write_fails_mid_batch(tmp_path, monkeypatch):
    """Tier-3 CI-gate re-review (P3.4 high): ``apply_upgrades`` writes each
    bare-tag upgrade immediately as it iterates candidates, so an I/O failure
    partway through a multi-file batch previously propagated straight out of
    ``main()`` -- the orphan rollback above only runs on a NORMAL return, so
    a file already written before the failure stayed modified forever. A
    write failure on the SECOND file must restore the FIRST file too."""
    rel_a, rel_b = "tests/test_a.py", "tests/test_b.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel_a).write_text(_BARE_TAGGED, encoding="utf-8")
    (tmp_path / rel_b).write_text(_BARE_TAGGED.replace("test_one", "test_two"), encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text(_MINTED_SPEC, encoding="utf-8")

    fake_report = {"candidates": [
        _candidate("FR-01.01", "AC01", [rel_a]),
        _candidate("FR-01.01", "AC01", [rel_b]),
    ]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    real_write_bytes = Path.write_bytes
    calls = {"n": 0}

    def flaky_write_bytes(self, data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated disk failure")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel_a).read_text(encoding="utf-8") == _BARE_TAGGED       # restored after being written
    assert (tmp_path / rel_b).read_text(encoding="utf-8") == _BARE_TAGGED.replace("test_one", "test_two")
