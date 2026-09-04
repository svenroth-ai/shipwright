"""Integration test for cleanup-review-scratch-on-code-reviewer-failure.py
through the REAL Claude Code hook-dispatch contract: invoked as its own
`uv run` subprocess, payload delivered on stdin, session/plugin identity
read from the process environment — not by importing the module and
calling `main()` in-process (that in-process coverage lives in
test_cleanup_review_scratch_on_code_reviewer_failure.py).

PR #676 round-5 external-review finding: the unit tests exercise the hook's
logic but not the actual dispatch boundary (subprocess + stdin JSON + env),
so a wiring bug there (e.g. stdin not read as expected, env var name typo)
would pass every unit test and still break in production.
"""
from __future__ import annotations

import json
import os
import subprocess  # nosec B404 B603 - fixed argv, shell=False
from pathlib import Path
from uuid import uuid4

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = PLUGIN_ROOT / "scripts" / "hooks" / "cleanup-review-scratch-on-code-reviewer-failure.py"
REPO_ROOT = PLUGIN_ROOT.parent.parent
REVIEW_SCRATCH_CLI = REPO_ROOT / "shared" / "scripts" / "tools" / "review_scratch.py"


def _write_scratch_diff(run_id: str) -> Path:
    result = subprocess.run(  # nosec B603 - fixed argv, shell=False
        ["uv", "run", str(REVIEW_SCRATCH_CLI), "resolve", "--run-id", run_id,
         "--name", "shipwright-review-diff.txt"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    diff_path = Path(result.stdout.strip())
    diff_path.write_text("diff --git a/x b/x\n", encoding="utf-8")
    return diff_path


def _cleanup_scratch(run_id: str) -> None:
    subprocess.run(  # nosec B603 - fixed argv, shell=False
        ["uv", "run", str(REVIEW_SCRATCH_CLI), "cleanup", "--run-id", run_id],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
    )


def _dispatch_hook(run_id: str, transcript_path: Path) -> subprocess.CompletedProcess:
    """Invoke the hook exactly as `hooks.json`'s SubagentStop entry does:
    `uv run <script>`, payload JSON piped on stdin, identity via env."""
    payload = json.dumps({"transcript_path": str(transcript_path)})
    return subprocess.run(  # nosec B603 - fixed argv, shell=False
        ["uv", "run", str(HOOK_PATH)],
        input=payload, cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        env={**os.environ, "SHIPWRIGHT_SESSION_ID": run_id,
             "SHIPWRIGHT_PLUGIN_ROOT": str(PLUGIN_ROOT)},
    )


def test_dispatch_preserves_the_diff_when_the_transcript_ends_in_a_review():
    run_id = f"dispatch-ok-{uuid4().hex[:12]}"
    transcript = REPO_ROOT / f".pytest_dispatch_transcript_{run_id}.jsonl"
    try:
        diff_path = _write_scratch_diff(run_id)
        transcript.write_text(
            json.dumps({"role": "assistant",
                        "content": '```json\n{"section": "x", "review": []}\n```'}),
            encoding="utf-8",
        )
        result = _dispatch_hook(run_id, transcript)
        assert result.returncode == 0, result.stderr
        assert diff_path.exists(), "a parseable review must leave the diff for Step 6c"
    finally:
        transcript.unlink(missing_ok=True)
        _cleanup_scratch(run_id)


def test_dispatch_cleans_up_the_diff_when_the_transcript_is_a_crash():
    run_id = f"dispatch-crash-{uuid4().hex[:12]}"
    transcript = REPO_ROOT / f".pytest_dispatch_transcript_{run_id}.jsonl"
    try:
        diff_path = _write_scratch_diff(run_id)
        transcript.write_text(
            json.dumps({"role": "assistant", "content": "tool error — crashed"}),
            encoding="utf-8",
        )
        result = _dispatch_hook(run_id, transcript)
        assert result.returncode == 0, result.stderr
        assert not diff_path.exists(), (
            "a crashed/malformed reply must clean up the diff through the real dispatch path"
        )
    finally:
        transcript.unlink(missing_ok=True)
        _cleanup_scratch(run_id)
