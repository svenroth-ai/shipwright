#!/usr/bin/env python3
"""Design takes the Brief package (campaign brief-driven-run, B3a; BRIEF D8/D10).

When ``shipwright_run_config.json`` records ``brief_dir``, the supplied mockups are NOT
re-asked for in upload mode: ``screen-map.json`` answers the ``design.upload-screen-mapping``
question (which screen does each upload represent, and which requirements does it serve).

    uv run apply-brief-package.py --project-root <path>

* The package is re-verified (layout + hash held in run_config, approval) through
  ``brief_dir_intake.verify_run_config`` first; nothing is written for a refused package.
* Each mockup is copied to ``.shipwright/designs/uploads/<mockup>`` (byte-identical; an existing upload
  that differs, by the package hash's own CRLF rule, is ``exists_differs``) and, with the Linked-FR
  comment injected, to ``.shipwright/designs/screens/NN-<screen id>.html`` (NN = screen-map order).
* ``requirements`` in a screen-map entry are capability slugs; the FR ids are the ones Project MINTED
  in ``spec.md`` (``tools/brief_design_plan.py``, shared with the design verifier
  ``brief_design_applied``); nobody picks an id here. A slug with no FR row stops the run.
* Applying is recorded (``brief-package-applied.json`` holds the verified hash, written last). A
  re-entry with the same hash returns ``already_applied``: it checks that every upload still matches the
  package and every screen exists (``applied_files_missing``, exit 1), and writes nothing, so review-loop
  edits survive. A different hash after an apply is refused.
* Reset: delete the marker. The re-apply writes ONLY the missing targets; an existing screen or
  ``visual-guidelines.md`` is left alone (edits survive), an existing upload that differs is
  ``exists_differs`` (restore it). ``design-manifest.md`` is regenerated on every apply.
* ``visual-guidelines.md`` is taken from the package's ``design_system`` file.

All checks run before the first write. Exit 0 ok, 1 package content issues, 3 package refused.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# parents[0]=checks, [1]=scripts, [2]=shipwright-design, [3]=plugins, [4]=repo root.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.append(str(_SHARED_SCRIPTS))

from tools.brief_design_plan import applied_file_issues, fr_ids_by_slug, plan_screens, same_content  # noqa: E402

DESIGNS = ".shipwright/designs"
MARKER = "brief-package-applied.json"  # written last; its hash makes a re-entry a no-op


def _load(path: Path, name: str):
    """A module by file path under a private name (ADR-045: never bind ``lib``)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _issue(code: str, screen: str, message: str) -> dict:
    return {"code": code, "screen": screen, "message": message}


def apply(project_root: Path) -> dict:
    root = Path(project_root).resolve()
    bdi = _load(_SHARED_SCRIPTS / "lib" / "brief_dir_intake.py", "_shipwright_design_brief_dir_intake")
    info = bdi.verify_run_config(root)
    if not info.get("package"):
        raise bdi.BriefRefused("no_package", "run_config records no brief_dir: this run has no Brief package")
    bdir, _ = bdi.recorded_dir(bdi.load_config(root)["brief_dir"], root)
    designs = root / DESIGNS
    marker = designs / MARKER
    try:
        recorded = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
    except ValueError:
        recorded = None
    if not isinstance(recorded, dict):
        return {"ok": False, "issues": [_issue("bad_marker", MARKER, f"{MARKER} must hold a JSON object")]}
    applied = recorded.get("package_sha256")
    screen_map = json.loads((bdir / "screen-map.json").read_text(encoding="utf-8-sig"))
    if applied == info["package_sha256"]:  # re-entry: screen edits (review loop) stay untouched
        missing = applied_file_issues(bdir, designs, screen_map)
        return {"ok": False, "issues": missing} if missing else {"ok": True, "already_applied": True, "package_sha256": applied}
    if applied is not None:
        return {"ok": False, "issues": [_issue("package_changed_since_apply", "-", "the designs were applied from a different "
                "package hash: re-approve and restart Design, never re-apply over edited screens")]}
    plan, issues = plan_screens(bdir, screen_map, fr_ids_by_slug(root))
    registry = _load(_HERE.parent / "lib" / "screen_registry.py", "_shipwright_design_own_lib_screen_registry")
    brief = json.loads((bdir / "brief.json").read_text(encoding="utf-8-sig"))
    guidelines = bdir / str(brief.get("design_system") or "")
    if not guidelines.is_file():
        issues.append(_issue("missing_design_system", "-", "brief.json design_system names no file in the package"))
    targets: list[tuple[Path, bytes, bool]] = []  # (path, data, must match when it already exists)
    for item in plan:
        src = item["src"].read_bytes()
        targets += [(designs / "uploads" / item["mockup"], src, True),
                    (designs / "screens" / item["screen_file"], registry.inject_requirements(src, item["frs"]), False)]
    if guidelines.is_file():
        targets.append((designs / "visual-guidelines.md", guidelines.read_bytes(), False))
    for path, data, strict in targets:  # all checks first: a refusal writes nothing
        if strict and path.is_file() and not same_content(path.read_bytes(), data):
            issues.append(_issue("exists_differs", path.name, f"{path.name} exists and differs from the package: restore it, it is never overwritten"))
    if issues:
        return {"ok": False, "issues": issues}
    atomic = bdi._lib("atomic_write").durable_atomic_write  # temp file + os.replace: a crash leaves no truncated file
    kept = []
    for path, data, _strict in targets:
        if path.is_file():
            kept.append(path.name)  # an existing screen or guidelines file keeps its edits
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, data)
    registry.write_manifest(designs, profile_name=str(brief.get("profile") or ""))
    atomic(marker, json.dumps({"package_sha256": info["package_sha256"]}))
    return {"ok": True, "package_sha256": info["package_sha256"], "kept_existing": kept,
            "screens": [{"file": f"screens/{i['screen_file']}", "upload": f"uploads/{i['mockup']}", "frs": i["frs"]} for i in plan]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)
    try:
        out = apply(Path(args.project_root))
    except OSError as exc:  # a file could not be read or written
        out = {"ok": False, "issues": [_issue("io_error", "-", f"{type(exc).__name__}: {exc}")]}
    except ValueError as exc:  # malformed package files
        out = {"ok": False, "issues": [_issue("unreadable_package", "-", f"{type(exc).__name__}: {exc}")]}
    except Exception as exc:  # BriefRefused is defined in the file-path-loaded module
        if type(exc).__name__ != "BriefRefused":
            raise
        print(json.dumps(exc.as_dict(), indent=2))
        return 3
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
