#!/usr/bin/env python3
"""Is a converted plugin really converted? (deterministic-first programme Tz, pilot unit P7.)

Reads ``shared/config/plugin_conversion.json`` and checks one registered plugin:

* **prose** - every second-pass A-item (a mechanic that moved into code) is gone from the live prose;
* **code** - every B-item (record, hook, verify, stored date, closing summary) exists, the CLI exists and the prose
  calls each of its subcommands, and the committed ``trace.json`` export equals the promise list;
* **bundle** (``--bundle``) - the Codex bundle built from this tree holds the CLI and every script the prose cites;
* **report** (``--junit FILE``) - from the plugin's own JUnit report: every ``passing`` promise ran and passed,
  the freeze sentinel ran and passed, every seeded regression test ran and passed (``junit_promises.py``);
* **verify_local** (``--verify-local``) - ``scripts/verify_local.py`` exits 0.

    uv run shared/scripts/tools/check_plugin_conversion.py --project-root . --plugin shipwright-changelog \\
        --junit <report.xml> --bundle [--verify-local] [--write-export]

Exit codes: 0 clean; 1 findings; 2 the registry, the report or a registered file cannot be read. It is an operator
and stop-3 tool, not a CI step: wiring it into ``ci.yml`` is a trust-boundary edit (FINDINGS D63).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import junit_promises as jp  # noqa: E402

REGISTRY = Path(__file__).resolve().parents[2] / "config" / "plugin_conversion.json"
CITED = re.compile(r"\{(plugin_root|shared_root)\}/(scripts/[\w./-]+)")
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
ENTRY_KEYS = ("plugin", "skill", "references", "cli", "subcommands", "promise_list", "export", "sentinel", "seeded",
              "a_items", "b_items")
A_KEYS, B_KEYS = ("id", "scope", "forbidden", "why"), ("id", "file", "pattern", "why")


class ConversionError(Exception):
    """The registry, a registered file or the bundle build cannot be read (exit 2)."""


def kill_tree(proc) -> None:
    """End the process and everything it started (``taskkill /T`` on Windows, the process group elsewhere)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        os.killpg(proc.pid, signal.SIGKILL)
    proc.kill()


def run_tree(cmd: list[str], cwd=None, timeout: int = 120, popen=subprocess.Popen, kill=kill_tree):
    """Run ``cmd`` in its own process group; on timeout kill the whole tree. Output is decoded as utf-8, errors replaced."""
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **group)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill(proc)
        proc.communicate()
        raise
    return SimpleNamespace(returncode=proc.returncode, stdout=out.decode("utf-8", "replace"), stderr=err.decode("utf-8", "replace"))


def read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConversionError(f"{rel}: cannot be read ({exc})") from exc


def load_entry(plugin: str, registry: Path = REGISTRY) -> dict:
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
        entry = next(e for e in data["plugins"] if e["plugin"] == plugin)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        raise ConversionError(f"{registry}: no readable entry for {plugin!r} ({exc!r})") from exc
    missing = [k for k in ENTRY_KEYS if k not in entry]
    missing += [f"a_items[{i}].{k}" for i, item in enumerate(entry.get("a_items", [])) for k in A_KEYS if k not in item]
    missing += [f"b_items[{i}].{k}" for i, item in enumerate(entry.get("b_items", [])) for k in B_KEYS if k not in item]
    missing += [f"sentinel.{k}" for k in ("file", "name") if k not in entry.get("sentinel", {})]
    if missing:
        raise ConversionError(f"{registry}: the entry for {plugin!r} lacks {', '.join(missing)}")
    return entry


def _prose(root: Path, entry: dict, scope: str) -> dict[str, str]:
    files = {entry["skill"]: read(root, entry["skill"])}
    if scope == "prose":
        for ref in sorted((root / entry["references"]).glob("*.md")):
            files[ref.relative_to(root).as_posix()] = read(root, ref.relative_to(root).as_posix())
    return files


def check_prose(root: Path, entry: dict) -> list[str]:
    """An A-item still in the live prose: one finding per forbidden match."""
    problems = []
    for item in entry["a_items"]:
        try:
            pattern = re.compile(item["forbidden"], re.M)
        except re.error as exc:
            raise ConversionError(f"{item['id']}: the forbidden pattern is not a regex ({exc})") from exc
        for path, text in _prose(root, entry, item["scope"]).items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{item['id']}: {path}:{line}: {match.group(0).strip()[:60]!r} is back in the prose ({item['why']})")
    return problems


def check_code(root: Path, entry: dict) -> list[str]:
    problems = []
    for item in entry["b_items"]:
        if not re.search(item["pattern"], read(root, item["file"]), re.M):
            problems.append(f"{item['id']}: {item['file']} has no {item['pattern']!r} ({item['why']})")
    skill = read(root, entry["skill"])
    cli_name = Path(entry["cli"]).name
    if not (root / entry["cli"]).is_file():
        problems.append(f"CLI: {entry['cli']} does not exist")
    blocks = "\n".join(FENCE.findall(skill.replace("\r\n", "\n")))
    for sub in entry["subcommands"]:  # a call is a command line of a fenced block, not a mention in running text
        if not re.search(rf"^\s*uv run \S*{re.escape(cli_name)}\"?\s+{re.escape(sub)}(\s|$)", blocks, re.M):
            problems.append(f"CLI: SKILL.md never calls `{cli_name} {sub}` in a fenced block")
    return problems


