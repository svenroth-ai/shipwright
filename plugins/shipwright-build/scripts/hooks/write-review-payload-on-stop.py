#!/usr/bin/env python3
"""Best-effort FALLBACK: salvage a review subagent's raw reply if the
orchestrator has not recorded it yet.

Fires on SubagentStop for spec-reviewer / code-reviewer / doubt-reviewer
(shipwright-build). The orchestrator OWNS recording — it writes the payload
file and calls ``record_review_pass.py record`` as its very next action after
the subagent returns (SKILL.md Step 8). This hook is a DEFENSIVE FALLBACK for
the case a compaction lands between the subagent returning and that write
happening — it fires synchronously as part of the subagent's own lifecycle,
independent of the orchestrator's remaining context budget. It NEVER blocks:

  * if the run has no ``reviews.json`` AT ALL under the resolved project
    root, this hook resolved a different root than the orchestrator's
    (SKILL.md Step 7's ``init`` always creates it before any of these three
    reviewers is spawned, so total absence means "wrong tree", never "not
    yet recorded") — no-op, and never creates the directory;
  * if the run's ``reviews.json`` already shows a terminal status for this
    review type, the orchestrator already recorded it — no-op;
  * otherwise, salvage the subagent's raw JSON reply from its own transcript
    and write it directly to the SAME canonical basename Step 8's own write
    targets (``spec_review_reply.json`` / ``code_review_reply.json`` /
    ``doubt_review_reply.json`` under
    ``.shipwright/planning/iterate/{run_id}/`` — trg-3b206c08's
    ``lib.review_payloads.CANONICAL_PAYLOAD_BASENAMES``, duplicated here
    rather than imported for the ADR-044 reason below) so a resuming session
    can feed that same path straight into
    ``record_review_pass.py record --payload-file`` with no separate copy
    step, instead of losing the findings to ``close-missing``'s ``not_run``
    default. The orchestrator's own normal-path write to the same file, when
    it happens, simply supersedes this one — both derive from the identical
    subagent reply, so the overwrite is harmless;
  * if a ``run_id`` or a parseable reply cannot be resolved, it logs to
    stderr and exits 0 — it never blocks the subagent.

Deliberately self-contained (no ``shared/scripts/lib`` import): this plugin
carries its own ``scripts/lib`` package, and a bare ``lib.xxx`` import here
would collide with whichever ``lib`` package another test in this plugin's
own pytest process happened to import first (ADR-044 — the two cannot be
told apart by import order once one is cached). Mirrors
``write-section-on-stop.py``'s own choice for the same reason: checking
``reviews.json``'s status field and extracting a JSON reply from prose are
both a few lines, not worth a cross-plugin import that this dependency graph
cannot make safe.

``run_id`` is resolved from the transcript text, never from an env var:
``SHIPWRIGHT_RUN_ID``/``SHIPWRIGHT_PLANNING_DIR`` are documented
(iterate-2026-07-27-c3-phase-history-join; and this repo's own
write-section-on-stop.py precedent, whose ``SHIPWRIGHT_PLANNING_DIR`` is
"normally unset" when that hook fires) as unreliable for a Claude-Code-launched
hook subprocess. SKILL.md Step 8 / sub-iterate-runner.md Step 3.7 require the
orchestrator's spawn prompt to state the run_id in plain text, so it is always
present in the subagent's own transcript.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

RUN_ID_RE = re.compile(r"iterate-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*")
TERMINAL_STATUSES = {"completed", "not_run", "not_applicable"}
_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)

# Mirrors lib.review_payloads.CANONICAL_PAYLOAD_BASENAMES for this hook's three
# review types (trg-3b206c08) — duplicated, not imported, for the ADR-044
# reason in the module docstring.
CANONICAL_BASENAME = {
    "spec": "spec_review_reply.json",
    "code": "code_review_reply.json",
    "doubt": "doubt_review_reply.json",
}


def _diag(message: str, **detail: Any) -> None:
    sys.stderr.write(f"[shipwright:review-payload] {message}\n")
    if detail:
        sys.stderr.write(
            f"[shipwright:review-payload] detail={json.dumps(detail, ensure_ascii=False)}\n"
        )


def read_transcript_with_retry(transcript_path: str, max_retries: int = 4) -> list[dict]:
    """Read JSONL transcript with retry for the flush race (50ms -> 400ms)."""
    delays = [0.05, 0.1, 0.2, 0.4]
    for attempt in range(max_retries):
        try:
            if not os.path.exists(transcript_path):
                if attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                return []
            with open(transcript_path, encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                if attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                return []
            entries = []
            for line in content.splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            if entries:
                return entries
            if attempt < max_retries - 1:
                time.sleep(delays[attempt])
        except OSError:
            if attempt < max_retries - 1:
                time.sleep(delays[attempt])
    return []


def _entry_text(entry: dict) -> str:
    content = entry.get("content", "")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return content if isinstance(content, str) else ""


def extract_run_id(entries: list[dict]) -> Optional[str]:
    """The run_id named in the orchestrator's spawn prompt (any role, any
    turn) — required to be present in plain text by SKILL.md Step 8 /
    sub-iterate-runner.md Step 3.7."""
    for entry in entries:
        match = RUN_ID_RE.search(_entry_text(entry))
        if match:
            return match.group(0)
    return None


def last_assistant_reply(entries: list[dict]) -> Optional[str]:
    for entry in reversed(entries):
        if entry.get("role") == "assistant":
            text = _entry_text(entry)
            if text.strip():
                return text
    return None


def looks_like_review_payload(text: str) -> bool:
    """A cheap plausibility check, not a full parse — this hook only needs to
    avoid salvaging pure prose/failure chatter. The real parse (matching the
    exact adapter for this review type) happens later, when a resuming
    session feeds the salvaged file into
    ``record_review_pass.py record --payload-file``."""
    for match in _FENCE_RE.finditer(text):
        try:
            json.loads(match.group(1))
            return True
        except json.JSONDecodeError:
            continue
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def reviews_json_path(project_root: Path, run_id: str) -> Path:
    return (
        Path(project_root) / ".shipwright" / "planning" / "iterate" / run_id
        / "reviews.json"
    )


def wrong_root(project_root: Path, run_id: str) -> bool:
    """True iff this run has NO ``reviews.json`` at all under the resolved
    root — never true for a genuine "not yet recorded" case, since SKILL.md
    Step 7's ``init`` always creates it before any of the three reviewers this
    hook backstops is ever spawned. A total absence instead means the hook
    resolved a DIFFERENT root than the orchestrator's — e.g.
    ``SHIPWRIGHT_PROJECT_ROOT`` unset and cwd is the main checkout while the
    orchestrator is working in a worktree (trg-3b206c08: now that the salvage
    file shares the canonical basename the orchestrator's own write and F6's
    directory-add target, planting it in the wrong tree is a stray the next
    fast-forward of main can collide with, not just a leftover)."""
    return not reviews_json_path(project_root, run_id).exists()


def already_recorded(project_root: Path, run_id: str, review_type: str) -> bool:
    """True iff the orchestrator already closed this review type. Reads
    ``reviews.json`` directly rather than importing the schema module (see
    module docstring) — checks both the current ``reviews`` section and the
    legacy ``gates`` section (``spec`` only — the only type ever written
    there). Any read/parse/shape failure — bad JSON, or a structurally wrong
    document (list-shaped, a section holding a non-dict) — is treated as "not
    recorded" so the salvage still runs; a redundant salvage file is
    harmless, a lost one is not. Total absence is handled by ``wrong_root``
    before this is ever called."""
    path = reviews_json_path(project_root, run_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        sections = [("reviews", review_type)]
        if review_type == "spec":
            sections.append(("gates", review_type))
        for section, key in sections:
            entry = (record.get(section) or {}).get(key)
            if entry:
                return entry.get("status", "pending") in TERMINAL_STATUSES
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        return False
    return False


def salvage_path(project_root: Path, run_id: str, review_type: str) -> Path:
    return (
        Path(project_root) / ".shipwright" / "planning" / "iterate" / run_id
        / CANONICAL_BASENAME[review_type]
    )


def resolve_project_root() -> Path:
    env = os.environ.get("SHIPWRIGHT_PROJECT_ROOT", "").strip()
    return Path(env) if env else Path.cwd()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-type", required=True,
                        choices=("spec", "code", "doubt"))
    args = parser.parse_args(argv)

    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001 — a bad payload must not block
        _diag("could not parse SubagentStop stdin payload", exception=str(exc))
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        _diag("no transcript_path in payload", payload_keys=list(payload.keys()))
        return 0

    entries = read_transcript_with_retry(transcript_path)
    if not entries:
        _diag("transcript empty — nothing to salvage", transcript_path=transcript_path)
        return 0

    run_id = extract_run_id(entries)
    if not run_id:
        _diag("no run_id found in transcript — orchestrator prompt must state it",
              review_type=args.review_type)
        return 0

    project_root = resolve_project_root()

    if wrong_root(project_root, run_id):
        _diag("no reviews.json for this run under the resolved project root — "
              "refusing to salvage (likely a stale cwd / unset "
              "SHIPWRIGHT_PROJECT_ROOT pointing outside the run's worktree)",
              run_id=run_id, project_root=str(project_root))
        return 0

    if already_recorded(project_root, run_id, args.review_type):
        _diag(f"{args.review_type} already recorded in reviews.json — hook is a no-op",
              run_id=run_id)
        return 0

    reply = last_assistant_reply(entries)
    if not reply or not looks_like_review_payload(reply):
        _diag("no salvageable review payload found in transcript", run_id=run_id)
        return 0

    out_path = salvage_path(project_root, run_id, args.review_type)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(reply, encoding="utf-8")
    except OSError as exc:
        _diag("could not write salvage file — hook must not block on it",
              run_id=run_id, out_path=str(out_path), exception=str(exc))
        return 0
    _diag(f"salvaged {args.review_type} reviewer reply: {out_path}", run_id=run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
