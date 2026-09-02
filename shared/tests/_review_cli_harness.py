"""Shared harness for the `record_review_pass.py` CLI tests.

Not named ``test_*``, so pytest does not collect it. It exists because
``test_record_review_pass_cli.py`` reached 496 lines against a 300-line limit
with roughly 90 of them being setup — fixture, subprocess wrapper and the
reviewer-reply payloads — that every group of tests needs. Splitting the file
along its own section headers without lifting this out would have duplicated
the setup three times.

The fixtures live here rather than in ``shared/tests/conftest.py`` on purpose:
that conftest is loaded for the whole shared suite, and a `project` fixture
visible to ~5900 unrelated tests is a name collision waiting to happen.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

TOOL = str(_SHARED / "scripts" / "tools" / "record_review_pass.py")
RUN_ID = "iterate-2026-07-21-review-record"
REASON = "docs-only diff; the doubt pass is conditional per iteration-reviews.md"

CODE_REVIEWER_REPLY = """\
Here is my review.

```json
{"section": "review-record", "review": [
  {"severity": "high", "category": "correctness", "file": "lib/x.py", "line": 12,
   "finding": "the lock is released before the write", "suggestion": "widen the lock"}
]}
```
"""

DOUBT_REVIEWER_REPLY = json.dumps({
    "stage": "doubt", "gating": "advisory-must-address", "trigger": "io-boundary",
    "doubts": [{"severity": "medium", "lens": "reversibility",
                "claim_under_doubt": "the record is safe to rewrite",
                "disproof_attempt": "a terminal status can be overwritten with --force",
                "what_would_resolve_it": "log every forced overwrite"}],
})

SELF_REVIEW_REPLY = json.dumps({"items": [
    {"name": "Spec Compliance", "verdict": "pass", "note": "all ACs covered"},
    {"name": "Test Quality", "verdict": "fail", "note": "no error-path test on the CLI"},
]})

EXTERNAL_REVIEW_OUTPUT = json.dumps({
    "review_schema": 2, "success": True, "provider": "openrouter",
    "reviews": {
        "glm": {"status": "success", "feedback":
                   "- **Category:** Risk\n- **Severity:** Medium\n"
                   "- **Finding:** The gate blocks in-flight runs.\n\n"
                   "SHIPWRIGHT_VERDICT: approve\n"},
        "openai": {"status": "success", "feedback":
                   "- Category: bug\n- Severity: high\n- File: tools/x.py:7\n"
                   "- Finding: the marker write is not transactional.\n\n"
                   "SHIPWRIGHT_VERDICT: revise\n"},
    },
})


def make_project(tmp_path):
    """Build the project tree the CLI writes into. A plain function, not a fixture.

    Each test module wraps this in its own one-line ``project`` fixture instead
    of importing a fixture from here. Importing a fixture makes ruff read every
    test that takes ``project`` as a parameter as an F811 redefinition of the
    imported name — 28 of them — and silencing that per test would be noisier
    than the three lines the wrapper costs.
    """
    iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True)
    (iterates / f"{RUN_ID}.json").write_text(json.dumps({
        "run_id": RUN_ID, "date": "2026-07-21T00:00:00+00:00", "type": "feature",
        "complexity": "medium", "branch": "iterate/review-record", "tests_passed": True,
    }), encoding="utf-8")
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    return tmp_path


def run_tool(project, *args):
    result = subprocess.run(
        [sys.executable, TOOL, *args, "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    return result.returncode, result.stdout + result.stderr


def payload(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)