def check_export(root: Path, entry: dict) -> list[str]:
    promise_list = json.loads(read(root, entry["promise_list"]))
    if read(root, entry["export"]) != jp.dump(jp.export_trace(promise_list)):
        return [f"export: {entry['export']} differs from the promise list (re-run with --write-export)"]
    return []


def check_report(root: Path, entry: dict, junit: Path) -> list[str]:
    try:
        cases = jp.load_cases(junit)
    except ValueError as exc:
        raise ConversionError(str(exc)) from exc
    promises = json.loads(read(root, entry["promise_list"]))["promises"]
    sentinel = entry["sentinel"]
    return (jp.passing_problems(promises, cases)
            + jp.named_problems("sentinel", [f"{sentinel['file']}::{sentinel['name']}"], cases)
            + jp.named_problems("seeded regression", entry["seeded"], cases))


def check_bundle(root: Path, entry: dict, build=None, run=run_tree) -> list[str]:
    """Build the Codex bundle from this tree; the CLI and everything the prose cites must be in it and the CLI must start."""
    if build is None:
        try:
            from build_codex_plugin import build_bundle as build
        except ImportError as exc:
            raise ConversionError(f"bundle: build_codex_plugin cannot be imported ({exc})") from exc
    skill_name = Path(entry["skill"]).parent.name
    with tempfile.TemporaryDirectory(prefix="plugin-conversion-") as tmp:
        bundle = Path(tmp) / "bundle"
        try:
            build(project_root=root, out_dir=bundle)
        except Exception as exc:  # the builder raises whatever its inputs make it raise: any failure is "cannot check"
            raise ConversionError(f"bundle: the Codex bundle cannot be built ({type(exc).__name__}: {exc})") from exc
        origin = bundle / "origin" / entry["plugin"]
        cli = origin / "scripts" / Path(entry["cli"]).name
        problems = [] if cli.is_file() else [f"bundle: origin/{entry['plugin']}/scripts/{cli.name} is missing"]
        if not (bundle / "skills" / skill_name / "SKILL.md").is_file():
            problems.append(f"bundle: skills/{skill_name}/SKILL.md is missing")
        for which, rel in sorted(set(CITED.findall(read(root, entry["skill"])))):
            target = origin / rel if which == "plugin_root" else bundle / "shared" / rel
            if not target.is_file():
                problems.append(f"bundle: SKILL.md cites {{{which}}}/{rel}, which the bundle does not hold")
        if not problems:
            try:
                done = run([sys.executable, str(cli), "--help"], timeout=120)
            except subprocess.TimeoutExpired:
                return [f"bundle: `{cli.name} --help` did not answer within 120 s"]
            except OSError as exc:
                raise ConversionError(f"bundle: `{cli.name} --help` cannot be started ({exc})") from exc
            if done.returncode != 0:
                problems.append(f"bundle: `{cli.name} --help` exits {done.returncode}: {(done.stderr or '').strip()[-200:]}")
    return problems


def check_verify_local(root: Path, run=run_tree) -> list[str]:
    try:
        done = run(["uv", "run", "scripts/verify_local.py"], cwd=root, timeout=1800)
    except subprocess.TimeoutExpired:
        return ["verify_local: did not finish within 1800 s"]
    except OSError as exc:
        raise ConversionError(f"verify_local: cannot be started ({exc})") from exc
    return [] if done.returncode == 0 else [f"verify_local: exits {done.returncode}: {(done.stdout or '')[-300:]}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--junit", help="the plugin's own JUnit report")
    parser.add_argument("--bundle", action="store_true", help="build the Codex bundle and resolve the CLI in it")
    parser.add_argument("--verify-local", action="store_true")
    parser.add_argument("--write-export", action="store_true", help="rewrite the trace.json export from the promise list ")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        entry = load_entry(args.plugin, Path(args.registry))
        if args.write_export:
            trace = jp.export_trace(json.loads(read(root, entry["promise_list"])))  # never the report's statuses: the committed file must equal check_export's
            target = root / entry["export"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(jp.dump(trace), encoding="utf-8", newline="\n")
        ran = ["static"]
        problems = check_prose(root, entry) + check_code(root, entry) + check_export(root, entry)
        if args.junit:
            problems += check_report(root, entry, Path(args.junit))
            ran.append("junit")
        if args.bundle:
            problems += check_bundle(root, entry)
            ran.append("bundle")
        if args.verify_local:
            problems += check_verify_local(root)
            ran.append("verify_local")
    except (ConversionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem)
    print(f"{args.plugin}: {verdict(problems, ran)}")
    return 1 if problems else 0


def verdict(problems: list[str], ran: list[str]) -> str:
    """``converted`` only when the report was read too: static checks alone prove the tree, not that its tests ran."""
    if problems:
        return f"{len(problems)} finding(s) ({', '.join(ran)})"
    return f"converted ({', '.join(ran)})" if "junit" in ran else f"static checks clean ({', '.join(ran)}; no --junit: the promise tests were not checked)"


if __name__ == "__main__":
    sys.exit(main())
