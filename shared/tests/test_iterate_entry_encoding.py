"""`lib.iterate_entry` — a file that is not valid UTF-8 is corrupt, not fatal.

Both readers decode with ``read_text(encoding="utf-8")`` inside
``except (json.JSONDecodeError, OSError)``. The decode happens BEFORE any JSON
parsing, and ``UnicodeDecodeError`` is a ``ValueError`` — so it was caught by
neither arm and propagated out of ``find_entry_by_run_id``.
``verify_iterate_finalization.main`` has no try/except around ``run_all_checks``,
so F11 exited with a traceback and EMPTY stdout: the operator lost the report for
every check, not just the one that raised (trg-06216b9f).

The sibling ``verifiers/_iterate_latest.py`` already catches ``UnicodeDecodeError``
on the same kind of read, so the intended posture was settled — the two readers
simply disagreed.

**What this does and does not buy — stated precisely, because an earlier draft of
this docstring overclaimed it.** An undecodable file is skipped, so the run's entry
is absent from every EXACT-MATCH lookup, and the gates keyed on one (``code`` /
``spec`` records, ADR presence, integration coverage) still refuse. It is NOT true
that "every gate refuses without it": ``spec_checks._read_iterate_entry`` and
``iterate_compliance._latest_iterate_entry`` TAIL-FALL-BACK to ``entries[-1]``, so a
corrupt entry makes them hand back the most recent OTHER run, and S9 / S10 / W2 then
decide on inherited ``category`` / ``complexity``. That substitution is PRE-EXISTING
and not introduced here — it already happens for a malformed-JSON entry, which this
reader has always skipped (both measured; see
``test_a_corrupt_entry_substitutes_the_previous_run_in_tail_fallback_readers``).
This change makes the non-UTF-8 class behave like the malformed-JSON class instead
of crashing, which is strictly better than losing all 20 checks — but it does not
close the tail-fallback hole. Fixing that is trg-e0a0f569.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import iterate_entry as ie  # noqa: E402

_RUN = "iterate-encoding-probe"

#: Structurally valid JSON whose BYTES are not valid UTF-8 — a cp1252 editor save.
#: Encoding the payload rather than splicing a raw byte keeps the file genuinely
#: parseable-if-decoded, so the test isolates the DECODE failure and cannot pass by
#: accident through the JSONDecodeError arm that was already handled.
_CP1252_ENTRY = json.dumps(
    {"run_id": _RUN, "date": "2026-08-01", "adr": _RUN, "note": "café résumé"},
    ensure_ascii=False,
).encode("cp1252")


def _seed_entry_bytes(project_root: Path, run_id: str, raw: bytes) -> Path:
    directory = project_root / ".shipwright" / "agent_docs" / "iterates"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.json"
    path.write_bytes(raw)
    return path


def test_the_fixture_is_undecodable_but_otherwise_valid(tmp_path):
    """The negative control. If the payload were plain ASCII, or malformed JSON,
    every assertion below would pass against the UNFIXED reader and prove nothing."""
    with pytest.raises(UnicodeDecodeError):
        _CP1252_ENTRY.decode("utf-8")
    assert json.loads(_CP1252_ENTRY.decode("cp1252"))["run_id"] == _RUN


# --- the entry-file reader ----------------------------------------------------


def test_a_non_utf8_entry_file_is_skipped_not_raised(tmp_path):
    _seed_entry_bytes(tmp_path, _RUN, _CP1252_ENTRY)
    assert ie.read_iterate_entries(tmp_path) == []


def test_find_entry_by_run_id_reports_absent_rather_than_raising(tmp_path):
    """The exact call the F11 verifiers make. Absent is the fail-CLOSED answer:
    every gate that needs this entry refuses without it."""
    _seed_entry_bytes(tmp_path, _RUN, _CP1252_ENTRY)
    assert ie.find_entry_by_run_id(tmp_path, _RUN) is None


def test_last_iterate_entry_survives_a_corrupt_file(tmp_path):
    _seed_entry_bytes(tmp_path, _RUN, _CP1252_ENTRY)
    assert ie.last_iterate_entry(tmp_path) is None


def test_one_undecodable_file_does_not_hide_its_readable_neighbours(tmp_path):
    """The whole point of skipping rather than raising: a single bad file must cost
    only itself. A reader that aborted would lose the healthy entries too."""
    _seed_entry_bytes(tmp_path, _RUN, _CP1252_ENTRY)
    good = {"run_id": "iterate-2026-08-01-good", "date": "2026-08-01"}
    _seed_entry_bytes(tmp_path, good["run_id"],
                      json.dumps(good).encode("utf-8"))

    run_ids = [e.get("run_id") for e in ie.read_iterate_entries(tmp_path)]
    assert run_ids == ["iterate-2026-08-01-good"]


def test_the_skip_is_announced_on_the_logger(tmp_path, caplog):
    """Silent data loss is its own defect — the corrupt-file path already warns, and
    the widened except must keep reaching it rather than swallowing quietly."""
    _seed_entry_bytes(tmp_path, _RUN, _CP1252_ENTRY)
    with caplog.at_level("WARNING"):
        ie.read_iterate_entries(tmp_path)
    # ``getMessage()`` interpolates the lazy %-args the logger was called with;
    # reading ``.message`` raw would miss the filename and the decode error.
    rendered = [r.getMessage() for r in caplog.records]
    assert any("skip corrupt entry file" in m for m in rendered), rendered
    assert any(f"{_RUN}.json" in m and "utf-8" in m for m in rendered), rendered


def test_a_corrupt_entry_substitutes_the_previous_run_in_tail_fallback_readers(tmp_path):
    """Pins what skipping does NOT buy, so the limit is recorded rather than assumed.

    ``spec_checks._read_iterate_entry`` and ``iterate_compliance._latest_iterate_entry``
    end with ``return entries[-1]``, so a run whose own entry is unreadable gets handed
    the most recent OTHER run — and S9 / S10 / W2 then branch on inherited ``category``
    / ``complexity``. Asserted here in the fail-OPEN direction on purpose: this test
    documents a hole, so it must fail if someone closes it, forcing the prose above and
    trg-e0a0f569 to be revisited rather than silently going stale.

    Both corruption classes are driven, because that is the whole scope argument: the
    malformed-JSON case ALREADY behaved this way before this change (the reader has
    always skipped it), so the tail fallback is pre-existing and the non-UTF-8 case is
    merely joining it instead of crashing.
    """
    import sys as _sys  # noqa: PLC0415
    _sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
    from tools.verifiers import spec_checks as sc  # noqa: PLC0415

    older = {"run_id": "iterate-2026-07-01-other", "date": "2026-07-01T00:00:00Z",
             "type": "change", "complexity": "small", "branch": "b", "tests_passed": True}

    for label, raw in (("non-utf8", _CP1252_ENTRY), ("malformed-json", b"{ not json")):
        root = tmp_path / label
        (root / ".shipwright" / "agent_docs" / "iterates").mkdir(parents=True)
        _seed_entry_bytes(root, older["run_id"], json.dumps(older).encode("utf-8"))
        _seed_entry_bytes(root, _RUN, raw)

        got = sc._read_iterate_entry(root, _RUN)
        assert got is not None and got["run_id"] == older["run_id"], (label, got)
        assert got["complexity"] == "small", (label, got)


# --- the legacy run-config reader --------------------------------------------


def test_a_non_utf8_run_config_is_tolerated(tmp_path):
    """The second except tuple, on the legacy ``iterate_history`` array. Same
    decode, same class, same fix — and it is reached by the very same
    ``read_iterate_entries`` call, so leaving it would only move the crash."""
    (tmp_path / "shipwright_run_config.json").write_bytes(
        json.dumps({"iterate_history": [{"run_id": _RUN}], "note": "café"},
                   ensure_ascii=False).encode("cp1252"))
    assert ie.read_iterate_entries(tmp_path) == []


# --- end to end: the report the operator actually loses ------------------------


def test_f11_still_prints_a_report_when_an_entry_file_is_undecodable(tmp_path):
    """The consequence, driven through the real CLI.

    Asserting on the reader alone would not pin what was actually broken: F11 exited
    1 with EMPTY stdout and a traceback on stderr. The run must still FAIL here (the
    entry is genuinely unreadable) — but it must fail as a REPORT, naming its checks,
    not as a crash.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@e.st",
                    "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base"],
                   check=True)
    commit = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    _seed_entry_bytes(tmp_path, _RUN, _CP1252_ENTRY)

    proc = subprocess.run(
        [sys.executable,
         str(REPO_ROOT / "shared" / "scripts" / "tools" / "verify_iterate_finalization.py"),
         "--project-root", str(tmp_path), "--run-id", _RUN, "--commit", commit],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert "UnicodeDecodeError" not in proc.stderr, proc.stderr[-2000:]
    assert "Traceback" not in proc.stderr, proc.stderr[-2000:]
    assert proc.stdout.strip(), "F11 produced no report at all"
    # Smoke only, and deliberately NOT advertised as the fail-closed half: this bare
    # fixture has no events log, no test results and no ack, so a dozen checks ERROR
    # regardless of how the entry decodes and `exit 1` is overdetermined. The three
    # assertions above are the ones that pin the fix (Stage-3 doubt review).
    assert proc.returncode == 1, (proc.returncode, proc.stdout[-2000:])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
