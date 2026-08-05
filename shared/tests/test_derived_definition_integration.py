"""END-TO-END: the churn resolver and the F11 revert gate agree on "derived".

`cross_component` integration coverage for
iterate-2026-07-28-f11-verifies-own-run. Two components that never call each
other, on real git, in the scenario where their disagreement bites:

  - `lib.churn_merge.classify` — what the MERGE RESOLVER may auto-resolve when
    an integration conflicts;
  - `verifiers.silent_revert.dropped_lines` — what the F11 GATE exempts from
    line-by-line comparison after that integration.

They used to hold different answers. The verifier asked `path in
CHURN_ALLOWLIST`; the resolver asked `... or is_campaign_status(rel)`. A campaign
`status.json` therefore came out of the resolver as regenerated churn — resolved
wholesale to one side by design — and went into the gate as authored content
whose every replaced line reads as work being thrown away. Unit tests on either
side pass in both worlds; only the composition shows it.

The scenario is the real one: a branch integrates `main`, `main` had regenerated
the campaign board meanwhile, and the branch's own regeneration wins. Not marked
`slow` — it is a handful of git calls and should gate in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.churn_merge import classify  # noqa: E402
from tools.verifiers.silent_revert import dropped_lines  # noqa: E402

CAMPAIGN_STATUS = ".shipwright/planning/iterate/campaigns/it3-probe/status.json"
AUTHORED = "docs/hand-written.md"
THROUGHPUT_REPORT = ".shipwright/compliance/performance/iterate-throughput.md"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", check=False)
    return result


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _board(*slugs: str) -> str:
    """A campaign board — regenerated wholesale from the event log every time."""
    return json.dumps(
        {"campaign": "it3-probe", "units": [{"id": s, "status": "merged"} for s in slugs]},
        indent=2,
    ) + "\n"


@pytest.fixture
def integrated(tmp_path: Path) -> Path:
    """A branch that has integrated `main`, both sides having regenerated."""
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")

    _write(root, CAMPAIGN_STATUS, _board("s1"))
    _write(root, AUTHORED, "line one\nline two\n")
    _commit(root, "fork point")

    _git(root, "checkout", "-q", "-b", "iterate/x")
    # main moves: the board is regenerated, and a human adds a paragraph.
    _git(root, "checkout", "-q", "main")
    _write(root, CAMPAIGN_STATUS, _board("s1", "s2", "s3"))
    _write(root, AUTHORED, "line one\nline two\nline three from main\n")
    _commit(root, "main regenerates the board and gains prose")

    # The branch regenerates its own board from ITS event log, then integrates.
    _git(root, "checkout", "-q", "iterate/x")
    _write(root, CAMPAIGN_STATUS, _board("s1", "s9"))
    _commit(root, "branch regenerates the board")
    _git(root, "merge", "-q", "--no-edit", "-X", "ours", "main")
    # Resolve the way the churn resolver does: the branch's regeneration stands,
    # main's authored prose is kept.
    _write(root, CAMPAIGN_STATUS, _board("s1", "s9"))
    _write(root, AUTHORED, "line one\nline two\nline three from main\n")
    _commit(root, "regenerate-at-merge resolution")
    return root


def test_the_two_components_agree_on_the_campaign_board(integrated: Path):
    """The composition claim: what the resolver auto-resolves, the gate exempts."""
    resolvable, blocking = classify([CAMPAIGN_STATUS, AUTHORED])
    assert resolvable == [CAMPAIGN_STATUS]
    assert blocking == [AUTHORED]

    dropped = dropped_lines(integrated, "main")

    assert CAMPAIGN_STATUS not in dropped, (
        "the merge resolver regenerates this file wholesale, so the F11 gate "
        "must not read its replaced lines as work thrown away"
    )


@pytest.fixture
def integrated_with_throughput_report(tmp_path: Path) -> Path:
    """Same real-git-integration scenario as ``integrated`` above, for
    ``THROUGHPUT_REPORT`` — the churn artifact registered by
    iterate-2026-08-04-iterate-timing-attribution — instead of the campaign
    board. Proves the same cross-component composition claim for the newly
    added `CHURN_ALLOWLIST` member, not just the pre-existing one."""
    root = tmp_path / "repo2"
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")

    _write(root, THROUGHPUT_REPORT, "# throughput v1\n")
    _write(root, AUTHORED, "line one\nline two\n")
    _commit(root, "fork point")

    _git(root, "checkout", "-q", "-b", "iterate/y")
    # main moves: the report is regenerated, and a human adds a paragraph.
    _git(root, "checkout", "-q", "main")
    _write(root, THROUGHPUT_REPORT, "# throughput v2 (main)\n")
    _write(root, AUTHORED, "line one\nline two\nline three from main\n")
    _commit(root, "main regenerates the report and gains prose")

    # The branch regenerates its own report, then integrates.
    _git(root, "checkout", "-q", "iterate/y")
    _write(root, THROUGHPUT_REPORT, "# throughput v2 (branch)\n")
    _commit(root, "branch regenerates the report")
    _git(root, "merge", "-q", "--no-edit", "-X", "ours", "main")
    _write(root, THROUGHPUT_REPORT, "# throughput v2 (branch)\n")
    _write(root, AUTHORED, "line one\nline two\nline three from main\n")
    _commit(root, "regenerate-at-merge resolution")
    return root


def test_the_two_components_agree_on_the_throughput_report(
        integrated_with_throughput_report: Path):
    """The same composition claim as the campaign board test, for
    THROUGHPUT_REPORT: what the resolver auto-resolves, the gate exempts."""
    resolvable, blocking = classify([THROUGHPUT_REPORT, AUTHORED])
    assert resolvable == [THROUGHPUT_REPORT]
    assert blocking == [AUTHORED]

    dropped = dropped_lines(integrated_with_throughput_report, "main")

    assert THROUGHPUT_REPORT not in dropped, (
        "the merge resolver treats this as regenerated churn (--theirs), so "
        "the F11 gate must not read its replaced content as work thrown away"
    )


def test_the_gate_still_reports_a_real_loss_in_the_same_integration(integrated: Path):
    """The control. Without it, a gate that exempted EVERYTHING would pass the
    test above — the campaign board is only interesting next to a path that is
    genuinely compared."""
    _write(integrated, AUTHORED, "line one\nline two\n")   # drop main's paragraph
    _commit(integrated, "silently revert main's prose")

    dropped = dropped_lines(integrated, "main")

    assert AUTHORED in dropped
    assert any("line three from main" in line for line in dropped[AUTHORED])
    assert CAMPAIGN_STATUS not in dropped
