"""Harness for brief-driven runs (campaign brief-driven-run, unit A1): dry mode.

Three parts, kept in one helper module so tests share them:

* :func:`build_fixture_1` -- synthetic Brief package 1: classic bundled profile,
  ``deploy_target: none``, no external secrets. Built in code, not committed as
  files, so a CRLF checkout cannot skew it and its hash is always current.
* :func:`prepare_scratch_project` -- a scratch project directory with the package
  at ``<project>/brief/``.
* :func:`run_harness` / :func:`write_report` -- the driver and the report writer.

Dry mode makes **no model call and starts no subprocess**; it validates the
package and writes a report, which is what CI can run. A live mode (a real
``claude`` run) is the operator's, after campaign U; asking for it here refuses.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SHARED = str(_REPO / "shared" / "scripts")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from lib import brief_package  # noqa: E402

REPORT_SCHEMA_VERSION = 1
MODES = ("dry", "live")
OUTCOMES = ("dry-ok", "dry-failed", "complete", "escalated", "failed")
STAGE_STATUSES = ("passed", "failed", "skipped")
#: Pinned by ``test_brief_harness.py``: a field added or dropped here is a
#: deliberate, reviewed change to what the operator's report promises.
REPORT_KEYS = (
    "schema_version", "mode", "fixture", "autonomy", "started_at", "finished_at",
    "package", "fixture_approval", "stages", "gates_auto_approved", "escalations", "spend",
    "outcome", "stop_point",
)
PACKAGE_KEYS = ("sha256", "valid", "issues")
SPEND_KEYS = ("model_calls", "usd")
APPROVAL_KEYS = ("approved_by", "accepted_via_env")
#: BRIEF D1: a fixture approval is accepted only with this operator switch, and the
#: acceptance is recorded in the report.
FIXTURE_APPROVAL_ENV = "SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL"
STAGE_KEYS = ("name", "status", "detail")


def build_fixture_1(dest: Path, *, crlf: bool = False) -> Path:
    """Write synthetic fixture 1 at ``dest`` and return it, hash recorded.

    ``crlf=True`` writes every text file with CRLF line endings (a Windows
    checkout) -- the manifest hash must not notice.
    """
    nl = "\r\n" if crlf else "\n"

    def put(rel: str, text: str) -> None:
        f = dest / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(text.replace("\n", nl).encode("utf-8"))

    put("brief.md", "# Notes\n\n## capture-note\nA user can add a note with a title and a body.\n\n"
                    "## list-notes\nA user sees all notes, newest first.\n")
    put("scope.md", "# Scope\n\nIn: capture-note, list-notes. Out: sharing, accounts.\n")
    put("visual-guidelines.md", "# Visual guidelines\n\nPlain, high contrast, one accent colour.\n")
    put("mockups/01-notes.html", "<!doctype html>\n<html><body><h1>Notes</h1></body></html>\n")
    put("screen-map.json", json.dumps({"screens": [{"id": "notes", "mockup": "01-notes.html",
                                                    "requirements": ["capture-note", "list-notes"]}]}, indent=2) + "\n")
    brief = {
        "version": brief_package.BRIEF_VERSION, "profile": "vite-hono", "deploy_target": "none",
        "autonomy": "unattended", "ui_host": "web", "ux_shape": "classic", "source_class": "synthetic",
        "scope": "scope.md", "design_system": "visual-guidelines.md", "brief_dir": "brief",
        "env_preflight": [], "allow_parallel_builders": False,
        "approved_by": "fixture:synthetic-1", "approved_at": "2026-10-24T00:00:00Z",
    }
    put("brief.json", json.dumps(brief, indent=2) + "\n")
    brief["package_sha256"] = brief_package.package_sha256(dest)
    put("brief.json", json.dumps(brief, indent=2) + "\n")
    return dest


def prepare_scratch_project(root: Path, package: Path) -> Path:
    """Create ``root`` as a scratch project and copy ``package`` to ``root/brief``."""
    project = Path(root)
    target = project / "brief"
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} is not empty; a stale file would change the package hash")
    target.mkdir(parents=True, exist_ok=True)
    for rel, src in brief_package.iter_package_files(package):
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(src.read_bytes())
    return project


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_report(report: object) -> list[str]:
    """Schema problems of ``report`` (empty = conforms). Hand-checked: pinned shape."""
    if not isinstance(report, dict):
        return ["report must be an object"]
    problems = [f"missing key {k}" for k in REPORT_KEYS if k not in report]
    problems += [f"unexpected key {k}" for k in report if k not in REPORT_KEYS]
    if problems:
        return problems
    if type(report["schema_version"]) is not int or report["schema_version"] != REPORT_SCHEMA_VERSION:
        problems.append("schema_version mismatch")
    if report["mode"] not in MODES:
        problems.append("bad mode")
    if report["outcome"] not in OUTCOMES:
        problems.append("bad outcome")
    elif (report["mode"] == "dry") != report["outcome"].startswith("dry-"):
        problems.append("mode and outcome disagree")
    if report["stop_point"] is not None and not isinstance(report["stop_point"], str):
        problems.append("stop_point must be null or a string")
    if report["mode"] == "dry" and report["stop_point"] is not None:
        problems.append("a dry run never records a stop point")
    approval = report["fixture_approval"]
    if not (isinstance(approval, dict) and set(approval) == set(APPROVAL_KEYS)
            and isinstance(approval["accepted_via_env"], bool)
            and (approval["approved_by"] is None or isinstance(approval["approved_by"], str))):
        problems.append("bad fixture_approval block")
    for key in ("fixture", "autonomy", "started_at", "finished_at"):
        if not isinstance(report[key], str) or not report[key]:
            problems.append(f"{key} must be a non-empty string")
    pkg = report["package"]
    if not isinstance(pkg, dict) or set(pkg) != set(PACKAGE_KEYS):
        problems.append("bad package block")
    elif (not isinstance(pkg["sha256"], str) or not isinstance(pkg["valid"], bool)
          or not isinstance(pkg["issues"], list)):
        problems.append("package fields have the wrong types")
    spend = report["spend"]
    if not isinstance(spend, dict) or set(spend) != set(SPEND_KEYS):
        problems.append("bad spend block")
    else:
        if not isinstance(spend["model_calls"], int) or isinstance(spend["model_calls"], bool):
            problems.append("spend.model_calls must be an integer")
        usd = spend["usd"]
        if usd is not None and (isinstance(usd, bool) or not isinstance(usd, (int, float))):
            problems.append("spend.usd must be a number or null")
    if not isinstance(report["stages"], list) or any(
        not isinstance(s, dict) or set(s) != set(STAGE_KEYS) or s["status"] not in STAGE_STATUSES
        or not isinstance(s["name"], str) or not isinstance(s["detail"], str)
        for s in report["stages"]
    ):
        problems.append("bad stages")
    for key in ("gates_auto_approved", "escalations"):
        if not isinstance(report[key], list):
            problems.append(f"{key} must be a list")
    return problems


def write_report(report: dict, path: Path) -> Path:
    """Validate then write ``report`` as JSON; refuses a non-conforming report."""
    problems = validate_report(report)
    if problems:
        raise ValueError("report does not conform to the pinned schema: " + "; ".join(problems))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def run_harness(project: Path, *, fixture: str = "synthetic-1", mode: str = "dry",
                report_path: Path | None = None) -> dict:
    """Drive the scratch ``project``; dry mode only validates and reports.

    Live mode is not available until campaign U ships and an operator starts it.
    """
    if mode != "dry":
        raise NotImplementedError("live mode is the operator's, after campaign U; use mode='dry'")
    started = _now()
    brief_dir = Path(project) / "brief"
    issues = brief_package.validate_layout(brief_dir)
    stages = [{"name": "layout", "status": "failed" if issues else "passed",
               "detail": f"{len(issues)} defect(s)"}]
    sha, hash_ok = "", False
    if not issues:
        hash_ok, why = brief_package.verify_recorded_hash(brief_dir)
        sha = brief_package.package_sha256(brief_dir)
        stages.append({"name": "hash", "status": "passed" if hash_ok else "failed", "detail": why or "match"})
    ok = not issues and hash_ok
    autonomy, approved_by = "unknown", None
    try:
        brief = brief_package.loads_strict((brief_dir / "brief.json").read_text(encoding="utf-8-sig"))
        autonomy, approved_by = brief.get("autonomy"), brief.get("approved_by")
        autonomy = autonomy if isinstance(autonomy, str) and autonomy.strip() else "unknown"
    except (OSError, ValueError, AttributeError):
        pass
    report = {
        "schema_version": REPORT_SCHEMA_VERSION, "mode": mode, "fixture": fixture, "autonomy": autonomy,
        "started_at": started, "finished_at": _now(),
        "package": {"sha256": sha, "valid": ok, "issues": issues},
        "fixture_approval": {"approved_by": approved_by if isinstance(approved_by, str) else None,
                             "accepted_via_env": os.environ.get(FIXTURE_APPROVAL_ENV) == "1"},
        "stages": stages, "gates_auto_approved": [], "escalations": [],
        "spend": {"model_calls": 0, "usd": None},
        "outcome": "dry-ok" if ok else "dry-failed", "stop_point": None,
    }
    if report_path is not None:
        write_report(report, report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse
    import tempfile

    ap = argparse.ArgumentParser(description="Brief-driven run harness (dry mode)")
    ap.add_argument("--mode", default="dry", choices=MODES)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.mode != "dry":
        print("live mode is the operator's, after campaign U", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="brief-harness-") as tmp:
        pkg = build_fixture_1(Path(tmp) / "pkg")
        project = prepare_scratch_project(Path(tmp) / "project", pkg)
        report = run_harness(project, report_path=args.report)
    return 0 if report["outcome"] == "dry-ok" else 1


if __name__ == "__main__":
    sys.exit(main())
