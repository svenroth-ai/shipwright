"""Regression: update-marketplace.sh must verify the marketplace clone is
actually at origin/main's tip before syncing files into the cache.

Root cause (cache-sync-add-detection-gap): Step 1's happy path (``claude
plugin marketplace update`` exiting 0) was trusted blindly. Only the SSH
failure fallback did a verified ``git fetch`` + ``reset --hard`` against
``origin/main``. If the CLI's internal update has any staleness window, a
"successful" run can leave the marketplace clone lagging the true remote tip,
and Steps 2-3 then faithfully copy that stale source into the cache while
reporting no error — reproducing the reported symptom: a routine
update-marketplace.sh + check_plugin_cache_sync.py --strict pass, yet
recently-landed files under shared/scripts/lib and shared/scripts/tools/tests
still show as missing-in-cache. The fix cross-checks the clone's HEAD against
the true remote tip UNCONDITIONALLY (not just inside the fallback branch) and
forces a hard sync when they disagree, before any file is copied.

Follows the ``bash``-via-subprocess convention in
``test_installer_shell_scripts.py`` (ADR-044 CI-discipline: hard-fail in CI on
a missing ``bash``, skip locally).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "update-marketplace.sh"

sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402


def _read() -> str:
    return UPDATE_SH.read_text(encoding="utf-8")


def _require_bash_and_git() -> None:
    skip_or_fail_on_missing_binary("bash", "bash ships on every CI runner; install Git Bash locally")
    skip_or_fail_on_missing_binary("git", "git ships on every CI runner")


# Anchors the freshness-check block by its own comment header rather than by
# bracket-matching the CLI if/else's `fi` — that block nests a second `if`
# (the SSH-fallback's `[ -d "$MARKETPLACE_DIR/.git" ]` branch), so the FIRST
# `fi` after the outer `if` is the inner one's, not the outer close.
_VERIFY_MARKER = "# Verify the clone actually reached origin/main's true tip."


def _verification_block() -> str:
    """The freshness-check block: from its own header comment through the
    start of Step 2's file-sync loop. Extracted from the real script so the
    behavioral test below exercises exactly what ships, not a copy that can
    drift from it."""
    src = _read()
    start = src.index(_VERIFY_MARKER)
    end = src.index("# Step 2: Full file sync")
    return src[start:end]


def test_freshness_is_verified_unconditionally_not_only_in_the_fallback_branch():
    src = _read()
    # The marker itself must sit AFTER the if/else CLI-vs-fallback block's
    # own (zero-indented) closing `fi` — not nested only inside the `else`
    # (SSH-failure) branch, whose body is indented — otherwise a
    # "successful" CLI update path would skip it entirely. A bare `\nfi\n`
    # (no leading whitespace) can only be that outer close: every `fi`
    # nested inside the branches is indented in this script.
    cli_if = src.index("if claude plugin marketplace update")
    outer_fi = re.search(r"\nfi\n", src[cli_if:])
    assert outer_fi, "could not find the CLI-vs-fallback if/else's own closing `fi`"
    outer_fi_end = cli_if + outer_fi.end()
    marker_pos = src.index(_VERIFY_MARKER)
    assert marker_pos > outer_fi_end, (
        "the freshness-check marker sits inside the CLI-vs-fallback if/else "
        "(possibly only in the SSH-failure branch) — a 'successful' CLI "
        "update path would skip it"
    )
    block = _verification_block()
    assert re.search(r"ls-remote|rev-parse\s+HEAD", block), (
        "no freshness verification found after the CLI-update if/else block — "
        "a 'successful' claude plugin marketplace update is still trusted "
        "without confirming the clone reached origin/main's true tip"
    )


def _make_remote_and_stale_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A bare-ish 'remote' 2 commits ahead of a clone taken after commit 1 —
    the exact shape of "a file landed on main just ahead of the sync run"."""
    remote = tmp_path / "remote_repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.name", "t"], check=True)
    (remote / "file1.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "-C", str(remote), "add", "."], check=True)
    subprocess.run(["git", "-C", str(remote), "commit", "-q", "-m", "c1"], check=True)

    clone = tmp_path / "clone_dir"
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True,
                    capture_output=True)

    # The file that "landed on main just ahead of the sync run".
    (remote / "file2.txt").write_text("b", encoding="utf-8")
    subprocess.run(["git", "-C", str(remote), "add", "."], check=True)
    subprocess.run(["git", "-C", str(remote), "commit", "-q", "-m", "c2 (new file lands)"], check=True)
    return remote, clone


