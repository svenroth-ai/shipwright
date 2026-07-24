"""Shared helpers for the ``finalize_security_compliance`` test modules.

Not collected by pytest (``python_files = test_*.py``). Split out of
``test_finalize_security_compliance.py`` at
iterate-2026-07-24-finalizer-events-staging so the write-set regression suite
could live in its own ``<300``-line sibling module without ratcheting the bloat
baseline. Imported by that file, ``test_finalize_write_set.py``, and
``conftest.py`` (for the fixtures).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


def load_finalize_module():
    """Load ``finalize_security_compliance`` via importlib + sentinel name.

    ``tools/`` is a namespace package shared across plugins; an earlier test in
    the run may pin ``tools`` to a sibling plugin's ``scripts/tools/``. Loading
    via a sentinel name avoids the ``tools`` slot entirely (mirrors
    ``audit_adapters.load_shared_lib``).
    """
    target = PLUGIN_ROOT / "scripts" / "tools" / "finalize_security_compliance.py"
    sentinel = "_test_security_finalize_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, target)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(sentinel, None)
        raise
    return mod


# --- git fixture helpers (mirror test_audit_snapshot.py) -------------------


def git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tester"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"],
                   check=True, capture_output=True)


def git_commit(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, content in files.items():
        full = repo / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", msg],
                   check=True, capture_output=True)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def porcelain(repo: Path) -> str:
    """Full working-tree status — empty string means a clean tree."""
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def committed_files(repo: Path) -> set[str]:
    """Paths touched by HEAD (forward-slash normalized)."""
    out = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--format=", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout
    return {ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()}


def baseline_compliance() -> dict[str, str]:
    return {
        ".shipwright/compliance/dashboard.md":
            "# Dashboard\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
        ".shipwright/compliance/test-evidence.md":
            "# Test Evidence\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
        ".shipwright/compliance/change-history.md":
            "# Change History\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
        ".shipwright/compliance/sbom.md":
            "# SBOM\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
    }


def faithful_regen(*, change_md: bool = True, append_event: bool = True,
                   touch_config: bool = True, append_triage: bool = True):
    """A ``_run_update_compliance`` fake that mirrors the REAL write-set.

    ``update_compliance.py --phase security`` writes up to FOUR tracked artifact
    groups; a fake that writes only an MD (as the pre-2026-07-24 tests did)
    could never expose the events.jsonl / config / triage staging leaks. This
    reproduces each so the finalizer is tested against what the real producer
    actually dirties:

    - a compliance MD (``.shipwright/compliance/``)
    - a ``grade_snapshot`` line in ``shipwright_events.jsonl`` (unconditional
      per regen)
    - ``shipwright_compliance_config.json`` (``phases_covered``)
    - a ``.shipwright/triage.jsonl`` line — models ``emit_sbom_triage`` /
      ``emit_test_failure_triage`` appending DIRECT to the tracked log (the
      no-``origin`` routing case; with an origin these go to the gitignored
      outbox instead)

    Flags select which groups fire, to model the derived edge cases.
    """
    state = {"n": 0}

    def _fake(project_root: Path) -> dict:
        state["n"] += 1
        n = state["n"]
        updated: list[str] = []
        if change_md:
            md = project_root / ".shipwright" / "compliance" / "dashboard.md"
            md.write_text(
                f"# Dashboard\n\nGenerated: 2026-05-24T00:00:{n:02d}Z\n\n"
                f"Post-security {n}\n",
                encoding="utf-8",
            )
            updated.append(".shipwright/compliance/dashboard.md")
        if append_event:
            ev = project_root / "shipwright_events.jsonl"
            with ev.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "v": 1, "id": f"evt-fake{n:04d}", "type": "grade_snapshot",
                    "grade": "A", "score": 92.3,
                }) + "\n")
        if touch_config:
            cfg = project_root / "shipwright_compliance_config.json"
            data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
            phases = data.get("phases_covered", [])
            if "security" not in phases:
                phases.append("security")
            data["phases_covered"] = phases
            cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if append_triage:
            tri = project_root / ".shipwright" / "triage.jsonl"
            with tri.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "event": "append", "id": f"trg-fake{n:04d}",
                    "source": "test-evidence", "status": "triage",
                }) + "\n")
        return {"updated_reports": updated}

    _fake.state = state
    return _fake
