#!/usr/bin/env python3
"""Drive the REAL iterate-setup CLI against the shipwright-webui failure shape.

The unit + component tests call ``sweep_outbox_to_branch`` directly. This drives the
command an operator actually runs — ``setup_iterate_worktree.py``, the entry point that
owns the sweep — against a real git repository seeded with the exact state that ate two
dismisses in shipwright-webui on 2026-07-14:

    main's TRACKED triage.jsonl carries an uncommitted append (in NO git object),
    and the operator's dismiss for it sits in the gitignored outbox.

Then it asks the question the OPERATOR asks — "is the item dismissed?" — through the
same reader the Command Center board uses (``triage.read_all_items``). Before the fix
the answer was "no": the dismiss was quarantined away, the sweep reported success, and
the item resurrected on the board forever.

    uv run scripts/verify_sweep_delivery_surface.py

Exit 0 = the dismiss survives, is delivered on the branch, and a real quarantine is
surfaced to the operator. Non-zero = the delivery surface can still lose an operator
action.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SETUP = _ROOT / "shared" / "scripts" / "tools" / "setup_iterate_worktree.py"
_SHARED_SCRIPTS = _ROOT / "shared" / "scripts"

TRIAGE = ".shipwright/triage.jsonl"
OUTBOX = ".shipwright/triage.outbox.jsonl"
QUARANTINE = ".shipwright/triage.outbox.quarantine.jsonl"
HEADER = '{"v":1,"schema":"triage","created":"2026-07-14T00:00:00Z"}'
DRIFT_ID = "trg-6db81c59"   # the webui item, by name
GHOST_ID = "trg-ghost"      # a genuine orphan: a status whose append exists nowhere

_checks: list[tuple[bool, str]] = []


def _force_utf8_stdio() -> None:
    """Emit UTF-8 regardless of the console code page. This script prints arrows; on a
    Windows cp1252 console a bare ``print`` of those raises UnicodeEncodeError and the
    whole gate dies for a cosmetic reason. Same guard verify_contract_surface.py carries."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - defensive
                pass


def check(ok: bool, label: str) -> None:
    _checks.append((bool(ok), label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def item(iid: str) -> str:
    return json.dumps(
        {"event": "append", "id": iid, "ts": "2026-07-14T06:00:00Z",
         "title": "board item", "status": "triage"},
        separators=(",", ":"),
    )


def status(iid: str) -> str:
    return json.dumps(
        {"event": "status", "id": iid, "ts": "2026-07-14T14:55:07Z",
         "newStatus": "dismissed", "by": "operatorReview"},
        separators=(",", ":"),
    )


def seed_repo(root: Path) -> Path:
    """A git repo with an origin remote, a committed triage log, and the webui state."""
    origin, work = root / "origin.git", root / "work"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(work)], capture_output=True)
    git(work, "config", "user.email", "surface@test.invalid")
    git(work, "config", "user.name", "Surface Check")
    git(work, "remote", "add", "origin", str(origin))
    (work / ".shipwright").mkdir(parents=True, exist_ok=True)
    (work / TRIAGE).write_text(f"{HEADER}\n{item('trg-seed')}\n", encoding="utf-8", newline="\n")
    (work / ".gitattributes").write_text(f"{TRIAGE} merge=union\n", encoding="utf-8", newline="\n")
    (work / ".gitignore").write_text(f"{OUTBOX}\n{QUARANTINE}\n", encoding="utf-8", newline="\n")
    git(work, "add", "--", TRIAGE, ".gitattributes", ".gitignore")
    git(work, "commit", "-m", "seed triage")
    git(work, "push", "origin", "main")
    git(work, "remote", "set-head", "origin", "main")

    # THE FAILURE SHAPE. The append exists in no git object — only as an uncommitted
    # modification of main's TRACKED log. The dismiss for it waits in the outbox.
    append_line(work / TRIAGE, item(DRIFT_ID))
    append_line(work / OUTBOX, status(DRIFT_ID))
    # ...plus a genuine orphan, whose quarantine MUST reach the operator.
    append_line(work / OUTBOX, status(GHOST_ID))
    return work


def main() -> int:
    _force_utf8_stdio()
    with tempfile.TemporaryDirectory() as tmp:
        work = seed_repo(Path(tmp))
        dirty = git(work, "status", "--porcelain", "--", TRIAGE).stdout.strip()
        check(dirty.startswith("M"), "fixture: the append is undelivered drift on main (M triage.jsonl)")

        proc = subprocess.run(
            [sys.executable, str(_SETUP), "--project-root", str(work),
             "--slug", "surface-check", "--run-id", "surface-check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(work),
        )
        print(f"\n  setup exit={proc.returncode}")
        if proc.returncode != 0:
            print(proc.stdout[-2000:], proc.stderr[-2000:])
            return 1
        payload = json.loads(proc.stdout)
        worktree = Path(payload["project_root"])

        # 1. The operator's question, asked through the board's own reader.
        sys.path.insert(0, str(_SHARED_SCRIPTS))
        import triage  # noqa: PLC0415 — the real reader, imported after path wiring

        resolved = {i["id"]: i["status"] for i in triage.read_all_items(worktree)}
        check(resolved.get(DRIFT_ID) == "dismissed",
              f"the operator's dismiss survived: {DRIFT_ID} reads as "
              f"{resolved.get(DRIFT_ID, 'MISSING')!r} (was: back to 'triage', forever)")

        # 2. Delivered, not merely present locally: both lines are COMMITTED on the branch.
        branch = git(worktree, "show", f"HEAD:{TRIAGE}").stdout
        check(item(DRIFT_ID) in branch, "the drift append is committed on the iterate branch (→ PR → origin)")
        check(status(DRIFT_ID) in branch, "the dismiss is committed on the iterate branch (→ PR → origin)")

        # 3. The dismiss was never quarantined; the GENUINE orphan was — and said so.
        quarantined = (work / QUARANTINE).read_text(encoding="utf-8") if (work / QUARANTINE).exists() else ""
        check(DRIFT_ID not in quarantined, "the dismiss was NOT eaten by the quarantine")
        check(GHOST_ID in quarantined, "a genuine orphan is still quarantined (the #303 behavior holds)")
        warned = [w for w in payload.get("warnings", []) if "QUARANTINED" in w]
        check(bool(warned), f"the quarantine reached the operator: {warned or 'NOTHING WAS PRINTED'}")

        # 4. Main is left clean — the drift is delivered, not duplicated.
        check(not git(work, "status", "--porcelain", "--", TRIAGE).stdout.strip(),
              "main's tracked log is clean again (the drift moved, it was not copied)")

    failed = [label for ok, label in _checks if not ok]
    print(f"\n{len(_checks) - len(failed)}/{len(_checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
