"""What an F0.5 surface runner ran: the test paths it names, and their latest staged results.

:func:`runner_test_paths` reads the ``runner`` string of the F0.5 block. It
understands a ``cd <dir> &&`` prefix, uv's ``--directory <dir>`` /
``--project <dir>`` (``=`` form too), and absolute paths under the project
root, so a plugin-located runner (``cd plugins/x && uv run pytest tests/...``)
resolves to project-relative paths. Each named path is tried against the last
such directory first and the project root second; only test paths that exist
are kept.

:func:`latest_attempts` reads the staged reports one by one, in staging order,
and lets a later report's verdict for a test id replace an earlier one: a test
that failed and then passed on a staged retry counts as passed. (The evidence
index proper, ``fresh_evidence``, folds every report fail-closed instead; that
stays the rule for the whole-suite check.) Within one report the collector's
fail-closed reduction still applies.
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import shlex
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import evidence_drop  # noqa: E402

from ._surface_detect import is_test_path  # noqa: E402

__all__ = ["latest_attempts", "passing_case_count", "passing_case_counts", "runner_test_paths", "under"]

_DIR_FLAGS = ("--directory", "--project")
_SEPARATORS = frozenset({"&&", "||", ";", "|"})


def _clean(token: str) -> str:
    rel = token.split("::", 1)[0].rstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _inside(root: Path, raw: str) -> str | None:
    """Project-relative POSIX form of an absolute ``raw`` under ``root``, else ``None``."""
    try:
        return Path(raw).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _is_absolute(raw: str) -> bool:
    return raw.startswith("/") or Path(raw).is_absolute()


def _join(cwd: str | None, rel: str) -> str | None:
    if cwd is None:
        return None
    joined = posixpath.normpath(posixpath.join(cwd, rel)) if cwd else posixpath.normpath(rel)
    return None if joined == ".." or joined.startswith("../") else ("" if joined == "." else joined)


def _test_path(root: Path, rel: str | None) -> bool:
    return bool(rel) and (is_test_path(rel) or is_test_path(rel + "/_")) and (root / rel).exists()


def runner_test_paths(project_root: Path, runner: object) -> list[str]:
    """Project-relative test paths the runner command names and that exist."""
    if not isinstance(runner, str) or not runner.strip():
        return []
    root = Path(project_root)
    text = runner.replace("\\", "/")
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    cwd: str | None = ""  # None: a directory outside the project, relative paths cannot be placed
    paths: list[str] = []
    expect_dir = False
    for token in tokens:
        if expect_dir or token.startswith(tuple(f"{flag}=" for flag in _DIR_FLAGS)):
            raw = token.split("=", 1)[1] if not expect_dir else token
            expect_dir = False
            cwd = _inside(root, raw) if _is_absolute(raw) else _join(cwd, _clean(raw) or ".")
            continue
        if token == "cd" or token in _DIR_FLAGS:
            expect_dir = True
            continue
        if token.startswith("-") or token in _SEPARATORS:
            continue
        rel = _clean(token)
        if _is_absolute(rel):
            candidates = [_inside(root, rel)]
        else:  # outside the project (cwd None) a relative path names nothing here
            candidates = [_join(cwd, rel), _join("", rel) if cwd is not None else None]
        found = next((c for c in candidates if _test_path(root, c)), None)
        if found and found not in paths:
            paths.append(found)
    return paths


def under(tid: str, paths: list[str]) -> bool:
    """``tid`` is a result of a test under one of ``paths`` (a file, or a directory)."""
    return any(tid == p or tid.startswith(p + "/") or tid.startswith(p + "::") for p in paths)


def passing_case_counts(project_root: Path, evio) -> dict[str, int]:
    """``{folded test id: passing JUnit cases}``; the runner's own counting unit.

    The evidence index folds ``test_foo[a]`` / ``test_foo[b]`` into one id, but a runner
    reports ``tests_run`` per case (pytest's "N passed"). Comparing the two units made a
    parametrized unit's honest ``tests_run=18`` read as 10 passing. An id absent here
    (Playwright, Vitest) counts as 1. Known fail-closed limits (they undercount, never
    overcount): the Playwright reader folds every project (browser) into one id, so a
    multi-project run recording N per project is refused; and a later staged report
    REPLACES an earlier one's count, as in :func:`latest_attempts`, so a partial ``--lf``
    retry undercounts. Do not "fix" the second by summing reports: a full re-run would
    double-count and fail open.
    """
    prov = evidence_drop.read_provenance(project_root) or {}
    evd = evidence_drop.evidence_dir(project_root)
    counts: dict[str, int] = {}
    for entry in (prov.get("reports") or {}).get("junit") or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        if (not isinstance(name, str) or "/" in name or "\\" in name or "base" not in entry
                or not fnmatch.fnmatchcase(name, evidence_drop.JUNIT_GLOB)):
            continue
        try:
            text = (evd / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # unread => no extra cases credited; the id still counts once
        counts.update(evio.read_junit_cases(text, root=Path(project_root), base=str(entry["base"])))
    return counts


def passing_case_count(passed: list[str], cases: dict[str, int]) -> int:
    """Passing cases behind the ``passed`` ids: a JUnit id counts its cases, any other 1."""
    return sum(max(cases.get(tid, 1), 1) for tid in passed)


def _results(evio, project_root: Path, prov: dict, **reports) -> dict | None:
    try:
        index = evio.build_index(root=Path(project_root), resumed_local=prov.get("resumed_local"), **reports)
    except Exception:  # noqa: BLE001 - an unreadable report is unread evidence, never a pass
        return None
    results = index.get("results") if isinstance(index, dict) else None
    return results if isinstance(results, dict) else None


def latest_attempts(project_root: Path, evio) -> dict | None:
    """``{test id: entry}`` with the latest staged report's verdict per id; ``None`` if unreadable."""
    prov = evidence_drop.read_provenance(project_root) or {}
    evd = evidence_drop.evidence_dir(project_root)
    staged = prov.get("reports") or {}
    merged: dict = {}
    for entry in staged.get("junit") or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        if (not isinstance(name, str) or "/" in name or "\\" in name or "base" not in entry
                or not fnmatch.fnmatchcase(name, evidence_drop.JUNIT_GLOB)):
            continue  # the same malformed-entry rejection fresh_evidence applies
        try:
            text = (evd / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        results = _results(evio, project_root, prov, junit_reports=[(text, str(entry["base"]))])
        if results is None:
            return None
        merged.update(results)
    for kind in ("playwright", "vitest"):
        if kind not in staged:
            continue
        try:
            data = json.loads((evd / evidence_drop.REPORT_NAMES[kind]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        results = _results(evio, project_root, prov, **{kind: data})
        if results is None:
            return None
        merged.update(results)
    return merged
