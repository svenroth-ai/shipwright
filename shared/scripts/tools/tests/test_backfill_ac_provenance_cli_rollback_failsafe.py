"""``_backfill_ac_provenance_rollback.py``'s ``apply_with_rollback`` failure-safety
seams: ``validate_applied`` and ``_restore()`` must never leave a partially
applied tree behind an uncaught exception or a silently-dropped restore
failure, and the T4 symlink containment guard must extend to the
snapshot/restore pair too. Split out of ``test_backfill_ac_provenance_cli_rollback.py``
at the 300-LOC bloat-baseline threshold (same precedent as that file's own
split from ``test_backfill_ac_provenance_cli.py``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

_SPEC = importlib.util.spec_from_file_location(
    "backfill_ac_provenance_cli_rollback_failsafe", _TOOLS / "backfill_ac_provenance.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[union-attr]


def _candidate(fr_id, ac_id, files, status="candidate"):
    return {"fr_id": fr_id, "ac_id": ac_id, "slug": f"iterate-{fr_id}-{ac_id}".lower(),
             "commit": "deadbeef", "status": status, "test_files": list(files)}


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


def test_main_rolls_back_when_validate_applied_raises_after_a_successful_write(tmp_path, monkeypatch):
    """Tier-3 CI-gate re-review (P3.4 high): ``validate_applied`` previously
    ran OUTSIDE any ``try``/``except`` -- a transient failure reading spec.md
    AFTER a write already landed on disk crashed ``main()`` uncaught, leaving
    that write un-rolled-back. A ``validate_applied`` that raises ``OSError``
    must still trigger the same restore."""
    rel = "tests/test_bare.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_BARE_TAGGED, encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text(_MINTED_SPEC, encoding="utf-8")

    fake_report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    def fake_apply_upgrades(project_root, report):
        (project_root / rel).write_text(
            _BARE_TAGGED.replace('covers("FR-01.01")', 'covers("FR-01.01/AC01")'), encoding="utf-8")
        return {
            "upgraded_bare_tags": [{"file": rel, "fr_id": "FR-01.01", "ac_id": "AC01",
                                     "slug": "x", "commit": "deadbeef", "tags_upgraded": 1}],
            "inserted_new_tags": [], "skipped": [],
            "tags_upgraded_total": 1, "tags_inserted_total": 0,
            "write_failures_occurred": False,
        }
    monkeypatch.setattr(mod, "apply_upgrades", fake_apply_upgrades)
    monkeypatch.setattr(mod, "validate_applied",
                         lambda *_a, **_k: (_ for _ in ()).throw(OSError("simulated transient spec read failure")))

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel).read_text(encoding="utf-8") == _BARE_TAGGED  # rolled back, not left applied


def test_main_rolls_back_when_spec_md_is_not_valid_utf8_after_a_successful_write(tmp_path, monkeypatch):
    """Tier-3 CI-gate re-review (P3.4 high, round 9): ``validate_applied``
    reads spec.md via ``read_text(encoding="utf-8")``, which raises
    ``UnicodeDecodeError`` (a ``ValueError``, NOT an ``OSError``) on malformed
    UTF-8 -- a bare ``except OSError`` around the call does not catch it. Uses
    the REAL ``validate_applied`` (not monkeypatched) against a genuinely
    malformed spec.md to prove the wrapper's exception clause actually
    matches this exception type."""
    rel = "tests/test_bare.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_BARE_TAGGED, encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_bytes(b"\xff\xfe not valid utf-8")

    fake_report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    def fake_apply_upgrades(project_root, report):
        (project_root / rel).write_text(
            _BARE_TAGGED.replace('covers("FR-01.01")', 'covers("FR-01.01/AC01")'), encoding="utf-8")
        return {
            "upgraded_bare_tags": [{"file": rel, "fr_id": "FR-01.01", "ac_id": "AC01",
                                     "slug": "x", "commit": "deadbeef", "tags_upgraded": 1}],
            "inserted_new_tags": [], "skipped": [],
            "tags_upgraded_total": 1, "tags_inserted_total": 0,
            "write_failures_occurred": False,
        }
    monkeypatch.setattr(mod, "apply_upgrades", fake_apply_upgrades)

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel).read_text(encoding="utf-8") == _BARE_TAGGED  # rolled back, not left applied


def test_apply_with_rollback_restore_is_best_effort_across_multiple_files(tmp_path, monkeypatch):
    """Tier-3 CI-gate re-review (P3.4 high): ``_restore()`` previously aborted
    its own loop at the first ``write_bytes`` failure, silently leaving every
    LATER file un-restored. A failure restoring one file must not stop the
    others from being restored, and the failure must be reported, not
    swallowed."""
    rel_a, rel_b = "tests/test_a.py", "tests/test_b.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel_a).write_text(_BARE_TAGGED, encoding="utf-8")
    (tmp_path / rel_b).write_text(_BARE_TAGGED.replace("test_one", "test_two"), encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("### FR-01.01 — /shipwright-run\n\nno minted ACs here.\n", encoding="utf-8")

    fake_report = {"candidates": [
        _candidate("FR-01.01", "AC01", [rel_a]),
        _candidate("FR-01.01", "AC01", [rel_b]),
    ]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    def fake_apply_upgrades(project_root, report):
        # Both files get mutated; the real (unmocked) validate_applied finds
        # an orphan against this test's spec (nothing minted) and triggers
        # a restore of BOTH.
        (project_root / rel_a).write_text("mutated-a", encoding="utf-8")
        (project_root / rel_b).write_text("mutated-b", encoding="utf-8")
        return {
            "upgraded_bare_tags": [
                {"file": rel_a, "fr_id": "FR-01.01", "ac_id": "AC01",
                 "slug": "x", "commit": "deadbeef", "tags_upgraded": 1},
                {"file": rel_b, "fr_id": "FR-01.01", "ac_id": "AC01",
                 "slug": "x", "commit": "deadbeef", "tags_upgraded": 1},
            ],
            "inserted_new_tags": [], "skipped": [],
            "tags_upgraded_total": 2, "tags_inserted_total": 0,
            "write_failures_occurred": False,
        }
    monkeypatch.setattr(mod, "apply_upgrades", fake_apply_upgrades)

    real_write_bytes = Path.write_bytes
    rel_a_abs = str((tmp_path / rel_a).resolve())

    def flaky_write_bytes(self, data):
        # rel_a is processed FIRST (candidate order) -- fail its restore and
        # confirm rel_b (processed after) still gets restored regardless.
        if str(self.resolve()) == rel_a_abs:
            raise OSError("simulated restore failure")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel_a).read_text(encoding="utf-8") == "mutated-a"          # restore failed, left as-is
    assert (tmp_path / rel_b).read_text(encoding="utf-8") == _BARE_TAGGED.replace("test_one", "test_two")  # still restored


def _plant_reparse_point(path: Path, target: Path) -> None:
    """Create a real symlink (POSIX) or directory junction (Windows) at
    `path` pointing at `target`. Junctions need no elevated privilege on
    Windows, unlike symlinks (SeCreateSymbolicLinkPrivilege) -- this is what
    lets the reparse-point test below run unconditionally on every host
    instead of skipping (Tier-3 CI-gate re-review, P3.4 high, round 10 --
    same helper as ``test_review_scratch.py``'s own precedent)."""
    target.mkdir(exist_ok=True)
    if sys.platform == "win32":
        import subprocess  # nosec B404 - fixed argv, shell=False
        subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
            ["cmd", "/c", "mklink", "/J", str(path), str(target)],
            capture_output=True, text=True, check=True, timeout=30,
        )
    else:
        path.symlink_to(target, target_is_directory=True)


