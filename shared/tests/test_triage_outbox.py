"""D1 (campaign 2026-06-08-triage-outbox-delivery): per-tree gitignored outbox.

The outbox ``.shipwright/triage.outbox.jsonl`` is a transient, per-tree,
GITIGNORED buffer for background main-tree triage producers. Idle-main
producers route there (no tracked-log churn -> no main drift); worktree /
iterate-branch producers keep writing the tracked ``triage.jsonl`` directly
(those ship in the PR). The shared reader ``read_all_items`` returns the
UNION (tracked then outbox, last-status-wins keyed by id) so Python consumers
see background findings immediately.

Acceptance criteria covered (D1 spec):
- AC1: a ``to_outbox=True`` append lands in the outbox; the tracked file is
  byte-unchanged.
- AC2: ``read_all_items`` returns tracked UNION outbox.
- AC3: the outbox is gitignored (covered by ``test_triage_outbox_gitignored``).
- AC4: an iterate-branch ``should_route_to_outbox`` is False (tracked); idle
  main is True (outbox).

Boundary probes (touches_io_boundary, ADR-024 / references/boundary-probes.md):
round-trip producer->outbox->union-reader, CRLF + non-ASCII tolerance,
idempotent dedup across the union, and an outbox-resident ``mark_status`` flip.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from triage import (  # noqa: E402
    OUTBOX_FILE,
    TRIAGE_FILE,
    append_triage_item,
    append_triage_item_idempotent,
    mark_status,
    read_all_items,
    should_route_to_outbox,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _tracked_path(project: Path) -> Path:
    return project / ".shipwright" / TRIAGE_FILE


def _outbox_path(project: Path) -> Path:
    return project / ".shipwright" / OUTBOX_FILE


# --- Constants ----------------------------------------------------------

def test_outbox_constant_present() -> None:
    assert triage.OUTBOX_FILE == "triage.outbox.jsonl"


# --- AC1: to_outbox=True routes to the outbox, tracked stays clean ------

def test_to_outbox_append_lands_in_outbox_not_tracked(project: Path) -> None:
    item_id = append_triage_item(
        project,
        source="plugin-sync",
        severity="low",
        kind="maintenance",
        title="background finding",
        detail="d",
        to_outbox=True,
    )
    assert item_id.startswith("trg-")
    assert _outbox_path(project).exists()
    # Tracked file must NOT have been created/written by an outbox append.
    assert not _tracked_path(project).exists()
    # Resolved view (union) sees it.
    [resolved] = read_all_items(project)
    assert resolved["id"] == item_id
    assert resolved["source"] == "plugin-sync"


def test_to_outbox_append_does_not_touch_existing_tracked(project: Path) -> None:
    """AC1: a pre-existing tracked log is byte-unchanged by an outbox append."""
    append_triage_item(
        project, source="iterate", severity="low", kind="bug",
        title="tracked item", detail="d",
    )
    tracked_before = _tracked_path(project).read_bytes()

    append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="bg item", detail="d", to_outbox=True,
    )
    tracked_after = _tracked_path(project).read_bytes()
    assert tracked_after == tracked_before  # zero main drift


def test_outbox_has_no_schema_header(project: Path) -> None:
    """The outbox is a transient buffer; it carries no schema header line."""
    append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="t", detail="d", to_outbox=True,
    )
    lines = [
        L for L in _outbox_path(project).read_text(encoding="utf-8").splitlines()
        if L.strip()
    ]
    # Exactly one append line, no header.
    assert len(lines) == 1
    assert '"event":"append"' in lines[0]
    assert '"schema":"triage"' not in lines[0]


# --- AC2: read_all_items returns the union -----------------------------

def test_read_all_items_returns_union(project: Path) -> None:
    tracked_id = append_triage_item(
        project, source="iterate", severity="medium", kind="bug",
        title="tracked", detail="d",
    )
    outbox_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="outbox", detail="d", to_outbox=True,
    )
    ids = {it["id"] for it in read_all_items(project)}
    assert ids == {tracked_id, outbox_id}


def test_union_is_tracked_then_outbox_order(project: Path) -> None:
    """Tracked items resolve BEFORE outbox items in the returned list (the
    union reader inserts tracked appends first, then outbox appends)."""
    tracked_id = append_triage_item(
        project, source="iterate", severity="low", kind="bug",
        title="a", detail="d",
    )
    outbox_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="b", detail="d", to_outbox=True,
    )
    items = read_all_items(project)
    assert [it["id"] for it in items] == [tracked_id, outbox_id]


# --- AC4: should_route_to_outbox is branch-based -----------------------

def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(["init"], tmp_path)
    _git(["config", "user.email", "t@t.t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["commit", "--allow-empty", "-m", "init"], tmp_path)
    return tmp_path


def test_should_route_idle_main_is_true(git_repo: Path, tmp_path: Path) -> None:
    """On the default branch (idle main) WITH an origin, route to the outbox.

    FIX 2 (D1 review cascade): routing now ALSO requires a real delivery path —
    an ``origin`` remote — so the test must add one (a throwaway local URL).
    """
    # default_branch() falls back to "main"; rename the init branch to match.
    _git(["branch", "-M", "main"], git_repo)
    origin = tmp_path / "origin-throwaway"
    _git(["remote", "add", "origin", str(origin)], git_repo)
    assert should_route_to_outbox(git_repo) is True


def test_should_route_no_origin_is_false(git_repo: Path) -> None:
    """Idle main but NO ``origin`` remote → False (no delivery path; tracked).

    FIX 2: ``default_branch`` falls back to literal ``"main"`` with no
    ``origin/HEAD``, so without the origin check a fresh/no-origin repo on
    ``main`` would route a background finding to the gitignored outbox and BURY
    it. The origin requirement keeps it on the tracked log (safe default).
    """
    _git(["branch", "-M", "main"], git_repo)
    assert should_route_to_outbox(git_repo) is False


def test_should_route_iterate_branch_is_false(git_repo: Path, tmp_path: Path) -> None:
    """On an iterate/* branch (worktree or runner), write the tracked log.

    Origin present (so the ONLY reason to route tracked is the branch), proving
    the branch check still gates even when the delivery path exists.
    """
    _git(["branch", "-M", "main"], git_repo)
    _git(["remote", "add", "origin", str(tmp_path / "origin-throwaway")], git_repo)
    _git(["checkout", "-b", "iterate/some-work"], git_repo)
    assert should_route_to_outbox(git_repo) is False


def test_should_route_non_git_is_false(tmp_path: Path) -> None:
    """Non-git / adopt-not-yet repo: fail safe to the tracked log."""
    assert should_route_to_outbox(tmp_path) is False


# --- Idempotent dedup works ACROSS the union ----------------------------

def test_idempotent_outbox_suppresses_outbox_duplicate(project: Path) -> None:
    first = append_triage_item_idempotent(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="t", detail="d", dedup_key="plugin-sync:x",
        match_commit=False, window_seconds=None, to_outbox=True,
    )
    second = append_triage_item_idempotent(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="t", detail="d", dedup_key="plugin-sync:x",
        match_commit=False, window_seconds=None, to_outbox=True,
    )
    assert first is not None
    assert second is None
    assert len(read_all_items(project)) == 1


def test_idempotent_open_tracked_suppresses_outbox_append(project: Path) -> None:
    """An open TRACKED item suppresses a duplicate OUTBOX append (union scan)."""
    tracked = append_triage_item_idempotent(
        project, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key="compliance:backlog:abc",
        match_commit=False, window_seconds=None,
    )
    dup = append_triage_item_idempotent(
        project, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key="compliance:backlog:abc",
        match_commit=False, window_seconds=None, to_outbox=True,
    )
    assert tracked is not None
    assert dup is None  # dedup spans the union
    assert len(read_all_items(project)) == 1


def test_idempotent_open_outbox_suppresses_tracked_append(project: Path) -> None:
    """An open OUTBOX item suppresses a duplicate TRACKED append (union scan)."""
    out = append_triage_item_idempotent(
        project, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key="compliance:backlog:zzz",
        match_commit=False, window_seconds=None, to_outbox=True,
    )
    dup = append_triage_item_idempotent(
        project, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key="compliance:backlog:zzz",
        match_commit=False, window_seconds=None,
    )
    assert out is not None
    assert dup is None
    assert len(read_all_items(project)) == 1


# --- mark_status can flip an outbox-resident item -----------------------

def test_mark_status_flips_outbox_item(project: Path) -> None:
    item_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="t", detail="d", to_outbox=True,
    )
    # Residence-derived (FIX 1): the item lives in the outbox, so the dismiss
    # lands in the outbox WITHOUT any caller flag.
    mark_status(
        project, item_id, new_status="dismissed", by="op",
        reason="handled",
    )
    [resolved] = read_all_items(project)
    assert resolved["id"] == item_id
    assert resolved["status"] == "dismissed"
    assert resolved["statusReason"] == "handled"
    # The status event landed in the outbox, NOT the tracked log.
    assert not _tracked_path(project).exists()


def test_mark_status_finds_outbox_id_via_union(project: Path) -> None:
    """mark_status' id-existence check is union-aware (id lives in the outbox)."""
    item_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="t", detail="d", to_outbox=True,
    )
    # No tracked file exists; the id is only in the outbox. This must NOT
    # raise FileNotFoundError / KeyError, and (FIX 1) residence-derives outbox.
    mark_status(
        project, item_id, new_status="promoted", by="op",
        promoted_task_id="EXT:1",
    )
    [resolved] = read_all_items(project)
    assert resolved["status"] == "promoted"
    assert resolved["promotedTaskId"] == "EXT:1"


def test_mark_status_unknown_id_still_raises(project: Path) -> None:
    append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="t", detail="d", to_outbox=True,
    )
    with pytest.raises(KeyError, match="trg-00000000"):
        mark_status(
            project, "trg-00000000", new_status="dismissed", by="t",
        )


# --- Cross-file precedence (external-review High; probe-found) ----------

def _append_raw(path: Path, obj: dict) -> None:
    """Write one raw JSONL line to ``path`` (header-less append)."""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(obj) + "\n")


def _append_raw_line(path: Path, line: str) -> None:
    """Write a pre-serialized JSONL ``line`` to ``path`` (header-less append)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(line.rstrip("\n") + "\n")


def test_tracked_status_wins_over_outbox_append(project: Path) -> None:
    """A background item whose ``append`` lives in the OUTBOX, then dismissed
    by a TRACKED status line, resolves to ``dismissed`` — the outbox append must
    NOT clobber the tracked status back to ``triage``.

    Regression guard for the two-pass union resolver. External plan review
    (OpenAI #5 / Gemini #1, High) flagged this; an empirical probe reproduced
    it under the naive single-pass tracked-then-outbox resolution. The status
    is injected RAW into the tracked file (a genuine cross-file shape, e.g. an
    out-of-band tracked append) since residence-derived ``mark_status`` would
    co-locate the dismiss with its outbox append.
    """
    item_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="bg", detail="d", to_outbox=True,
    )
    # Cross-file dismiss: status raw in the TRACKED log (append is in outbox).
    _append_raw(_tracked_path(project), {
        "event": "status", "id": item_id, "ts": "2026-06-08T00:00:05Z",
        "newStatus": "dismissed", "by": "user", "reason": "handled",
        "promotedTaskId": None,
    })
    [resolved] = read_all_items(project)
    assert resolved["status"] == "dismissed"
    assert resolved["statusReason"] == "handled"


def test_outbox_status_wins_over_tracked_append(project: Path) -> None:
    """Symmetric: a tracked item flipped by an OUTBOX status resolves flipped
    (tracked append applied first, outbox status overlays it). Status injected
    RAW into the outbox (cross-file shape; residence-derived mark_status would
    write tracked for a tracked-resident append)."""
    item_id = append_triage_item(
        project, source="compliance", severity="high", kind="compliance",
        title="c", detail="d",
    )
    _append_raw(_outbox_path(project), {
        "event": "status", "id": item_id, "ts": "2026-06-08T00:00:05Z",
        "newStatus": "promoted", "by": "op", "reason": None,
        "promotedTaskId": "EXT:9",
    })
    [resolved] = read_all_items(project)
    assert resolved["status"] == "promoted"
    assert resolved["promotedTaskId"] == "EXT:9"


def test_cross_file_status_resolves_by_timestamp(project: Path) -> None:
    """When the same id is flipped in BOTH files, the chronologically-later
    flip wins regardless of source file (ts-primary ordering).

    Probe-found during the asymptote pass: under pure file-order (tracked
    statuses always before outbox statuses), a later tracked ``promoted`` was
    clobbered by an earlier outbox ``dismissed``. ts-primary fixes it.
    """
    import json
    # Base item created in the TRACKED log (realistic header-bearing shape).
    item_id = append_triage_item(
        project, source="compliance", severity="high", kind="compliance",
        title="x", detail="d",
    )
    tracked = _tracked_path(project)
    assert tracked.read_text(encoding="utf-8").splitlines()[0].startswith(
        '{"v":1,"schema":"triage"'
    ), "precondition: tracked file carries the schema header"

    # Earlier OUTBOX dismiss (ts T1) ... then later TRACKED promote (ts T2>T1).
    # Explicit, ordered timestamps so the test is clock-independent.
    outbox = _outbox_path(project)
    outbox.parent.mkdir(parents=True, exist_ok=True)
    with outbox.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps({
            "event": "status", "id": item_id, "ts": "2026-06-08T00:00:01Z",
            "newStatus": "dismissed", "by": "op", "reason": "early",
            "promotedTaskId": None,
        }) + "\n")
    with tracked.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps({
            "event": "status", "id": item_id, "ts": "2026-06-08T00:00:02Z",
            "newStatus": "promoted", "by": "op", "reason": "late",
            "promotedTaskId": "EXT:1",
        }) + "\n")
    [resolved] = read_all_items(project)
    assert resolved["status"] == "promoted"  # later ts wins across files
    assert resolved["statusReason"] == "late"


def test_malformed_ts_status_does_not_override_valid_later(project: Path) -> None:
    """A status line with a malformed/null ts must NOT outrank a later valid
    status (external code review, OpenAI High). Malformed ts sorts earliest.
    """
    import json
    item_id = append_triage_item(
        project, source="compliance", severity="high", kind="compliance",
        title="x", detail="d",
    )
    tracked = _tracked_path(project)
    with tracked.open("a", encoding="utf-8") as fp:
        # Malformed ts (null) dismiss — must be treated as "oldest/unknown".
        fp.write(json.dumps({
            "event": "status", "id": item_id, "ts": None,
            "newStatus": "dismissed", "by": "op", "reason": "malformed",
            "promotedTaskId": None,
        }) + "\n")
        # Valid later promote.
        fp.write(json.dumps({
            "event": "status", "id": item_id, "ts": "2026-06-08T00:00:02Z",
            "newStatus": "promoted", "by": "op", "reason": "valid",
            "promotedTaskId": "EXT:1",
        }) + "\n")
    [resolved] = read_all_items(project)
    assert resolved["status"] == "promoted"
    assert resolved["statusReason"] == "valid"


# --- Boundary probes: round-trip + CRLF + non-ASCII ---------------------

def test_round_trip_outbox_all_fields(project: Path) -> None:
    """ADR-024 round-trip: produce->outbox file->union consumer preserves fields."""
    item_id = append_triage_item(
        project,
        source="plugin-sync",
        severity="medium",
        kind="maintenance",
        title="Üñîçōdé ✓ 中文 background finding",
        detail="multi\nline\ndetail",
        evidence_path=".shipwright/x.json",
        run_id="iterate-2026-06-08-outbox-delivery-d1",
        commit="abc1234",
        to_outbox=True,
    )
    [resolved] = read_all_items(project)
    assert resolved["id"] == item_id
    assert resolved["title"] == "Üñîçōdé ✓ 中文 background finding"
    assert "\n" in resolved["detail"]
    assert resolved["evidencePath"] == ".shipwright/x.json"
    assert resolved["runId"] == "iterate-2026-06-08-outbox-delivery-d1"
    assert resolved["commit"] == "abc1234"
    assert resolved["status"] == "triage"


def test_outbox_crlf_lines_tolerated(project: Path) -> None:
    """A CRLF-terminated outbox line round-trips through the union reader.

    references/boundary-probes.md CRLF probe: a human-edited or
    Windows-written outbox could carry CRLF; the reader strips and parses it.
    """
    real_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="real", detail="d", to_outbox=True,
    )
    # Inject a CRLF-terminated valid append line directly.
    import json
    extra = {
        "event": "append", "id": "trg-crlf0001", "ts": "2026-06-08T00:00:00Z",
        "originalTs": "2026-06-08T00:00:00Z", "source": "plugin-sync",
        "severity": "low", "kind": "maintenance", "title": "crlf",
        "detail": "d", "status": "triage",
    }
    with _outbox_path(project).open("ab") as fp:
        fp.write((json.dumps(extra) + "\r\n").encode("utf-8"))

    ids = {it["id"] for it in read_all_items(project)}
    assert {real_id, "trg-crlf0001"} <= ids


# --- AC3: the outbox is gitignored (in this repo) -----------------------

def test_triage_outbox_gitignored() -> None:
    """`git check-ignore` confirms the outbox is ignored in the framework repo.

    The outbox sits under `.shipwright/` which the `/.shipwright/*` wildcard
    ignores; D1 deliberately adds NO `!` negation for it, so it stays ignored.
    """
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "-C", str(repo_root), "check-ignore",
         ".shipwright/triage.outbox.jsonl"],
        capture_output=True, text=True,
    )
    # exit 0 => the path is ignored.
    assert result.returncode == 0, (
        f"outbox not gitignored: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


# --- FIX 1 (D1 review cascade): residence-derived mark_status -----------

def test_mark_status_residence_outbox_no_tracked_orphan(project: Path) -> None:
    """Split/resurrection guard: an OUTBOX-resident item dismissed via
    ``mark_status`` writes the status to the OUTBOX, NOT the tracked log.

    HIGH-1: under the old caller-flag routing a dismiss could land in the
    tracked log while the append lived only in the gitignored outbox → on a
    tree without that outbox the status vanished and the item RESURRECTED, AND
    an orphan status polluted the tracked log on idle main (reconcile rejects
    it → unhealable pull-block). Residence-derivation keeps status with append.
    """
    item_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="bg", detail="d", to_outbox=True,
    )
    mark_status(project, item_id, new_status="dismissed", by="op", reason="r")

    # (a) the status event is in the OUTBOX file, not tracked.
    outbox_raw = _outbox_path(project).read_text(encoding="utf-8")
    assert '"event":"status"' in outbox_raw
    assert f'"id":"{item_id}"' in outbox_raw
    # (b) NO tracked file / NO orphan status line for that id in tracked.
    if _tracked_path(project).exists():
        tracked_raw = _tracked_path(project).read_text(encoding="utf-8")
        assert '"event":"status"' not in tracked_raw, "orphan status in tracked log"
    else:
        assert True  # cleaner: tracked log never created at all
    # (c) the union resolves the item as dismissed.
    [resolved] = read_all_items(project)
    assert resolved["id"] == item_id
    assert resolved["status"] == "dismissed"


def test_mark_status_residence_tracked_preferred_on_overlap(project: Path) -> None:
    """Tracked-preferred: when the same append id exists in BOTH files
    (post-sweep, pre-GC), ``mark_status`` writes the status to TRACKED so it
    ships in the PR and the GC can later drop the outbox copy."""
    item_id = append_triage_item(
        project, source="plugin-sync", severity="low", kind="maintenance",
        title="bg", detail="d", to_outbox=True,
    )
    # Simulate the sweep having folded the same append into the tracked log.
    src_line = next(
        L for L in _outbox_path(project).read_text(encoding="utf-8").splitlines()
        if f'"id":"{item_id}"' in L and '"event":"append"' in L
    )
    _append_raw_line(_tracked_path(project), src_line)

    mark_status(project, item_id, new_status="dismissed", by="op", reason="r")

    tracked_raw = _tracked_path(project).read_text(encoding="utf-8")
    assert '"event":"status"' in tracked_raw, "status must land in TRACKED on overlap"
    outbox_raw = _outbox_path(project).read_text(encoding="utf-8")
    assert '"event":"status"' not in outbox_raw, "status must NOT land in outbox on overlap"
    [resolved] = read_all_items(project)
    assert resolved["status"] == "dismissed"


def test_mark_status_has_no_to_outbox_param() -> None:
    """``mark_status`` no longer accepts a ``to_outbox`` kwarg (residence-derived).

    The caller can no longer control the write target (idle-main vs iterate);
    passing the old kwarg raises TypeError, and the signature omits it.
    """
    import inspect
    params = inspect.signature(mark_status).parameters
    assert "to_outbox" not in params

    # Need a real item so the call gets past validation before the kwarg error.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        item_id = append_triage_item(
            root, source="iterate", severity="low", kind="bug",
            title="t", detail="d",
        )
        with pytest.raises(TypeError):
            mark_status(  # type: ignore[call-arg]
                root, item_id, new_status="dismissed", by="t", to_outbox=True,
            )


# --- Idle-main status symmetry (2026-06-12) -----------------------------
# `append_triage_item` routes idle-main writes to the outbox (via
# `should_route_to_outbox`), but `mark_status` historically used pure
# residence (TRACKED-PREFERRED) — so a status flip on a TRACKED-resident item
# on idle main landed in the tracked log = undelivered drift: it blocks a hand
# `git pull --ff-only` and never reaches origin (the iterate sweep delivers
# ONLY the outbox; reconcile_main_triage is manual-CLI-only post-D2). This
# completes D1's "tracked clean on idle main" intent for the STATUS side.


def test_mark_status_idle_main_tracked_item_routes_to_outbox(
    git_repo: Path, tmp_path: Path,
) -> None:
    """On idle main (origin + default branch) a status flip on a TRACKED item
    routes to the OUTBOX (delivered by the sweep), NOT the tracked log — so it
    never becomes undelivered drift. The tracked log stays byte-unchanged; the
    union still resolves the item as dismissed immediately."""
    _git(["branch", "-M", "main"], git_repo)
    _git(["remote", "add", "origin", str(tmp_path / "origin-throwaway")], git_repo)
    assert should_route_to_outbox(git_repo) is True  # precondition: idle main

    # A TRACKED-resident append (the common case — a committed finding on origin).
    item_id = append_triage_item(
        git_repo, source="iterate", severity="low", kind="bug",
        title="t", detail="d", to_outbox=False,
    )
    tracked_before = _tracked_path(git_repo).read_text(encoding="utf-8")
    assert '"event":"status"' not in tracked_before  # sanity

    mark_status(git_repo, item_id, new_status="dismissed", by="webui", reason="done")

    # (a) status landed in the OUTBOX, keyed by the item id.
    assert _outbox_path(git_repo).exists(), "status flip created no outbox"
    outbox_raw = _outbox_path(git_repo).read_text(encoding="utf-8")
    assert '"event":"status"' in outbox_raw and f'"id":"{item_id}"' in outbox_raw
    # (b) tracked log is byte-unchanged — no idle-main drift, no pull-block.
    assert _tracked_path(git_repo).read_text(encoding="utf-8") == tracked_before
    # (c) loss-proof: the union resolves the dismiss immediately.
    [resolved] = read_all_items(git_repo)
    assert resolved["id"] == item_id and resolved["status"] == "dismissed"


def test_mark_status_iterate_branch_tracked_item_stays_tracked(
    git_repo: Path, tmp_path: Path,
) -> None:
    """Regression guard: NOT idle main (an iterate/* branch — a worktree) keeps
    residence (TRACKED-PREFERRED), because there a tracked write ships in the
    PR. The idle-main routing must not leak into the worktree path."""
    _git(["branch", "-M", "main"], git_repo)
    _git(["remote", "add", "origin", str(tmp_path / "origin-throwaway")], git_repo)
    item_id = append_triage_item(
        git_repo, source="iterate", severity="low", kind="bug",
        title="t", detail="d", to_outbox=False,
    )
    _git(["checkout", "-b", "iterate/some-work"], git_repo)
    assert should_route_to_outbox(git_repo) is False  # precondition: not idle main

    mark_status(git_repo, item_id, new_status="dismissed", by="op", reason="r")

    tracked_raw = _tracked_path(git_repo).read_text(encoding="utf-8")
    assert '"event":"status"' in tracked_raw, "worktree status must ship in tracked/PR"
    if _outbox_path(git_repo).exists():
        assert '"event":"status"' not in _outbox_path(git_repo).read_text(encoding="utf-8")
