"""Inventory React components under conventional locations.

Scans `<frontend_root>/src/components/**`, `<frontend_root>/src/ui/**`,
and `<frontend_root>/src/app/**` for `.tsx`/`.jsx` files containing
component declarations. Counts:
- props_count via the simplest interface match (`interface XProps { ... }`)
- usage_count via grep across the rest of the source tree

Pure-regex parsing — no Node runtime in adopt's process. Robust enough
for the common React conventions; documented limitations for higher-order
components, dynamic components, and components co-located with their
consumer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_COMPONENT_DIRS = ("src/components", "src/ui", "src/app")
_COMPONENT_EXTS = {".tsx", ".jsx"}
_SKIP_DIR_NAMES = {
    "node_modules", "dist", "build", ".next", ".turbo", ".cache",
    "coverage", ".pytest_cache", "__pycache__",
}

# `export function Foo(...)`, `export const Foo = ...`, `export default function Foo(...)`,
# `export default Foo`. Captures the component identifier (PascalCase).
_EXPORT_RE = re.compile(
    r"\bexport\s+(?:default\s+)?(?:function|const|class)\s+([A-Z][A-Za-z0-9_]*)\b"
)
# Anonymous default export with a clear name nearby — common shadcn pattern.
_DEFAULT_NAMED_RE = re.compile(
    r"\bconst\s+([A-Z][A-Za-z0-9_]*)\s*=.*?\n+export\s+default\s+\1\b",
    re.DOTALL,
)


def _scan_component_file(path: Path) -> list[str]:
    """Return the PascalCase identifiers exported as components from this file."""
    try:
        body = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    names: set[str] = set()
    for m in _EXPORT_RE.finditer(body):
        names.add(m.group(1))
    for m in _DEFAULT_NAMED_RE.finditer(body):
        names.add(m.group(1))
    # Filter to "looks like a component" — must start with uppercase letter
    return sorted(n for n in names if n[:1].isupper())


def _count_props(file_body: str, component_name: str) -> int:
    """Count props on the matching `<component>Props` interface OR inline type.

    Heuristic: looks for `interface FooProps { ... }`, `type FooProps = { ... }`,
    or — last resort — destructured props in the function signature like
    `function Foo({ a, b, c }: ...)`. Returns 0 when no match.
    """
    iface_re = re.compile(
        rf"(?:interface|type)\s+{re.escape(component_name)}Props\s*[=]?\s*\{{([^}}]*)\}}",
        re.DOTALL,
    )
    m = iface_re.search(file_body)
    if m:
        # Each prop is "name: type" or "name?: type" on its own line / separated by ;
        body = m.group(1)
        # Split by `;` or newline; keep only entries that look like `ident:`
        prop_lines = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\??\s*:", body)
        return len(prop_lines)
    # Fallback: destructured props in function signature
    sig_re = re.compile(
        rf"(?:function|const)\s+{re.escape(component_name)}\b[^{{]*\{{([^}}]*)\}}\s*[:)]",
    )
    s = sig_re.search(file_body)
    if s:
        return len([p for p in s.group(1).split(",") if p.strip()])
    return 0


def _count_usages(component_name: str, search_root: Path, declaring_file: Path) -> int:
    """Grep the source tree (excluding the declaring file) for references to the component."""
    if not search_root.is_dir():
        return 0
    refs = 0
    pattern = re.compile(rf"\b{re.escape(component_name)}\b")
    for ts_file in search_root.rglob("*"):
        if not ts_file.is_file():
            continue
        if ts_file == declaring_file:
            continue
        if any(part in _SKIP_DIR_NAMES for part in ts_file.parts):
            continue
        if ts_file.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        try:
            body = ts_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        refs += len(pattern.findall(body))
    return refs


def build_component_inventory(frontend_root: Path) -> dict[str, Any]:
    """Walk the conventional component dirs under `frontend_root` and return
    `{components: [{name, path, props_count, usage_count}], total: N}`.
    """
    components: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()  # (name, path)
    for rel in _COMPONENT_DIRS:
        base = frontend_root / rel
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in _COMPONENT_EXTS:
                continue
            if any(part in _SKIP_DIR_NAMES for part in f.parts):
                continue
            try:
                body = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            names = _scan_component_file(f)
            for name in names:
                key = (name, f.relative_to(frontend_root).as_posix())
                if key in seen:
                    continue
                seen.add(key)
                components.append({
                    "name": name,
                    "path": key[1],
                    "props_count": _count_props(body, name),
                    "usage_count": _count_usages(name, frontend_root, f),
                })
    return {"total": len(components), "components": components}
