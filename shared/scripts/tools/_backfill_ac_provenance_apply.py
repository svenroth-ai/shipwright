"""The WRITE half of ``backfill_ac_provenance.py`` — split out the moment the
combined file crossed the 300-LOC bloat-baseline threshold (same precedent as
``_layer_coverage_binding.py`` / ``_backfill_title_sim.py``: the caller stays
the derive/CLI half, this module is the apply/validate half, and only the
caller imports it, never the other way round).

Owns: writing an AC-scoped tag into a candidate file (upgrade a bare tag, or
insert a brand-new decorator on a wholly-untagged test), and the post-write
guard that every tag just written resolves against the CURRENTLY minted
spec.md (external plan review, P3.4, glm medium — "never trust that
derive-time and apply-time agree").
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from ac_identity import read_all  # noqa: E402
from backfill_write import apply_writes  # noqa: E402
from fr_tag_grammar import parse_source  # noqa: E402


class _Candidate:
    """Minimal stand-in for ``backfill_signals.Candidate`` — ``apply_writes``
    only ever reads ``.fr`` off the second element of a write pair."""

    def __init__(self, fr: str) -> None:
        self.fr = fr


class _Record:
    """Minimal stand-in for ``backfill_scan.TestRecord`` — ``apply_writes``
    only ever reads ``.rel_path``/``.decl_line``/``.indent`` off the first
    element of a write pair; ``test_id`` is carried for this tool's own report."""

    def __init__(self, test_id: str, rel_path: str, decl_line: int, indent: int) -> None:
        self.test_id = test_id
        self.rel_path = rel_path
        self.decl_line = decl_line
        self.indent = indent


def _enumerate_python_tests(source: str) -> list[tuple[str, int, int]]:
    """``(name, decl_line, indent)`` for every ``test*`` function — the Python
    half of ``backfill_scan._enumerate``, kept local so this tool depends on
    the shared engine's WRITER (``backfill_write``) but not its private
    filesystem-scan internals."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [
        (n.name, n.lineno - 1, n.col_offset)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")
    ]


def _covers_pattern(fr_id: str) -> re.Pattern:
    return re.compile(r'covers\(\s*(["\'])' + re.escape(fr_id) + r"\1")


#: A line that IS an ``@pytest.mark.covers(...)`` decorator, nothing else on it
#: (its own indentation and an optional trailing carriage return are the only
#: thing allowed around it) -- external code review (P3.4, openai high): a raw
#: whole-file regex substitution would also rewrite the same-looking text
#: inside a docstring, a comment, an assertion literal, or a fixture string.
#: Scoping the substitution to a line that IS this decorator (never a string
#: that merely CONTAINS the pattern) closes that gap without needing a full
#: AST rewrite.
_DECORATOR_LINE_RE = re.compile(r"^\s*@pytest\.mark\.covers\(.*\)\s*$")


def _upgrade_bare_tags(text: str, fr_id: str, ac_id: str) -> tuple[str, int]:
    """Widen an already-bare ``covers("<fr_id>")`` to name ``ac_id`` -- ONLY on a
    line that is itself a ``@pytest.mark.covers(...)`` decorator, never a
    same-looking occurrence anywhere else in the file's text."""
    pattern = _covers_pattern(fr_id)
    lines = text.split("\n")
    count = 0
    for i, line in enumerate(lines):
        if not _DECORATOR_LINE_RE.match(line):
            continue
        new_line, n = pattern.subn(f'covers("{fr_id}/{ac_id}"', line)
        if n:
            lines[i] = new_line
            count += n
    return "\n".join(lines), count


