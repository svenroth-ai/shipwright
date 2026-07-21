"""Collect one import realm's behaviour. Runs INSIDE a subprocess.

Invoked by ``collect.py`` as::

    python _collect_realm.py --realm <name> --repo-root <path> --out <json>

Why a subprocess: ``scripts`` and ``lib`` are ambiguous top-level package names
here, and importing ``group_i`` reorders ``sys.path`` and evicts
``sys.modules['tools']`` at module level. Enforcing an import ORDER inside one
process is not enough -- pytest may collect another module that imports a
target first. A process boundary is the only containment that actually holds.

The serialization deliberately records MORE than values. If the golden file
only held normalized value payloads, S2 could change a target's return type,
its laziness, its ordering, or its exception behaviour and the matrix would
still pass -- which would make this harness worse than useless, because it
would certify a change it cannot see.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import inspect
import json
import sys
import tempfile
from pathlib import Path

_PKG_PARENT = str(Path(__file__).resolve().parent.parent)
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from requirements_corpus.corpus import materialize  # noqa: E402
from requirements_corpus.corpus_data import FIXTURE_NAMES  # noqa: E402
from requirements_corpus._serialize import _record, _spec_files  # noqa: E402
from requirements_corpus.registry import REALMS, targets_for_realm  # noqa: E402

def _load(target: dict, repo_root: Path):
    """Return the callable for *target*, honouring its realm's import style."""
    style = REALMS[target["realm"]]["style"]
    mod_ref = target["module"]
    if style == "by_path":
        plugin_root = repo_root / _PLUGIN_DIR[target["realm"]]
        path = plugin_root / "scripts" / mod_ref
        name = "_swc_" + mod_ref.replace("/", "_").replace("-", "_").removesuffix(".py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    else:
        # `mod_ref` is target["module"], and every target is a literal row in
        # requirements_corpus/registry.py — the registry is a static table, not
        # loaded from disk, env or argv, so no caller-supplied name reaches here.
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        module = importlib.import_module(mod_ref)
    return getattr(module, target["attr"])


_PLUGIN_DIR = {
    "adopt": "plugins/shipwright-adopt",
    "design": "plugins/shipwright-design",
}


def _invoke(fn, target: dict, root: Path):
    """Call *fn* per its calling convention against materialized *root*."""
    conv = target["invoke"]
    if conv == "project_root":
        return fn(root)
    if conv == "planning_dir":
        return fn(root / ".shipwright" / "planning")
    if conv == "project_root_include_retired":
        return fn(root, include_retired=True)
    raise AssertionError(f"parser convention {conv!r} is driven by _parser_cells")


def _parser_cells(fn, target: dict, root: Path) -> dict:
    """Drive a parser over every spec file the fixture contains."""
    conv = target["invoke"]
    if conv == "project_root":  # rtm walks itself
        return _record(lambda: fn(root), root, target)
    out = {}
    for spec in _spec_files(root):
        rel = spec.relative_to(root).as_posix()
        split = spec.parent.name
        text = spec.read_text(encoding="utf-8")
        if conv == "text":
            call = lambda t=text: fn(t)  # noqa: E731
        elif conv == "text_split":
            call = lambda t=text, s=split, r=rel: fn(t, s, r)  # noqa: E731
        elif conv == "text_kw":
            # No `namespace=`: manifest v3 derives it from each row's FR id, so the
            # split directory is no longer an input to the parser (campaign S3).
            call = lambda t=text, r=rel: fn(t, spec_path=r)  # noqa: E731
        elif conv == "path_split":
            call = lambda p=spec, s=split, r=rel: fn(p, s, r)  # noqa: E731
        else:
            raise AssertionError(f"unknown parser convention {conv!r}")
        out[rel] = _record(call, root, target)
    return {"per_spec": out}


def collect(realm: str, repo_root: Path) -> dict:
    for rel in REALMS[realm]["paths"]:
        p = str(repo_root / rel)
        if p not in sys.path:
            sys.path.insert(0, p)

    results: dict[str, dict] = {}
    for target in targets_for_realm(realm):
        tid = target["id"]
        if target["invoke"] == "source_only":
            # Freeze the enclosing function's SOURCE. The previous version
            # recorded a bare {"kind": "source_only"} constant, which froze
            # nothing at all while the registry claimed a source-level
            # guarantee -- so 1 of the 15 walks was unpinned and the harness
            # said otherwise. Hashing the function body makes any edit to it a
            # golden diff the S2 reviewer has to explain, which is what the
            # claim always meant. (Caught in adversarial review.)
            try:
                fn = _load(target, repo_root)
                src = inspect.getsource(fn)
            except Exception as exc:  # noqa: BLE001
                results[tid] = {"kind": "source_error",
                                "exception": type(exc).__name__}
                continue
            results[tid] = {
                "kind": "source_only",
                "sha256": hashlib.sha256(src.encode("utf-8")).hexdigest(),
                "source_lines": len(src.splitlines()),
            }
            continue
        try:
            fn = _load(target, repo_root)
        except Exception as exc:  # noqa: BLE001
            results[tid] = {"kind": "import_error",
                            "exception": type(exc).__name__, "message": str(exc)[:200]}
            continue
        per_fixture = {}
        for fixture in FIXTURE_NAMES:
            with tempfile.TemporaryDirectory(prefix="swcorpus-") as tmp:
                root = materialize(fixture, Path(tmp) / "project")
                if tid.startswith("parse."):
                    per_fixture[fixture] = _parser_cells(fn, target, root)
                else:
                    per_fixture[fixture] = _record(
                        lambda f=fn, t=target, r=root: _invoke(f, t, r),
                        root, target,
                    )
        results[tid] = {"kind": "invoked", "fixtures": per_fixture}
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--realm", required=True)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    data = collect(args.realm, Path(args.repo_root))
    Path(args.out).write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
