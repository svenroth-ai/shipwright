"""The lock writer of a golden-trace freeze (programme P9): ``golden.lock.json`` and ``promise.lock.json``. Stdlib only.

One writer for every plugin that keeps golden traces under ``plugins/<plugin>/tests/golden`` (the plugin is a parameter;
``shipwright-changelog`` is only the default)::

    uv run shared/testkit/golden_lock.py [--plugin NAME | --golden-dir DIR] [--repo-root ROOT] [--spec PATH]
                                         [--check | --promise-only] [--repin]

* ``promise.lock.json`` (``{"version": 1, "promises": {"<path>::<test>": {"acs": [...], "hash": ...}}}``): one entry per
  test of every ``test_promise_*.py`` in the golden dir, built by ``promise_lock.lock_entry`` with the spec's
  ``## AC-Move-Map`` and the golden dir's ``conftest.py`` - the same inputs :func:`promise_lock_problems` checks with.
* ``golden.lock.json`` (``{"version": 1, "files": {"<path>": "<sha256>"}}``): every ``*.trace.json`` under the golden dir,
  every file the freeze test's ``REQUIRED`` tuple names (read from its source, never imported) and the harness
  ``golden_trace.py``. Hashes are ``golden_trace.file_sha256`` (CRLF read as LF); the promise lock is hashed as written.

Both files are written byte-stable (sorted keys, two-space indent, LF, trailing newline). A lock that exists and would
change is refused without ``--repin``: after the freeze a change to a frozen file is an entry in ``approved_deltas.json``
(``golden_trace.freeze_problems`` honours it), a re-pin is a decision. ``--repin`` rewrites both locks from the tree and
so replaces every approved delta: empty ``approved_deltas.json`` in the same change (the report counts the deltas it made
moot). ``--promise-only`` rewrites only ``promise.lock.json`` (a promise test changed on purpose) and prints its sha256
before and after: the values of the approved delta the golden lock then needs for it. ``--check`` writes nothing and
exits 1 unless the freeze holds the way the freeze test reads it: the golden lock names exactly the files it should, every
difference is covered by an approved delta, and the promise lock matches the promise tests.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import golden_trace as gt  # noqa: E402
import promise_hash as ph  # noqa: E402
import promise_lock as pl  # noqa: E402

VERSION = 1
GOLDEN_LOCK, PROMISE_LOCK, DELTAS = "golden.lock.json", "promise.lock.json", "approved_deltas.json"
HARNESS = "shared/testkit/golden_trace.py"
FREEZE_TEST = "test_trace_freeze.py"
PROMISE_GLOB = "test_promise_*.py"
DEFAULT_PLUGIN = "shipwright-changelog"
DEFAULT_SPEC = ".shipwright/planning/01-adopted/spec.md"
TRACE_SUFFIX = ".trace.json"


class LockError(ValueError):
    """The lock cannot be written as asked (a missing file, an unreadable ``REQUIRED``, a re-pin without ``--repin``)."""


def dumps(doc: Mapping[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise LockError(f"{path}: outside the repository {repo_root}") from exc


def required_files(freeze_test: Path) -> list[str]:
    """The paths of the freeze test's module-level ``REQUIRED`` tuple, read from its source (strings, or names of
    module-level string constants such as ``HARNESS``). Anything else is refused: the writer never guesses."""
    body = ast.parse(freeze_test.read_text(encoding="utf-8")).body
    single = [n for n in body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)]
    constants = {n.targets[0].id: n.value.value for n in single  # type: ignore[attr-defined]
                 if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
    if any(isinstance(n, (ast.AnnAssign, ast.AugAssign)) and isinstance(n.target, ast.Name) and n.target.id == "REQUIRED"
           for n in body):
        raise LockError(f"{freeze_test.name}: REQUIRED is annotated or extended; write it as one plain assignment")
    required: list[str] | None = None
    for node in single:
        name, value = node.targets[0].id, node.value  # type: ignore[attr-defined]
        if name == "REQUIRED":
            if not isinstance(value, (ast.Tuple, ast.List)):
                raise LockError(f"{freeze_test.name}: REQUIRED is not a literal tuple or list")
            required = []
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    required.append(elt.value)
                elif isinstance(elt, ast.Name) and elt.id in constants:
                    required.append(constants[elt.id])
                else:
                    raise LockError(f"{freeze_test.name}:{elt.lineno}: a REQUIRED element that is not a string literal or constant")
    if required is None:
        raise LockError(f"{freeze_test.name}: no module-level REQUIRED")
    return required


def promise_inputs(repo_root: Path, golden_dir: Path, spec: Path | None) -> tuple[dict[str, str], list[str], str]:
    """``({path: source}, [conftest source], spec text)``: what a promise entry is computed from, for writer and check alike."""
    sources = {_rel(p, repo_root): p.read_text(encoding="utf-8") for p in sorted(golden_dir.glob(PROMISE_GLOB))}
    conftest = golden_dir / "conftest.py"
    conftests = [conftest.read_text(encoding="utf-8")] if conftest.is_file() else []
    spec_text = spec.read_text(encoding="utf-8") if spec is not None and spec.is_file() else ""
    return sources, conftests, spec_text


def promise_doc(repo_root: Path, golden_dir: Path, spec: Path | None) -> dict[str, Any]:
    sources, conftests, spec_text = promise_inputs(repo_root, golden_dir, spec)
    entries: dict[str, Any] = {}
    for path, source in sources.items():
        for name in ph.tests_in(source):
            entries[pl.lock_key(path, name)] = pl.lock_entry(name, source, spec_text, conftests)
    return {"version": VERSION, "promises": entries}


def promise_lock_problems(repo_root: Path, golden_dir: Path, spec: Path | None) -> list[str]:
    """Everything wrong with ``promise.lock.json`` against the promise tests as they stand; ``[]`` when it holds."""
    path = golden_dir / PROMISE_LOCK
    if not path.is_file():
        return [f"{_rel(path, repo_root)}: the promise lock is missing"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("version") != VERSION or not isinstance(doc.get("promises"), dict):
        return [f"{_rel(path, repo_root)}: not a version-{VERSION} promise lock"]
    sources, conftests, spec_text = promise_inputs(repo_root, golden_dir, spec)
    return pl.lock_problems(doc["promises"], sources, conftests, spec_text)


def freeze_problems(repo_root: Path, golden_dir: Path, freeze_test: Path, spec: Path | None) -> list[str]:
    """Why the freeze does NOT hold, read the way the freeze test reads it (approved deltas honoured); ``[]`` when it does."""
    lock_path, deltas_path = golden_dir / GOLDEN_LOCK, golden_dir / DELTAS
    if not lock_path.is_file():
        return [f"{_rel(lock_path, repo_root)}: the golden lock is missing"]
    lock = json.loads(lock_path.read_text(encoding="utf-8")).get("files", {})
    deltas = json.loads(deltas_path.read_text(encoding="utf-8")) if deltas_path.is_file() else []
    wanted = set(golden_files(repo_root, golden_dir, freeze_test))
    problems = [f"{rel}: should be in the golden lock and is not" for rel in sorted(wanted - set(lock))]
    problems += [f"{rel}: in the golden lock but no longer named for it" for rel in sorted(set(lock) - wanted)]
    return problems + gt.freeze_problems(repo_root, lock, deltas) + promise_lock_problems(repo_root, golden_dir, spec)


def golden_files(repo_root: Path, golden_dir: Path, freeze_test: Path) -> list[str]:
    traces = [_rel(p, repo_root) for p in golden_dir.rglob(f"*{TRACE_SUFFIX}")]
    return sorted({*traces, *required_files(freeze_test), HARNESS})


def golden_doc(repo_root: Path, files: Sequence[str], overrides: Mapping[str, bytes] | None = None) -> dict[str, Any]:
    """``overrides``: bytes a file is about to have (the promise lock, hashed before it is written)."""
    hashes: dict[str, str] = {}
    overrides = overrides or {}
    for rel in files:
        if rel in overrides:
            hashes[rel] = _sha(overrides[rel])
        elif (repo_root / rel).is_file():
            hashes[rel] = gt.file_sha256(repo_root / rel)
        else:
            raise LockError(f"{rel}: named for the lock but missing")
    return {"version": VERSION, "files": hashes}


def plan(repo_root: Path, golden_dir: Path, freeze_test: Path, spec: Path | None) -> dict[Path, bytes]:
    """The two files and the bytes they would get, promise lock first (the golden lock hashes it)."""
    promise_path = golden_dir / PROMISE_LOCK
    promise_bytes = dumps(promise_doc(repo_root, golden_dir, spec)).encode("utf-8")
    files = golden_files(repo_root, golden_dir, freeze_test)
    golden = golden_doc(repo_root, files, {_rel(promise_path, repo_root): promise_bytes})
    return {promise_path: promise_bytes, golden_dir / GOLDEN_LOCK: dumps(golden).encode("utf-8")}


def stale(planned: Mapping[Path, bytes]) -> list[Path]:
    """The planned files whose bytes on disk (CRLF read as LF) differ; a missing file is stale."""
    return [p for p, data in planned.items()
            if not p.is_file() or p.read_bytes().replace(b"\r\n", b"\n") != data]


def write(repo_root: Path, golden_dir: Path, freeze_test: Path, spec: Path | None, *, repin: bool = False,
          promise_only: bool = False, planned: Mapping[Path, bytes] | None = None) -> list[Path]:
    """Write the locks (only the promise lock with ``promise_only``); returns the files written. Refuses, writing
    nothing, to change an existing lock without ``repin``. ``planned``: a :func:`plan` result already computed."""
    planned = dict(planned if planned is not None else plan(repo_root, golden_dir, freeze_test, spec))
    if promise_only:
        planned = {p: data for p, data in planned.items() if p.name == PROMISE_LOCK}
    changed = stale(planned)
    existing = [p for p in changed if p.is_file()]
    if existing and not repin:
        raise LockError(f"{', '.join(p.name for p in existing)}: exists and would change; after the freeze a change is an "
                        "approved delta - pass --repin only for a decided re-pin")
    for path in changed:
        path.write_bytes(planned[path])
    return changed


def _args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write (or --check) a plugin's golden.lock.json and promise.lock.json.")
    parser.add_argument("--plugin", default=DEFAULT_PLUGIN, help="plugins/<plugin>/tests/golden (default: %(default)s)")
    parser.add_argument("--golden-dir", type=Path, help="the golden dir itself, relative to the repo root (overrides --plugin)")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="the spec with the AC-Move-Map, relative to the repo root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="write nothing; exit 1 unless the freeze holds")
    mode.add_argument("--promise-only", action="store_true", help="rewrite only promise.lock.json (needs --repin once it exists)")
    parser.add_argument("--repin", action="store_true", help="allow changing an existing lock (a decision, not a fix)")
    return parser.parse_args(argv)


def _written_report(root: Path, golden: Path, planned: Mapping[Path, bytes], before: Mapping[Path, str],
                    written: Sequence[Path], promise_only: bool, old: Mapping[str, str]) -> dict[str, Any]:
    """``old``: the golden lock's entries before the write. A re-pin lists every entry it added, removed or changed,
    so a reviewer sees whether it moved more than the files the change declares."""
    deltas, promise = golden / DELTAS, golden / PROMISE_LOCK
    repinned_golden = any(p.name == GOLDEN_LOCK and p in before for p in written)
    moot = len(json.loads(deltas.read_text(encoding="utf-8"))) if repinned_golden and deltas.is_file() else 0
    files = json.loads(planned[golden / GOLDEN_LOCK])["files"]
    report: dict[str, Any] = {"status": "ok", "written": [_rel(p, root) for p in written],
                              "repinned": [_rel(p, root) for p in written if p in before], "deltas_made_moot": moot,
                              "files": len(files), "traces": sum(1 for f in files if f.endswith(TRACE_SUFFIX)),
                              "promises": len(json.loads(planned[promise])["promises"])}
    if repinned_golden:
        report["entries"] = {"added": sorted(set(files) - set(old)), "removed": sorted(set(old) - set(files)),
                             "changed": sorted(r for r in set(files) & set(old) if files[r] != old[r])}
    if promise_only:  # the delta's "before" is what the golden lock holds, which is not the file once a delta exists
        locked = old.get(_rel(promise, root), before.get(promise))
        report["promise_lock_sha256"] = {"before": locked, "after": _sha(planned[promise])}
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = _args(argv)
    root = args.repo_root.resolve()
    golden = (root / args.golden_dir if args.golden_dir else root / "plugins" / args.plugin / "tests" / "golden").resolve()
    spec, freeze_test = root / args.spec, golden / FREEZE_TEST
    try:
        if not golden.is_dir():
            raise LockError(f"{golden}: no golden dir")
        if not spec.is_file():
            raise LockError(f"{spec}: no spec (the AC-Move-Map is read from it; pass --spec)")
        if args.check:
            problems = freeze_problems(root, golden, freeze_test, spec)
            report: dict[str, Any] = {"status": "stale" if problems else "ok", "problems": problems}
        else:
            planned = plan(root, golden, freeze_test, spec)
            before = {p: _sha(p.read_bytes()) for p in planned if p.is_file()}
            lock = golden / GOLDEN_LOCK
            old = json.loads(lock.read_text(encoding="utf-8")).get("files", {}) if lock.is_file() else {}
            written = write(root, golden, freeze_test, spec, repin=args.repin, promise_only=args.promise_only, planned=planned)
            report = _written_report(root, golden, planned, before, written, args.promise_only, old)
    except (ValueError, OSError, SyntaxError) as exc:  # LockError, a promise test without covers ids, a file not in utf-8
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    report["golden_dir"] = _rel(golden, root)
    print(json.dumps(report, sort_keys=True))
    return 1 if report["status"] == "stale" else 0


if __name__ == "__main__":
    sys.exit(main())
