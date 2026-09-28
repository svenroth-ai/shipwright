#!/usr/bin/env python3
"""Write a sanitized copy of a spec file for `architecture-internal-reviewer`.

That agent has ``tools: Read, Grep, Glob`` and is hand-fed a spec file PATH,
so a prose instruction to "ignore prior-review sections" is not a real
defense — it can simply re-read the original file. The external architecture
pass closed this same anchoring gap in code
(:func:`lib.external_review_modes.strip_prior_review_sections`, wired into
``external_review.py``'s ``--mode architecture``); this tool applies the
identical strip and hands the agent the SANITIZED COPY's path instead of the
original spec's, so there is nothing left to re-read even if it tried.

Output path: ``{project_root}/.shipwright/runs/{run_id}/architecture-internal-spec.md``
(same ephemeral, gitignored location `surface_verification.py` uses for
per-run scratch evidence — this file carries no information the committed
spec.md doesn't already have, so it is never committed itself).

Prints the output path on success (exit 0).

Two disclosed, accepted residuals (external review, both Windows-only /
low-impact): the ``is_symlink()`` ancestor checks below do not detect an
NTFS directory junction — no stdlib primitive detects one across the
Python versions this repo supports, and the CI gate that matters runs on
POSIX, where junctions do not exist. And ``--spec-file`` itself carries no
containment check against ``--project-root`` (unlike the output path,
which gets the full strict-run-id + symlink + containment treatment) —
it is read-only and its content only ever lands in the gitignored runs
directory, so the asymmetry has no write-side consequence.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# parents[0]=tools, [1]=scripts, [2]=shared.
_SHARED_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from external_review_modes import strip_prior_review_sections  # noqa: E402
from iterate_entry import RUN_ID_STRICT  # noqa: E402


def _write_refusing_symlinks(out_path: Path, content: str) -> None:
    """Write ``content`` to ``out_path``, refusing to follow a pre-existing
    symlink at that exact filename — a fixed, predictable output path is
    exactly what a symlink-redirect attack needs. ``O_NOFOLLOW`` makes this
    atomic (no check-then-write race) on POSIX, where the CI gate that
    matters actually runs; Windows has no such flag, so this falls back to
    a plain existence check there (best-effort, not atomic)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    elif out_path.is_symlink():
        raise OSError(f"refusing to write through an existing symlink: {out_path}")
    fd = os.open(out_path, flags, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--spec-file", required=True)
    args = parser.parse_args(argv)

    if RUN_ID_STRICT.fullmatch(args.run_id) is None:
        print(
            f"error: --run-id {args.run_id!r} does not match the iterate "
            f"run-id format ({RUN_ID_STRICT.pattern}) — refusing to build a "
            f"filesystem path from it",
            file=sys.stderr,
        )
        return 1

    spec_path = Path(args.spec_file)
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: could not read --spec-file {spec_path}: {exc}", file=sys.stderr)
        return 1
    sanitized = strip_prior_review_sections(spec_text)

    # Check for a symlinked ancestor BEFORE resolving — resolving first would
    # silently follow it, so the containment check below would only ever
    # compare a symlink-escaped path against itself (external review,
    # medium): a `.shipwright` or `.shipwright/runs` planted as a symlink to
    # outside the project would pass containment trivially post-resolve. The
    # run-id directory itself needs the same check (external review, medium,
    # a second round on this file): a symlink at `runs/{run_id}` pointing at
    # a DIFFERENT run's directory would still resolve to somewhere under the
    # (legitimate) runs root, so containment alone would not catch it —
    # it would silently overwrite that other run's sanitized spec.
    shipwright_dir = Path(args.project_root) / ".shipwright"
    runs_root_unresolved = shipwright_dir / "runs"
    run_dir_unresolved = runs_root_unresolved / args.run_id
    for ancestor in (shipwright_dir, runs_root_unresolved, run_dir_unresolved):
        if ancestor.is_symlink():
            print(
                f"error: refusing to write through a symlinked directory: {ancestor}",
                file=sys.stderr,
            )
            return 1

    runs_root = runs_root_unresolved.resolve()
    runs_dir = (runs_root / args.run_id).resolve()
    if runs_dir != runs_root and runs_root not in runs_dir.parents:
        print(
            f"error: resolved output directory {runs_dir} escapes the "
            f"intended {runs_root} — refusing to write",
            file=sys.stderr,
        )
        return 1

    runs_dir.mkdir(parents=True, exist_ok=True)
    out_path = runs_dir / "architecture-internal-spec.md"
    try:
        _write_refusing_symlinks(out_path, sanitized)
    except OSError as exc:
        print(f"error: refusing to write {out_path}: {exc}", file=sys.stderr)
        return 1
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
