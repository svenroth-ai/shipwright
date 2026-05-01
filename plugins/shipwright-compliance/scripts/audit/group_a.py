"""Group A — Artifact / path integrity (plan v7 Option Z, Step 4).

A2 / A3 / A4 — detective-only checks that validate the project's documented
commands, declared entry-points and config-driven path references actually
resolve against the working tree. None of these are preventive re-runs;
they catch drift that no other layer sees:

- A2 reads the ``## Development`` block of ``CLAUDE.md`` and asserts every
  ``npm run <script>`` / ``uv run <tool>`` / ``make <target>`` reference
  resolves against the nearest ``package.json`` / on-disk file / Makefile.
- A3 reads ``[project.scripts]`` from every ``pyproject.toml`` in the
  project (root + every plugin) and asserts each entry-point's module path
  exists on disk.
- A4 walks every path-valued field listed in ``audit_config.json``'s
  ``a4_path_fields`` (defaults: ``project_config.splits[].spec_path``,
  ``plan_config.sections[].section_file``) inside the ``shipwright_*_config.json``
  files and asserts each path points to an existing file.

Step 5 (Group A5 — CI security workflow integrity) is intentionally out of
scope; that requires the adopt-iterate to scaffold the workflow template
first.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    Finding,
    load_shared_lib,
)

# Pollution-free import: ``load_shared_lib`` registers the module in
# ``sys.modules`` under a unique sentinel name (NOT ``lib.drift_parsers``),
# so the compliance plugin's own ``lib`` package — and its
# ``thresholds.py`` etc. — stay reachable for the rest of the test session.
# ``from lib import drift_parsers`` would not be safe here.
drift_parsers = load_shared_lib("drift_parsers")


# ---------------------------------------------------------------------------
# Suggested-iterate hints
# ---------------------------------------------------------------------------

def _suggest(check_id: str, label: str) -> str:
    return (
        f"/shipwright-iterate --type change "
        f"\"reconcile {check_id} ({label}) "
        f"— see .shipwright/compliance/audit-report.md\""
    )


# ---------------------------------------------------------------------------
# A2 — dev-block command refs resolve
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _A2Issue:
    kind: str   # "npm" | "uv" | "make"
    detail: str


def _check_a2_dev_block(project_root: Path) -> tuple[str, str, list[str]]:
    """Return (status, detail, evidence_lines).

    status: "pass" | "fail" | "skip".
    """
    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        return "skip", "no CLAUDE.md found", []
    try:
        content = claude_md.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return "skip", f"could not read CLAUDE.md: {exc}", []

    blocks = drift_parsers.extract_dev_blocks(content)
    if not blocks:
        return "skip", "no '## Development' bash block in CLAUDE.md", []

    issues: list[_A2Issue] = []
    for block in blocks:
        for npm_ref in drift_parsers.parse_npm_run_refs(block):
            issue = _verify_npm_ref(project_root, npm_ref)
            if issue is not None:
                issues.append(issue)
        for uv_ref in drift_parsers.parse_uv_run_refs(block):
            issue = _verify_uv_ref(project_root, uv_ref)
            if issue is not None:
                issues.append(issue)
        for make_ref in drift_parsers.parse_make_refs(block):
            issue = _verify_make_ref(project_root, make_ref)
            if issue is not None:
                issues.append(issue)

    if not issues:
        return "pass", "every dev-block command resolves", []

    detail = "; ".join(i.detail for i in issues[:5])
    if len(issues) > 5:
        detail += f"; ({len(issues) - 5} more)"
    evidence = [i.detail for i in issues]
    return "fail", detail, evidence


def _verify_npm_ref(
    project_root: Path,
    ref: drift_parsers.NpmRunRef,
) -> _A2Issue | None:
    start_dir = project_root / (ref.cd_target or ".")
    if not start_dir.is_dir():
        return _A2Issue("npm", f"npm run {ref.script}: cd target '{ref.cd_target}' missing")
    pkg = drift_parsers.find_nearest_package_json(str(start_dir), str(project_root))
    if pkg is None:
        return _A2Issue("npm", f"npm run {ref.script}: no package.json found")
    scripts = drift_parsers.read_package_scripts(pkg)
    if ref.script not in scripts:
        return _A2Issue("npm", f"npm run {ref.script}: script not declared in {Path(pkg).name}")
    return None


def _verify_uv_ref(
    project_root: Path,
    ref: drift_parsers.UvRunRef,
) -> _A2Issue | None:
    """uv-run references can be either a script path or a module name.

    We accept the reference as resolving when EITHER:

    - A file exists at ``cd_target/tool`` (script path), OR
    - The nearest ``pyproject.toml`` declares the tool as a console script
      entry-point.

    **Design choice — bare tool names pass silently.** ``uv run pytest``
    or ``uv run ruff`` reference *transitive dev-dependencies* that
    aren't files in the project tree and aren't declared as console
    scripts in pyproject. Treating them as failures would produce
    constant false positives on every Python project that documents its
    test command. We only flag the reference when it *looks like a path*
    (contains ``/``, ``\\``, or ends with ``.py``), so missing script
    files in the repo are still caught — but bare tool names like
    ``pytest`` are accepted on faith. If your project wants stricter
    enforcement, declare the tool as a ``[project.scripts]`` entry-point
    so A3 covers it.
    """
    start_dir = project_root / (ref.cd_target or ".")
    if not start_dir.is_dir():
        return _A2Issue("uv", f"uv run {ref.tool}: cd target '{ref.cd_target}' missing")

    # Fast path: file at the expected location.
    candidate = start_dir / ref.tool
    if candidate.exists():
        return None

    # Console-script entry-point lookup.
    pyproject = drift_parsers.find_nearest_pyproject_toml(
        str(start_dir), str(project_root),
    )
    if pyproject is not None:
        scripts = _read_project_scripts_table(Path(pyproject))
        if ref.tool in scripts:
            return None

    # Some bare tools (pytest, ruff) come from installed deps. Don't fail
    # those: heuristically, anything that doesn't look like a path stays
    # silent. We only flag when the reference *looks* like a script path
    # (contains '/' or '\\' or ends with '.py').
    looks_like_path = (
        "/" in ref.tool
        or "\\" in ref.tool
        or ref.tool.endswith(".py")
    )
    if looks_like_path:
        return _A2Issue("uv", f"uv run {ref.tool}: file not found at {candidate}")
    return None


def _verify_make_ref(
    project_root: Path,
    ref: drift_parsers.MakeRef,
) -> _A2Issue | None:
    start_dir = project_root / (ref.cd_target or ".")
    if not start_dir.is_dir():
        return _A2Issue("make", f"make {ref.target}: cd target '{ref.cd_target}' missing")
    makefile = drift_parsers.find_nearest_makefile(str(start_dir), str(project_root))
    if makefile is None:
        return _A2Issue("make", f"make {ref.target}: no Makefile found")
    try:
        body = Path(makefile).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return _A2Issue("make", f"make {ref.target}: Makefile unreadable")
    # Match a target rule: line starting with "<target>:". Accept tabs or
    # spaces around the colon, but the target must be the first non-space
    # token on the line.
    pattern = re.compile(rf"(?m)^{re.escape(ref.target)}\s*:")
    if not pattern.search(body):
        return _A2Issue("make", f"make {ref.target}: target not found in Makefile")
    return None


# ---------------------------------------------------------------------------
# A3 — pyproject [project.scripts] entry-points resolve
# ---------------------------------------------------------------------------


def _check_a3_pyproject_scripts(project_root: Path) -> tuple[str, str, list[str]]:
    """Walk every ``pyproject.toml`` under ``project_root`` and verify each
    ``[project.scripts] foo = "module.path:func"`` entry-point's module
    path is reachable as a file under the same directory tree."""
    pyprojects = list(_iter_pyprojects(project_root))
    if not pyprojects:
        return "skip", "no pyproject.toml files found", []

    found_any_scripts = False
    issues: list[str] = []
    for pyproject in pyprojects:
        scripts = _read_project_scripts_table(pyproject)
        if not scripts:
            continue
        found_any_scripts = True
        base = pyproject.parent
        for entry_name, target in scripts.items():
            module_path = target.split(":", 1)[0].strip()
            if not _module_exists(base, module_path):
                rel = pyproject.relative_to(project_root).as_posix()
                issues.append(
                    f"{rel} :: {entry_name}={target} → module '{module_path}' not on disk"
                )

    if not found_any_scripts:
        return "skip", "no [project.scripts] tables declared", []

    if not issues:
        return "pass", "every [project.scripts] entry-point resolves", []

    detail = "; ".join(issues[:3])
    if len(issues) > 3:
        detail += f"; ({len(issues) - 3} more)"
    return "fail", detail, issues


def _iter_pyprojects(project_root: Path) -> Iterable[Path]:
    """Yield every ``pyproject.toml`` under the project root, skipping
    common dependency/cache directories."""
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv",
                 "dist", "build", ".pytest_cache", ".ruff_cache",
                 ".mypy_cache", ".tox", ".worktrees"}
    for pyproject in sorted(project_root.rglob("pyproject.toml")):
        # Skip if any ancestor is in skip_dirs.
        if any(p.name in skip_dirs for p in pyproject.parents):
            continue
        yield pyproject


def _read_project_scripts_table(pyproject_path: Path) -> dict[str, str]:
    """Return ``{name: target}`` from ``[project.scripts]`` (and ``[tool.poetry.scripts]``)."""
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return {}
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    project = data.get("project", {})
    if isinstance(project, dict):
        scripts = project.get("scripts", {})
        if isinstance(scripts, dict):
            out.update({k: str(v) for k, v in scripts.items()})
    tool = data.get("tool", {})
    if isinstance(tool, dict):
        poetry = tool.get("poetry", {})
        if isinstance(poetry, dict):
            scripts = poetry.get("scripts", {})
            if isinstance(scripts, dict):
                out.update({k: str(v) for k, v in scripts.items()})
    return out


def _module_exists(base: Path, module_path: str) -> bool:
    """Return True if ``module_path`` resolves to a file or package under base."""
    parts = module_path.split(".")
    if not parts or any(not p for p in parts):
        return False
    candidate_dir = base.joinpath(*parts)
    if (candidate_dir / "__init__.py").is_file():
        return True
    candidate_file = base.joinpath(*parts[:-1], parts[-1] + ".py")
    return candidate_file.is_file()


# ---------------------------------------------------------------------------
# A4 — config path-field integrity
# ---------------------------------------------------------------------------


def _check_a4_config_paths(
    project_root: Path,
    a4_fields: list[str],
) -> tuple[str, str, list[str]]:
    """Walk every ``shipwright_*_config.json`` and verify each field listed
    in ``a4_fields`` resolves to an existing file/dir."""
    targets = list(_resolve_a4_targets(project_root, a4_fields))
    if not targets:
        return "skip", "no shipwright_*_config.json with declared path-fields", []

    issues: list[str] = []
    for config_name, field, value in targets:
        path = (project_root / value).resolve()
        if not path.exists():
            issues.append(f"{config_name}::{field}={value} (no such path)")

    if not issues:
        return "pass", f"every path-field in {len(targets)} entries resolves", []

    detail = "; ".join(issues[:3])
    if len(issues) > 3:
        detail += f"; ({len(issues) - 3} more)"
    return "fail", detail, issues


def _resolve_a4_targets(
    project_root: Path,
    a4_fields: list[str],
) -> Iterable[tuple[str, str, str]]:
    """Yield ``(config_name, field_path, value)`` triples for every
    a4_fields-matched leaf in the project's config jsons."""
    for field_spec in a4_fields:
        # Spec shape: "<config>.<dotted-path>" where each segment may be a
        # dict key OR a list-iterator marker "[]".
        if "." not in field_spec:
            continue
        config_name, _, dotted = field_spec.partition(".")
        config_path = project_root / f"shipwright_{config_name}.json"
        if not config_path.exists():
            continue
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for value in _walk_dotted_path(data, dotted):
            if isinstance(value, str) and value:
                yield config_name, dotted, value


