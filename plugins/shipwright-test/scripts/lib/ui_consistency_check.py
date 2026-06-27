#!/usr/bin/env python3
"""Cross-page UI consistency check: detect pattern inconsistencies across pages.

Usage:
    uv run ui_consistency_check.py --cwd <project_root>
    uv run ui_consistency_check.py --cwd <project_root> --guidelines .shipwright/designs/visual-guidelines.md
    uv run ui_consistency_check.py --cwd <project_root> --category heading --category spacing
    uv run ui_consistency_check.py --cwd <project_root> --files src/app/courses/page.tsx src/app/admin/page.tsx

Scans all page/component source files and detects cross-page inconsistencies in 6 categories:
  1. heading_hierarchy  — Page heading sizes (text-* classes on h1-h6 / Title components)
  2. spacing_patterns   — Section/card gaps (gap-*, space-y-*, space-x-*)
  3. component_patterns — Same purpose = same component (DataTable vs Table vs raw table)
  4. form_patterns      — Form field structure (FieldGroup/Field/FieldLabel vs raw div+Label)
  5. token_usage        — Semantic tokens vs hardcoded colors (bg-black/50, text-gray-*)
  6. interactive_patterns — Dialog/Toast/EmptyState consistency

Algorithm: Majority-wins — the most common variant is "expected", deviations are outliers.
Returns JSON with per-category results and root-cause grouping.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

# Root-cause group mapping (same taxonomy as design fidelity)
ROOT_CAUSE_GROUPS = {
    "Spacing": ["heading_hierarchy", "spacing_patterns"],
    "Components": ["component_patterns", "form_patterns", "interactive_patterns"],
    "Colors": ["token_usage"],
}

ALL_CATEGORIES = [
    "heading_hierarchy",
    "spacing_patterns",
    "component_patterns",
    "form_patterns",
    "token_usage",
    "interactive_patterns",
]

# ---------------------------------------------------------------------------
# Regex patterns for detection
# ---------------------------------------------------------------------------

# Heading sizes: match text-{size} on lines containing h1-h6 or common title components
_HEADING_TAG_RE = re.compile(
    r"<(?:h[1-6]|Heading|PageTitle|CardTitle|DialogTitle|SheetTitle)\b[^>]*"
    r"(?:className|class)\s*=\s*[\"'][^\"']*?(text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl))",
    re.IGNORECASE,
)

# JSX heading components with className prop
_HEADING_JSX_RE = re.compile(
    r"<(?:h[1-6])\b[^>]*className\s*=\s*[{\"'][^}\"']*?(text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl))",
)

# Section-level spacing: gap-*, space-y-*, space-x-* on container-like elements
_SPACING_RE = re.compile(
    r"(?:className|class)\s*=\s*[{\"'][^}\"']*?((?:gap|space-[xy])-(?:\d+|px|0\.5|1\.5|2\.5|3\.5))",
)

# Table component detection
_TABLE_COMPONENT_RE = re.compile(r"<(DataTable|Table|table)\b")

# Form structure detection
_FORM_FIELD_RE = re.compile(r"<(FieldGroup|Field|FieldLabel|FormInput|FormField)\b")
_FORM_RAW_RE = re.compile(r"<(?:div|label)\b[^>]*(?:className|class)[^>]*>[\s\S]{0,200}?<(?:Input|input|Select|Textarea)\b")

# Hardcoded color values (not semantic tokens)
_HARDCODED_COLOR_RE = re.compile(
    r"(?:bg|text|border|ring|shadow|outline|fill|stroke)-"
    r"(?:black|white|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)"
    r"(?:-\d+)?(?:/\d+)?"
)

# Interactive component detection
_DIALOG_RE = re.compile(r"<(Dialog|AlertDialog|Sheet|Drawer|Modal)\b")
_TOAST_RE = re.compile(r"(?:toast\(|sonner|useToast|Toaster|toast\.)")
_EMPTY_STATE_RE = re.compile(r"<(EmptyState|Empty|NoData|NoResults)\b")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Outlier:
    file: str
    line: int
    found: str
    expected: str

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "found": self.found, "expected": self.expected}


@dataclass
class CategoryResult:
    status: str = "CONSISTENT"  # CONSISTENT | INCONSISTENT | SKIPPED
    majority_pattern: str = ""
    outliers: list[Outlier] = field(default_factory=list)
    skip_reason: str = ""

    def to_dict(self) -> dict:
        d: dict = {"status": self.status, "majority_pattern": self.majority_pattern}
        if self.outliers:
            d["outliers"] = [o.to_dict() for o in self.outliers]
        if self.skip_reason:
            d["skip_reason"] = self.skip_reason
        return d


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _discover_page_files(project_root: Path, file_filter: list[str] | None = None) -> list[Path]:
    """Find all page and component TSX/JSX files."""
    if file_filter:
        return [project_root / f for f in file_filter if (project_root / f).exists()]

    files: list[Path] = []
    src = project_root / "src"
    if not src.exists():
        return files

    for pattern in ["app/**/page.tsx", "app/**/page.jsx", "app/**/layout.tsx",
                     "components/**/*.tsx", "components/**/*.jsx"]:
        files.extend(src.glob(pattern))

    # Exclude node_modules, .next, test files
    return [f for f in files if ".next" not in f.parts and "node_modules" not in f.parts
            and not f.name.endswith((".test.tsx", ".test.jsx", ".spec.tsx", ".spec.jsx"))]


def _read_file(path: Path) -> tuple[str, list[str]]:
    """Read file content, return (full_text, lines)."""
    try:
        text = path.read_text(encoding="utf-8")
        return text, text.splitlines()
    except OSError:
        return "", []


def _rel(path: Path, root: Path) -> str:
    """Return relative path string."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Category analyzers
