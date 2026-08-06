"""``resolve_run_id`` resolves the iterate's own run_id from the run pointer.

The Stop-time audits (``audit_phase_quality_on_stop``,
``audit_compliance_on_stop``) get their ``run_id`` from
``phase_quality.resolve_run_id``. For an iterate, none of its three
non-session sources is ever populated — run_config carries no top-level
``run_id``, nothing emits a ``run_started`` event, and the loop vars are
campaign-only — so the audit was handed the raw session UUID (or ``"unknown"``
when the env var did not reach the hook). Neither is an ``iterate_history``
key, so every check behind ``unresolvable_run_id_skip`` (S2, S3, W2, S9, S10)
SKIPped on every real invocation.

``setup_iterate_worktree.py`` already writes a per-session pointer at B1a
naming the canonical run. These pin it as priority 0, and pin the failure
posture that keeps a bad pointer from ever reaching the hook: ``resolve_run_id``
is called OUTSIDE ``audit_phase_quality_on_stop``'s per-phase ``try`` and AFTER
the once-per-Stop claim is taken, so a raise there kills the audit for every
phase and the sibling fan-out invocations then no-op on the burned claim.

Composition over a real git worktree lives in
``test_resolve_run_id_pointer_composition.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402
import lib.worktree_isolation as wi  # noqa: E402

SID = "1ce34d44-0ee1-4c91-871e-d2d52fea7247"
RID = "iterate-2026-08-06-resolve-run-id-seam"
_LOOP_ENV = ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID")


@pytest.fixture(autouse=True)
def _no_loop_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """The loop vars are ambient in campaign runs; pin them off by default."""
    for var in _LOOP_ENV:
        monkeypatch.delenv(var, raising=False)


def _live_worktree(proj: Path, slug: str = "slug") -> Path:
    """A directory standing in for a live worktree.

    The real producer only ever writes a pointer whose ``worktree_path`` it has
    just created, so a pointer naming a non-existent directory is not a shape
    production emits — tests must not accidentally rely on one.
    """
    wt = proj / ".worktrees" / slug
    wt.mkdir(parents=True, exist_ok=True)
    return wt


def _pointer(proj: Path, payload: object, *, key: str = SID) -> Path:
    """Write a RAW pointer file — payload verbatim, no producer validation.

    A ``dict`` payload without its own ``worktree_path`` gets a live one, so
    each test exercises the field it is actually about.
    """
    if isinstance(payload, dict) and "worktree_path" not in payload:
        payload = {**payload, "worktree_path": str(_live_worktree(proj))}
    d = proj / ".shipwright" / "iterate_active"
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{key}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _run_config(proj: Path, data: dict) -> None:
    (proj / "shipwright_run_config.json").write_text(
        json.dumps(data), encoding="utf-8")


# --- AC-1: the pointer outranks all three lower sources -------------------

def test_pointer_outranks_every_lower_priority_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decisive precedence property, with all four sources populated.

    The pointer is keyed by the exact session being audited, so it is the only
    source that answers "which run is THIS session executing". The other three
    are project- or process-global and can name a different run entirely.
    """
    _run_config(tmp_path, {"run_id": "run-id-from-run-config"})
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "run_started", "run_id": "run-id-from-event"}) + "\n",
        encoding="utf-8")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "campaign-alpha")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "unit-3")
    _pointer(tmp_path, {"run_id": RID, "session_id": SID})

    assert pq.resolve_run_id(tmp_path, SID) == RID


# --- AC-3: with no pointer, the existing chain is untouched ---------------

def test_run_config_still_wins_when_no_pointer_exists(tmp_path: Path) -> None:
    _run_config(tmp_path, {"run_id": "run-id-from-run-config"})
    assert pq.resolve_run_id(tmp_path, SID) == "run-id-from-run-config"


def test_run_started_event_still_resolves_when_no_pointer_exists(
    tmp_path: Path,
) -> None:
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "run_started", "run_id": "run-id-from-event"}) + "\n",
        encoding="utf-8")
    assert pq.resolve_run_id(tmp_path, SID) == "run-id-from-event"


def test_loop_vars_still_resolve_when_no_pointer_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "campaign-alpha")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "unit-3")
    assert pq.resolve_run_id(tmp_path, SID) == "campaign-alpha-unit-3"


def test_session_and_unknown_tails_are_unchanged(tmp_path: Path) -> None:
    assert pq.resolve_run_id(tmp_path, SID) == SID
    assert pq.resolve_run_id(tmp_path, "") == "unknown"


# --- AC-4: a sentinel session never touches the pointer directory ---------

@pytest.mark.parametrize("session_id", ["", "unknown", "UNKNOWN", "  "])
def test_sentinel_session_attempts_no_pointer_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session_id: str,
) -> None:
    """A degenerate ``unknown.json`` must never be able to bind a run.

    Spying on the reader (rather than asserting the return value) is what makes
    "no lookup attempted" falsifiable — the return value alone would also pass
    if the lookup ran and merely missed.

    The return value is asserted only as "not the pointer's run": the tail
    returns the session id verbatim, and case-folding it is deliberately NOT
    part of this change. ``test_session_and_unknown_tails_are_unchanged``
    pins the tail itself.
    """
    _pointer(tmp_path, {"run_id": RID, "session_id": SID}, key="unknown")
    calls: list[object] = []
    monkeypatch.setattr(
        wi, "read_run_pointer", lambda *a, **k: calls.append(a) or None)

    resolved = pq.resolve_run_id(tmp_path, session_id)

    assert calls == []
    assert resolved != RID


