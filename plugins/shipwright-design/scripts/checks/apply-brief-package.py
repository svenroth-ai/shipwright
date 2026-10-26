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
  ``exists_differs`` (restore it). ``design-manifest.md`` is regenerated on every non-no-op apply (not on ``already_applied``).
  An existing screen is kept only when it links the FR ids minted for it AND at least one upload of the package
  exists (a reset); otherwise ``pre_existing_screen`` (nothing written: move that screen away). A missing upload is
  restored byte-identical. A foreign screen with exactly the minted ids during a reset is an accepted hole.
* A different package hash after an apply is refused (``package_changed_since_apply``, exit 1, nothing written):
  redoing an applied Design phase for a changed package is an operator-led decision (follow-up), see the message.
* A kept file that differs from the package (a pre-existing ``visual-guidelines.md``) is listed in
  ``kept_existing_differs`` (a warning, not a refusal); any file in ``screens/``, ``uploads/`` or ``flows/`` (and
  ``chrome-definition.md``) that the package did not place is listed in ``foreign_existing``. The agent reports both, and ``unmapped_frs`` (minted FR ids no screen covers; informational).
* ``visual-guidelines.md`` is taken from the package's ``design_system`` file.

All checks run before the first write. Exit 0 ok, 1 package content issues, 3 package refused.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# parents[0]=checks, [1]=scripts, [2]=shipwright-design, [3]=plugins, [4]=repo root.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.append(str(_SHARED_SCRIPTS))

from tools.brief_design_plan import MARKER_NAME, applied_file_issues, fr_ids_by_slug, linked_frs, plan_screens, same_content  # noqa: E402

DESIGNS = ".shipwright/designs"
_HASH_RE = re.compile(r"[0-9a-f]{64}")
MARKER = MARKER_NAME  # written last; its hash makes a re-entry a no-op