def test_stale_clone_is_hard_synced_to_the_true_remote_tip_before_any_copy(tmp_path):
    """Drive the REAL extracted block against a clone that lags the remote by
    one commit — exactly the reported race. It must end up at the remote's
    tip, with the recently-landed file present, before Step 2 would run."""
    _require_bash_and_git()
    remote, clone = _make_remote_and_stale_clone(tmp_path)

    script = (
        'set -euo pipefail\n'
        f'MARKETPLACE_DIR="{clone.as_posix()}"\n'
        f'HTTPS_URL="{remote.as_posix()}"\n'
        + _verification_block()
    )
    res = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert res.returncode == 0, f"verification block aborted: {res.stderr}"
    assert (clone / "file2.txt").exists(), (
        "clone was not hard-synced to the remote's true tip — the recently-"
        f"landed file is still missing after the check. stdout={res.stdout!r} "
        f"stderr={res.stderr!r}"
    )
    remote_head = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    clone_head = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert clone_head == remote_head, "clone HEAD does not match the remote's true tip"


def test_clone_already_at_remote_tip_is_left_alone(tmp_path):
    """No drift, no false action: a clone already at the remote's tip must
    not be touched (no needless network operation, no reset noise)."""
    _require_bash_and_git()
    remote = tmp_path / "remote_repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.name", "t"], check=True)
    (remote / "file1.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "-C", str(remote), "add", "."], check=True)
    subprocess.run(["git", "-C", str(remote), "commit", "-q", "-m", "c1"], check=True)
    clone = tmp_path / "clone_dir"
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True,
                    capture_output=True)

    script = (
        'set -euo pipefail\n'
        f'MARKETPLACE_DIR="{clone.as_posix()}"\n'
        f'HTTPS_URL="{remote.as_posix()}"\n'
        + _verification_block()
    )
    res = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert res.returncode == 0, f"verification block aborted on an in-sync clone: {res.stderr}"
    assert "lagging" not in res.stdout, (
        f"an already-fresh clone was reported as lagging: {res.stdout!r}"
    )


def test_unreachable_remote_degrades_instead_of_aborting_the_sync(tmp_path):
    """`set -euo pipefail` is active in the real script — an `ls-remote` that
    fails outright (offline / unreachable HTTPS_URL) must not abort the whole
    sync, only skip this check, same as every other advisory probe here."""
    _require_bash_and_git()
    clone = tmp_path / "clone_dir"
    subprocess.run(["git", "init", "-q", "-b", "main", str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "user.name", "t"], check=True)
    (clone / "file1.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "."], check=True)
    subprocess.run(["git", "-C", str(clone), "commit", "-q", "-m", "c1"], check=True)

    unreachable = tmp_path / "does_not_exist_remote"
    script = (
        'set -euo pipefail\n'
        f'MARKETPLACE_DIR="{clone.as_posix()}"\n'
        f'HTTPS_URL="{unreachable.as_posix()}"\n'
        + _verification_block()
        + '\necho "SURVIVED"\n'
    )
    res = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert res.returncode == 0, (
        f"an unreachable remote aborted the whole sync instead of degrading: "
        f"rc={res.returncode} stderr={res.stderr!r}"
    )
    assert "SURVIVED" in res.stdout, (
        f"script did not reach the line after the verification block: {res.stdout!r}"
    )
