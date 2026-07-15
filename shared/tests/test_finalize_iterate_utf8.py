"""finalize_iterate.py stdio must be UTF-8, not the Windows console codepage.

iterate-2026-07-15-finalize-utf8-guard. ``finalize_iterate.py``'s ``main()``
writes ``json.dumps(result, ensure_ascii=False)`` to stdout (the machine
contract ``finalize_bundle.py`` captures for F5b) and interpolates exception /
path text into stderr. On Windows ``sys.stdout``/``sys.stderr`` default to the
console codepage (cp1252) whenever the stream is a pipe (``capture_output=True``)
— exactly how ``finalize_bundle.py`` (#374) invokes F5b as a subprocess. Any
non-cp1252 character in the echoed result (a repo under a CJK / Cyrillic path
lands verbatim in ``result["project_root"]``; non-ASCII exception text lands in
stderr) raised ``UnicodeEncodeError`` in the child, exiting non-zero and
aborting the whole finalize bundle. Same class as #244 (verifier cp1252) and
iterate-2026-06-10-triage-cli-json-utf8.

The parent bundle's ``errors="replace"`` only guards its own *decode* of the
child's bytes — it cannot stop the child crashing on its own *encode*. The fix
is the in-process guard (``sys.stdout/stderr.reconfigure(encoding="utf-8")``),
matching finalize_bundle.py / triage_cli.py / resolve_gate_policy.py /
verifiers/stdio.py — NOT a PYTHONIOENCODING env var every caller must remember.

``PYTHONIOENCODING=cp1252`` pins the child's stdio codec so the regression
reproduces deterministically on every platform, not just a Windows console.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_WORKTREE = Path(__file__).resolve().parents[2]
FINALIZE_ITERATE = _WORKTREE / "shared" / "scripts" / "tools" / "finalize_iterate.py"

_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from tools import finalize_iterate  # noqa: E402  (in-process guard-helper tests)

# Outside cp1252 (Western European): CJK + a U+2713 check mark. If either reaches
# a cp1252-encoded stdout/stderr, the pre-fix CLI dies with UnicodeEncodeError.
NON_CP1252 = "中文_✓"  # 中文_✓

# A valid FR-gate classification so run() completes and echoes project_root into
# the result JSON — the FinalizeGateError path (a bare gate message) would not.
_VALID_EXTRAS = {"change_type": "tooling", "none_reason": "utf8 regression probe"}


def _make_project(tmp_path: Path) -> Path:
    """A repo whose path carries a non-cp1252 char (real on Windows machines
    with CJK/Cyrillic usernames) — it lands verbatim in ``result["project_root"]``,
    which ``main()`` prints as ``ensure_ascii=False`` JSON."""
    root = tmp_path / f"repo_{NON_CP1252}"
    (root / ".shipwright" / "agent_docs").mkdir(parents=True)
    (root / ".shipwright" / "compliance").mkdir(parents=True)
    (root / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}), encoding="utf-8"
    )
    return root


def _run_legacy_console(
    project_root: Path, run_id: str
) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    return subprocess.run(
        [
            sys.executable, str(FINALIZE_ITERATE),
            "--project-root", str(project_root),
            "--run-id", run_id,
            "--reason", f"iterate finalization {NON_CP1252}",
            "--event-extras-json", json.dumps(_VALID_EXTRAS, ensure_ascii=False),
        ],
        capture_output=True, check=False, env=env,
    )


def test_stdout_is_utf8_under_legacy_console_encoding(tmp_path: Path) -> None:
    """main()'s result JSON is a machine contract consumed by finalize_bundle:
    UTF-8 bytes regardless of the console codepage. Pre-fix this exited
    non-zero with UnicodeEncodeError on the non-cp1252 project_root."""
    root = _make_project(tmp_path)
    res = _run_legacy_console(root, "iterate-2026-07-15-utf8-probe-a")

    assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
    data = json.loads(res.stdout.decode("utf-8"))
    assert NON_CP1252 in data["project_root"]
    # stderr diagnostics interpolate exception/path text — also UTF-8, never a
    # cp1252 crash. Strict decode (no errors=) would raise on any stray byte.
    res.stderr.decode("utf-8")


def test_gate_error_stdout_is_utf8_under_legacy_console_encoding(
    tmp_path: Path,
) -> None:
    """The fail-closed FinalizeGateError branch shares the same stdout writer.
    Its detail echoes the caller's ``change_type`` verbatim (``{change_type!r}``),
    so a non-cp1252 change_type is the one gate-error path that plants a
    non-cp1252 byte on stdout — it must still emit a clean UTF-8 error document.
    Pre-fix this crashed the codec (empty stdout → JSONDecodeError below)."""
    root = _make_project(tmp_path)
    # Invalid change_type → FR-gate rejects BEFORE inspecting any other field,
    # and the rejection detail interpolates change_type verbatim onto stdout.
    bad_extras = {"change_type": NON_CP1252}
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    res = subprocess.run(
        [
            sys.executable, str(FINALIZE_ITERATE),
            "--project-root", str(root),
            "--run-id", "iterate-2026-07-15-utf8-probe-b",
            "--reason", "gate probe",
            "--event-extras-json", json.dumps(bad_extras, ensure_ascii=False),
        ],
        capture_output=True, check=False, env=env,
    )
    # Fail-closed exit 1, but via a structured UTF-8 error document — never a
    # traceback from the stdout encoder (that would give empty stdout).
    assert res.returncode == 1, res.stderr.decode("utf-8", "replace")
    doc = json.loads(res.stdout.decode("utf-8"))
    assert doc["error"] == "fr_gate_unclassified"
    assert NON_CP1252 in doc["detail"]  # the non-cp1252 char round-tripped as UTF-8


# ---------------------------------------------------------------------------
# In-process unit coverage of the guard helper. The subprocess tests above
# exercise it end-to-end, but coverage.py cannot see a child process — these
# pin both branches (reconfigure applied / reconfigure raises) in-process so
# the defensive fail-soft path is proven, not just line-covered.
# ---------------------------------------------------------------------------


class _RecordingStream:
    """A stream stub whose reconfigure() records its kwargs."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def reconfigure(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


class _BoomStream:
    """A stream stub whose reconfigure() raises — a detached/closed stream."""

    def reconfigure(self, **kwargs: object) -> None:
        raise ValueError("underlying buffer has been detached")


def test_reconfigure_stdio_utf8_pins_both_streams(monkeypatch) -> None:
    """Happy path: both stdout and stderr are reconfigured to UTF-8."""
    out, err = _RecordingStream(), _RecordingStream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    finalize_iterate._reconfigure_stdio_utf8()
    assert out.calls == [{"encoding": "utf-8"}]
    assert err.calls == [{"encoding": "utf-8"}]


def test_reconfigure_stdio_utf8_swallows_stream_errors(monkeypatch) -> None:
    """Fail-soft: a stream whose reconfigure raises must not propagate — the
    later write surfaces any real problem, the guard never crashes main()."""
    monkeypatch.setattr(sys, "stdout", _BoomStream())
    monkeypatch.setattr(sys, "stderr", _BoomStream())
    finalize_iterate._reconfigure_stdio_utf8()  # must NOT raise


def test_reconfigure_stdio_utf8_skips_streams_without_reconfigure(monkeypatch) -> None:
    """A stream lacking reconfigure (e.g. a StringIO / capture object) is
    skipped via the callable() guard, not crashed on."""
    import io

    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    finalize_iterate._reconfigure_stdio_utf8()  # must NOT raise
