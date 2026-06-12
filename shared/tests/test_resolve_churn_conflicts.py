"""AC-3/AC-4/AC-5 — churn-conflict resolver (git integration).

Real merge-conflict repos exercise ``complete_merge`` end-to-end (events +
triage reconcile, allowlist gate, --ours/--theirs resolution). The pure
allowlist/classify/dedup/validate unit tests live in ``test_churn_merge.py``.
Regeneration is tested with the canonical ``finalize_iterate`` producers
monkeypatched (the real regeneration is dogfooded end-to-end, AC-10).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.churn_merge import TRIAGE_LOG  # noqa: E402
from tools import resolve_churn_conflicts as rcc  # noqa: E402

# Pure allowlist/classify/dedup/validate unit tests live in test_churn_merge.py.
# Campaign status.json conflict + regenerate (S3) live in
# test_resolve_churn_campaign_status.py (reuses _make_conflict_repo / _git here).

_TRIAGE_HEADER = '{"v":1,"schema":"triage","created":"2026-06-05T00:00:00Z"}'


# --------------------------------------------------------------------------- #
# git integration                                                             #
# --------------------------------------------------------------------------- #

def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="Churn Test",
        GIT_AUTHOR_EMAIL="churn@test.invalid",
        GIT_COMMITTER_NAME="Churn Test",
        GIT_COMMITTER_EMAIL="churn@test.invalid",
    )
    return env


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=_env(), capture_output=True, text=True, check=check
    )


def _make_conflict_repo(root: Path, files: dict[str, tuple[str, str, str]]) -> subprocess.CompletedProcess[str]:
    """``files``: relpath -> (base, ours, theirs). Returns the (conflicting) merge."""
    _git(root, "init", "-b", "main")
    for rel, (base, _o, _t) in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(base, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    _git(root, "checkout", "-b", "theirs")
    for rel, (_b, _o, theirs) in files.items():
        (root / rel).write_text(theirs, encoding="utf-8")
    _git(root, "commit", "-am", "theirs")
    _git(root, "checkout", "main")
    _git(root, "checkout", "-b", "ours")
    for rel, (_b, ours, _t) in files.items():
        (root / rel).write_text(ours, encoding="utf-8")
    _git(root, "commit", "-am", "ours")
    return _git(root, "merge", "theirs", "-m", "merge theirs", check=False)


def test_preflight_aborts_on_source_conflict_touching_nothing(tmp_path: Path) -> None:
    merge = _make_conflict_repo(
        tmp_path,
        {
            "src/app.py": ("base\n", "ours\n", "theirs\n"),
            ".shipwright/compliance/dashboard.md": ("b\n", "o\n", "t\n"),
        },
    )
    assert merge.returncode != 0
    before = set(rcc.conflicted_paths(tmp_path))

    result = rcc.complete_merge(tmp_path, run_id="iterate-x")

    assert result.status == "blocked"
    assert result.exit_code == 2
    assert "src/app.py" in result.blocking
    # Hard invariant: nothing resolved/staged — every conflict still unmerged.
    assert set(rcc.conflicted_paths(tmp_path)) == before
    assert result.resolved == []


def test_resolves_churn_only_merge(tmp_path: Path) -> None:
    merge = _make_conflict_repo(
        tmp_path,
        {
            ".shipwright/compliance/dashboard.md": ("b\n", "ours-md\n", "theirs-md\n"),
            "shipwright_test_results.json": ('{"r":0}\n', '{"r":1}\n', '{"r":2}\n'),
        },
    )
    assert merge.returncode != 0

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "resolved"
    assert rcc.conflicted_paths(tmp_path) == []  # merge is now committable
    # test_results.json resolved to OURS (PR-owned snapshot).
    assert (tmp_path / "shipwright_test_results.json").read_text(encoding="utf-8") == '{"r":1}\n'
    # derived MD cleared to THEIRS as a placeholder (regenerated in follow-up).
    assert (tmp_path / ".shipwright/compliance/dashboard.md").read_text(encoding="utf-8") == "theirs-md\n"


def test_events_deduped_and_validated_even_without_conflict(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    run_evt = '{"type":"work_completed","adr_id":"iterate-x","id":"evt-run","v":1}'
    dup = '{"type":"phase_completed","id":"evt-dup","v":1}'
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text(f"{dup}\n{run_evt}\n{dup}\n", encoding="utf-8")  # dup appears twice
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "log")

    result = rcc.complete_merge(tmp_path, run_id="iterate-x")

    text = log.read_text(encoding="utf-8")
    assert text.count("evt-dup") == 1  # exact-line dedup ran
    assert "evt-run" in text
    assert result.status in ("resolved", "clean")


def test_events_invalid_when_run_event_missing(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text('{"type":"phase_completed","id":"evt-1","v":1}\n', encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "log")

    result = rcc.complete_merge(tmp_path, run_id="iterate-missing")

    assert result.status == "events_invalid"
    assert result.exit_code == 4
    assert any("absent" in e for e in result.errors)


def test_triage_deduped_and_validated_even_without_conflict(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    dup = '{"event":"append","id":"trg-a"}'
    log.write_text(f"{_TRIAGE_HEADER}\n{dup}\n{dup}\n", encoding="utf-8")  # dup twice
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "triage")

    result = rcc.complete_merge(tmp_path, run_id="iterate-x")

    text = log.read_text(encoding="utf-8")
    assert text.count("trg-a") == 1                 # exact-line dedup ran
    assert "schema" in text.splitlines()[0]          # header preserved
    assert result.status in ("resolved", "clean")


def test_triage_conflict_unions_both_sides(tmp_path: Path) -> None:
    """Codex BLOCKER fix: a hard triage.jsonl conflict UNIONS both sides (keeps
    ours AND theirs items). Target projects lack the merge=union driver, so the
    old `--ours` path would silently drop the other side's backlog items.
    """
    merge = _make_conflict_repo(
        tmp_path,
        {".shipwright/triage.jsonl": (
            f"{_TRIAGE_HEADER}\n",
            f'{_TRIAGE_HEADER}\n{{"event":"append","id":"trg-ours"}}\n',
            f'{_TRIAGE_HEADER}\n{{"event":"append","id":"trg-theirs"}}\n',
        )},
    )
    assert merge.returncode != 0
    result = rcc.complete_merge(tmp_path, run_id=None)
    assert result.status == "resolved"
    assert rcc.conflicted_paths(tmp_path) == []
    assert TRIAGE_LOG in result.resolved
    text = (tmp_path / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert "trg-ours" in text and "trg-theirs" in text  # NEITHER side dropped
    assert text.count("schema") == 1                    # header deduped to one


def test_triage_conflict_unions_non_ascii_byte_identical(tmp_path: Path) -> None:
    """WP6/F22 regression: a hard triage.jsonl conflict whose lines carry
    non-ASCII content (CJK, em-dash, accented) must round-trip BYTE-IDENTICAL
    through ``_union_conflict`` — i.e. ``git show :2:/:3:`` is decoded UTF-8 and
    re-encoded UTF-8, never via the Windows cp1252 locale (which would mojibake
    the tracked log — the sole safety net in repos lacking the merge=union
    driver). Asserts the exact bytes of each side survive in the unioned file.
    """
    ours_line = '{"event":"append","id":"trg-ours","title":"鸢尾花 — café façade"}'
    theirs_line = '{"event":"append","id":"trg-theirs","title":"naïve Москва ☃"}'
    merge = _make_conflict_repo(
        tmp_path,
        {".shipwright/triage.jsonl": (
            f"{_TRIAGE_HEADER}\n",
            f"{_TRIAGE_HEADER}\n{ours_line}\n",
            f"{_TRIAGE_HEADER}\n{theirs_line}\n",
        )},
    )
    assert merge.returncode != 0

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "resolved"
    assert rcc.conflicted_paths(tmp_path) == []
    assert TRIAGE_LOG in result.resolved
    # Byte-identity of the CONTENT (external-review code #3): decode strict UTF-8
    # (mojibake would raise here), then assert each line's exact UTF-8 bytes — in
    # exact order, with the header deduped to one. Line endings are compared after
    # universal-newline normalization: `write_text`/`git show` apply the platform
    # newline (CRLF on Windows) and the real merge path re-normalizes via
    # `dedup_triage_lines`/`splitlines()`, so the EOL byte is orthogonal to the
    # F22 encoding contract. What F22 guarantees — and this asserts — is that no
    # character of the multi-byte payload is altered, dropped, or re-encoded.
    raw = (tmp_path / ".shipwright" / "triage.jsonl").read_bytes()
    lines = raw.decode("utf-8").splitlines()  # strict decode; EOL-normalized
    assert lines == [_TRIAGE_HEADER, ours_line, theirs_line], (
        "unioned triage.jsonl content not byte-identical to the UTF-8 source"
    )
    # And the exact raw UTF-8 byte sequence of each non-ASCII payload is on disk.
    assert "鸢尾花 — café façade".encode("utf-8") in raw
    assert "naïve Москва ☃".encode("utf-8") in raw


def test_triage_conflict_non_utf8_byte_returns_triage_invalid_not_traceback(tmp_path: Path) -> None:
    """WP6/F22 hardening (external-review Gemini/OpenAI MED): a triage.jsonl stage
    carrying a legacy non-UTF-8 byte must NOT crash _union_conflict with a bare
    traceback (None.splitlines() on Windows / UnicodeDecodeError on POSIX) — it
    must translate to a structured ``triage_invalid`` status and abort the merge,
    preserving the JSON-status contract. Strict UTF-8 keeps the round-trip
    byte-identical; this is the loud-fail path for genuinely-corrupt input.
    """
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    # base: valid header + one valid line.
    log.write_bytes(f"{_TRIAGE_HEADER}\n".encode("utf-8") + b'{"event":"append","id":"trg-base"}\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "checkout", "-b", "theirs")
    # theirs: append a line with a raw cp1252-undefined byte (0x81) — NOT valid UTF-8.
    log.write_bytes(
        f"{_TRIAGE_HEADER}\n".encode("utf-8")
        + b'{"event":"append","id":"trg-base"}\n'
        + b'{"event":"append","id":"trg-\x81bad"}\n'
    )
    _git(tmp_path, "commit", "-am", "theirs adds non-utf8 byte")
    _git(tmp_path, "checkout", "main")
    _git(tmp_path, "checkout", "-b", "ours")
    log.write_bytes(
        f"{_TRIAGE_HEADER}\n".encode("utf-8")
        + b'{"event":"append","id":"trg-base"}\n'
        + b'{"event":"append","id":"trg-ours"}\n'
    )
    _git(tmp_path, "commit", "-am", "ours")
    merge = _git(tmp_path, "merge", "theirs", "-m", "merge", check=False)
    assert merge.returncode != 0  # conflict

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "triage_invalid"
    assert result.exit_code == 4
    assert any("UTF-8" in e for e in result.errors)
    # Merge aborted: no unmerged paths left wedged.
    assert rcc.conflicted_paths(tmp_path) == []


def test_triage_invalid_when_header_dropped(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('{"event":"append","id":"trg-1"}\n', encoding="utf-8")  # no header
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "triage")

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "triage_invalid"
    assert result.exit_code == 4
    assert any("header" in e for e in result.errors)


def test_regenerate_invokes_canonical_producers_and_stages(tmp_path: Path, monkeypatch) -> None:
    _git(tmp_path, "init", "-b", "main")
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")

    from tools import finalize_iterate

    calls: list[str] = []

    def fake_compliance(project_root: Path) -> list[str]:
        calls.append("compliance")
        rels = []
        for name in ("dashboard", "sbom", "test-evidence", "traceability-matrix", "change-history"):
            rel = f".shipwright/compliance/{name}.md"
            (project_root / rel).write_text(f"# {name}\n", encoding="utf-8")
            rels.append(rel)
        return rels

    monkeypatch.setattr(finalize_iterate, "_update_compliance", fake_compliance)

    outcomes = rcc.regenerate_tracked_snapshots(
        tmp_path, "iterate-x", session_id="s", only=set(rcc.COMPLIANCE_MDS)
    )

    assert calls == ["compliance"]
    assert all(v == "regenerated" for v in outcomes.values())
    # the 5 compliance MDs are now staged
    staged = _git(tmp_path, "diff", "--name-only", "--cached").stdout.split()
    assert ".shipwright/compliance/dashboard.md" in staged
    assert len([s for s in staged if s.startswith(".shipwright/compliance/")]) == 5
