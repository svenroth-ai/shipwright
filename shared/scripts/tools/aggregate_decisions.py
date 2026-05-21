#!/usr/bin/env python3
"""Aggregate per-run ADR decision-drops into ``decision_log.md``.

The serialized counterpart of ``write_decision_drop.py``. Iterate F3 writes one
JSON drop per ADR under ``.shipwright/agent_docs/decision-drops/`` keyed by
``run_id`` — never a number. This script, invoked from ``/shipwright-changelog``
Step 4, is the ONE serialized point that assigns the sequential ``ADR-NNN``:

1. Acquire the ``decision_log.md`` lock for the whole read-render-write-cleanup.
2. Compute the next ADR number from the current ``decision_log.md``.
3. Snapshot the drop files, render each through
   ``write_decision_log.format_entry`` (zero format drift vs the direct path),
   numbering them sequentially.
4. Append the rendered entries, write ``decision_log.md`` once.
5. Delete only the drop files that were snapshotted (drops written mid-run
   survive into the next release).

Because numbering happens here — single-threaded, lock-held — two parallel
iterates can never claim the same ADR number.

CLI:
    uv run shared/scripts/tools/aggregate_decisions.py \\
        --project-root . [--dry-run] [--lock-timeout 10.0]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_main_repo_root  # noqa: E402
from lib.file_lock import LockTimeout, file_lock  # noqa: E402
from tools.write_decision_log import (  # noqa: E402
    ADR_SPEC_FOLDER,
    DECISION_LOG_HEADER,
    _append_architecture_update,
    format_entry,
    get_next_adr_number,
)

DROP_DIRNAME = "decision-drops"  # under .shipwright/agent_docs/
_REQUIRED_DROP_FIELDS = ("run_id", "section", "decision")
ADR_INDEX_FILENAME = "INDEX.md"
_ADR_FILENAME_RE = re.compile(r"^(?P<num>\d{3,4})-(?P<slug>.+)\.md$")


class DecisionAggregatorError(RuntimeError):
    """Raised on an unrecoverable aggregation failure."""


def drop_dir(project_root: Path) -> Path:
    """Resolve ``.shipwright/agent_docs/decision-drops/``, git-worktree-aware.

    Symmetric with ``write_decision_drop.drop_dir`` — the producer (iterate
    F3) and the consumer (this aggregator) MUST agree on where the drop
    files live, or aggregation silently misses them. See that function for
    the worktree rationale. ``/shipwright-changelog`` runs the aggregator on
    the main repo, so this resolves to ``project_root`` itself there; the
    worktree-awareness keeps producer/consumer in lock step regardless.
    """
    project_root = Path(project_root)
    root = resolve_main_repo_root(project_root) or project_root
    return root / ".shipwright" / "agent_docs" / DROP_DIRNAME


def _snapshot_drops(dd: Path) -> list[Path]:
    """Deterministically-ordered list of drop files to process.

    Lexicographic sort over ``<run_id>_<NNN>.json`` keeps a run's ADRs in
    counter order and gives a stable batch order across runs. Files starting
    with ``_`` and ``.gitkeep`` are skipped (scaffolding / sentinels).
    """
    if not dd.is_dir():
        return []
    out: list[Path] = []
    for f in sorted(dd.iterdir()):
        if f.suffix != ".json" or f.is_symlink() or not f.is_file():
            continue
        if f.name.startswith("_") or f.name == ".gitkeep":
            continue
        out.append(f)
    return out


def _load_drop(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DecisionAggregatorError(f"{path.name}: not a JSON object")
    for field in _REQUIRED_DROP_FIELDS:
        if not str(data.get(field, "")).strip():
            raise DecisionAggregatorError(
                f"{path.name}: missing required field {field!r}"
            )
    return data


def aggregate(
    project_root: Path | str,
    *,
    dry_run: bool = False,
    lock_timeout_seconds: float = 10.0,
) -> dict:
    """Fold every decision-drop into ``decision_log.md``. Returns a summary."""
    project_root = Path(project_root).resolve()
    # Deliberate asymmetry: ``dd`` (the gitignored decision-drop STAGING dir)
    # is repo-scoped and resolved worktree-aware, exactly like the event log
    # — a drop written from an iterate worktree lives next to the main repo.
    # ``log_path`` (and architecture.md, via _append_architecture_update) is
    # a TRACKED, committed artifact and stays ``project_root``-relative: it
    # belongs to whichever checkout the aggregator is invoked on.
    # ``/shipwright-changelog`` runs the aggregator on the main repo, so the
    # two resolve to the same root in practice — but the distinction is
    # load-bearing if the aggregator is ever invoked elsewhere.
    log_path = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    dd = drop_dir(project_root)

    result: dict = {
        "aggregated": 0,
        "adr_numbers": [],
        "processed": [],
        "errors": [],
        "dry_run": dry_run,
    }

    if not dd.is_dir():
        return result

    with file_lock(str(log_path) + ".lock", timeout_seconds=lock_timeout_seconds):
        # Snapshot under the lock so the whole read-render-write-cleanup
        # transaction is atomic against a concurrent aggregation.
        drops = _snapshot_drops(dd)
        if not drops:
            return result
        content = (
            log_path.read_text(encoding="utf-8")
            if log_path.exists()
            else DECISION_LOG_HEADER
        )
        next_num = get_next_adr_number(content)

        valid: list[tuple[Path, dict]] = []
        for drop_path in drops:
            try:
                valid.append((drop_path, _load_drop(drop_path)))
            except (json.JSONDecodeError, DecisionAggregatorError, OSError) as exc:
                result["errors"].append(f"{drop_path.name}: {exc}")

        rendered: list[str] = []
        for offset, (drop_path, data) in enumerate(valid):
            number = next_num + offset
            commit = (data.get("commit") or "").strip() or "(assigned post-merge)"
            rendered.append(
                format_entry(
                    number,
                    data["section"],
                    commit,
                    data.get("context", ""),
                    data["decision"],
                    data.get("consequences", ""),
                    data.get("rejected", ""),
                    data.get("title", ""),
                    data.get("rationale", ""),
                    entry_date=data.get("date"),
                    run_id=data.get("run_id", ""),
                    spec_ref=data.get("spec_ref", ""),
                )
            )
            result["adr_numbers"].append(number)
            result["processed"].append(drop_path.name)

        if rendered and not dry_run:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(content + "".join(rendered), encoding="utf-8")
            for offset, (drop_path, data) in enumerate(valid):
                impact = data.get("architecture_impact", "none")
                if impact and impact != "none":
                    summary = data.get("title") or data.get("decision", "")[:60]
                    _append_architecture_update(
                        project_root, next_num + offset, impact, summary,
                        entry_date=data.get("date"),
                    )
                try:
                    drop_path.unlink()
                except OSError as exc:
                    result["errors"].append(
                        f"{drop_path.name}: could not delete after aggregation: {exc}"
                    )
            # Rebuild INDEX.md whenever a release pass touches the ADR spec
            # folder — keeps INDEX in lock step with the actual files on disk.
            try:
                rebuild_adr_index(project_root)
            except OSError as exc:
                result["errors"].append(f"INDEX.md: regenerate failed: {exc}")

        result["aggregated"] = len(valid)

    return result


def _adr_spec_folder(project_root: Path) -> Path:
    return project_root / ADR_SPEC_FOLDER


def rebuild_adr_index(project_root: Path) -> Path | None:
    """Regenerate ``.shipwright/planning/adr/INDEX.md`` from the folder.

    Lists every ``<NNN>-<slug>.md`` (or freeform `*.md`) found in the spec
    folder, sorted by numeric prefix when present. No-op when the folder is
    missing — returns ``None`` so callers can keep going.
    """
    folder = _adr_spec_folder(Path(project_root))
    if not folder.is_dir():
        return None
    entries: list[tuple[int, str, str]] = []  # (sort-key, label, href)
    for md in sorted(folder.iterdir()):
        if md.is_symlink() or not md.is_file() or md.suffix.lower() != ".md":
            continue
        if md.name == ADR_INDEX_FILENAME:
            continue
        match = _ADR_FILENAME_RE.match(md.name)
        if match:
            try:
                sort_key = int(match.group("num"))
            except ValueError:
                sort_key = 10**9
            label = f"ADR-{match.group('num')} — {match.group('slug').replace('-', ' ')}"
        else:
            sort_key = 10**9 + 1  # freeform names land at the end
            label = md.stem.replace("-", " ")
        entries.append((sort_key, label, md.name))
    entries.sort(key=lambda row: (row[0], row[1]))

    lines = [
        "# ADR Spec Folder — INDEX",
        "",
        "_Auto-generated by `aggregate_decisions.py`. Do not edit by hand —",
        "regeneration overwrites this file on every release pass._",
        "",
    ]
    if not entries:
        lines += [
            "_No ADR specs yet. Add `.md` files under `"
            f"{ADR_SPEC_FOLDER}/<NNN>-<slug>.md` and re-run "
            "`aggregate_decisions.py`._",
            "",
        ]
    else:
        for _, label, href in entries:
            lines.append(f"- [{label}]({href})")
        lines.append("")
    index_path = folder / ADR_INDEX_FILENAME
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate ADR decision-drops into decision_log.md.",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be aggregated without modifying disk.",
    )
    parser.add_argument("--lock-timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    try:
        summary = aggregate(
            Path(args.project_root),
            dry_run=args.dry_run,
            lock_timeout_seconds=args.lock_timeout,
        )
    except LockTimeout as exc:
        print(f"ERROR: could not lock decision_log.md: {exc}", file=sys.stderr)
        return 1

    prefix = "[dry-run] " if args.dry_run else ""
    if summary["aggregated"]:
        nums = ", ".join(f"ADR-{n:03d}" for n in summary["adr_numbers"])
        print(f"{prefix}aggregated {summary['aggregated']} decision-drop(s): {nums}")
    else:
        print(f"{prefix}no decision-drops to aggregate")
    for err in summary["errors"]:
        print(f"WARNING: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