# ---------------------------------------------------------------------------

def _check_heading_hierarchy(files: list[Path], root: Path) -> CategoryResult:
    """Check that page headings use consistent text-* sizes."""
    page_headings: dict[str, list[tuple[int, str]]] = {}

    for fpath in files:
        # Only check page files for primary headings
        if "page." not in fpath.name:
            continue
        _, lines = _read_file(fpath)
        for i, line in enumerate(lines, 1):
            for m in _HEADING_TAG_RE.finditer(line):
                size = m.group(1)
                rel = _rel(fpath, root)
                page_headings.setdefault(rel, []).append((i, size))
            for m in _HEADING_JSX_RE.finditer(line):
                size = m.group(1)
                rel = _rel(fpath, root)
                page_headings.setdefault(rel, []).append((i, size))

    if not page_headings:
        return CategoryResult(status="SKIPPED", skip_reason="No heading patterns found in page files")

    # For each page, take the first (primary) heading size
    primary_sizes: dict[str, tuple[int, str]] = {}
    for rel_path, headings in page_headings.items():
        if headings:
            primary_sizes[rel_path] = headings[0]

    if not primary_sizes:
        return CategoryResult(status="SKIPPED", skip_reason="No primary headings found")

    # Find majority
    size_counter = Counter(size for _, size in primary_sizes.values())
    majority_size = size_counter.most_common(1)[0][0]

    outliers = []
    for rel_path, (line_num, size) in primary_sizes.items():
        if size != majority_size:
            outliers.append(Outlier(file=rel_path, line=line_num, found=size, expected=majority_size))

    return CategoryResult(
        status="INCONSISTENT" if outliers else "CONSISTENT",
        majority_pattern=majority_size,
        outliers=outliers,
    )


def _check_spacing_patterns(files: list[Path], root: Path) -> CategoryResult:
    """Check that section spacing is consistent across pages."""
    page_spacings: dict[str, list[tuple[int, str]]] = {}

    for fpath in files:
        if "page." not in fpath.name:
            continue
        _, lines = _read_file(fpath)
        for i, line in enumerate(lines, 1):
            for m in _SPACING_RE.finditer(line):
                spacing = m.group(1)
                # Only track section-level spacing (space-y-* and gap-*)
                if spacing.startswith(("space-y-", "gap-")):
                    rel = _rel(fpath, root)
                    page_spacings.setdefault(rel, []).append((i, spacing))

    if not page_spacings:
        return CategoryResult(status="SKIPPED", skip_reason="No spacing patterns found in page files")

    # For each page, take the first section-level spacing
    primary_spacings: dict[str, tuple[int, str]] = {}
    for rel_path, spacings in page_spacings.items():
        if spacings:
            primary_spacings[rel_path] = spacings[0]

    if not primary_spacings:
        return CategoryResult(status="SKIPPED", skip_reason="No section-level spacing found")

    spacing_counter = Counter(sp for _, sp in primary_spacings.values())
    majority_spacing = spacing_counter.most_common(1)[0][0]

    outliers = []
    for rel_path, (line_num, spacing) in primary_spacings.items():
        if spacing != majority_spacing:
            outliers.append(Outlier(file=rel_path, line=line_num, found=spacing, expected=majority_spacing))

    return CategoryResult(
        status="INCONSISTENT" if outliers else "CONSISTENT",
        majority_pattern=majority_spacing,
        outliers=outliers,
    )