# --- AC-5 / AC-5b: a bad pointer falls through, and never raises ----------

@pytest.mark.parametrize(
    "payload,label",
    [
        ([1, 2], "json-array"),
        ("a-bare-string", "json-string"),
        (None, "json-null"),
        ({}, "no-run-id-key"),
        ({"run_id": None, "session_id": SID}, "run-id-null"),
        ({"run_id": 42, "session_id": SID}, "run-id-number"),
        ({"run_id": ["x"], "session_id": SID}, "run-id-list"),
        ({"run_id": "", "session_id": SID}, "run-id-empty"),
        ({"run_id": "   ", "session_id": SID}, "run-id-whitespace"),
        ({"run_id": "unknown", "session_id": SID}, "run-id-sentinel"),
        ({"run_id": "UNKNOWN", "session_id": SID}, "run-id-sentinel-upper"),
    ],
)
def test_structurally_invalid_pointer_falls_through_to_the_chain(
    tmp_path: Path, payload: object, label: str,
) -> None:
    _run_config(tmp_path, {"run_id": "run-id-from-run-config"})
    _pointer(tmp_path, payload)
    assert pq.resolve_run_id(tmp_path, SID) == "run-id-from-run-config"


def test_malformed_json_pointer_falls_through(tmp_path: Path) -> None:
    d = tmp_path / ".shipwright" / "iterate_active"
    d.mkdir(parents=True)
    (d / f"{SID}.json").write_text("{not json", encoding="utf-8")
    assert pq.resolve_run_id(tmp_path, SID) == SID


def test_invalid_utf8_pointer_cannot_escape_the_resolver(tmp_path: Path) -> None:
    """The regression that would burn the once-per-Stop claim.

    ``read_run_pointer`` catches ``JSONDecodeError`` and ``OSError`` but NOT
    ``UnicodeDecodeError`` — a ``ValueError`` subclass raised by
    ``read_text(encoding="utf-8")``. Because ``resolve_run_id`` runs outside the
    hook's per-phase ``try`` and after the claim is taken, a raise here would
    kill the audit for EVERY phase while the siblings no-op on the burned claim.
    """
    d = tmp_path / ".shipwright" / "iterate_active"
    d.mkdir(parents=True)
    (d / f"{SID}.json").write_bytes(b'{"run_id": "\xff\xfe not utf-8"}')

    assert pq.resolve_run_id(tmp_path, SID) == SID


def test_unreadable_pointer_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pointer(tmp_path, {"run_id": RID, "session_id": SID})

    def _boom(*_a: object, **_k: object) -> None:
        raise OSError("pointer unreadable")

    monkeypatch.setattr(wi, "read_run_pointer", _boom)
    assert pq.resolve_run_id(tmp_path, SID) == SID


def test_a_programming_error_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-open must be narrow. A blanket ``except Exception`` around the
    lookup would hide a genuine defect in the imported helpers behind a silent
    fallback, which is how a broken seam stays broken."""
    _pointer(tmp_path, {"run_id": RID, "session_id": SID})

    def _bug(*_a: object, **_k: object) -> None:
        raise TypeError("helper signature changed")

    monkeypatch.setattr(wi, "read_run_pointer", _bug)
    with pytest.raises(TypeError):
        pq.resolve_run_id(tmp_path, SID)


# AC-9 (payload session identity) lives in
# test_resolve_run_id_pointer_identity.py.


def test_a_non_git_directory_resolves_its_own_pointer(tmp_path: Path) -> None:
    """AC-2's third shape, named explicitly.

    ``main_repo_root_or`` degrades to ``project_root`` when git resolution
    fails, so a project that is not a git repository at all still resolves its
    pointer. Most tests in this file happen to be this shape; this one asserts
    it on purpose rather than by accident.
    """
    assert not (tmp_path / ".git").exists()
    _pointer(tmp_path, {"run_id": RID, "session_id": SID})
    assert pq.resolve_run_id(tmp_path, SID) == RID


def test_a_whitespace_only_session_resolves_to_the_unknown_sentinel(
    tmp_path: Path,
) -> None:
    """The one tail change this iterate makes, pinned explicitly.

    ``session_id`` is normalised once, so whitespace-only collapses to the
    ``"unknown"`` sentinel instead of being returned verbatim. Unreachable from
    either production caller (both pass ``.strip() or "unknown"``), but pinned
    so the documented change is falsifiable.
    """
    assert pq.resolve_run_id(tmp_path, "   ") == "unknown"


# --- AC-6: producer -> consumer round trip through the real writer --------

@pytest.mark.parametrize(
    "session_id",
    [
        SID,
        "sess/with/slashes",
        "sess:with*punct?",
        "sess.with.dots",
    ],
    ids=["plain-uuid", "slashes", "punctuation", "dots"],
)
def test_round_trip_through_the_real_producer(
    tmp_path: Path, session_id: str,
) -> None:
    """The pointer FILENAME is derived from the session id via
    ``sanitize_run_id_for_filename``; the ``run_id`` is a payload value and is
    never transformed. Driving the real ``write_run_pointer`` proves producer
    and consumer agree on the filename for session ids the sanitiser rewrites,
    and that the run_id survives byte-identical.
    """
    wi.write_run_pointer(
        tmp_path,
        run_id=RID,
        slug="resolve-run-id-seam",
        branch="iterate/resolve-run-id-seam",
        worktree_path=_live_worktree(tmp_path, "resolve-run-id-seam"),
        session_id=session_id,
    )
    assert pq.resolve_run_id(tmp_path, session_id) == RID
