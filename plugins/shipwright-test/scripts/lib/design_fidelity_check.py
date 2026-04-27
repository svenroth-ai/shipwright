#!/usr/bin/env python3
"""Design fidelity check: structural comparison of mockup HTML vs implementation TSX.

Usage:
    uv run design_fidelity_check.py --cwd <project_root>
    uv run design_fidelity_check.py --cwd <project_root> --screen 01-login.html --screen 02-register.html

Reads .shipwright/designs/screen-routes.json for mockup-to-route mapping.
For each screen, extracts structural information from both mockup HTML and
implementation TSX, then runs automated checks.  The agent uses this output
to decide which screens need deeper manual review.

Returns JSON with per-screen structural data and auto-check results.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Structure extraction — Mockup HTML
# ---------------------------------------------------------------------------

# Layout-level CSS classes in mockup HTML
_LAYOUT_CLASS_RE = re.compile(
    r"(?:class|className)\s*=\s*[\"'][^\"']*?"
    r"((?:grid|flex|block|inline-flex|inline-grid)"
    r"(?:\s+(?:grid-cols-\d+|flex-col|flex-row|items-\w+|justify-\w+|gap-\w+))*)",
)

_HEADING_RE = re.compile(r"<(h[1-6])\b", re.IGNORECASE)

_SEMANTIC_SECTION_RE = re.compile(
    r"<(?:nav|header|footer|main|aside|section|article)\b", re.IGNORECASE,
)

_COMPONENT_RE = re.compile(
    r'class\s*=\s*["\'][^"\']*?'
    r"(stat-card|data-table|sidebar|empty-state|card|badge|avatar|"
    r"dialog|modal|form-field|tab|accordion|breadcrumb|dropdown|"
    r"tooltip|alert|toast|table|pagination)",
    re.IGNORECASE,
)


def _extract_mockup_structure(html_text: str) -> dict:
    """Extract structural summary from mockup HTML source."""
    layouts = list({m.group(1).strip() for m in _LAYOUT_CLASS_RE.finditer(html_text)})
    headings = sorted(set(m.group(1).lower() for m in _HEADING_RE.finditer(html_text)))
    semantic_sections = sorted(
        set(m.group(0).strip("<").lower() for m in _SEMANTIC_SECTION_RE.finditer(html_text))
    )
    components = sorted(set(m.group(1).lower() for m in _COMPONENT_RE.finditer(html_text)))

    return {
        "layout_classes": layouts,
        "heading_levels": headings,
        "semantic_sections": semantic_sections,
        "component_classes": components,
    }


# ---------------------------------------------------------------------------
# Structure extraction — Implementation TSX
# ---------------------------------------------------------------------------

_SHADCN_IMPORT_RE = re.compile(
    r'import\s+\{([^}]+)\}\s+from\s+["\']@/components/ui/([^"\']+)["\']'
)

_JSX_COMPONENT_RE = re.compile(r"<((?:Card|Button|Badge|Avatar|Dialog|Sheet|Drawer|"
                                r"Table|DataTable|Tabs|Accordion|Input|Select|Textarea|"
                                r"Checkbox|Switch|Label|Separator|Skeleton|Alert|"
                                r"DropdownMenu|Popover|Tooltip|Command|Form|"
                                r"Breadcrumb|Pagination|EmptyState|ScrollArea|"
                                r"NavigationMenu|Sidebar|FieldGroup|Field|FieldLabel"
                                r")(?:Header|Title|Content|Footer|Trigger|Item|"
                                r"Body|Row|Cell|Head|Caption|Description|Action|"
                                r"Close|Overlay|Portal|Group|Sub|Separator|"
                                r"Label|Value|Link|List|Viewport)?)\b")

_TSX_HEADING_RE = re.compile(r"<(h[1-6])\b")

_TSX_LAYOUT_RE = re.compile(
    r"className\s*=\s*[{\"'][^}\"']*?"
    r"((?:grid|flex|block|inline-flex)"
    r"(?:\s+(?:grid-cols-\d+|flex-col|flex-row|items-\w+|justify-\w+|gap-\w+))*)",
)

_GAP_RE = re.compile(r"\bgap-\w+")
_SPACE_Y_RE = re.compile(r"\bspace-y-\w+")

_HARDCODED_COLOR_RE = re.compile(
    r"(?:bg|text|border)-"
    r"(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|"
    r"emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d+"
)

_SEMANTIC_COLOR_RE = re.compile(
    r"(?:bg|text|border)-"
    r"(?:background|foreground|card|popover|primary|secondary|muted|accent|"
    r"destructive|sidebar|input|ring)"
)


def _extract_implementation_structure(tsx_text: str) -> dict:
    """Extract structural summary from implementation TSX source."""
    # shadcn imports
    shadcn_imports: list[str] = []
    for m in _SHADCN_IMPORT_RE.finditer(tsx_text):
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        shadcn_imports.extend(names)
    shadcn_imports = sorted(set(shadcn_imports))

    # JSX component usage
    jsx_components = sorted(set(m.group(1) for m in _JSX_COMPONENT_RE.finditer(tsx_text)))

    # Headings
    headings = sorted(set(m.group(1).lower() for m in _TSX_HEADING_RE.finditer(tsx_text)))

    # Layout classes
    layouts = list({m.group(1).strip() for m in _TSX_LAYOUT_RE.finditer(tsx_text)})

    # gap vs space-y usage
    uses_gap = bool(_GAP_RE.search(tsx_text))
    uses_space_y = bool(_SPACE_Y_RE.search(tsx_text))

    # Color token usage
    hardcoded_colors = sorted(set(_HARDCODED_COLOR_RE.findall(tsx_text)))
    semantic_colors = sorted(set(_SEMANTIC_COLOR_RE.findall(tsx_text)))

    return {
        "shadcn_imports": shadcn_imports,
        "jsx_components": jsx_components,
        "heading_levels": headings,
        "layout_classes": layouts,
        "uses_gap": uses_gap,
        "uses_space_y": uses_space_y,
        "hardcoded_colors": hardcoded_colors,
        "semantic_colors": semantic_colors,
    }


# ---------------------------------------------------------------------------
# Auto-checks
# ---------------------------------------------------------------------------

def _run_auto_checks(mockup: dict, impl: dict) -> dict:
    """Run quick automated checks comparing mockup and implementation structures."""
    checks: dict[str, bool] = {}

    # 1. Heading hierarchy match
    checks["heading_hierarchy_match"] = mockup["heading_levels"] == impl["heading_levels"]

    # 2. Layout pattern present (at least one layout class in both)
    checks["layout_present"] = bool(mockup["layout_classes"]) == bool(impl["layout_classes"])

    # 3. Semantic colors used (no hardcoded colors, or at least some semantic)
    checks["has_semantic_colors"] = (
        len(impl["hardcoded_colors"]) == 0
        or len(impl["semantic_colors"]) > 0
    )

    # 4. gap preferred over space-y (shadcn best practice)
    checks["gap_not_space_y"] = not impl["uses_space_y"] or impl["uses_gap"]

    # 5. Component count plausibility (implementation should use some components
    #    if mockup has component classes)
    mockup_count = len(mockup["component_classes"])
    impl_count = len(impl["jsx_components"])
    if mockup_count == 0:
        checks["component_count_plausible"] = True
    else:
        # Implementation should have at least half as many component types
        checks["component_count_plausible"] = impl_count >= max(1, mockup_count // 2)

    return checks


# ---------------------------------------------------------------------------
# Route → file resolution
# ---------------------------------------------------------------------------

def _resolve_route_to_files(project_root: Path, route: str) -> list[str]:
    """Resolve a route path to implementation TSX file(s).

    Handles Next.js App Router conventions:
    - /login → src/app/login/page.tsx or src/app/(auth)/login/page.tsx
    - / → src/app/page.tsx
    """
    src_app = project_root / "src" / "app"
    if not src_app.exists():
        return []

    # Direct path
    route_clean = route.strip("/")
    candidates: list[Path] = []

    if route_clean:
        # Direct: src/app/{route}/page.tsx
        direct = src_app / route_clean / "page.tsx"
        if direct.exists():
            candidates.append(direct)

        # Route groups: src/app/({group})/{route}/page.tsx
        if not candidates:
            for page in src_app.rglob("page.tsx"):
                # Check if the route segment appears in the path
                parts = [p for p in page.relative_to(src_app).parts if not p.startswith("(")]
                page_route = "/".join(parts[:-1])  # exclude "page.tsx"
                if page_route == route_clean:
                    candidates.append(page)
    else:
        # Root route
        root_page = src_app / "page.tsx"
        if root_page.exists():
            candidates.append(root_page)

    return [str(p.relative_to(project_root)) for p in candidates]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _parse_screen_list(data: dict | list) -> tuple[str, list[dict]]:
    """Parse screen-routes.json into (base_url, screen_list).

    Supports both nested format (base_url + screens array) and legacy flat dict.
    """
    base_url = ""
    if isinstance(data, dict) and "screens" in data:
        base_url = data.get("base_url", "")
        return base_url, data["screens"]
    if isinstance(data, dict):
        screen_list = [
            {"mockup": k, **(v if isinstance(v, dict) else {"route": v})}
            for k, v in data.items()
        ]
        return base_url, screen_list
    return base_url, []


def run_design_fidelity_check(
    project_root: Path,
    screens: list[str] | None = None,
) -> dict:
    """Run design fidelity check and return structural comparison results.

    Args:
        project_root: Path to the project root directory.
        screens: Optional list of mockup filenames to check. When None, all
                 screens from screen-routes.json are checked.
    """
    routes_path = project_root / ".shipwright" / "designs" / "screen-routes.json"
    if not routes_path.exists():
        return {
            "passed": 0, "total": 0, "skipped": True,
            "skip_reason": "No .shipwright/designs/screen-routes.json found",
            "screens": [],
            "summary": {"total": 0, "auto_pass": 0, "needs_agent_review": 0},
        }

    try:
        data = json.loads(routes_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {
            "passed": 0, "total": 0, "skipped": True,
            "skip_reason": f"Failed to read screen-routes.json: {e}",
            "screens": [],
            "summary": {"total": 0, "auto_pass": 0, "needs_agent_review": 0},
        }

    _, screen_list = _parse_screen_list(data)

    if not screen_list:
        return {
            "passed": 0, "total": 0, "skipped": True,
            "skip_reason": "screen-routes.json is empty",
            "screens": [],
            "summary": {"total": 0, "auto_pass": 0, "needs_agent_review": 0},
        }

    # Filter to requested screens
    if screens is not None:
        available = {s.get("mockup", "") for s in screen_list}
        requested = set(screens)
        missing = requested - available
        if missing:
            return {
                "passed": 0, "total": 0, "skipped": False,
                "screens": [],
                "summary": {"total": 0, "auto_pass": 0, "needs_agent_review": 0},
                "error": (
                    f"Requested screens not found in screen-routes.json: "
                    f"{sorted(missing)}. Available: {sorted(available)}"
                ),
            }
        screen_list = [s for s in screen_list if s.get("mockup") in requested]

    results: list[dict] = []
    auto_pass = 0

    for entry in screen_list:
        mockup_file = entry.get("mockup", "")
        route = entry.get("route", "/")

        # Find mockup HTML
        mockup_path = project_root / ".shipwright" / "designs" / mockup_file
        if not mockup_path.exists():
            results.append({
                "mockup": mockup_file, "route": route,
                "status": "error",
                "error": f"Mockup file not found: {mockup_file}",
            })
            continue

        # Find implementation files
        impl_files = _resolve_route_to_files(project_root, route)

        if not impl_files:
            results.append({
                "mockup": mockup_file, "route": route,
                "mockup_path": str(mockup_path.relative_to(project_root)),
                "implementation_files": [],
                "status": "needs_review",
                "note": f"No implementation file found for route {route}",
            })
            continue

        # Read and extract structures
        mockup_html = mockup_path.read_text(encoding="utf-8")
        mockup_structure = _extract_mockup_structure(mockup_html)

        # Read first implementation file (primary page)
        impl_path = project_root / impl_files[0]
        impl_tsx = impl_path.read_text(encoding="utf-8")
        impl_structure = _extract_implementation_structure(impl_tsx)

        # Run auto-checks
        auto_checks = _run_auto_checks(mockup_structure, impl_structure)
        all_pass = all(auto_checks.values())

        if all_pass:
            auto_pass += 1

        results.append({
            "mockup": mockup_file,
            "route": route,
            "mockup_path": str(mockup_path.relative_to(project_root)),
            "implementation_files": impl_files,
            "mockup_structure": mockup_structure,
            "implementation_structure": impl_structure,
            "auto_checks": auto_checks,
            "status": "pass" if all_pass else "needs_review",
        })

    total = len(results)
    needs_review = total - auto_pass

    return {
        "passed": auto_pass,
        "total": total,
        "skipped": False,
        "screens": results,
        "summary": {
            "total": total,
            "auto_pass": auto_pass,
            "needs_agent_review": needs_review,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Design fidelity check: structural comparison of mockup HTML vs implementation TSX"
    )
    parser.add_argument("--cwd", required=True, help="Project root directory")
    parser.add_argument(
        "--screen", action="append", dest="screens", metavar="FILENAME",
        help="Screen filename to check (repeatable). When omitted, all screens are checked.",
    )
    args = parser.parse_args()

    screens = args.screens
    if screens is not None:
        screens = [s.strip() for s in screens if s.strip()]
        if not screens:
            print(json.dumps({"error": "--screen flag provided but no valid screen names given"}))
            return 1

    result = run_design_fidelity_check(Path(args.cwd).resolve(), screens=screens)

    if result.get("error"):
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
