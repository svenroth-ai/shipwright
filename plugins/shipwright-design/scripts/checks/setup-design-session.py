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
from lib.screen_registry import scan_designs_dir


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


def load_project_config(project_root: Path) -> dict:
    """Load shipwright_project_config.json."""
    config_path = project_root / "shipwright_project_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def load_profile_design_system(plugin_root: Path, profile_name: str) -> dict:
    """Load design_system config from stack profile."""
    profile_path = plugin_root.parent.parent / "shared" / "profiles" / f"{profile_name}.json"
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        return profile.get("design_system", {})
    return {}


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
    parser.add_argument("--plugin-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    plugin_root = Path(args.plugin_root).resolve()

    project_config = load_project_config(project_root)
    profile_name = project_config.get("profile", "supabase-nextjs")
    design_system = load_profile_design_system(plugin_root, profile_name)
    specs = find_specs(project_root)
    mode = detect_mode(project_root)

    # Ensure designs directory structure under canonical .shipwright/.
    designs_dir = project_root / ".shipwright" / "designs"
    (designs_dir / "screens").mkdir(parents=True, exist_ok=True)
    (designs_dir / "flows").mkdir(parents=True, exist_ok=True)
    (designs_dir / "uploads").mkdir(parents=True, exist_ok=True)

    existing = scan_designs_dir(designs_dir)

    result = {
        "success": True,
        "project_root": str(project_root),
        "profile": profile_name,
        "design_system": design_system,
        "specs_found": specs,
        "existing_designs": existing,
        "mode": mode,
        "message": f"Design session ({mode}): {len(specs)} specs, {len(existing['screens'])} screens, {len(existing['uploads'])} uploads",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
