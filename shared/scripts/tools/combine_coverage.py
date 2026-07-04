#!/usr/bin/env python3
"""Combine per-tier coverage data into ONE repo-relative ``coverage.xml``.

Diff-coverage roadmap **Phase 2** (``iterate-2026-07-04-diff-coverage-rollout-
combine``). The monorepo measures coverage in many separate processes — the
``shared/`` tier and ``integration-tests`` run from the repo root (so they record
**repo-relative** source paths: ``shared/...``), but every plugin suite runs
``cd plugins/<name> && pytest`` in its own uv env, so ``[tool.coverage.run]
relative_files`` records paths **relative to the plugin CWD** — ``scripts/lib/
foo.py`` — with the plugin identity LOST in the data file.

A single global ``coverage combine`` ``[paths]`` mapping CANNOT disambiguate N
plugins that all recorded ``scripts/...`` (they'd collapse onto one plugin's
directory). The fix — proven on a synthetic 2-plugin fixture at kickoff — is to
remap **one data file at a time** with a *plugin-specific* ``[paths]``::

    [paths]
    src =
        plugins/<name>/scripts/     # canonical (repo-relative)
        scripts/                    # alias (what that plugin recorded)

``coverage combine --append`` of that single file then rewrites ``scripts/foo.py``
-> ``plugins/<name>/scripts/foo.py`` and accumulates into one data file. ``shared``
/``integration`` data is already repo-relative, so it is appended un-remapped.
``coverage xml`` over the accumulated data emits the combined repo-relative report
that ``diff-cover`` (and Phase-2's tracked ``coverage.total`` recorder) consume.

Absent-input safe: an empty/missing data dir produces no ``coverage.xml`` and
exits 0 — the measurement chain never blocks a run.

Usage::

    combine_coverage.py --project-root . --data-dir .cov-data \
        [--output coverage.xml]

The per-tier data files must be named ``.coverage.<label>`` (e.g.
``.coverage.shared``, ``.coverage.integration``, ``.coverage.shipwright-build``).
A label that resolves to ``plugins/<label>/scripts/`` is remapped; any other label
(``shared``, ``integration``, ...) is treated as already repo-relative.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_TOOLS_ROOT = Path(__file__).resolve().parent
if str(_TOOLS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT.parent))

# Reuse the Phase-1 line-rate parser (same repo-relative coverage.xml shape).
from tools.measure_diff_coverage import line_rate_percent  # noqa: E402

DATA_PREFIX = ".coverage."
DEFAULT_DATA_DIR = ".cov-data"
DEFAULT_OUTPUT = "coverage.xml"
# Tests are not product code — mirror pyproject [tool.coverage.run].omit so the
# combined line-rate reflects source coverage, not tests covering themselves.
_OMIT = ("*/tests/*", "*/tests/fixtures/*")


# --------------------------------------------------------------------------- #
# Discovery + per-label path mapping (pure)
# --------------------------------------------------------------------------- #
def discover_data_files(data_dir: Path | str) -> list[Path]:
    """Every ``.coverage.<label>`` file in ``data_dir``, sorted for determinism.

    The bare ``.coverage`` (no label) and the tool's own accumulator are ignored
    — only labelled per-tier files count."""
    d = Path(data_dir)
    if not d.is_dir():
        return []
    out = [
        p for p in sorted(d.iterdir())
        if p.is_file() and p.name.startswith(DATA_PREFIX)
        and p.name != DATA_PREFIX.rstrip(".")  # not ".coverage"
        and p.name[len(DATA_PREFIX):] not in ("", "combined")
    ]
    return out


def label_of(data_file: Path | str) -> str:
    """``.coverage.shipwright-build`` -> ``shipwright-build``."""
    return Path(data_file).name[len(DATA_PREFIX):]


def resolve_plugin_label(label: str, project_root: Path) -> str | None:
    """The plugin whose ``scripts/`` dir this data-file label maps to.

    Exact match first; otherwise the **longest** plugin name that is a dotted
    prefix of ``label`` — pytest-cov's parallel / pytest-xdist mode appends
    ``.<host>.<pid>.<rand>`` to ``COVERAGE_FILE``, so ``.coverage.shipwright-
    build.gw0.1234`` must still resolve to ``shipwright-build`` (else its
    ``scripts/...`` data is silently treated as already-repo-relative and
    dropped by ``coverage xml``). Returns ``None`` for non-plugin tiers
    (``shared``, ``integration``) or an unknown label."""
    plugins_dir = project_root / "plugins"
    if not plugins_dir.is_dir():
        return None
    names = [p.name for p in plugins_dir.iterdir() if (p / "scripts").is_dir()]
    # A dotted delimiter avoids matching `shipwright-test` against
    # `shipwright-test-extra`; the longest match wins.
    matches = [n for n in names if label == n or label.startswith(n + ".")]
    return max(matches, key=len) if matches else None


def paths_alias_for(label: str, project_root: Path) -> str | None:
    """The repo-relative canonical prefix a plugin's ``scripts/`` data remaps to,
    or ``None`` when the tier is already repo-relative (``shared``/``integration``
    or any label that resolves to no plugin ``scripts/`` dir)."""
    plugin = resolve_plugin_label(label, project_root)
    return f"plugins/{plugin}/scripts/" if plugin else None


def _combine_rcfile(canonical: str | None) -> str:
    """A ``.coveragerc`` body for one combine step. ``relative_files`` is always
    on; a ``[paths]`` block is added only when the tier needs remapping."""
    body = "[run]\nrelative_files = true\n"
    if canonical is not None:
        body += f"[paths]\nsrc =\n    {canonical}\n    scripts/\n"
    return body


def _report_rcfile() -> str:
    omit = "".join(f"    {pat}\n" for pat in _OMIT)
    return f"[run]\nrelative_files = true\nomit =\n{omit}"


# --------------------------------------------------------------------------- #
# coverage subprocess wrapper (binary, then ``python -m coverage`` fallback)
# --------------------------------------------------------------------------- #
def _run_coverage(
    args: list[str], *, cwd: Path, env_file: Path, rcfile: Path,
    runner: Any = subprocess.run,
) -> subprocess.CompletedProcess | None:
    """Run ``coverage <args>`` with COVERAGE_FILE/COVERAGE_RCFILE pinned. Returns
    the completed process, or ``None`` if the binary is unavailable both ways."""
    import os
    env = dict(os.environ)
    env["COVERAGE_FILE"] = str(env_file)
    env["COVERAGE_RCFILE"] = str(rcfile)
    for base in (["coverage"], [sys.executable, "-m", "coverage"]):
        try:
            return runner(base + args, cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=300)
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
    return None


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def combine_to_xml(
    project_root: Path | str,
    data_dir: Path | str,
    output: Path | str,
    *,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Remap-combine every per-tier data file into one repo-relative
    ``coverage.xml`` at ``output``. Returns a structured result dict with
    ``status`` (``ok``/``n-a``), ``combined`` (file count), ``total`` (line-rate
    percent or ``None``), and ``xml`` (output path or ``None``)."""
    project_root = Path(project_root).resolve()
    output = Path(output)
    if not output.is_absolute():
        output = project_root / output
    files = discover_data_files(data_dir)
    discovered = len(files)
    if not files:
        return {"status": "n-a", "combined": 0, "discovered": 0,
                "total": None, "xml": None,
                "note": "no per-tier coverage data files found"}

    with tempfile.TemporaryDirectory() as td:
        accum = Path(td) / ".coverage.combined"
        n_ok = 0
        failed: list[str] = []
        for data_file in files:
            canonical = paths_alias_for(label_of(data_file), project_root)
            rc = Path(td) / "combine.rc"
            rc.write_text(_combine_rcfile(canonical), encoding="utf-8")
            # --keep so a re-run over the same data dir is idempotent.
            proc = _run_coverage(
                ["combine", "--append", "--keep", str(Path(data_file).resolve())],
                cwd=project_root, env_file=accum, rcfile=rc, runner=runner,
            )
            if proc is not None and proc.returncode == 0:
                n_ok += 1
            else:
                failed.append(label_of(data_file))
        if n_ok == 0 or not accum.exists():
            return {"status": "n-a", "combined": 0, "discovered": discovered,
                    "total": None, "xml": None,
                    "note": "coverage combine produced no data"}

        rc_report = Path(td) / "report.rc"
        rc_report.write_text(_report_rcfile(), encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        proc = _run_coverage(
            ["xml", "-o", str(output)],
            cwd=project_root, env_file=accum, rcfile=rc_report, runner=runner,
        )
        if proc is None or proc.returncode != 0 or not output.exists():
            detail = "" if proc is None else (proc.stderr or "").strip()[:200]
            return {"status": "n-a", "combined": n_ok, "discovered": discovered,
                    "total": None, "xml": None,
                    "note": f"coverage xml failed: {detail}"}

    total = line_rate_percent(output)
    # A PARTIAL combine (some tiers failed to fold in) still writes a valid XML,
    # but its line-rate is over FEWER tiers than exist — a silently wrong
    # "repo-wide" total. Flag it non-ok so the recorder / CI refuse to trust it:
    # a green-but-wrong baseline is worse than an honest failure.
    if n_ok < discovered:
        return {"status": "partial", "combined": n_ok, "discovered": discovered,
                "total": total, "xml": str(output), "failed": failed,
                "note": f"only {n_ok}/{discovered} tiers combined; failed: "
                        f"{', '.join(failed)}"}
    return {"status": "ok", "combined": n_ok, "discovered": discovered,
            "total": total, "xml": str(output)}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Combine per-tier coverage into one "
                                             "repo-relative coverage.xml (Phase 2).")
    ap.add_argument("--project-root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                    help=f"dir holding .coverage.<label> files (default: {DEFAULT_DATA_DIR})")
    ap.add_argument("--output", default=DEFAULT_OUTPUT,
                    help=f"combined coverage.xml path (default: {DEFAULT_OUTPUT})")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = project_root / data_dir
    result = combine_to_xml(project_root, data_dir, args.output)
    if result["status"] == "ok":
        total = result["total"]
        extra = f" (repo line-rate {total:.1f}%)" if total is not None else ""
        print(f"combine-coverage: {result['combined']} tier(s) -> "
              f"{result['xml']}{extra}")
        return 0
    if result["status"] == "partial":
        # Non-zero exit so a chained `combine && record_coverage_total` refuses to
        # commit a subset baseline, and CI fails loud rather than green-but-wrong.
        sys.stderr.write(f"combine-coverage: PARTIAL — {result['note']}. "
                         f"Refusing to treat this as a repo-wide total.\n")
        return 1
    # n-a: no data at all (e.g. clean main) — absent-safe, not an error.
    print(f"combine-coverage: n/a — {result.get('note', 'no data')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
