"""Tail-fallback readers must fail closed for a corrupt REQUESTED run (trg-e0a0f569).

Split out of ``test_iterate_entry_encoding.py`` (which covers ``lib.iterate_entry``'s
own decode-safety, trg-06216b9f) once it crossed the 300-line bloat guideline —
these tests exercise a different, higher layer: the two verifier-side readers that
sit on top of ``lib.iterate_entry.read_iterate_entries``.

``spec_checks._read_iterate_entry`` and ``iterate_compliance._latest_iterate_entry``
end with ``return entries[-1]`` when the requested ``run_id`` is not found in the
merged entries. That tail-fallback is legitimate for a genuinely unwritten entry
(mid-flow finalize reaching a verifier before F5c writes it — see
``test_read_iterate_entry_falls_back_to_tail_on_unknown_run_id`` in
test_verifiers_dual_mode.py) but was WRONG when the requested run's own entry
existed on disk and simply failed to parse: silently handing back the most recent
OTHER run let S9 / S10 / W2 branch on an inherited ``category`` / ``complexity``
that belongs to a different run entirely.

Both readers now delegate to ``tools.verifiers._iterate_run_id.resolve_iterate_entry``,
which calls ``own_entry_file_is_corrupt`` first and fails CLOSED to ``None`` when the
REQUESTED run's own entry is unreadable (per-file OR legacy-array corruption,
oversized, or a dangling symlink) — never substituting a different run's data. The
tail-fallback itself is not removed; only corruption of the requested run's own
entry is distinguished from genuine absence and refused.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import iterate_entry as ie  # noqa: E402
from tools.verifiers import iterate_compliance as ic  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402

_RUN = "iterate-encoding-probe"

#: Structurally valid JSON whose BYTES are not valid UTF-8 — a cp1252 editor save.
#: Encoding the payload rather than splicing a raw byte keeps the file genuinely
#: parseable-if-decoded, so the test isolates the DECODE failure and cannot pass by
#: accident through the JSONDecodeError arm that was already handled.
_CP1252_ENTRY = json.dumps(
    {"run_id": _RUN, "date": "2026-08-01", "adr": _RUN, "note": "café résumé"},
    ensure_ascii=False,
).encode("cp1252")

_OLDER = {"run_id": "iterate-2026-07-01-other", "date": "2026-07-01T00:00:00Z",
          "type": "change", "complexity": "small", "branch": "b", "tests_passed": True}


def _seed_entry_bytes(project_root: Path, run_id: str, raw: bytes) -> Path:
    directory = project_root / ".shipwright" / "agent_docs" / "iterates"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.json"
    path.write_bytes(raw)
    return path


def test_a_corrupt_entry_fails_closed_in_tail_fallback_readers(tmp_path):
    """Closes trg-e0a0f569: a corrupt REQUESTED-run entry must never resolve to
    a different run's data.

    Both corruption classes are driven, because that is the whole scope
    argument: the malformed-JSON case has always been skipped by the reader
    (not introduced by the non-UTF-8 fix in test_iterate_entry_encoding.py), so
    both must fail closed identically — this is not a decode-error-specific fix.
    """
    for label, raw in (("non-utf8", _CP1252_ENTRY), ("malformed-json", b"{ not json")):
        root = tmp_path / label
        (root / ".shipwright" / "agent_docs" / "iterates").mkdir(parents=True)
        _seed_entry_bytes(root, _OLDER["run_id"], json.dumps(_OLDER).encode("utf-8"))
        _seed_entry_bytes(root, _RUN, raw)

        assert sc._read_iterate_entry(root, _RUN) is None, label
        assert ic._latest_iterate_entry(root, _RUN) is None, label


def test_a_genuinely_unwritten_entry_still_tail_falls_back(tmp_path):
    """The fallback itself is not removed — only corruption is refused.

    No file exists for ``_RUN`` at all here (as opposed to the corrupt-file
    case above), so both readers still hand back the most recent entry —
    the legitimate mid-flow-finalize convenience the fallback exists for.
    """
    _seed_entry_bytes(tmp_path, _OLDER["run_id"], json.dumps(_OLDER).encode("utf-8"))

    for reader in (sc._read_iterate_entry, ic._latest_iterate_entry):
        got = reader(tmp_path, _RUN)
        assert got is not None and got["run_id"] == _OLDER["run_id"], (reader, got)


def test_a_corrupt_legacy_config_masking_the_current_run_also_fails_closed(tmp_path):
    """The corruption-awareness must not be per-file-store-only.

    If the requested run's own entry lived ONLY in the legacy
    ``iterate_history`` array (never migrated to a per-file entry) and
    ``shipwright_run_config.json`` itself fails to parse, the legacy array
    reads back as an empty list — indistinguishable, to a per-file-only
    check, from "this run was never recorded". Since we cannot rule out the
    entry being in there, this must fail closed exactly like per-file
    corruption, not silently fall back to a different run.
    """
    (tmp_path / ".shipwright" / "agent_docs" / "iterates").mkdir(parents=True)
    _seed_entry_bytes(tmp_path, _OLDER["run_id"], json.dumps(_OLDER).encode("utf-8"))
    # No per-file entry for _RUN, and the legacy config — its only other
    # possible home — is itself undecodable.
    (tmp_path / "shipwright_run_config.json").write_bytes(b"{ not json")

    assert sc._read_iterate_entry(tmp_path, _RUN) is None
    assert ic._latest_iterate_entry(tmp_path, _RUN) is None


def test_own_entry_file_is_corrupt_fails_closed_on_unexpected_error(tmp_path, monkeypatch):
    """An unexpected error while checking corruption is itself the ambiguous
    case this guard exists for, so it must resolve toward "corrupt" (fail
    closed), never toward "absent" (permit a substitution)."""
    from tools.verifiers import _iterate_run_id as run_id_guard  # noqa: PLC0415

    def _boom(*_a, **_kw):
        raise OSError("simulated stat failure")

    monkeypatch.setattr(
        run_id_guard.Path, "exists", _boom, raising=True,
    )
    assert run_id_guard.own_entry_file_is_corrupt(tmp_path, _RUN) is True


def test_an_oversized_entry_file_is_treated_as_corrupt_not_absent(tmp_path):
    """``_is_entry_file`` silently drops a file over ``MAX_ENTRY_FILE_BYTES`` —
    the same "on disk but absent from the merged read" shape as a decode
    failure, so it must fail closed identically rather than tail-falling-back."""
    (tmp_path / ".shipwright" / "agent_docs" / "iterates").mkdir(parents=True)
    _seed_entry_bytes(tmp_path, _OLDER["run_id"], json.dumps(_OLDER).encode("utf-8"))

    oversized = json.dumps({"run_id": _RUN, "padding": "x" * ie.MAX_ENTRY_FILE_BYTES})
    _seed_entry_bytes(tmp_path, _RUN, oversized.encode("utf-8"))

    assert sc._read_iterate_entry(tmp_path, _RUN) is None
    assert ic._latest_iterate_entry(tmp_path, _RUN) is None


def test_a_dangling_symlink_at_the_entry_path_is_treated_as_corrupt_not_absent(tmp_path):
    """``Path.exists()`` follows symlinks and reports ``False`` for a DANGLING
    one (target missing) — but ``_is_entry_file`` excludes every symlink at
    this location regardless of target validity (a symlink could otherwise
    mask or redirect a legitimate entry file). ``own_entry_file_is_corrupt``
    must agree: a dangling link at the canonical path is "present but
    unreadable", not "genuinely absent" (Stage-3 doubt review)."""
    import os

    iterates_dir = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    iterates_dir.mkdir(parents=True)
    _seed_entry_bytes(tmp_path, _OLDER["run_id"], json.dumps(_OLDER).encode("utf-8"))

    link_path = iterates_dir / f"{_RUN}.json"
    missing_target = iterates_dir / "does-not-exist.json"
    try:
        os.symlink(missing_target, link_path)
    except OSError as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    assert sc._read_iterate_entry(tmp_path, _RUN) is None
    assert ic._latest_iterate_entry(tmp_path, _RUN) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