def _walk_dotted_path(data: Any, dotted: str) -> Iterable[Any]:
    """Walk ``data`` along the dotted path, yielding every leaf value reached.

    Path segment grammar:
    - ``key``   — descend into ``data[key]`` (must be dict).
    - ``key[]`` — iterate ``data[key]`` (must be list); each element becomes a
      branch in the walk. Bare ``[]`` iterates ``data`` itself.
    - ``key{}`` — iterate ``data[key].values()`` (must be dict). Bare ``{}``
      iterates ``data.values()``. Used when the schema keys are dynamic
      (e.g. ``splits.<name>.plan_file`` where ``<name>`` is per-project).

    Missing keys / wrong types yield nothing rather than raising.
    """
    parts = dotted.split(".")
    queue: list[tuple[Any, list[str]]] = [(data, parts)]
    while queue:
        node, remaining = queue.pop()
        if not remaining:
            yield node
            continue
        head, *tail = remaining
        if head.endswith("[]"):
            key = head[:-2]
            if key:
                if not isinstance(node, dict):
                    continue
                seq = node.get(key)
            else:
                seq = node
            if not isinstance(seq, list):
                continue
            for item in seq:
                queue.append((item, tail))
            continue
        if head.endswith("{}"):
            key = head[:-2]
            if key:
                if not isinstance(node, dict):
                    continue
                inner = node.get(key)
            else:
                inner = node
            if not isinstance(inner, dict):
                continue
            for value in inner.values():
                queue.append((value, tail))
            continue
        if not isinstance(node, dict):
            continue
        if head not in node:
            continue
        queue.append((node[head], tail))


