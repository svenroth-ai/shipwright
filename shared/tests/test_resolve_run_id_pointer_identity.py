"""AC-9 — a run pointer must prove which session it belongs to.

The pointer's FILENAME is derived from the session id via
``sanitize_run_id_for_filename``, which maps several distinct characters onto
``-``. Two different session ids can therefore land on the same filename, and
the file is world-writable local state besides. So the filename is not proof of
ownership: ``pointer_run_id`` additionally requires the payload's own
``session_id`` to name the session being audited.

The comparison is ``isinstance``-guarded before it is normalised. Coercing
through ``str()`` would let a non-string payload bind whenever its repr matched
the audited id — ``42`` against ``"42"``, ``true`` against ``"True"`` — which is
precisely the structural spoofing the check exists to refuse.
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

SID = "1ce34d44-0ee1-4c91-871e-d2d52fea7247"
RID = "iterate-2026-08-06-resolve-run-id-seam"
_FALLBACK = "run-id-from-run-config"


@pytest.fixture(autouse=True)
def _no_loop_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID"):
        monkeypatch.delenv(var, raising=False)


def _pointer(proj: Path, payload_session: object, *, key: str = SID,
             fallback: bool = True) -> None:
    if fallback:
        (proj / "shipwright_run_config.json").write_text(
            json.dumps({"run_id": _FALLBACK}), encoding="utf-8")
    wt = proj / ".worktrees" / "slug"
    wt.mkdir(parents=True, exist_ok=True)
    d = proj / ".shipwright" / "iterate_active"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(
        json.dumps({"run_id": RID, "session_id": payload_session,
                    "worktree_path": str(wt)}),
        encoding="utf-8")


@pytest.mark.parametrize(
    "payload_session",
    ["a-different-session", "", None, [SID], {"id": SID}],
    ids=["foreign", "blank", "null", "list", "dict"],
)
def test_pointer_naming_another_session_is_rejected(
    tmp_path: Path, payload_session: object,
) -> None:
    _pointer(tmp_path, payload_session)
    assert pq.resolve_run_id(tmp_path, SID) == _FALLBACK


@pytest.mark.parametrize(
    "audited,payload_session",
    [("42", 42), ("True", True), ("3.5", 3.5)],
    ids=["int", "bool", "float"],
)
def test_a_non_string_session_cannot_bind_via_its_repr(
    tmp_path: Path, audited: str, payload_session: object,
) -> None:
    """The case a ``str()``-coercing comparison would wave through.

    Each payload here has a repr EQUAL to the audited session id, so a
    coercing check accepts it and only an ``isinstance`` check refuses it.
    That makes this the test that actually pins the guard — the ``42`` case in
    the rejection list above passes either way, since ``"42" != SID``.
    """
    _pointer(tmp_path, payload_session, key=audited)
    assert str(payload_session) == audited  # the spoof is real, not hypothetical
    assert pq.resolve_run_id(tmp_path, audited) == _FALLBACK


def test_session_identity_is_compared_after_normalisation(
    tmp_path: Path,
) -> None:
    """The guard must not over-fire on the producer/consumer asymmetry.

    ``setup_iterate_worktree`` stores the session id as given; the Stop hook
    strips it before calling. Both sides are normalised so a padded payload
    still matches a genuine pointer.
    """
    _pointer(tmp_path, f"  {SID}  ")
    assert pq.resolve_run_id(tmp_path, SID) == RID


def test_a_matching_session_still_resolves(tmp_path: Path) -> None:
    """Baseline that keeps the rejections above meaningful."""
    _pointer(tmp_path, SID)
    assert pq.resolve_run_id(tmp_path, SID) == RID