def test_apply_with_rollback_never_reads_or_writes_through_an_escaping_symlink(tmp_path, monkeypatch):
    """Tier-3 CI-gate re-review (P3.4 high): the snapshot/restore pair
    previously bypassed the T4 containment guard entirely -- ``write_bytes``
    on restore FOLLOWS a symlink, so an escaping candidate's external target
    could be rewritten purely by an UNRELATED sibling's rollback. A candidate
    reached through a symlinked (or, on Windows, an unprivileged junctioned)
    ANCESTOR directory, alongside a sibling whose upgrade gets rolled back,
    must leave the real external target byte-for-byte untouched."""
    outside_dir = tmp_path.parent / "outside_project_root_dir"
    outside_target = outside_dir / "test_link.py"
    outside_content = "def test_it():\n    assert True\n"

    rel_link, rel_b = "tests/escaped/test_link.py", "tests/test_bare.py"
    (tmp_path / "tests").mkdir()
    _plant_reparse_point(tmp_path / "tests" / "escaped", outside_dir)
    outside_target.write_text(outside_content, encoding="utf-8")
    (tmp_path / rel_b).write_text(_BARE_TAGGED, encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text(_MINTED_SPEC, encoding="utf-8")

    fake_report = {"candidates": [
        _candidate("FR-01.01", "AC01", [rel_link]),
        _candidate("FR-01.01", "AC01", [rel_b]),
    ]}
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: False)
    monkeypatch.setattr(mod, "derive", lambda *_a, **_k: fake_report)

    def fake_apply_upgrades(project_root, report):
        # The symlinked candidate is never touched here either -- only the
        # normal sibling's upgrade lands, then a write_failure is reported.
        (project_root / rel_b).write_text(
            _BARE_TAGGED.replace('covers("FR-01.01")', 'covers("FR-01.01/AC01")'), encoding="utf-8")
        return {
            "upgraded_bare_tags": [{"file": rel_b, "fr_id": "FR-01.01", "ac_id": "AC01",
                                     "slug": "x", "commit": "deadbeef", "tags_upgraded": 1}],
            "inserted_new_tags": [], "skipped": [],
            "tags_upgraded_total": 1, "tags_inserted_total": 0,
            "write_failures_occurred": True,
        }
    monkeypatch.setattr(mod, "apply_upgrades", fake_apply_upgrades)

    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])

    assert rc == 1
    assert (tmp_path / rel_b).read_text(encoding="utf-8") == _BARE_TAGGED  # rolled back
    assert outside_target.read_text(encoding="utf-8") == outside_content   # external target NEVER touched
