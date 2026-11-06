#!/usr/bin/env python3
"""Write one architecture / convention / learning bullet as its own drop file (iterate F2 / F3a).

Instead of editing the shared ``## Architecture Updates`` / ``## Convention Updates`` section
(which conflicts between parallel PRs), the bullet goes into a file of its own:

    .shipwright/agent_docs/decision-drops/bullets/<target>--<key>--<wt8>--<nonce8>.md

``/shipwright-changelog`` folds the files into the curated docs at release (``aggregate_decisions``
runs ``lib.doc_bullets.fold`` BEFORE the ADR fold). Until then every budget / shape / "documented"
check and the context load read folded + pending. A re-run with identical content returns the
existing file. See ``lib/doc_bullets.py``.

CLI:
    write_doc_bullet.py --project-root . --target conventions --run-id iterate-2026-11-06-x \\
        --impact convention --summary "what changed + key surface"
    write_doc_bullet.py --project-root . --target learnings --run-id <id> --text "- (2026-11-06) ..."
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.agent_doc_budget import ENTRY_MAX_CHARS, entry_anchor  # noqa: E402
from lib.agent_doc_shape import is_canonical, render_canonical_bullet  # noqa: E402
from lib.artifact_migrations import ARTIFACT_MIGRATIONS  # noqa: E402
from lib.doc_bullets import TARGETS, bullets_dir, pending  # noqa: E402
from lib.events_layout import worktree_id  # noqa: E402
from lib.events_read import sanitize_key  # noqa: E402

_IMPACTS = {"architecture": ("component", "data-flow"), "conventions": ("convention",)}


# A bullet file is a tracked non-exempt file, unlike the curated docs: repo-wide prose guards (artifact path
# canon, stack-profile prose guard) would flag text those docs may carry, so the writer rejects it up front.
_BUNDLED_PROFILES = re.compile(
    r"shared(?:_root)?\}?>?[\\/]+(?:[^\s`\"']*[\\/])?profiles\b"
    r"(?![\\/]+(?:deploy[\\/-]|reducibility-idioms\.json|deploy-profile))",
    re.IGNORECASE,
)


class DocBulletError(RuntimeError):
    """A bullet drop cannot be written (bad input, never a partial file)."""


def compose(target: str, run_id: str, *, text: str = "", impact: str = "", summary: str = "",
            pointer: str = "", entry_date: str = "") -> str:
    """The validated one-line bullet. ``text`` wins; else the canonical grammar is rendered."""
    if target not in TARGETS:
        raise DocBulletError(f"unknown target {target!r}; allowed: {sorted(TARGETS)}")
    if text.strip():
        bullet = text.strip()
    else:
        if impact not in _IMPACTS.get(target, ()):
            raise DocBulletError(f"--impact for {target} must be one of {list(_IMPACTS.get(target, ()))}")
        if not summary.strip():
            raise DocBulletError("--summary is empty")
        bullet = render_canonical_bullet(
            run_id, entry_date or date.today().isoformat(), impact, summary,
            pointer or f"decision_log (ADR via Run-ID: {run_id})",
        )
    if len(bullet.splitlines()) != 1 or not bullet.startswith("- "):
        raise DocBulletError("a bullet is exactly one line starting with '- '")
    if len(bullet) > ENTRY_MAX_CHARS:
        raise DocBulletError(f"bullet is {len(bullet)} chars (> {ENTRY_MAX_CHARS}); point, don't paste")
    for mig in ARTIFACT_MIGRATIONS:
        if mig["status"] in ("in_progress", "migrated") and any(re.search(pat, bullet) for pat in mig["old_path_patterns"]):
            raise DocBulletError(f"names a legacy artifact path ({mig['name']}); write the full .shipwright/... path instead")
    if _BUNDLED_PROFILES.search(bullet):
        raise DocBulletError("names the bundled stack-profile directory; describe it without a hand-built path")
    if target != "learnings" and not bullet.startswith(f"- **{run_id}**"):
        raise DocBulletError(f"the bullet must be anchored on this run: '- **{run_id}** ...'")
    if target != "learnings" and not is_canonical(bullet):
        raise DocBulletError("not canonical: '- **<run_id|ADR-NNN>** (YYYY-MM-DD): <Impact> — <sentence>. → decision_log (...)'")
    return bullet


def write_doc_bullet(project_root: Path | str, target: str, run_id: str, **kw: str) -> Path:
    """Write the drop (O_EXCL, LF). Same run + target + identical text = the existing file."""
    if not run_id.strip():
        raise DocBulletError("run_id is empty")
    bullet = compose(target, run_id, **kw)
    root = Path(project_root).resolve()
    key = sanitize_key(run_id)
    for b in pending(root, target)[0]:
        if b.key == key and b.text == bullet:
            return b.path
        if b.key == key and entry_anchor(b.text) == entry_anchor(bullet):
            raise DocBulletError(f"{b.path.name} already holds this run's {target} bullet; edit that file instead")
    bd = bullets_dir(root)
    bd.mkdir(parents=True, exist_ok=True)
    wt8 = worktree_id(root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for _ in range(5):
        path = bd / f"{target}--{key}--{wt8}--{uuid4().hex[:8]}.md"
        try:
            fd = os.open(path, flags, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write((bullet + "\n").encode("utf-8"))
        return path
    raise DocBulletError("could not claim a unique bullet file name")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project-root", default=".")
    p.add_argument("--target", required=True, choices=sorted(TARGETS))
    p.add_argument("--run-id", required=True)
    p.add_argument("--impact", default="", help="component|data-flow (architecture), convention (conventions)")
    p.add_argument("--summary", default="")
    p.add_argument("--pointer", default="", help="default: decision_log (ADR via Run-ID: <run_id>)")
    p.add_argument("--date", default="")
    p.add_argument("--text", default="", help="the full bullet line (learnings, or a hand-composed one)")
    a = p.parse_args(argv)
    try:
        path = write_doc_bullet(a.project_root, a.target, a.run_id, text=a.text, impact=a.impact,
                                summary=a.summary, pointer=a.pointer, entry_date=a.date)
    except DocBulletError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(path.relative_to(Path(a.project_root).resolve()).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
