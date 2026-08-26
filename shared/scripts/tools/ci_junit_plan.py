#!/usr/bin/env python3
"""CI's own test-root JUnit plan (iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC4).

ci.yml's three pytest steps (plugin loop, shared-tier loop, integration-tests)
each need to know WHERE to write their `--junit-xml`, using the SAME base
convention F0's retention (AC2) uses — one shared derivation
(`suite_root_plan.plan_root`/`base_for_root`), never a hand-maintained
base-to-path table duplicated in YAML.

Three subcommands, each its own ci.yml step:

  plan    — discover every test root (`conftest.py::discover_test_roots`, the
            SAME function the repo-root pytest guard uses) and write
            `plan.json`: the full expected (rel_root, base, junit_out) set.
            Run ONCE, early, before any pytest step.
  lookup  — print one root's planned `--junit-xml` path, by `--rel-root`.
            Called inline by each of the three test-running steps so the
            filename is READ from `plan.json`, never recomputed ad hoc.
  verify  — after all three test steps ran: assert every planned file was
            actually produced (External Review, both reviewers — nothing
            before this verified the three steps collectively covered every
            root; a silently-dropped root would either read as false
            structural drift in the manifest comparator, or get masked as a
            "platform-selection difference" it is not).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SHARED_ROOT = Path(__file__).resolve().parents[2]
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))
from scripts.lib.suite_root_plan import plan_all_roots  # noqa: E402


def _load_discover_test_roots(repo_root: Path):
    """ADR-045: register in ``sys.modules`` BEFORE ``exec_module`` — a unique
    synthetic name, never a bare ``sys.path`` insert (mirrors
    ``run_full_suite_evidence._load_discover_test_roots``)."""
    conftest_path = repo_root / "conftest.py"
    spec = importlib.util.spec_from_file_location("_ci_junit_plan_conftest", conftest_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ci_junit_plan_conftest"] = module
    spec.loader.exec_module(module)
    return module.discover_test_roots


def write_plan(project_root: Path, out_dir: Path) -> list[dict]:
    discover_test_roots = _load_discover_test_roots(project_root)
    roots = discover_test_roots(project_root)
    plans = plan_all_roots(project_root, roots, out_dir)
    entries = [
        {"rel_root": p.rel_root, "base": p.base, "junit_out": str(p.junit_out)}
        for p in plans
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return entries


def _cmd_plan(args: argparse.Namespace) -> int:
    entries = write_plan(args.project_root.resolve(), args.out.resolve())
    print(f"planned {len(entries)} test root(s) -> {args.out.resolve() / 'plan.json'}")
    return 0


def _load_plan(plan_path: Path) -> list[dict] | None:
    """Returns None (after printing an ERROR) on any read/parse failure —
    callers turn that into exit 2, never an unhandled traceback."""
    try:
        return json.loads(plan_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read {plan_path}: {exc}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"ERROR: {plan_path} is not valid JSON: {exc}", file=sys.stderr)
        return None


def _cmd_lookup(args: argparse.Namespace) -> int:
    entries = _load_plan(args.plan)
    if entries is None:
        return 2
    matches = [e for e in entries if e["rel_root"] == args.rel_root]
    if not matches:
        print(
            f"ERROR: {args.rel_root!r} is not in {args.plan} - discovered roots: "
            f"{[e['rel_root'] for e in entries]}", file=sys.stderr,
        )
        return 2
    print(matches[0]["junit_out"])
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    entries = _load_plan(args.plan)
    if entries is None:
        return 2
    missing = [e["rel_root"] for e in entries if not Path(e["junit_out"]).is_file()]
    if missing:
        print(
            f"ERROR: no JUnit report was produced for: {missing} - a test root's own "
            "pytest step did not run, crashed before writing --junit-xml, or the "
            "step's junit path diverged from the plan.", file=sys.stderr,
        )
        return 2
    bases = sorted({e["base"] for e in entries})
    print(f"verified {len(entries)} test root(s), {len(bases)} distinct base(s): {bases}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-root", default=Path("."), type=Path)
    sub = ap.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--out", required=True, type=Path)
    p_plan.set_defaults(func=_cmd_plan)

    p_lookup = sub.add_parser("lookup")
    p_lookup.add_argument("--plan", required=True, type=Path)
    p_lookup.add_argument("--rel-root", required=True)
    p_lookup.set_defaults(func=_cmd_lookup)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--plan", required=True, type=Path)
    p_verify.set_defaults(func=_cmd_verify)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