def _load(path: Path, name: str):
    """A module by file path under a private name (ADR-045: never bind ``lib``)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # registered before exec (ADR-045), dropped again when the load fails
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _issue(code: str, screen: str, message: str) -> dict:
    return {"code": code, "screen": screen, "message": message}


def _unmapped(by_slug: dict, plan: list) -> list:
    """Minted FR ids that no planned screen links."""
    return sorted({i for ids in by_slug.values() for i in ids} - {fr for it in plan for fr in it["frs"]})


def apply(project_root: Path) -> dict:
    root = Path(project_root).resolve()
    bdi = _load(_SHARED_SCRIPTS / "lib" / "brief_dir_intake.py", "_shipwright_design_brief_dir_intake")
    info = bdi.verify_run_config(root)
    if not info.get("package"):
        raise bdi.BriefRefused("no_package", "run_config records no brief_dir: this run has no Brief package")
    bdir, _ = bdi.recorded_dir(info["brief_dir"], root)
    designs = root / DESIGNS
    marker = designs / MARKER
    try:
        recorded = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
    except ValueError:
        recorded = None
    if not isinstance(recorded, dict):
        return {"ok": False, "issues": [_issue("bad_marker", MARKER, f"{MARKER} must hold a JSON object")]}
    applied = recorded.get("package_sha256")
    if applied is not None and not (isinstance(applied, str) and _HASH_RE.fullmatch(applied)):
        return {"ok": False, "issues": [_issue("bad_marker", MARKER, f"{MARKER} package_sha256 must be a 64-character lowercase hex hash")]}
    screen_map = json.loads((bdir / "screen-map.json").read_text(encoding="utf-8-sig"))
    if applied == info["package_sha256"]:  # re-entry: screen edits (review loop) stay untouched
        missing = applied_file_issues(bdir, designs, screen_map)
        if missing:
            return {"ok": False, "issues": missing}
        by_slug = fr_ids_by_slug(root)  # the report of an unmapped FR must survive a resume
        return {"ok": True, "already_applied": True, "package_sha256": applied,
                "unmapped_frs": _unmapped(by_slug, plan_screens(bdir, screen_map, by_slug)[0])}
    if applied is not None:
        return {"ok": False, "issues": [_issue("package_changed_since_apply", "-", f"the designs in {DESIGNS}/ were applied from a "
                "different package: this tool will not re-apply over them. Redoing an already-applied Design phase for a changed "
                "package is an operator-led decision outside this unit (follow-up). If the operator wants it: remove "
                f"{DESIGNS}/ (git history keeps the old files; nothing is copied back automatically), re-approve the package, "
                "restart the run, and run this tool again.")]}
    by_slug = fr_ids_by_slug(root)
    plan, issues = plan_screens(bdir, screen_map, by_slug)
    registry = _load(_HERE.parent / "lib" / "screen_registry.py", "_shipwright_design_own_lib_screen_registry")
    brief = json.loads((bdir / "brief.json").read_text(encoding="utf-8-sig"))
    guidelines = bdir / str(brief.get("design_system") or "")
    targets: list[tuple[Path, bytes, bool]] = []  # (path, data, must match when it already exists)
    for item in plan:
        src = item["src"].read_bytes()
        page = registry.inject_requirements(src, item["frs"])
        if linked_frs(page.decode("utf-8", errors="ignore")) != set(item["frs"]):  # the writer and the reader must agree
            issues.append(_issue("injection_failed", item["screen_file"], "the Requirements comment could not be injected readably"))
        targets += [(designs / "uploads" / item["mockup"], src, True), (designs / "screens" / item["screen_file"], page, False)]
    placed = any((designs / "uploads" / item["mockup"]).is_file() for item in plan)  # an earlier apply left uploads: a reset
    for item in plan:  # EVERY kept screen links the ids minted for it (so "tool ok" means "gate green"); without its own upload it needs a reset
        screen = designs / "screens" / item["screen_file"]
        if not screen.is_file():
            continue
        has_ids = set(item["frs"]) <= linked_frs(screen.read_text(encoding="utf-8", errors="ignore"))
        if not has_ids or not placed:
            issues.append(_issue("pre_existing_screen", item["screen_file"], f"screens/{item['screen_file']} already exists but "
                                 "is not this package's screen (no own upload, or it lacks the minted FR ids): move that screen away, "
                                 "delete nothing else, and run this tool again"))
    if guidelines.is_file():
        targets.append((designs / "visual-guidelines.md", guidelines.read_bytes(), False))
    for path, data, strict in targets:  # all checks first: a refusal writes nothing
        if strict and path.is_file() and not same_content(path.read_bytes(), data):
            issues.append(_issue("exists_differs", path.name, f"{path.name} exists and differs from the package: restore it, it is never overwritten"))
    if issues:
        return {"ok": False, "issues": issues}
    atomic = bdi._lib("atomic_write").durable_atomic_write  # targets and marker: temp file + os.replace. design-manifest.md is written by the registry and is NOT atomic; the marker comes last: a crash leaves no marker and the next run completes the missing targets
    placed_rel = {f"screens/{i['screen_file']}" for i in plan} | {f"uploads/{i['mockup']}" for i in plan}
    foreign = sorted(p.relative_to(designs).as_posix() for sub in ("screens", "uploads", "flows") if (designs / sub).is_dir()
                     for p in (designs / sub).rglob("*") if p.is_file() and p.relative_to(designs).as_posix() not in placed_rel)
    foreign += ["chrome-definition.md"] if (designs / "chrome-definition.md").is_file() else []
    kept, differs = [], []
    for path, data, _strict in targets:
        if path.is_file():
            kept.append(path.relative_to(designs).as_posix())  # an existing screen or guidelines file keeps its edits
            if path.suffix != ".html" and not same_content(path.read_bytes(), data):  # screens differ by design; guidelines should not
                differs.append(path.relative_to(designs).as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic(path, data)
    registry.write_manifest(designs, profile_name=str(brief.get("profile") or ""))
    atomic(marker, json.dumps({"package_sha256": info["package_sha256"]}))
    return {"ok": True, "package_sha256": info["package_sha256"], "kept_existing": kept,
            "foreign_existing": foreign,  # not placed by this package (flows of an earlier Design run on a reset are expected)
            "unmapped_frs": _unmapped(by_slug, plan),  # informational: the agent reports
            "kept_existing_differs": differs,  # a warning, not a refusal: a kept file that is not the package's own
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