# ---------------------------------------------------------------------------
# Top-level run()
# ---------------------------------------------------------------------------


_SEVERITY_BY_CHECK = {"A2": "HIGH", "A3": "MEDIUM", "A4": "HIGH"}
_NAME_BY_CHECK = {
    "A2": "Dev-block command refs resolve",
    "A3": "[project.scripts] entry-points resolvable",
    "A4": "Config path-fields integrity",
}


def run(
    project_root: Path,
    config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run A2/A3/A4 and return Findings."""
    cfg = config or {}
    a4_fields = cfg.get("a4_path_fields") or []

    out: list[Finding] = []

    runners: list[tuple[str, callable]] = [
        ("A2", lambda: _check_a2_dev_block(project_root)),
        ("A3", lambda: _check_a3_pyproject_scripts(project_root)),
        ("A4", lambda: _check_a4_config_paths(project_root, a4_fields)),
    ]
    for check_id, fn in runners:
        try:
            status, detail, evidence = fn()
        except Exception as exc:  # noqa: BLE001 — never crash the whole group
            out.append(Finding(
                group="A", check_id=check_id, name=_NAME_BY_CHECK[check_id],
                severity=_SEVERITY_BY_CHECK[check_id],
                source=SOURCE_DETECTIVE_ONLY, status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            ))
            continue
        out.append(Finding(
            group="A", check_id=check_id, name=_NAME_BY_CHECK[check_id],
            severity=_SEVERITY_BY_CHECK[check_id],
            source=SOURCE_DETECTIVE_ONLY,
            status=status,
            detail=detail,
            evidence=list(evidence),
            suggested_iterate_cmd=(
                _suggest(check_id, _NAME_BY_CHECK[check_id])
                if status == "fail" else None
            ),
        ))
    return out
