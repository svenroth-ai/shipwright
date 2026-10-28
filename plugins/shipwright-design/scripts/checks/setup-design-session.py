#!/usr/bin/env python3
"""Setup shipwright-design session.

Reads project config and specs, prepares design session state.

Usage:
    uv run setup-design-session.py --project-root <path> --plugin-root <path>

Output (JSON):
    {
        "success": true/false,
        "project_root": "/path",
        "profile": "supabase-nextjs",
        "design_system": { ... },
        "specs_found": ["01-auth/spec.md", ...],
        "existing_designs": { screens: [...], flows: [...], uploads: [...] },
        "mode": "new" | "iterate" | "upload"
    }
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.boundary_baseline import write_baseline
from lib.screen_registry import scan_designs_dir

# Stack-profile resolution (project > user > bundled). Appended, then removed again:
# shared/scripts holds a `tools` package that would shadow this plugin's own.
_SHARED = str(Path(__file__).resolve().parents[4] / "shared" / "scripts")
_ADDED = _SHARED not in sys.path
if _ADDED:
    sys.path.append(_SHARED)
import profile_consumer as pc  # noqa: E402

if _ADDED:
    sys.path.remove(_SHARED)

PROJECT_CONFIG = "shipwright_project_config.json"
PROFILE_KEYS_READ = ("design_system",)  # D6: consumed profile keys (checked against the schema)


def _discovery():
    # Shared planning walk, loaded by FILE LOCATION under a sentinel name so no
    # ambiguous ``lib``/``scripts`` package is ever bound (ADR-045).
    mod = sys.modules.get("_shipwright_planning_discovery")
    if mod is None:
        import importlib.util
        path = Path(__file__).resolve().parents[4] / "shared/scripts/lib/planning_discovery.py"
        spec = importlib.util.spec_from_file_location("_shipwright_planning_discovery", path)
        sys.modules["_shipwright_planning_discovery"] = mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def find_specs(project_root: Path) -> list[str]:
    """Find all spec.md files from shipwright-project output."""
    planning = project_root / ".shipwright" / "planning"
    specs = []

    # sort=True (S2b pass B3), then sorted() on the STRINGS below regardless.
    # This site re-sorts its own OS-separator strings after the walk, so the
    # helper's own sort has NO observable effect here -- a known no-op, not a
    # bug (S2b campaign C3 is what will change what gets sorted, by switching
    # these strings to posix separators). Path ordering is case-insensitive on
    # Windows while str ordering is not, so sorting here rather than relying on
    # the helper is what keeps this call site's output identical.
    # include_iterate=False (S2b pass C2): iterate/ holds per-run iterate
    # specs, not a split spec -- on this repo it excludes the four real
    # nested `iterate/<run-id>/spec.md` files this walk previously (and
    # wrongly) offered as candidates for a new design session.
    for spec_file in _discovery().iter_spec_files(
        planning, recursive=True, guard="is_dir", sort=True, include_iterate=False, require="exists"
    ):
        relative = spec_file.relative_to(planning)
        # .as_posix() (S2b pass C3): was str(relative), which emits OS-native
        # separators -- "\\" is 0x5C, "/" is 0x2F, so sorting siblings like
        # "01-a" / "01-a2" could tie-break differently on Windows than on
        # Linux. Posix separators make the sort below platform-invariant.
        specs.append(relative.as_posix())

    return sorted(specs)


def load_profile_design_system(project_root: Path, profile_name: str) -> tuple[dict, str]:
    """design_system of the resolved stack profile, and where it came from.

    A reserved sentinel (``generic`` / ``detecting``) means built-in defaults (``{}``).
    An unknown or invalid profile raises (ValueError with ``.kind``) - never ``{}``.
    """
    res = pc.resolve_named(profile_name, project_root, origin=PROJECT_CONFIG)
    return (res.data.get("design_system") or {}), res.source


def detect_mode(project_root: Path) -> str:
    """Detect design session mode."""
    designs = project_root / ".shipwright" / "designs"

    if not designs.is_dir():
        return "new"

    uploads = designs / "uploads"
    if uploads.is_dir() and any(uploads.iterdir()):
        return "upload"

    screens = designs / "screens"
    if screens.is_dir() and any(screens.iterdir()):
        return "iterate"

    return "new"


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup design session")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--plugin-root", required=True)  # accepted for compatibility; profiles resolve via the resolver
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    profile_name = None
    try:
        # absent / null / empty -> the legacy default; a corrupt config is an error, not a traceback
        profile_name = pc.config_profile(project_root, PROJECT_CONFIG) or "supabase-nextjs"
        design_system, profile_source = load_profile_design_system(project_root, profile_name)
    except ValueError as exc:  # unknown / invalid / too new: stop, name the file, no fallback
        sys.stderr.write(f"error: {exc}\n")
        print(json.dumps({"success": False, "project_root": str(project_root),
                          "profile": profile_name, **pc.error_fields(exc)}, indent=2))
        return pc.exit_code(exc)
    specs = find_specs(project_root)
    mode = detect_mode(project_root)

    # Ensure designs directory structure under canonical .shipwright/.
    designs_dir = project_root / ".shipwright" / "designs"
    (designs_dir / "screens").mkdir(parents=True, exist_ok=True)
    (designs_dir / "flows").mkdir(parents=True, exist_ok=True)
    (designs_dir / "uploads").mkdir(parents=True, exist_ok=True)

    # FR-01.04 #11: what an earlier phase left uncommitted is not this session's change.
    try:
        boundary_baseline = "written" if write_baseline(project_root) else "kept"
    except OSError:  # the gate then stays strict; never fail the session over it
        boundary_baseline = "not_written"

    existing = scan_designs_dir(designs_dir)

    result = {
        "success": True,
        "project_root": str(project_root),
        "profile": profile_name,
        "profile_source": profile_source,
        "design_system": design_system,
        "specs_found": specs,
        "existing_designs": existing,
        "mode": mode,
        "boundary_baseline": boundary_baseline,
        "message": f"Design session ({mode}): {len(specs)} specs, {len(existing['screens'])} screens, {len(existing['uploads'])} uploads",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
