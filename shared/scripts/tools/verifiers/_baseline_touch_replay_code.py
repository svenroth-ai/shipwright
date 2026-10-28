"""T-code leg of the baseline replay (BP unit BL0): context runs at a PR's merge base + probes.

For each sampled PR a detached worktree of the merge base is checked out, the chosen test
tiers run there with ``--cov-context=test`` (all from the repo root: a simplification the
report discloses - CI runs plugin tiers from the plugin directory), and the PR's own diff is
attributed through the resulting contexts. The wall-clock of every tier is recorded: it is the
context-run cost the brief asks BL0 to measure. ``probe`` then seeds synthetic production
changes into the base tree to see WHICH source notices them (the mutation probe).
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import time
from pathlib import Path

from ._baseline_touch_binding import index_tests
from ._baseline_touch_core import touched_set
from ._baseline_touch_coverage import load_contexts, merge_contexts
from ._baseline_proc import clean_env, guard_workdir
from ._baseline_touch_git import GitRev, is_test_path

__all__ = ["DEFAULT_TIERS", "select_prs", "replay_code"]

#: (tests root, coverage target) - the tiers cheap enough to run per PR; the rest is disclosed.
DEFAULT_TIERS = (
    ("shared/scripts/tools/tests", "shared"),
    ("shared/scripts/tests", "shared"),
    ("plugins/shipwright-iterate/tests", "plugins/shipwright-iterate/scripts"),
    ("plugins/shipwright-changelog/tests", "plugins/shipwright-changelog/scripts"),
)
_PROD = re.compile(r"^(shared/|plugins/[^/]+/scripts/).*\.py$")


def _measured(path: str, tiers) -> bool:
    return any(path.startswith(target.rstrip("/") + "/") for _root, target in tiers)


def select_prs(records: list[dict], k: int, tiers=DEFAULT_TIERS) -> list[dict]:
    """The ``k`` most recent PRs whose merge changed Python production code INSIDE a measured
    target, so 'unattributed because not measured' never masquerades as 'no bound test'."""
    if k <= 0:
        return []
    out = []
    for r in sorted((r for r in records if not r.get("error") and any(_measured(f, tiers) for f in r.get("code_files") or [])),
                    key=lambda r: -r["pr"]):
        out.append(r)
        if len(out) == k:
            break
    return out


def _run_tier(wt: Path, root: str, target: str, db: Path, env: dict) -> dict:
    cmd = ["uv", "run", "--with", "pytest", "--with", "pytest-mock", "--with", "pytest-cov", "pytest", root, "-q",
           "-p", "no:cacheprovider", "-m", "not slow and not cross_plugin", f"--cov={target}",
           "--cov-context=test", "--cov-config=pyproject.toml", "--cov-report="]
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=wt, env={**env, "COVERAGE_FILE": str(db)}, capture_output=True, text=True, check=False)
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    return {"tier": root, "seconds": round(time.monotonic() - started, 1), "rc": proc.returncode, "summary": tail,
            "db_bytes": db.stat().st_size if db.exists() else 0}


def _commit(wt: Path, rel: str, text: str, message: str) -> str:
    (wt / rel).write_text(text, encoding="utf-8", newline="")
    cfg = ["-c", "user.email=probe@example.com", "-c", "user.name=probe", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(wt), "add", "--", rel], check=True, capture_output=True)  # only the seeded file
    subprocess.run(["git", "-C", str(wt), *cfg, "commit", "-q", "--no-verify", "-m", message], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def _mutate(text: str, line_no: int) -> str:
    lines = text.splitlines(keepends=True)
    line = lines[line_no - 1]
    for old, new in (("==", "!="), (" and ", " or "), ("True", "False"), (" + 1", " + 2"), (" > ", " >= ")):
        if old in line:
            lines[line_no - 1] = line.replace(old, new, 1)
            return "".join(lines)
    indent = re.match(r"\s*", line)[0]
    lines.insert(line_no, f"{indent}_probe = 1\n")
    return "".join(lines)


def _bound(wt: Path, test_id: str, cache: dict) -> bool:
    """True when the test is bound to at least one FR (read from the base tree)."""
    if test_id not in cache:
        path, _, name = test_id.partition("::")
        text = (wt / path).read_text(encoding="utf-8", errors="replace") if (wt / path).is_file() else ""
        info = (index_tests(text) or {}).get(name) if text else None
        cache[test_id] = bool(info and info.frs)
    return cache[test_id]


def _candidates(wt: Path, contexts: dict) -> tuple[list, list]:
    """One simple executable line per production file: (bound to an FR-bound test, only unbound tests)."""
    cache: dict = {}
    bound, unbound = [], []
    for f, lines in sorted(contexts.items()):
        if not _PROD.match(f) or not (wt / f).is_file():
            continue
        src = (wt / f).read_text(encoding="utf-8", errors="replace").splitlines()
        for kind, want in ((bound, True), (unbound, False)):
            for ln, tests in sorted(lines.items()):
                if 5 < ln <= len(src) and re.match(r"\s+(return|\w+ =)\s", src[ln - 1]) and \
                        any(_bound(wt, t, cache) for t in tests) == want:
                    kind.append((f, ln))
                    break
    return bound, unbound


def probe(wt: Path, base: str, contexts: dict, variant: int = 0) -> list[dict]:
    """Seed three changes and report which touched-set source notices each: (a) a line an FR-bound
    test executes, (b) a line executed only by tests with no FR binding, (c) a prose line in a
    SKILL.md. ``variant`` rotates the chosen file so different PRs probe different code."""
    bound, unbound = _candidates(wt, contexts)
    kinds = []
    for label, cands in (("production line executed by an FR-bound test", bound),
                         ("production line executed only by tests without an FR binding", unbound)):
        if not cands:
            continue
        f, ln = cands[variant % len(cands)]
        mutated = _mutate((wt / f).read_text(encoding="utf-8"), ln)
        try:
            ast.parse(mutated)
            kinds.append((label, f, mutated))
        except SyntaxError:
            kinds.append((label + " [seeded edit did not parse - not counted]", f, None))
    skills = sorted(p for p in GitRev(wt, base, base).listing("base") if p.endswith("SKILL.md"))
    if skills:
        skill = skills[variant % len(skills)]
        kinds.append(("prose (SKILL.md) line", skill, (wt / skill).read_text(encoding="utf-8") + "\nA seeded sentence that changes behaviour.\n"))
    out = []
    for label, rel, text in kinds:
        if text is None:
            out.append({"probe": label, "file": rel, "noticed": None})
            continue
        try:
            sha = _commit(wt, rel, text, f"probe: {label}")
        except subprocess.CalledProcessError as exc:  # e.g. the seeded edit changed nothing
            out.append({"probe": label, "file": rel, "noticed": None, "error": (exc.stderr or b"").decode("utf-8", "replace")[:200] or "git commit failed"})
            subprocess.run(["git", "-C", str(wt), "reset", "-q", "--hard", base], check=True, capture_output=True)
            continue
        try:
            t = touched_set(GitRev(wt, base, sha), contexts)
            out.append({"probe": label, "file": rel, "sources": {fr: sorted(x) for fr, x in t.sources().items()},
                        "noticed": bool(t.sources()), "unattributed": t.unattributed[:2]})
        finally:
            subprocess.run(["git", "-C", str(wt), "reset", "-q", "--hard", base], check=True, capture_output=True)
    return out


def rerun_probes(repo: Path, records: list[dict], k: int, workdir: Path, tiers=DEFAULT_TIERS) -> list[dict]:
    """Probes only, over context databases an earlier ``replay_code`` left in ``workdir``."""
    guard_workdir(repo, workdir)
    results = []
    for n, rec in enumerate(select_prs(records, k, tiers)):
        wt = workdir / f"probe{rec['pr']}"
        shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), f"{rec['merge']}^"], check=True, capture_output=True)
        try:
            base_sha = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            parts = [load_contexts(db, wt) for i in range(len(tiers)) if (db := workdir / f"cov-{rec['pr']}-{i}").exists()]
            results.append({"pr": rec["pr"], "probes": probe(wt, base_sha, merge_contexts(parts), n)})
        finally:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
            shutil.rmtree(wt, ignore_errors=True)
            subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
    return results


def replay_code(repo: Path, records: list[dict], k: int, workdir: Path, probes: int,
                tiers=DEFAULT_TIERS) -> dict:
    guard_workdir(repo, workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    env = clean_env(workdir / "venv")
    for r in records:  # a PR "has code files" when its merge changed Python in a measured target
        if not r.get("error") and "code_files" not in r:
            rev = GitRev(repo, f"{r['merge']}^", r["merge"])
            r["code_files"] = [n for _s, _o, n in rev.changed() if _PROD.match(n) and not is_test_path(n)]
    results = []
    for n, rec in enumerate(select_prs(records, k)):
        wt = workdir / f"pr{rec['pr']}"
        base = f"{rec['merge']}^"
        shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), base], check=True, capture_output=True)
        try:
            base_sha = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            timings, parts = [], []
            for i, (root, target) in enumerate(tiers):
                if not (wt / root).is_dir():
                    timings.append({"tier": root, "missing_at_base": True})
                    continue
                db = workdir / f"cov-{rec['pr']}-{i}"
                timings.append(_run_tier(wt, root, target, db, env))
                if db.exists():
                    parts.append(load_contexts(db, wt))
            contexts = merge_contexts(parts)
            t = touched_set(GitRev(repo, base, rec["merge"]), contexts)
            entry = {"pr": rec["pr"], "class": rec["class"], "tiers": timings, "code": {fr: sorted(v) for fr, v in t.code.items()},
                     "fan_out": {k2: sorted(v) for k2, v in t.fan_out.items()}, "unattributed": t.unattributed,
                     "code_files": rec["code_files"], "sources": {fr: sorted(s) for fr, s in t.sources().items()}}
            if n < probes:
                entry["probes"] = probe(wt, base_sha, contexts, n)
            results.append(entry)
        finally:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
            shutil.rmtree(wt, ignore_errors=True)
            subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
    return {"tiers": [list(t) for t in tiers], "prs": results}
