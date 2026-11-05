#!/usr/bin/env python3
"""Standing replay gate for the per-run drops layout (issue 978, campaign S0).

Runs every EVENT-RELATED test file of every test root (one pytest process per root,
the repo rule) under the TEST-ONLY layout override::

    SHIPWRIGHT_EVENTS_LAYOUT=drops  SHIPWRIGHT_EVENTS_LAYOUT_TEST=1

and compares the failures against a committed, RATCHETED known set
(``events_replay_known_failing.json``):

* a failure that is NOT in the known set        -> gate FAILS (new regression);
* a known entry that now passes ("stale")       -> reported; ``--tighten`` removes it
  (and ``--strict-stale`` makes it a failure). The set may only SHRINK: ``init``
  refuses to run over a non-empty set and ``tighten`` can only delete.
* wall-clock over ``budget_seconds``            -> gate FAILS (the stated time budget).

A test that fails under ``drops`` is re-run under ``legacy``; if it fails there too it
is a baseline failure of the platform, not a drops finding, and is excluded (this makes
a set recorded on one OS valid on another).

Each known entry carries the unit that owes the fix: ``S2``/``S3`` = product READER
items, ``S4`` = WRITER / finalization items (``unit`` is editable by hand).

Usage::

    uv run --with pytest shared/scripts/tools/events_replay_gate.py            # check (CI)
    uv run --with pytest shared/scripts/tools/events_replay_gate.py --list     # show the selection
    uv run --with pytest shared/scripts/tools/events_replay_gate.py init       # first recording
    uv run --with pytest shared/scripts/tools/events_replay_gate.py tighten    # drop fixed entries
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_SHARED_ROOT = Path(__file__).resolve().parents[2]
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))
from scripts.lib.suite_root_plan import RootPlan, plan_all_roots  # noqa: E402

KNOWN_PATH = Path(__file__).with_name("events_replay_known_failing.json")
DROPS_ENV = {"SHIPWRIGHT_EVENTS_LAYOUT": "drops", "SHIPWRIGHT_EVENTS_LAYOUT_TEST": "1"}
LEGACY_ENV = {"SHIPWRIGHT_EVENTS_LAYOUT": "legacy", "SHIPWRIGHT_EVENTS_LAYOUT_TEST": "1"}

#: A test file is "event related" when its text mentions the event log or one of
#: its writers/readers. Deliberately broad: a miss silently shrinks the gate.
EVENT_RELATED = re.compile(
    r"shipwright_events|record_event|events_log|events_layout|read_events|EVENT_FILE|"
    r"ensure_current|finalize_iterate|events\.jsonl|append_event|latest_event_dt|"
    r"finalized_run_ids|work_completed|phase_completed|event_context|attach_commit"
)
_UNIT_S4 = re.compile(
    r"finalize|record_event|attach_commit|completion_writer|newline_integrity|iterate_entry|"
    r"append_|commit_event_followup|event_seeder|phase_history|decision_drop|convert_configs|"
    r"verif|tests_block|test_evidence|f11|seal")
_UNIT_S2 = re.compile(r"ledger_anchor|reader|read_events|latest_event|record_boundary|events_log|position")
_FAIL_LINE = re.compile(r"^(?:FAILED|ERROR) (.+?)(?: - .*)?$")


def classify_unit(test_id: str) -> str:
    """Initial owner of a known failure (hand-editable in the JSON afterwards)."""
    low = test_id.lower()
    if _UNIT_S4.search(low):
        return "S4"
    if _UNIT_S2.search(low):
        return "S2"
    return "S3"


def select_files(plan: RootPlan) -> list[Path]:
    """Event-related ``test_*.py`` files of one root (fixture trees are data)."""
    out = []
    for path in sorted(plan.root.rglob("test_*.py")):
        rel = path.relative_to(plan.root).parts
        if "fixtures" in rel or "node_modules" in rel or ".venv" in rel:
            continue
        try:
            if EVENT_RELATED.search(path.read_text(encoding="utf-8", errors="replace")):
                out.append(path)
        except OSError:
            continue
    return out


def _pytest_cmd(plan: RootPlan, args: list[str]) -> list[str]:
    cmd = ["uv", "run", "--with", "pytest", "--with", "pytest-mock"]
    if plan.base == "":
        cmd += ["--with", "diff-cover==10.3.0"]
    # The root's own addopts (e.g. a plugin's `-m 'not empirical'`) stay in force.
    cmd += ["pytest", "-q", "--tb=no", "-rfE", "-p", "no:cacheprovider"]
    if plan.marker_expr:
        cmd += ["-m", plan.marker_expr]
    return cmd + args


def _run(plan: RootPlan, args: list[str], env_extra: dict[str, str], timeout: int) -> tuple[set[str], str]:
    """Failure ids of one pytest process. FAIL-CLOSED: anything that is not a clean
    0/1 exit, or an exit 1 with no parseable failure, yields a ``<pytest-...>`` sentinel."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_EVENTS_LAYOUT")}
    env.update(env_extra)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(_pytest_cmd(plan, args), cwd=plan.cwd, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {f"{plan.pytest_arg}::<pytest-timeout>"}, ""
    failed: set[str] = set()
    for line in proc.stdout.splitlines():
        m = _FAIL_LINE.match(line.strip())
        if m:
            failed.add(m.group(1))
    if proc.returncode not in (0, 1) or (proc.returncode == 1 and not failed):
        failed.add(f"{plan.pytest_arg}::<pytest-exit-{proc.returncode}>")
    return failed, proc.stdout[-400:]


def _global_id(plan: RootPlan, node: str) -> str:
    """Repo-relative, posix, stable across cwd choices."""
    node = node.replace("\\", "/")
    return f"{plan.base}/{node}" if plan.base else node


def run_root(plan: RootPlan, timeout: int) -> dict:
    files = select_files(plan)
    if not files:
        return {"root": plan.rel_root, "files": 0, "drops_failed": [], "baseline_failed": [], "seconds": 0.0}
    started = time.monotonic()
    rel = [f.relative_to(plan.cwd).as_posix() for f in files]
    drops_failed, _ = _run(plan, rel, DROPS_ENV, timeout)
    baseline: set[str] = set()
    if drops_failed:
        # Re-run only the failing tests with the layout forced back to legacy.
        runnable = sorted(n for n in drops_failed if "<pytest-" not in n and "::" in n)
        if runnable:
            baseline, _ = _run(plan, runnable, LEGACY_ENV, timeout)
    # The legacy re-run itself broke (sentinel): never read that as "no baseline
    # failures" -- surface it as a failure of this root. Collection errors (no `::`)
    # mean the selected tests never ran, so they are never excused as baseline.
    drops_failed = drops_failed | {n for n in baseline if "<pytest-" in n}
    baseline = {n for n in baseline if "<pytest-" not in n and "::" in n}
    return {
        "root": plan.rel_root, "files": len(files), "seconds": round(time.monotonic() - started, 1),
        "drops_failed": sorted(_global_id(plan, n) for n in drops_failed - baseline),
        "baseline_failed": sorted(_global_id(plan, n) for n in baseline & drops_failed),
    }


def _plans(repo: Path, only: list[str]) -> list[RootPlan]:
    spec = importlib.util.spec_from_file_location("_events_replay_conftest", repo / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_events_replay_conftest"] = module  # ADR-045: register BEFORE exec
    spec.loader.exec_module(module)
    plans = plan_all_roots(repo, module.discover_test_roots(repo), repo / ".events-replay")
    return [p for p in plans if not only or any(o in p.rel_root for o in only)]


def preflight(repo: Path) -> str | None:
    """Canary: the override must really select ``drops`` (and legacy without the flag).

    Without it a renamed variable would make every replay run legacy and, once the
    known set is empty, turn the gate vacuously green.
    """
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import tempfile; "
            "from lib.events_layout import events_layout as e; print(e(tempfile.mkdtemp()))")

    def probe(env_extra: dict[str, str]) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_EVENTS_LAYOUT")}
        env.update(env_extra)
        r = subprocess.run([sys.executable, "-c", code, str(repo / "shared" / "scripts")],
                           capture_output=True, text=True, env=env, timeout=120)
        return r.stdout.strip() or r.stderr.strip()[-200:]

    got = probe(DROPS_ENV)
    if got != "drops":
        return f"DROPS_ENV resolved to {got!r}, expected 'drops'"
    got = probe({"SHIPWRIGHT_EVENTS_LAYOUT": "drops"})
    return None if got == "legacy" else f"the plain env var resolved to {got!r}, expected 'legacy'"


def load_known() -> dict:
    """Missing file = empty set (first recording). An unparseable file is an ERROR."""
    if not KNOWN_PATH.exists():
        return {"schema": 1, "budget_seconds": 0, "known": {}}
    try:
        doc = json.loads(KNOWN_PATH.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("known"), dict):
            raise ValueError("no `known` object")
        return doc
    except (OSError, ValueError) as exc:
        raise SystemExit(f"ERROR: {KNOWN_PATH.name} is unreadable ({exc}); refusing to treat it as empty")


def ratchet_violations(doc: dict, base_doc: dict | None) -> list[str]:
    """The set may only shrink relative to the merge-base copy (None = no base copy)."""
    if base_doc is None:
        return []
    out = [f"entry added since the merge-base: {n}"
           for n in doc.get("known", {}) if n not in base_doc.get("known", {})]
    base_budget, budget = int(base_doc.get("budget_seconds", 0)), int(doc.get("budget_seconds", 0))
    if base_budget > 0 and budget <= 0:
        out.append("budget_seconds removed or zeroed (the stated time budget cannot be switched off)")
    elif budget > base_budget > 0 and not str(doc.get("budget_reason", "")).strip():
        out.append(f"budget_seconds raised {base_budget} -> {budget} without a `budget_reason`")
    return out


def base_known(repo: Path) -> tuple[str, dict | None]:
    """The known file at the merge-base with origin/main as ``(state, doc)``.

    ``ok`` = loaded; ``absent`` = the base has no such file (the set is being
    introduced); ``unresolved`` = the base could not be determined at all.
    """
    rel = KNOWN_PATH.resolve().relative_to(repo.resolve()).as_posix()
    try:
        base = subprocess.run(["git", "-C", str(repo), "merge-base", "HEAD", "origin/main"],
                              capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unresolved", None
    try:
        blob = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{base}:{rel}"],
                              capture_output=True, text=True, timeout=30)
        if blob.returncode != 0:
            return "absent", None
        shown = subprocess.run(["git", "-C", str(repo), "show", f"{base}:{rel}"],
                               capture_output=True, text=True, timeout=30, check=True).stdout
        return "ok", json.loads(shown)
    except (OSError, subprocess.SubprocessError, ValueError):
        return "unresolved", None


def save_known(doc: dict) -> None:
    KNOWN_PATH.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="check", choices=("check", "init", "tighten"))
    ap.add_argument("--repo", type=Path, default=_SHARED_ROOT.parent)
    ap.add_argument("--root", action="append", default=[], help="only roots whose path contains this")
    ap.add_argument("--jobs", type=int, default=1, help="roots run in parallel (separate processes)")
    ap.add_argument("--timeout", type=int, default=3000, help="per pytest process, seconds")
    ap.add_argument("--list", action="store_true", help="print the selected files and exit")
    ap.add_argument("--strict-stale", action="store_true", help="fail when a known entry now passes")
    ap.add_argument("--report", type=Path, help="write the full JSON report here")
    args = ap.parse_args(argv)
    repo = args.repo.resolve()
    plans = _plans(repo, args.root)

    if args.list:
        for plan in plans:
            sel = select_files(plan)
            print(f"{plan.rel_root}: {len(sel)} file(s)")
            for f in sel:
                print(f"  {f.relative_to(repo).as_posix()}")
        return 0

    problem = preflight(repo)
    if problem:
        print(f"FAIL: override canary -- {problem}")
        return 1
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(lambda p: run_root(p, args.timeout), plans))
    elapsed = round(time.monotonic() - started, 1)
    failing = sorted({n for r in results for n in r["drops_failed"]})
    baseline = sorted({n for r in results for n in r["baseline_failed"]})
    selected = sum(r["files"] for r in results)
    print(f"events-replay: {selected} event-related file(s) over {len(results)} root(s), {elapsed}s; "
          f"{len(failing)} drops-only failure(s), {len(baseline)} baseline failure(s) excluded")
    for n in baseline:
        print(f"  baseline (fails under legacy too, excluded -- check it is not caused by THIS change): {n}")
    for r in results:
        print(f"  {r['root']}: {r['files']} file(s), {r['seconds']}s, {len(r['drops_failed'])} failing")
    if args.report:
        args.report.write_text(json.dumps({"elapsed": elapsed, "results": results}, indent=2), encoding="utf-8")

    doc = load_known()
    known = doc.get("known", {})
    if args.mode == "init":
        if known:
            print("ERROR: known set is not empty; the ratchet may only shrink (use `tighten`).", file=sys.stderr)
            return 2
        if any("<pytest-" in n for n in failing):
            print("ERROR: a root crashed or timed out during recording; fix that first "
                  "(sentinels can never become known entries).", file=sys.stderr)
            return 2
        doc["known"] = {n: {"unit": classify_unit(n)} for n in failing}
        doc["budget_seconds"] = int(elapsed * 2) + 60
        save_known(doc)
        print(f"recorded {len(failing)} known failure(s); budget {doc['budget_seconds']}s")
        return 0

    new = [n for n in failing if n not in known]
    stale = [n for n in known if n not in failing and n not in baseline]
    by_unit: dict[str, int] = {}
    for n, meta in known.items():
        by_unit[meta.get("unit", "?")] = by_unit.get(meta.get("unit", "?"), 0) + 1
    print("known set by unit: " + (", ".join(f"{u}={c}" for u, c in sorted(by_unit.items())) or "empty"))
    if args.mode == "tighten":
        for n in stale:
            del known[n]
        save_known(doc)
        print(f"removed {len(stale)} fixed entr(y/ies); {len(known)} remain")
        return 1 if new else 0

    rc = 0
    base_state, base_doc = base_known(repo)
    if base_state == "unresolved":
        msg = "cannot read the known set at the merge-base with origin/main, so shrink-only is NOT verified"
        if os.environ.get("GITHUB_ACTIONS"):
            rc = 1
            print(f"FAIL: {msg} (CI must fetch full history)")
        else:
            print(f"NOTE: {msg}")
    for violation in ratchet_violations(doc, base_doc):
        rc = 1
        print(f"FAIL: ratchet may only shrink -- {violation}")
    budget = int(doc.get("budget_seconds", 0))
    if new:
        rc = 1
        print(f"FAIL: {len(new)} NEW drops-layout failure(s) not in the known set:")
        for n in new:
            print(f"  - {n}")
    if stale:
        print(f"{'FAIL' if args.strict_stale else 'NOTE'}: {len(stale)} known entr(y/ies) now pass; "
              f"run `events_replay_gate.py tighten` and commit the smaller set:")
        for n in stale[:50]:
            print(f"  - {n}")
        rc = rc or (1 if args.strict_stale else 0)
    if budget and elapsed > budget:
        rc = 1
        print(f"FAIL: wall-clock {elapsed}s exceeds the stated budget of {budget}s")
    return rc


if __name__ == "__main__":
    sys.exit(main())
