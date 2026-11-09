"""Cut one requirement (FR) into several, with a hard conservation check (atomic-frs U2).

    uv run shared/scripts/tools/fr_split.py --project-root . --grouping cut.json            # DRY RUN: diff + checks, writes nothing
    uv run shared/scripts/tools/fr_split.py --project-root . --grouping cut.json --apply    # writes, re-checks, restores on failure

``cut.json`` is the grouping (``lib.fr_split_spec``): ``{"source": "FR-01.11", "parts": [{"title", "description", "acs": [21, 22, 23]}],
"remaining": {"title", "description"}}``. Code proposes the seams (``fr_cluster_report.py``), the AI proposes ONE grouping, the operator
confirms it; this tool performs the cut. It MOVES criteria, never rewords or renumbers one (``AC21`` stays ``AC21``), re-points the
test tags that bind them, records every move in the spec's ``## AC-Move-Map`` and in the AC-coverage baseline.

Hard checks (any failure: exit 1, nothing written, or on ``--apply`` every file restored): each criterion exactly once with unchanged
text, test binding identical under the new ids, no test still naming an old id, the regenerated traceability manifest binds the same
tests, new names pass the Group I1 fence, no test names criteria of two parts (``--allow-shared-tests`` overrides, logged).
Exit codes: 0 ok, 1 a check failed, 2 unusable input. The regenerated manifest is restored to its committed bytes unless ``--keep-manifest``.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_catalog import parse_catalog  # noqa: E402
from lib.fr_cluster_evidence import _bindings, _read, _walk, collect_evidence, is_test_file  # noqa: E402
from lib.fr_split_check import check_bindings, check_catalog, check_manifest, check_names, coupling, dirty_targets, dotted  # noqa: E402
from lib.fr_split_report import origin_numbers, origin_readable, report  # noqa: E402
from lib.fr_split_spec import SplitError, split_spec, taken_fr_numbers  # noqa: E402
from lib.fr_split_tags import rewrite_tags  # noqa: E402

BASELINE = "shipwright_ac_coverage_baseline.json"
MANIFEST = ".shipwright/compliance/test-traceability.json"
REGISTRY = "shipwright_ac_registry.json"
NL = chr(10)
_BASELINE_ITEM = re.compile(r'^(\s*)"(FR-\d+\.\d+/AC\d+)"(,?)(\r?)$')
_REGEN = ("import sys\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\n"
          "from scripts.lib.collectors.test_links import generate_file\ngenerate_file(Path(sys.argv[2]))\n")


def _spec_files(root: Path) -> list[Path]:
    return sorted((root / ".shipwright" / "planning").glob("*/spec.md"))


def _read_text(p: Path) -> str:
    return p.read_bytes().decode("utf-8")


def _write(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))


def _diff(rel: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}", n=1))


def _baseline(root: Path, moves: dict[str, str]) -> tuple[str, str] | None:
    """The AC-coverage baseline with moved ids renamed IN PLACE (line edit: indentation, line endings and the rest stay byte-identical)."""
    p = root / BASELINE
    if not p.is_file():
        return None
    old = _read_text(p)
    lines = old.split(NL)
    idx = [i for i, ln in enumerate(lines) if _BASELINE_ITEM.match(ln)]
    if not idx or idx != list(range(idx[0], idx[0] + len(idx))):
        return None
    ids = [_BASELINE_ITEM.match(lines[i]).group(2) for i in idx]  # type: ignore[union-attr]
    mapped = [moves.get(x, x) for x in ids]
    if mapped == ids:
        return None
    if ids == sorted(ids):
        mapped = sorted(set(mapped))
    first = _BASELINE_ITEM.match(lines[idx[0]])
    cr = first.group(4)  # type: ignore[union-attr]
    for k, i in enumerate(idx[:len(mapped)]):
        lines[i] = first.group(1) + '"' + mapped[k] + '"' + ("" if k == len(mapped) - 1 else ",") + cr  # type: ignore[union-attr]
    del lines[idx[0] + len(mapped):idx[-1] + 1]
    return old, NL.join(lines)


def _registry(root: Path, old_acs: dict[str, str], src: str, moves: dict[str, str]) -> tuple[str, str]:
    """The AC-number registry with the high-water mark of the source (as it was BEFORE the cut) and of every new FR, so the minter can
    never hand out a number again that has moved away: ``FR-01.11/AC48`` must stay retired when AC48 became ``FR-01.22/AC48``."""
    p = root / REGISTRY
    old = _read_text(p) if p.is_file() else ""
    data = json.loads(old) if old.strip() else {}
    top: dict[str, int] = {}
    for key in old_acs:
        fr, n = key.rsplit(".AC", 1)
        if fr == src:
            top[fr] = max(top.get(fr, 0), int(n))
    for new in moves.values():
        fr, n = new.split("/AC")
        top[fr] = max(top.get(fr, 0), int(n))
    for fr, n in top.items():
        data[fr] = max(int(data.get(fr, 0)), n)
    eol = chr(13) + chr(10) if chr(13) in old else NL
    return old, json.dumps(dict(sorted(data.items())), indent=2).replace(NL, eol) + eol


def _regenerate_manifest(root: Path) -> dict:
    plugin = root / "plugins" / "shipwright-compliance"
    if not plugin.is_dir():  # another repo: use the compliance plugin that ships next to this tool
        plugin = _SCRIPTS_ROOT.parents[1] / "plugins" / "shipwright-compliance"
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp, "regen.py")
        script.write_text(_REGEN, encoding="utf-8")
        proc = subprocess.run(["uv", "run", "--project", str(plugin), "python", str(script), str(plugin), str(root)],
                              cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"manifest regeneration failed: {proc.stderr.strip()[-600:]}")
    return json.loads(_read_text(root / MANIFEST))


def plan(root: Path, grouping: dict, allow_shared: bool = False) -> dict:
    """Everything a run would do, without touching disk: ``{"files": {rel: (old, new)}, "problems", "notes", "moves", "new_ids"}``."""
    src = grouping.get("source", "")
    specs = {p: _read_text(p) for p in _spec_files(root)}
    heading = re.compile(rf"^#{{2,4}}\s+{re.escape(src)}\b", re.M)
    holder = next((p for p, t in specs.items() if heading.search(t)), None)
    if holder is None:
        raise SplitError(f"no spec.md under .shipwright/planning has a section for {src}")
    reg = _read_text(root / REGISTRY) if (root / REGISTRY).is_file() else ""  # a number that ever had minted criteria is never reused
    taken = {int(m) for m in re.findall(rf'"FR-{src[3:5]}\.(\d+)"', reg)}
    for t in specs.values():
        taken |= taken_fr_numbers(t, src[3:5])
    taken |= origin_numbers(root, [p.relative_to(root).as_posix() for p in specs], src[3:5])  # a number a parallel iterate already took on main
    old_spec = specs[holder]
    new_spec, moves, new_ids = split_spec(old_spec, grouping, taken)
    rel_spec = holder.relative_to(root).as_posix()
    files: dict[str, tuple[str, str]] = {rel_spec: (old_spec, new_spec)}

    tests, srcs = collect_evidence(root)
    new_tests = {ac: set(ts) for ac, ts in tests.items()}
    changed = 0
    not_utf8: list[str] = []
    mentions: list[str] = []
    fr_level: list[str] = []  # tests tagged with the bare source FR: they stay on it
    for rel in _walk(root):
        if not is_test_file(rel):
            continue
        if src not in _read(root / rel):
            continue
        try:
            text = _read_text(root / rel)  # the exact bytes: the rewrite keeps line endings, the restore needs them
            if re.search(rf"""["']{re.escape(src)}["']""", text):
                fr_level.append(rel)
        except UnicodeDecodeError:
            not_utf8.append(rel)  # the evidence reader decodes leniently, so it may bind here; this tool cannot rewrite it safely
            continue
        new = rewrite_tags(rel, text, moves)
        if any(o in new or dotted(o) in new for o in moves):
            mentions.append(rel)  # the old id is still quoted outside a tag (a string, a docstring)
        if new == text:
            continue
        changed += 1
        files[rel] = (text, new)
        for ac in list(new_tests):
            new_tests[ac] = {t for t in new_tests[ac] if not t.startswith(f"{rel}::")}
        for ac, ids in _bindings(rel, new).items():
            new_tests.setdefault(ac, set()).update(ids)
    new_tests = {ac: ts for ac, ts in new_tests.items() if ts}
    base = _baseline(root, moves)
    notes_extra: list[str] = []
    if base and base[0] != base[1]:
        files[BASELINE] = base
    elif (root / BASELINE).is_file() and any(f'"{o}"' in _read_text(root / BASELINE) for o in moves):
        notes_extra.append(f"{BASELINE} names moved criteria but its id list is not one block; rename them by hand")
    reg = _registry(root, parse_catalog(old_spec)[0], src, moves)
    if reg[0] != reg[1]:
        files[REGISTRY] = reg
    if not (root / MANIFEST).is_file():
        notes_extra.append("no committed traceability manifest: the manifest binding is not re-checked")
    if mentions:
        notes_extra.append(f"{len(mentions)} test file(s) still quote a moved id outside a tag (check they do not look it up): {', '.join(mentions[:3])}")

    problems = check_catalog(old_spec, new_spec, moves, new_ids) + check_bindings(tests, new_tests, moves)
    problems += [f"{rel} is not UTF-8 and names {src}; re-save it as UTF-8 so its tags can be re-pointed" for rel in not_utf8]
    parts = grouping["parts"]
    problems += check_names(parts, grouping.get("remaining"))
    kept = sorted(a for a in parse_catalog(old_spec)[0] if a.rsplit(".AC", 1)[0] == src)
    labels = {f"{fr} {p['title']}": [f"{src}.AC{int(a):02d}" for a in p["acs"]] for fr, p in zip(new_ids, parts)}
    moved = {dotted(o) for o in moves}
    labels[f"{src} (stays)"] = [a for a in kept if a not in moved]
    shared_problems, notes = coupling(labels, tests, srcs)
    notes.extend(notes_extra)
    (notes if allow_shared else problems).extend(f"{x}{' (allowed)' if allow_shared else ''}" for x in shared_problems)
    return {"files": files, "problems": problems, "notes": notes, "moves": moves, "new_ids": new_ids, "tag_files": changed, "fr_level_tags": fr_level, "origin_ref": origin_readable(root)}


def apply(root: Path, result: dict) -> list[str]:
    """Write every file, regenerate and compare the manifest; on ANY failure restore the original bytes. Returns the problems."""
    originals = {rel: old for rel, (old, _new) in result["files"].items()}
    created = {rel for rel in originals if not (root / rel).is_file()}  # files this run brings into being: a restore removes them again
    manifest_path = root / MANIFEST
    manifest_bytes = manifest_path.read_bytes() if manifest_path.is_file() else None
    interrupted: KeyboardInterrupt | SystemExit | None = None
    wrote = False
    try:
        # The committed manifest may already lag the code, so it is no baseline: regenerate it BEFORE the cut and AFTER, compare those.
        before = _regenerate_manifest(root) if manifest_bytes is not None else None
        stale = [rel for rel, old in originals.items() if not (root / rel).is_file() and old or (root / rel).is_file() and _read_text(root / rel) != old]
        if stale:  # something edited a target while the baseline regeneration ran: never write over it
            raise RuntimeError(f"{stale[0]} changed after the plan was made; nothing was written, run again")
        backup = Path(tempfile.mkdtemp(prefix="fr_split-backup-"))
        for rel, old in originals.items():
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            _write(backup / rel, old)
        result["backup"] = str(backup)
        wrote = True
        for rel, (_old, new) in result["files"].items():
            _write(root / rel, new)
        problems = check_manifest(before, _regenerate_manifest(root), result["moves"]) if before is not None else []
    except Exception as exc:  # noqa: BLE001 - any failure while writing must leave the tree as it was
        problems = [f"apply failed: {exc}"]
    except (KeyboardInterrupt, SystemExit) as exc:  # Ctrl-C during the long regeneration: restore first, then let it go on
        problems, interrupted = [f"apply interrupted: {type(exc).__name__}"], exc
    if (problems or not result.get("keep_manifest")) and manifest_bytes is not None:
        try:
            manifest_path.write_bytes(manifest_bytes)
        except OSError as exc:
            problems.append(f"could not restore {MANIFEST}: {exc}")
    if problems and wrote:
        for rel, old in originals.items():  # best effort per file: one failure must not stop the others
            try:
                if rel in created:
                    (root / rel).unlink(missing_ok=True)
                else:
                    _write(root / rel, old)
            except OSError as exc:
                problems.append(f"could not restore {rel}: {exc}")
    if interrupted is not None:
        raise interrupted
    if not problems and wrote:
        shutil.rmtree(result["backup"], ignore_errors=True)
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--grouping", required=True, help="JSON file with the grouping")
    ap.add_argument("--apply", action="store_true", help="write the cut (default: dry run)")
    ap.add_argument("--keep-manifest", action="store_true", help="keep the regenerated traceability manifest (default: restore the committed bytes)")
    ap.add_argument("--allow-shared-tests", action="store_true", help="a test naming criteria of two parts is reported, not refused")
    ap.add_argument("--allow-dirty", action="store_true", help="write even when a target file has uncommitted changes")
    ap.add_argument("--no-diff", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        grouping = json.loads(Path(args.grouping).read_text(encoding="utf-8"))
        result = plan(root, grouping, args.allow_shared_tests)
    except (SplitError, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:  # any unusable input: exit 2, never 1
        print(f"fr_split: cannot cut: {exc}", file=sys.stderr)
        return 2
    print(report(root, grouping, result))
    if not args.no_diff:
        for rel, (old, new) in result["files"].items():
            print(_diff(rel, old, new), end="")
    if result["problems"]:
        return 1
    if not args.apply:
        print("\nDry run: nothing written. Re-run with --apply after the operator confirms the cuts.")
        return 0
    result["keep_manifest"] = args.keep_manifest
    if (dirty := dirty_targets(root, list(result["files"]))) and not args.allow_dirty:
        print(f"fr_split: refusing to write: uncommitted changes in {', '.join(dirty[:4])}. Commit or stash them, or pass --allow-dirty.", file=sys.stderr)
        return 2
    if problems := apply(root, result):
        failed = [x for x in problems if x.startswith("could not restore")]
        verdict = f"RESTORE INCOMPLETE: originals are saved in {result.get('backup', '(none)')}" if failed else "All files restored."
        print("\n".join(f"PROBLEM after writing: {x}" for x in problems) + "\n" + verdict, file=sys.stderr)
        return 1
    print(f"Applied: {len(result['files'])} file(s) written; manifest binding re-checked against a fresh regeneration." + ("" if args.keep_manifest else " The committed manifest was left as is: regenerate it in the data PR."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