def apply_upgrades(project_root: Path, report: dict) -> dict:
    """Write every ``candidate`` entry's tests: upgrade an existing bare tag for
    the SAME fr_id, or insert a brand-new AC-scoped tag on a wholly-untagged
    test. Non-Python files and a test already carrying some OTHER tag are
    reported, never guessed at."""
    skipped: list[dict] = []
    upgraded: list[dict] = []
    writes: list[tuple[_Record, _Candidate]] = []
    write_meta: list[dict] = []
    for cand in report["candidates"]:
        if cand["status"] != "candidate":
            continue
        token = f'{cand["fr_id"]}/{cand["ac_id"]}'
        for rel in cand["test_files"]:
            abs_path = project_root / rel
            if not rel.endswith(".py"):
                skipped.append({**cand, "file": rel, "reason": "non_python_writer_not_built"})
                continue
            if not abs_path.is_file():
                skipped.append({**cand, "file": rel, "reason": "file_absent_at_head"})
                continue
            try:
                # Read RAW bytes (not read_text): universal-newline mode would
                # strip \r\n, so the CRLF detection below would be dead on
                # every platform (doubt-review, P3.4 — same discipline as
                # backfill_write.apply_writes).
                raw = abs_path.read_bytes()
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                skipped.append({**cand, "file": rel, "reason": "unreadable"})
                continue
            newline = "\r\n" if "\r\n" in text else "\n"
            new_text, count = _upgrade_bare_tags(text, cand["fr_id"], cand["ac_id"])
            if count:
                lines = new_text.split("\n")
                # _upgrade_bare_tags split on bare "\n": a CRLF source leaves a
                # trailing "\r" on every line, so re-join with the DETECTED
                # newline only after stripping that artifact back out.
                if newline == "\r\n":
                    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in lines]
                abs_path.write_bytes(newline.join(lines).encode("utf-8"))
                upgraded.append({
                    "file": rel, "fr_id": cand["fr_id"], "ac_id": cand["ac_id"],
                    "slug": cand["slug"], "commit": cand["commit"], "tags_upgraded": count,
                })
                continue
            # No bare tag to widen — offer every WHOLLY UNTAGGED test in the file
            # as a new-tag insertion candidate (re-read: the upgrade pass above
            # never touches this file, so `text` is still current).
            existing = {h.test for h in parse_source(rel, text).hits}
            for name, decl_line, indent in _enumerate_python_tests(text):
                test_id = f"{rel}::{name}"
                if test_id in existing:
                    continue  # already tagged for something else — never guessed
                writes.append((_Record(test_id, rel, decl_line, indent), _Candidate(token)))
                write_meta.append({
                    "test": test_id, "fr_id": cand["fr_id"], "ac_id": cand["ac_id"],
                    "slug": cand["slug"], "commit": cand["commit"],
                })
    # Dedupe by test_id (doubt-review, P3.4): two candidates naming the SAME
    # (fr_id, ac_id) pair via different commits (e.g. a file removed and
    # re-added) are not caught by the multiply-claimed-file check above, which
    # keys on (fr_id, ac_id) collisions across DIFFERENT pairs — an identical
    # pair from two commits would otherwise double-decorate every test in the
    # file. First candidate wins; the rest are reported, never silently merged.
    seen_ids: set[str] = set()
    deduped_writes: list[tuple[_Record, _Candidate]] = []
    deduped_meta: list[dict] = []
    for (record, cand), meta in zip(writes, write_meta):
        if record.test_id in seen_ids:
            skipped.append({"file": record.rel_path, "fr_id": meta["fr_id"],
                             "reason": "duplicate_candidate_same_test"})
            continue
        seen_ids.add(record.test_id)
        deduped_writes.append((record, cand))
        deduped_meta.append(meta)
    writes, write_meta = deduped_writes, deduped_meta
    written, write_failures = apply_writes(project_root, writes) if writes else ([], [])
    written_ids = {r.test_id for r, _c in written}
    inserted = [m for m in write_meta if m["test"] in written_ids]
    for f in write_failures:
        skipped.append({"file": f["test"].split("::")[0], "fr_id": f["fr"].split("/")[0],
                         "reason": f["reason"]})
    return {
        "upgraded_bare_tags": upgraded,
        "inserted_new_tags": inserted,
        "skipped": skipped,
        "tags_upgraded_total": sum(a["tags_upgraded"] for a in upgraded),
        "tags_inserted_total": len(inserted),
    }


def validate_applied(project_root: Path, apply_result: dict, spec_path: Path) -> list[str]:
    """Post-write guard (external plan review, P3.4, glm medium): every
    ``(fr_id, ac_id)`` this run just wrote must resolve against the CURRENT
    minted spec.md — never trust that derive-time and apply-time agree. Returns
    the ``fr_id/ac_id`` strings that do NOT resolve, i.e. an orphan tag was just
    written; empty means every write is backed by a real, currently-minted AC."""
    content = spec_path.read_text(encoding="utf-8")
    minted = read_all(content)
    valid_pairs = {(fr_id, ac_id) for fr_id, pairs in minted.items() for ac_id, _ in pairs if ac_id}
    written = {
        (a["fr_id"], a["ac_id"])
        for a in apply_result.get("upgraded_bare_tags", []) + apply_result.get("inserted_new_tags", [])
    }
    return sorted(f"{fr_id}/{ac_id}" for fr_id, ac_id in written if (fr_id, ac_id) not in valid_pairs)


__all__ = ["apply_upgrades", "validate_applied"]
