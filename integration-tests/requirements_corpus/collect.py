"""Orchestrate the realm subprocesses and merge their results.

One process per import realm, not one per target: a handful of processes keeps
the harness well clear of the ``slow`` marker while still giving real isolation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .registry import REALMS

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parent.parent

SCHEMA_VERSION = 1


class CollectError(RuntimeError):
    """A realm subprocess failed. Never swallow this -- a realm that fails to
    run silently would drop its targets from the matrix and read as green."""


def collect_all(repo_root: Path | None = None, timeout: int = 180) -> dict:
    root = Path(repo_root or REPO_ROOT)
    merged: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="swcorpus-out-") as tmp:
        for realm in REALMS:
            out = Path(tmp) / f"{realm}.json"
            proc = subprocess.run(
                [sys.executable, str(_HERE / "_collect_realm.py"),
                 "--realm", realm, "--repo-root", str(root), "--out", str(out)],
                capture_output=True, text=True, encoding="utf-8",
                cwd=str(root), timeout=timeout,
            )
            if proc.returncode != 0 or not out.exists():
                raise CollectError(
                    f"realm {realm!r} failed (exit {proc.returncode}).\n"
                    f"stdout: {proc.stdout[-1500:]}\nstderr: {proc.stderr[-2500:]}"
                )
            merged.update(json.loads(out.read_text(encoding="utf-8")))
    return {"schema_version": SCHEMA_VERSION, "targets": merged}


def dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
