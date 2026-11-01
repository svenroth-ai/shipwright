#!/usr/bin/env python3
"""Independent AI gap check: one non-Claude model call, advisory, never blocking.

Reads the change's diff, the requirement catalog (``spec.md`` acceptance criteria) and the
declaration on the change record, asks a model that is not Claude (GPT or GLM through the
external-review OpenRouter route, so the key check, model pinning and retry rules are the
shared ones) whether the declaration is a fair account of the diff, and writes:

* ``ai-gap-check.json`` - the machine record (``status`` ``ran`` or ``not_run``)
* ``ai-gap-check.md``   - the one PR-body block

Free text (diff, catalog, declaration) travels through files only. **Exit status is always 0**: no key,
a provider outage or an unreadable reply give ``status: "not_run"`` and a visible note, never a failure.

    uv run shared/scripts/tools/ai_gap_check.py --project-root . --run-id RUN \
        --diff-file DIFF --out-dir .shipwright/planning/iterate/RUN
    # replays / tests: --event-file EVENT.json and --spec-file SPEC.md (repeatable) replace the lookups
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
_SCRIPTS_ROOT = _TOOLS.parent
for _p in (str(_SCRIPTS_ROOT), str(_SCRIPTS_ROOT / "lib"), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from lib.ai_gap_check_core import (  # noqa: E402
        PROMPT_VERSION,
        SCHEMA,
        SYSTEM_PROMPT,
        USER_TEMPLATE,
        catalog_from_specs,
        declaration_from_event,
        parse_reply,
        render_block,
        render_not_run,
        render_spec_context,
        trim_diff,
    )
    _CORE_ERROR: Exception | None = None
except Exception as _exc:  # noqa: BLE001 - a broken import must still end in a not_run record and exit 0
    _CORE_ERROR = _exc

REVIEWERS = ("openai", "glm")
DEFAULT_MAX_DIFF = 400_000
MAX_PROMPT_CHARS = 700_000  # catalog + diff together


def _event_for_run(project_root: Path, run_id: str) -> dict | None:
    from lib.events_log import resolve_events_path
    from lib.jsonl_records import read_jsonl_records

    path = resolve_events_path(project_root)
    if not run_id or not path.exists():
        return None
    found = None
    for evt in read_jsonl_records(path).records:
        if evt.get("type") == "work_completed" and evt.get("adr_id") == run_id:
            found = evt
    return found


def working_tree_diff(root: Path, base_ref: str) -> str:
    """What this branch changes since it left ``base_ref``: committed, staged and unstaged changes of tracked files.

    Untracked files are never sent; stage the run's files first (``git add``, or ``git add -N`` for a new file).
    Renames are shown as delete plus add so a credential file cannot hide behind a harmless new name.
    """
    def git(*a: str) -> str:
        out = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *a], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", check=False)
        if out.returncode != 0:
            raise RuntimeError(f"git {a[0]} failed: {out.stderr.strip()[:200]}")
        return out.stdout

    base = git("merge-base", base_ref, "HEAD").strip()
    return git("diff", "--no-color", "--no-renames", base)


def run_check(diff_text: str, declaration: dict, spec_texts: list[str], reviewer: str, project_root: Path) -> dict:
    """The record for one check. Never raises: every failure is a ``not_run`` record."""
    record: dict = {"schema": SCHEMA, "prompt_version": PROMPT_VERSION, "status": "not_run", "reviewer": reviewer, "reason": ""}
    try:
        catalog = catalog_from_specs(spec_texts)
        if not catalog.strip():
            record["reason"] = "no requirement catalog (spec.md) was found"
            return record
        context = render_spec_context(declaration, catalog)
        budget = MAX_PROMPT_CHARS - len(context)
        if budget < 20_000:
            record["reason"] = "the requirement catalog alone is too large to send"
            return record
        diff, dropped, cut, withheld = trim_diff(diff_text, min(budget, DEFAULT_MAX_DIFF))
        if not diff.strip():
            record["reason"] = "nothing to check: the diff is empty, or every file was too large or withheld"
            return record
        import external_review as er  # the shared review route; imported here so a broken import is a not_run note
        from external_review_config import load_review_config
        from external_review_routing import resolve_reviewer_model

        config = load_review_config(project_root=project_root)
        from external_review_config import is_external_code_review_enabled, is_external_review_enabled
        from external_review_gateway import gateway_configured

        if gateway_configured():
            record["reason"] = "a gateway-only review route is configured; this check does not use it"
            return record
        if not (is_external_review_enabled(config) and is_external_code_review_enabled(config)):
            record["reason"] = "external review is switched off for this project"
            return record
        record["model"] = resolve_reviewer_model(config, reviewer, "openrouter")
        if any(bad in record["model"].lower() for bad in ("claude", "anthropic")):  # independence is the point of this check
            record["reason"] = f"the resolved model {record['model']} is not independent of the assistant"
            return record
        record["diff_chars"] = len(diff)
        record["records_left_out"] = len(dropped)
        record["files_cut"] = cut
        record["files_withheld"] = withheld
        reply = er.review_with_openrouter(
            diff, context, SYSTEM_PROMPT, USER_TEMPLATE, config, reviewer,
        )
        if reply.get("status") != "success":
            record["reason"] = f"{reply.get('status')}: {reply.get('reason') or 'no reply'}"
            return record
        raw = reply.get("feedback") or ""
        record["raw_reply"] = raw[:8000]
        record["result"] = parse_reply(raw)
        record["status"] = "ran"
    except Exception as exc:  # noqa: BLE001 - advisory by design: nothing here may fail the run
        record["status"] = "not_run"
        record["reason"] = f"{type(exc).__name__}: {exc}"
    return record


def block_for(record: dict) -> str:
    if record.get("status") == "ran":
        return render_block(record["result"], str(record.get("model") or ""), [*(record.get("files_cut") or ()), *(record.get("files_withheld") or ())])
    return render_not_run(record.get("reason") or "unknown")


def _fallback(args: argparse.Namespace, reason: str) -> int:
    """The core module would not even import: still leave a not_run record and exit 0."""
    note = "### Independent gap check\n\nNot run: " + " ".join(reason.split())[:200].replace("$", "S").replace(chr(34), "'") + ". Nothing was blocked.\n"
    try:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "ai-gap-check.json").write_text(json.dumps({"schema": 1, "status": "not_run", "reason": reason[:300], "run_id": args.run_id}) + "\n", encoding="utf-8")
        (out / "ai-gap-check.md").write_text(note, encoding="utf-8")
    except OSError:
        pass
    print(note)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Independent AI gap check (advisory, never blocks)")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--diff-file", help="the diff to check (default: the branch against --base-ref, working tree included)")
    ap.add_argument("--base-ref", default="origin/main", help="ref the branch left, for the default diff")
    ap.add_argument("--event-file", help="declaration source: a work_completed event as JSON (default: look the run up)")
    ap.add_argument("--spec-file", action="append", default=[], help="catalog source, repeatable (default: the catalog under .shipwright/planning)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--reviewer", choices=REVIEWERS, default="", help="default: openai, or glm under --driver codex")
    ap.add_argument("--driver", choices=("claude", "codex"), default="claude",
                    help="harness that wrote the change; codex never gets a GPT-family reviewer (not independent)")
    args = ap.parse_args()
    if _CORE_ERROR is not None:
        return _fallback(args, f"{type(_CORE_ERROR).__name__}: {_CORE_ERROR}")
    if hasattr(sys.stdout, "reconfigure"):  # a cp1252 pipe must not turn the block into a crash
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    root = Path(args.project_root).resolve()
    if args.driver == "codex" or not args.reviewer:
        args.reviewer = "glm" if args.driver == "codex" else (args.reviewer or "openai")
    out = Path(args.out_dir)
    try:
        out.mkdir(parents=True, exist_ok=True)
        diff_text = Path(args.diff_file).read_text(encoding="utf-8", errors="replace") if args.diff_file else working_tree_diff(root, args.base_ref)
        if args.event_file:
            event = json.loads(Path(args.event_file).read_text(encoding="utf-8"))
        else:
            event = _event_for_run(root, args.run_id) or {}
        spec_paths = [Path(p) for p in args.spec_file] or sorted((root / ".shipwright/planning").glob("*/spec.md"))
        specs = [p.read_text(encoding="utf-8", errors="replace") for p in spec_paths if p.exists()]
        record = run_check(diff_text, declaration_from_event(event), specs, args.reviewer, root)
    except Exception as exc:  # noqa: BLE001 - see run_check
        record = {"schema": SCHEMA, "prompt_version": PROMPT_VERSION, "status": "not_run", "reviewer": args.reviewer, "reason": f"{type(exc).__name__}: {exc}"}
    record["run_id"] = args.run_id
    record["block"] = block_for(record)
    try:
        (out / "ai-gap-check.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (out / "ai-gap-check.md").write_text(record["block"], encoding="utf-8")
    except OSError as exc:
        print(f"ai_gap_check: could not write the record: {exc}", file=sys.stderr)
    print(record["block"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