def _check_component_patterns(files: list[Path], root: Path) -> CategoryResult:
    """Check that tables/data displays use consistent component patterns."""
    table_usages: list[tuple[str, int, str]] = []

    for fpath in files:
        _, lines = _read_file(fpath)
        for i, line in enumerate(lines, 1):
            for m in _TABLE_COMPONENT_RE.finditer(line):
                component = m.group(1)
                table_usages.append((_rel(fpath, root), i, component))

    if not table_usages:
        return CategoryResult(status="SKIPPED", skip_reason="No table components found")

    component_counter = Counter(comp for _, _, comp in table_usages)
    majority_component = component_counter.most_common(1)[0][0]

    outliers = []
    for rel_path, line_num, component in table_usages:
        if component != majority_component:
            outliers.append(Outlier(file=rel_path, line=line_num, found=component, expected=majority_component))

    return CategoryResult(
        status="INCONSISTENT" if outliers else "CONSISTENT",
        majority_pattern=majority_component,
        outliers=outliers,
    )


def _check_form_patterns(files: list[Path], root: Path) -> CategoryResult:
    """Check that forms use consistent field structure."""
    structured_forms: list[tuple[str, int]] = []
    raw_forms: list[tuple[str, int]] = []

    for fpath in files:
        text, lines = _read_file(fpath)
        for i, line in enumerate(lines, 1):
            if _FORM_FIELD_RE.search(line):
                structured_forms.append((_rel(fpath, root), i))
        for m in _FORM_RAW_RE.finditer(text):
            # Find line number for match
            line_num = text[:m.start()].count("\n") + 1
            raw_forms.append((_rel(fpath, root), line_num))

    total = len(structured_forms) + len(raw_forms)
    if total == 0:
        return CategoryResult(status="SKIPPED", skip_reason="No form patterns found")

    if len(structured_forms) >= len(raw_forms):
        majority = "FieldGroup/Field/FieldLabel"
        outliers = [Outlier(file=f, line=l, found="raw div+Input", expected=majority) for f, l in raw_forms]
    else:
        majority = "raw div+Input"
        outliers = [Outlier(file=f, line=l, found="FieldGroup/Field", expected=majority) for f, l in structured_forms]

    return CategoryResult(
        status="INCONSISTENT" if outliers else "CONSISTENT",
        majority_pattern=majority,
        outliers=outliers,
    )


def _check_token_usage(files: list[Path], root: Path) -> CategoryResult:
    """Check for hardcoded color values instead of semantic tokens."""
    violations: list[Outlier] = []

    for fpath in files:
        _, lines = _read_file(fpath)
        for i, line in enumerate(lines, 1):
            # Skip comments and imports
            stripped = line.strip()
            if stripped.startswith(("//", "*", "import ", "from ")):
                continue

            hardcoded_matches = _HARDCODED_COLOR_RE.findall(line)
            if not hardcoded_matches:
                continue

            # Filter out those that are part of semantic tokens or CSS variable definitions
            for match in hardcoded_matches:
                # Allow bg-white/bg-black in specific contexts (often intentional)
                if match in ("bg-white", "bg-black", "text-white", "text-black"):
                    continue
                violations.append(Outlier(
                    file=_rel(fpath, root),
                    line=i,
                    found=match,
                    expected="semantic token (e.g. bg-primary, text-muted-foreground)",
                ))

    if not violations:
        return CategoryResult(status="CONSISTENT", majority_pattern="semantic tokens")

    return CategoryResult(
        status="INCONSISTENT",
        majority_pattern="semantic tokens",
        outliers=violations,
    )


