#!/usr/bin/env python3
"""Brief intake from a Brief PACKAGE DIRECTORY (campaign brief-driven-run, B2; BRIEF D1-D2).

``brief_intake.py`` reads one brief FILE or payload. This module reads the committed
package directory (``<project>/brief/``, layout and hash: ``brief_package.py``) and owns
the approval rules:

* the package must verify (layout + hash) before ``write-config``, on every resume / next /
  apply and on every ``needs_input`` answer -- :func:`open_package` / :func:`verify_run_config`;
* the first intake takes the expected hash from ``brief.json``; :func:`record` then stores it in
  ``shipwright_run_config.json`` (``brief_dir`` + ``brief_package``), so later checks compare
  against a hash held OUTSIDE the package; it never re-baselines, and a started run gets none;
* a missing approval is refused; ``approved_by: "fixture:<id>"`` needs
  ``SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL=1`` and the acceptance is recorded;
* brief fields override derived values (``profile``, ``deploy_target``, ``autonomy``).

Loading (ADR-045): ``brief_package`` uses package-relative imports, so this file loads the
shared ``lib`` directory as a privately named package instead of importing ``lib``; it is
itself loaded by file path from ``brief_intake.py``.

CLI: ``verify --project-root P`` and ``record --project-root P --brief-dir D`` (after
``write-config``). Exit 0 ok, 3 refused.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

FIXTURE_ENV = "SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL"
FIXTURE_PREFIX = "fixture:"
CONFIG_NAME = "shipwright_run_config.json"
_LIB = Path(__file__).resolve().parent
_PKG = "_shipwright_brief_dir_lib"
_SHA_RE = re.compile(r"[0-9a-f]{64}")


class BriefRefused(Exception):
    """The package cannot be used. ``code`` is a closed token; ``issues`` the details."""

    def __init__(self, code: str, message: str, issues: Optional[list] = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.issues = code, message, issues or []

    def as_dict(self) -> dict:
        return {"refused": True, "code": self.code, "message": self.message, "issues": self.issues}


def _lib(name: str) -> Any:
    """A module of the shared lib directory, via a privately named package."""
    if _PKG not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _PKG, _LIB / "__init__.py", submodule_search_locations=[str(_LIB)])
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[_PKG] = pkg
        try:
            spec.loader.exec_module(pkg)
        except BaseException:
            sys.modules.pop(_PKG, None)
            raise
    return importlib.import_module(f"{_PKG}.{name}")


def resolve_dir(source: str, project_root: Optional[Path] = None) -> Path:
    """The package directory named by ``source`` (project-relative or absolute)."""
    root = Path(project_root or os.getcwd()).resolve()
    text = str(source).strip().rstrip("/\\") or "."
    path = Path(text) if Path(text).is_absolute() else root / text
    if not path.is_dir():
        raise BriefRefused("bad_brief_dir", f"brief directory does not exist: {path}")
    return path.resolve()


def _relative(bdir: Path, root: Path) -> str:
    try:
        return bdir.relative_to(root.resolve()).as_posix()
    except ValueError:
        raise BriefRefused("bad_brief_dir", f"{bdir} is outside the project {root}; "
                           "the package must be project-relative and committable") from None


def check_approval(brief: Mapping[str, Any], env: Optional[Mapping[str, str]] = None) -> dict:
    """Refuse a missing approval; gate the fixture approval on the operator switch."""
    by, at = brief.get("approved_by"), brief.get("approved_at")
    if not (isinstance(by, str) and by.strip() and isinstance(at, str) and at.strip()):
        raise BriefRefused("missing_approval", "brief.json needs approved_by and approved_at")
    fixture = by.strip().lower().startswith(FIXTURE_PREFIX)
    if fixture and not by.strip()[len(FIXTURE_PREFIX):].strip():
        raise BriefRefused("missing_approval", "approved_by 'fixture:' carries no fixture id")
    if fixture and (os.environ if env is None else env).get(FIXTURE_ENV) != "1":
        raise BriefRefused("fixture_approval_refused",
                           f"approved_by {by!r} is a fixture approval; set {FIXTURE_ENV}=1 to accept it")
    return {"approved_by": by, "approved_at": at, "fixture_approval_accepted": fixture}


def open_package(bdir: Path, *, recorded: Optional[Mapping[str, Any]] = None,
                 env: Optional[Mapping[str, str]] = None) -> dict:
    """Verify the package and its approval; return ``{brief, package_sha256, ...approval}``.

    ``recorded`` is the ``brief_package`` block from run_config (resume / answer; ``{}`` when the
    record is missing). Once it is given it is the ONLY source of the expected hash -- there is
    no fallback to the self-attested hash inside ``brief.json`` -- and its ``approved_by`` must
    not have changed. ``brief.json`` is read BEFORE the verification: that narrows the swap window
    between check and use but does not close it (a run-scoped snapshot is deferred to U3).
    """
    bp = _lib("brief_package")
    try:
        brief = json.loads((bdir / "brief.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        brief = None
    expected = (recorded or {}).get("package_sha256") if recorded is not None else (
        brief.get("package_sha256") if isinstance(brief, dict) else None)
    if not (isinstance(expected, str) and _SHA_RE.fullmatch(expected)):
        bp_issues = bp.validate_layout(bdir)
        code = "missing_record" if recorded is not None else ("missing_approval" if not bp_issues else "invalid_package")
        raise BriefRefused(code, "no valid package_sha256 to verify against" if not bp_issues
                           else "the package is not valid", bp_issues)
    ok, issues = bp.verify_package(bdir, expected=expected)
    if not ok:
        code = "hash_mismatch" if any(i["code"] == "hash_mismatch" for i in issues) else "invalid_package"
        raise BriefRefused(code, "the package changed since approval or is not valid", issues)
    approval = check_approval(brief, env)
    if recorded is not None and any(recorded.get(k) != approval[k] for k in ("approved_by", "approved_at")):
        raise BriefRefused("approval_changed", "the approval differs from the one recorded in run_config")
    return {"brief": brief, "package_sha256": expected, **approval}


def check_config_matches(cfg: Mapping[str, Any], brief: Mapping[str, Any]) -> None:
    """The run config must carry the approved settings (brief fields win; nothing may drift)."""
    for key in ("profile", "autonomy", "deploy_target"):
        if key in cfg and cfg[key] != brief.get(key):
            raise BriefRefused("config_mismatch", f"run_config {key}={cfg[key]!r} differs from the approved "
                               f"brief.json {key}={brief.get(key)!r}")


def check_brief_dir(brief: Mapping[str, Any], rel: str) -> None:
    """``brief.json`` must name the directory it sits in."""
    if str(brief.get("brief_dir")).replace("\\", "/").strip("/") != rel:
        raise BriefRefused("bad_brief_dir", f"brief.json says brief_dir={brief.get('brief_dir')!r} "
                           f"but the package sits at {rel!r}")


def recorded_dir(raw: Any, root: Path) -> tuple[Path, str]:
    """The package directory recorded in run_config: project-relative, no ``..``, no escape by link."""
    text = str(raw).replace("\\", "/")
    if not isinstance(raw, str) or Path(text).is_absolute() or ".." in text.split("/"):
        raise BriefRefused("bad_brief_dir", f"recorded brief_dir {raw!r} is not a project-relative path")
    bdir = resolve_dir(text, root)
    return bdir, _relative(bdir, root)


def intake_dir(source: str, project_root: Optional[Path] = None,
               env: Optional[Mapping[str, str]] = None) -> dict:
    """``brief_intake.intake`` result for a package directory (raises :class:`BriefRefused`)."""
    try:
        return _intake_dir(source, project_root, env)
    except (OSError, RuntimeError) as exc:
        raise BriefRefused("io_error", str(exc)) from None


def _intake_dir(source: str, project_root: Optional[Path], env: Optional[Mapping[str, str]]) -> dict:
    root = Path(project_root or os.getcwd()).resolve()
    bdir = resolve_dir(source, root)
    rel = _relative(bdir, root)
    text = read_text(bdir / "brief.md").strip()
    info = open_package(bdir, env=env)  # text read first: narrows, does not close, the swap window (U3)
    brief = info["brief"]
    check_brief_dir(brief, rel)
    bi = _lib("brief_intake")
    result = bi.map_brief(bi.normalize_brief({"description": text}))  # derived values ...
    result.update(  # ... which the brief fields override
        profile=brief["profile"], profile_reason="brief.json profile (package field wins)",
        deploy_target=brief["deploy_target"], answered=["description", "profile", "deploy_target", "autonomy"],
        remaining_questions=[], env_questions=list(brief.get("env_preflight") or []),
        autonomy=brief["autonomy"], ux_shape=brief["ux_shape"], ui_host=brief["ui_host"],
        source_class=brief["source_class"], allow_parallel_builders=brief["allow_parallel_builders"],
        source="package", brief_dir=rel,
        package={k: info[k] for k in ("package_sha256", "approved_by", "approved_at", "fixture_approval_accepted")})
    return result


def read_text(path: Path) -> str:
    """UTF-8 text of a package file ('' when absent); unreadable content is a refusal."""
    try:
        return path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    except (OSError, ValueError) as exc:
        raise BriefRefused("invalid_package", f"{path.name} is not readable as UTF-8 text: {exc}") from None


def load_config(project_root: Path) -> dict:
    """run_config as a dict; ``{}`` when absent."""
    try:
        cfg = json.loads((Path(project_root) / CONFIG_NAME).read_text(encoding="utf-8-sig"))
    except OSError:
        return {}
    except ValueError as exc:
        raise BriefRefused("bad_run_config", f"{CONFIG_NAME} is not valid JSON: {exc}") from None
    return cfg if isinstance(cfg, dict) else {}


def record(project_root: Path, brief_dir: str, env: Optional[Mapping[str, str]] = None) -> dict:
    """Verify the package, then store ``brief_dir`` + ``brief_package`` in run_config (under the
    run-config lock). A second record never re-baselines: it verifies against the stored hash."""
    root = Path(project_root).resolve()
    path = Path(root) / CONFIG_NAME
    if not path.is_file():
        raise BriefRefused("no_run_config", f"{CONFIG_NAME} does not exist yet; run write-config first")
    bdir = resolve_dir(brief_dir, root)
    rel = _relative(bdir, root)
    with _lib("file_lock").file_lock(path.with_name(CONFIG_NAME + ".lock"), timeout_seconds=5.0):
        cfg = load_config(root)
        if cfg.get("brief_dir") not in (None, rel):
            raise BriefRefused("brief_dir_conflict", f"run_config already records {cfg['brief_dir']!r}; "
                               f"it can not be replaced by {rel!r}")
        has_record = "brief_dir" in cfg or "brief_package" in cfg  # either key: never re-baseline
        if not has_record and _run_started(cfg):  # the only legitimate first baseline is a fresh run's
            raise BriefRefused("run_already_started", "the run has progressed, so a first baseline would trust the "
                               "package's own hash: restore the original run_config, or re-approve and restart")
        info = open_package(bdir, recorded=(cfg.get("brief_package") or {}) if has_record else None, env=env)
        check_brief_dir(info["brief"], rel)
        check_config_matches(cfg, info["brief"])
        cfg["brief_dir"] = rel
        cfg["brief_package"] = {k: info[k] for k in
                                ("package_sha256", "approved_by", "approved_at", "fixture_approval_accepted")}
        _lib("atomic_write").durable_atomic_write(path, json.dumps(cfg, indent=2) + "\n")
    return {"recorded": True, "brief_dir": rel, **cfg["brief_package"]}


def _run_started(cfg: Mapping[str, Any]) -> bool:
    """True once any phase task left its initial state (or a phase task is recorded complete)."""
    tasks = [t for t in cfg.get("phase_tasks") or [] if isinstance(t, dict)]
    return bool(cfg.get("completed_phase_task_ids")) or any(t.get("status") not in ("awaiting_launch", "pending") for t in tasks)


def _package_dir_at_top_level(root: Path) -> str:
    """A top-level dir whose ``brief.json`` names itself as ``brief_dir`` ('' if none)."""
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        try:
            brief = json.loads((d / "brief.json").read_text(encoding="utf-8-sig"))
            if str(brief.get("brief_dir")).replace("\\", "/").strip("/") == d.name:
                return f"{d.name}/brief.json"
        except (OSError, ValueError, AttributeError):
            continue
    return ""


def verify_run_config(project_root: Path, env: Optional[Mapping[str, str]] = None) -> dict:
    """The resume / answer check: re-verify the package named by run_config against the hash
    recorded there. A run with neither ``brief_dir`` nor ``brief_package`` has no package and passes
    (``{"package": False}``, plus a ``warnings`` entry when a package directory sits next to it); a
    ``brief_package`` without ``brief_dir``, or a ``brief_dir`` without a valid record, is refused."""
    root = Path(project_root).resolve()
    cfg = load_config(root)
    if "brief_dir" not in cfg:
        if "brief_package" in cfg:  # NOT a re-record: that would re-baseline on the package's own hash
            raise BriefRefused("missing_record", f"{CONFIG_NAME} holds a brief_package but no brief_dir: restore the "
                               "original run_config, or re-approve the package (new approved_at) and restart the run")
        stray = _package_dir_at_top_level(root)
        warn = [f"{stray} is a Brief package, but run_config records none: this run does not use it"]
        return {"package": False, **({"warnings": warn} if stray else {})}
    bdir, rel = recorded_dir(cfg["brief_dir"], root)
    info = open_package(bdir, recorded=cfg.get("brief_package") or {}, env=env)
    check_brief_dir(info["brief"], rel)
    check_config_matches(cfg, info["brief"])
    return {"package": True, "verified": True, "brief_dir": cfg["brief_dir"],
            "package_sha256": info["package_sha256"], "fixture_approval_accepted": info["fixture_approval_accepted"]}


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify").add_argument("--project-root", default=".")
    rec = sub.add_parser("record")
    rec.add_argument("--project-root", default=".")
    rec.add_argument("--brief-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "verify" and not (Path(args.project_root) / CONFIG_NAME).is_file():
            raise BriefRefused("no_run_config", f"no {CONFIG_NAME} under {args.project_root}: wrong --project-root?")
        out = (verify_run_config(Path(args.project_root)) if args.cmd == "verify"
               else record(Path(args.project_root), args.brief_dir))
    except BriefRefused as exc:
        print(json.dumps(exc.as_dict(), indent=2))
        return 3
    except (OSError, RuntimeError) as exc:  # LockTimeout is a RuntimeError: report, never a traceback
        print(json.dumps({"refused": True, "code": "io_error", "message": str(exc), "issues": []}))
        return 3
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
