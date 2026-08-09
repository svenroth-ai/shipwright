"""Tests for `triage_cli.py list --json` — the machine-readable contract.

iterate-2026-06-10-triage-list-json. The WebUI live-view (trg-e2a0ebb3) consumes
this instead of re-parsing JSONL: it emits the unioned (tracked ∪ outbox) items
the human `list` shows, plus a `pendingDelivery` boolean so the UI can badge
outbox-only (not-yet-swept) items.

**Contract version 2** (iterate-2026-08-01-triage-defer-lifecycle): a bare
array of open items became an envelope — `contractVersion`, `open`, `deferred`
— because a parked entry had to become visible here and a flat array has no
sections. `_open()` below reads the `open` section, so the pre-existing cases
still say what they always said; the envelope itself is pinned separately.

**Contract version 2** gains the independent amend-delivery fact additively:
`pendingAmendDelivery` is always present on each row, while
`undeliveredAmends` is the capped `{count, truncated, ids}` envelope block.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import append_triage_item, mark_status  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"
OUTBOX_REL = ".shipwright/triage.outbox.jsonl"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), *args],
        capture_output=True, text=True, check=False,
    )


def _list_json(project: Path) -> dict:
    res = _run(["--project-root", str(project), "list", "--json"])
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _open(project: Path) -> list[dict]:
    return _list_json(project)["open"]


def _write_outbox(project: Path, *appends: dict) -> None:
    p = project / OUTBOX_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(a) + "\n" for a in appends), encoding="utf-8")


@pytest.fixture
def tracked_item(tmp_path: Path) -> str:
    return append_triage_item(
        tmp_path, source="github", severity="high", kind="bug",
        title="GitHub security", detail="ctx", dedup_key="gh-security:acme/foo",
        launch_payload="/shipwright-security\n\nContext: foo.",
    )


def test_list_json_emits_the_open_section(tmp_path: Path, tracked_item: str) -> None:
    payload = _list_json(tmp_path)
    assert payload["contractVersion"] == 2
    assert payload["deferred"] == []
    data = payload["open"]
    assert isinstance(data, list) and len(data) == 1
    item = data[0]
    assert item["id"] == tracked_item
    assert item["status"] == "triage"
    assert item["launchPayload"].startswith("/shipwright-security")
    assert item["pendingDelivery"] is False  # lives in the tracked log
    assert item["pendingAmendDelivery"] is False
    assert payload["undeliveredAmends"] == {"count": 0, "truncated": False, "ids": []}


def test_list_json_empty_is_two_empty_sections(tmp_path: Path) -> None:
    """An empty store: both sections empty, and the store itself reported clean.

    Pinned key-SET plus key-by-key, rather than by whole-dict equality. The
    envelope gained ``corruption`` in iterate-2026-08-06-p2-19c-corruption-absence.
    The separately meaningful `undeliveredAmends` envelope block is additive at
    v2, alongside its always-present row boolean, so the pinned consumer remains
    compatible while a later consumer can opt into the new fact.

    The split matters: a whole-payload `==` couples "which keys exist" to "what
    each key contains", so every additive field fails the test for the wrong
    reason. Asserting the key SET separately keeps the exhaustiveness (a fifth key
    still fails) while letting the per-key assertions say what they mean. The
    first version of this rewrite dropped the key-set line and was therefore
    weaker, not stronger, than what it replaced — caught by the Stage-1 review.
    """
    payload = _list_json(tmp_path)
    # Exhaustive on the top level, which the old whole-dict `==` also gave us: an
    # unnoticed FIFTH key is exactly the drift a cross-repo contract must not have.
    assert set(payload) == {"contractVersion", "open", "deferred", "corruption",
                            "undeliveredDecisions", "undeliveredAmends"}
    assert payload["contractVersion"] == 2
    assert payload["open"] == []
    assert payload["deferred"] == []
    assert payload["corruption"] == {"count": 0, "truncated": False, "spans": []}
    assert payload["undeliveredDecisions"] == {"count": 0, "truncated": False, "ids": []}
    assert payload["undeliveredAmends"] == {"count": 0, "truncated": False, "ids": []}


def test_list_json_excludes_dismissed(tmp_path: Path, tracked_item: str) -> None:
    mark_status(tmp_path, tracked_item, new_status="dismissed", by="x", reason="r")
    assert (_open(tmp_path), _list_json(tmp_path)["deferred"]) == ([], [])


def test_list_json_marks_outbox_only_pending_delivery(tmp_path: Path) -> None:
    """An item living ONLY in the gitignored outbox buffer (not yet swept to the
    tracked log) appears with pendingDelivery=true — the WebUI badge signal."""
    _write_outbox(tmp_path, {
        "event": "append", "id": "trg-outbox01", "ts": "2026-06-10T00:00:00Z",
        "source": "manual", "severity": "low", "kind": "improvement",
        "title": "outbox-only item", "status": "triage",
    })
    by_id = {d["id"]: d for d in _open(tmp_path)}
    assert "trg-outbox01" in by_id
    assert by_id["trg-outbox01"]["pendingDelivery"] is True


def test_list_json_tracked_preferred_when_in_both(tmp_path: Path, tracked_item: str) -> None:
    """TRACKED-PREFERRED: an id present in BOTH files is pendingDelivery=false
    (the tracked copy ships in the PR; the outbox copy is GC'd post-delivery)."""
    _write_outbox(tmp_path, {
        "event": "append", "id": tracked_item, "ts": "2026-06-10T00:00:00Z",
        "source": "github", "severity": "high", "kind": "bug",
        "title": "dup", "status": "triage",
    })
    [it] = [d for d in _open(tmp_path) if d["id"] == tracked_item]
    assert it["pendingDelivery"] is False


def test_list_default_output_is_not_json(tmp_path: Path, tracked_item: str) -> None:
    """Regression: the human-readable default (no --json) is unchanged."""
    res = _run(["--project-root", str(tmp_path), "list"])
    assert res.returncode == 0
    assert tracked_item in res.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(res.stdout)


# ---------------------------------------------------------------------------
# UTF-8 output contract under a legacy console encoding
# (iterate-2026-06-10-triage-cli-json-utf8)
#
# On Windows, sys.stdout defaults to the console codepage (cp1252) — writing
# `ensure_ascii=False` JSON for any non-cp1252 item title/detail (emoji, CJK)
# crashed the CLI with UnicodeEncodeError, breaking the WebUI live-view
# contract for exactly the real-world findings most likely to carry such
# characters. Found by the webui pending-delivery-badge boundary probe.
# PYTHONIOENCODING pins the child's stdout codec so the regression reproduces
# deterministically on every platform, not just a Windows console.
# ---------------------------------------------------------------------------

NON_ASCII_TITLE = "Outbox-önly finding ✨ 中文"


def _run_legacy_console(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), *args],
        capture_output=True, check=False, env=env,
    )