def _check_interactive_patterns(files: list[Path], root: Path) -> CategoryResult:
    """Check that dialogs, toasts, and empty states use consistent patterns."""
    dialog_types: list[tuple[str, int, str]] = []
    toast_types: list[tuple[str, int, str]] = []
    empty_types: list[tuple[str, int, str]] = []

    for fpath in files:
        _, lines = _read_file(fpath)
        for i, line in enumerate(lines, 1):
            for m in _DIALOG_RE.finditer(line):
                dialog_types.append((_rel(fpath, root), i, m.group(1)))
            if _TOAST_RE.search(line):
                toast_types.append((_rel(fpath, root), i, "toast"))
            for m in _EMPTY_STATE_RE.finditer(line):
                empty_types.append((_rel(fpath, root), i, m.group(1)))

    # Check dialog consistency
    outliers = []
    if dialog_types:
        dialog_counter = Counter(comp for _, _, comp in dialog_types)
        majority_dialog = dialog_counter.most_common(1)[0][0]
        for rel_path, line_num, comp in dialog_types:
            if comp != majority_dialog:
                outliers.append(Outlier(file=rel_path, line=line_num, found=comp, expected=majority_dialog))

    if empty_types:
        empty_counter = Counter(comp for _, _, comp in empty_types)
        majority_empty = empty_counter.most_common(1)[0][0]
        for rel_path, line_num, comp in empty_types:
            if comp != majority_empty:
                outliers.append(Outlier(file=rel_path, line=line_num, found=comp, expected=majority_empty))

    if not dialog_types and not toast_types and not empty_types:
        return CategoryResult(status="SKIPPED", skip_reason="No interactive patterns found")

    parts = []
    if dialog_types:
        parts.append(Counter(comp for _, _, comp in dialog_types).most_common(1)[0][0])
    if toast_types:
        parts.append("sonner/toast")
    if empty_types:
        parts.append(Counter(comp for _, _, comp in empty_types).most_common(1)[0][0])

    return CategoryResult(
        status="INCONSISTENT" if outliers else "CONSISTENT",
        majority_pattern=" + ".join(parts),
        outliers=outliers,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_ANALYZERS = {
    "heading_hierarchy": _check_heading_hierarchy,
    "spacing_patterns": _check_spacing_patterns,
    "component_patterns": _check_component_patterns,
    "form_patterns": _check_form_patterns,
    "token_usage": _check_token_usage,
    "interactive_patterns": _check_interactive_patterns,
}


def run_consistency_check(
    project_root: Path,
    guidelines_path: Path | None = None,
    categories: list[str] | None = None,
    file_filter: list[str] | None = None,
) -> dict:
    """Run cross-page UI consistency check.

    Args:
        project_root: Path to the project root directory.
        guidelines_path: Optional path to visual-guidelines.md (for future guideline-aware mode).
        categories: Optional list of categories to check. When None, all are checked.
        file_filter: Optional list of file paths (relative to project_root) to limit scan scope.
    """
    files = _discover_page_files(project_root, file_filter)
    if not files:
        return {
            "passed": 0, "total": 0, "skipped": True,
            "skip_reason": "No page/component files found in src/",
            "categories": {},
            "root_cause_groups": {},
        }

    cats_to_check = categories if categories else ALL_CATEGORIES
    results: dict[str, CategoryResult] = {}

    for cat in cats_to_check:
        analyzer = _ANALYZERS.get(cat)
        if not analyzer:
            results[cat] = CategoryResult(status="SKIPPED", skip_reason=f"Unknown category: {cat}")
            continue
        results[cat] = analyzer(files, project_root)

    # Count passed/total (exclude SKIPPED from total)
    active_results = {k: v for k, v in results.items() if v.status != "SKIPPED"}
    passed = sum(1 for v in active_results.values() if v.status == "CONSISTENT")
    total = len(active_results)

    # Build root-cause groups (only include groups with inconsistent categories)
    root_cause_groups: dict[str, list[str]] = {}
    for group_name, group_cats in ROOT_CAUSE_GROUPS.items():
        inconsistent = [c for c in group_cats if c in results and results[c].status == "INCONSISTENT"]
        if inconsistent:
            root_cause_groups[group_name] = inconsistent

    return {
        "passed": passed,
        "total": total,
        "skipped": total == 0,
        "skip_reason": "All categories skipped (no patterns found)" if total == 0 else "",
        "categories": {k: v.to_dict() for k, v in results.items()},
        "root_cause_groups": root_cause_groups,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-page UI consistency check")
    parser.add_argument("--cwd", required=True, help="Project root directory")
    parser.add_argument("--guidelines", help="Path to visual-guidelines.md (relative to cwd)")
    parser.add_argument(
        "--category", action="append", dest="categories", metavar="NAME",
        help=f"Category to check (repeatable). Available: {', '.join(ALL_CATEGORIES)}. "
             "When omitted, all categories are checked.",
    )
    parser.add_argument(
        "--files", nargs="+", metavar="FILE",
        help="File paths (relative to cwd) to limit scan scope. For scoped checks in iterate.",
    )
    args = parser.parse_args()

    project_root = Path(args.cwd).resolve()
    guidelines_path = (project_root / args.guidelines) if args.guidelines else None

    # Validate categories
    if args.categories:
        invalid = [c for c in args.categories if c not in ALL_CATEGORIES]
        if invalid:
            print(json.dumps({"error": f"Unknown categories: {invalid}. Valid: {ALL_CATEGORIES}"}))
            return 1

    result = run_consistency_check(
        project_root,
        guidelines_path=guidelines_path,
        categories=args.categories,
        file_filter=args.files,
    )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