def test_list_json_is_utf8_under_legacy_console_encoding(tmp_path: Path) -> None:
    """`list --json` is a machine contract: UTF-8 bytes regardless of the
    console codepage. Pre-fix this exited non-zero with UnicodeEncodeError."""
    append_triage_item(
        tmp_path, source="manual", severity="low", kind="improvement",
        title=NON_ASCII_TITLE, detail="ümläut ✓ detail", dedup_key="utf8:probe",
    )
    res = _run_legacy_console(["--project-root", str(tmp_path), "list", "--json"])
    assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
    data = json.loads(res.stdout.decode("utf-8"))["open"]
    assert data[0]["title"] == NON_ASCII_TITLE
    assert data[0]["pendingDelivery"] is False


def test_list_human_output_survives_legacy_console_encoding(tmp_path: Path) -> None:
    """The human `list` shares the stdout path: a non-ASCII title must render
    (UTF-8), not crash the CLI with a traceback."""
    append_triage_item(
        tmp_path, source="manual", severity="low", kind="improvement",
        title=NON_ASCII_TITLE, detail="d", dedup_key="utf8:probe2",
    )
    res = _run_legacy_console(["--project-root", str(tmp_path), "list"])
    assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
    assert NON_ASCII_TITLE in res.stdout.decode("utf-8")
