"""Behavioral tests for update-marketplace.sh's discard-path naming and
collision handling during lock reclamation.

Split out of ``test_marketplace_lock_ownership.py`` (which crossed the
300-line guideline for a third time) when the round-16 fix and its
regression tests pushed it over again. This file covers only how the
discard path itself is chosen before a reclaim's claiming `mv` runs: making
every attempt's name unique (round 14), then making it unique even across
separate process runs after pid reuse, with a bounded retry on collision
(round 16). What happens once a discard is already claimed — the ABA
mismatch check and restore/preserve logic — stays in the
``test_marketplace_lock_ownership.py`` sibling file.

Extracts functions out of the real script and drives them against fixture
trees under ``bash``, rather than sourcing the whole script (which would
immediately try to fetch the real marketplace). The closing brace of a
top-level function sits at column 0; an inner loop/if's closing brace is
indented — that is what lets a non-greedy ``^\\}`` anchor find the right one
without a real bash parser.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "update-marketplace.sh"
_SRC = UPDATE_SH.read_text(encoding="utf-8")


def _extract(name: str) -> str:
    m = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", _SRC, flags=re.DOTALL | re.MULTILINE)
    assert m, f"could not find {name}() in update-marketplace.sh — has it been renamed?"
    return f"{name}() {{\n{m.group(1)}}}"


def _require_bash() -> None:
    if not shutil.which("bash"):
        pytest.fail("bash ships on every CI runner; install Git Bash locally")


def _run_script(script: str, **kwargs) -> subprocess.CompletedProcess:
    """Writes the script to a temp file and runs `bash <file>` instead of
    `bash -c <script>` — extracted function text can run well past 8000
    characters, and Windows' classic ~8191-char command-line limit truncated
    it mid-function when passed inline, producing a baffling "unexpected end
    of file" bash syntax error with no size hint anywhere in it."""
    _require_bash()
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as f:
        f.write(script)
        script_path = f.name
    try:
        return subprocess.run(["bash", script_path], capture_output=True, text=True, **kwargs)
    finally:
        Path(script_path).unlink(missing_ok=True)


def _p(path: Path) -> str:
    """Windows backslash paths break bash's own string ops (rel_path
    stripping, dirname); Git Bash/MSYS accepts the forward-slash form."""
    return path.as_posix()


def test_second_reclaim_attempt_does_not_collide_with_a_stale_leftover_after_pid_reuse(tmp_path):
    """Tier-3 review, PR #796 round 16: `${lock}.stale.${reclaim_seq}.$$`
    (round 14) is unique only WITHIN one process's own reclaim attempts —
    reclaim_seq always restarts at 1 for a brand-new process, so after the OS
    recycles a pid, a fresh process's very FIRST reclaim attempt can compute
    the exact path an old, un-swept leftover from a long-dead, unrelated
    process (same recycled pid) already occupies. A bare (non `-T`)
    `mv "$lock" "$discard"` onto that existing directory moves the source
    INSIDE it instead of failing — the round-11 nesting gotcha again, this
    time via cross-run pid reuse rather than same-process reuse. The fix
    folds a random per-attempt token into the name and checks the candidate
    is genuinely free before committing, retrying with a fresh token on
    collision (round 16) — reproduced by pinning the token generator so its
    first draw collides with a pre-existing foreign leftover."""
    body = _extract("_atomic_sync_dir")
    start = body.index('local discard="" _discard_try _discard_candidate')
    end = body.index("# No unconditional", start)
    reclaim_snippet = body[start:end]

    lock = tmp_path / "dst.sync.lock"
    lock.mkdir()
    (lock / "pid").write_text("third_process_pid", encoding="utf-8")
    (lock / "token").write_text("third_process_token", encoding="utf-8")

    call_count_file = tmp_path / "call_count"
    script = ("set -euo pipefail\n"
              + f'call_count_file="{_p(call_count_file)}"\n'
              + 'echo 0 > "$call_count_file"\n'
              # `$(_new_claim_token)` runs in a SUBSHELL — a plain variable
              # increment inside it never reaches the parent script, so the
              # counter has to live in a file instead.
              + '_new_claim_token() {\n'
              + '    local n\n'
              + '    n=$(($(cat "$call_count_file") + 1))\n'
              + '    echo "$n" > "$call_count_file"\n'
              + '    if [ "$n" -eq 1 ]; then printf "collide"; '
              + 'else printf "fresh-%s" "$n"; fi\n'
              + '}\n'
              + f'lock="{_p(lock)}"\n'
              + 'foreign_discard="${lock}.stale.collide.$$"\n'
              + 'mkdir -p "$foreign_discard"\n'
              + 'echo "attempt1_orphan_pid" > "$foreign_discard/pid"\n'
              + 'holder_pid="third_process_pid"\n'
              + 'holder_token="third_process_token"\n'
              + 'empty_pid_waits=0\n'
              + "_reclaim() {\n" + reclaim_snippet + "\n}\n_reclaim\n"
              + 'echo "CALLS=$(cat "$call_count_file")"\n'
              + 'echo "FOREIGN_SURVIVED=$([ -d "$foreign_discard" ] && echo yes || echo no)"\n'
              + 'echo "FOREIGN_PID=$(cat "$foreign_discard/pid" 2>/dev/null || echo MISSING)"\n'
              + 'echo "FOREIGN_NESTED_COUNT=$(find "$foreign_discard" -mindepth 1 -maxdepth 1 -type d | wc -l)"\n'
              + 'echo "STALE_DIR_COUNT=$(find "' + _p(tmp_path)
              + '" -maxdepth 1 -name "dst.sync.lock.stale.*" | wc -l)"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert "CALLS=2" in res.stdout, (
        "expected exactly one retry past the colliding first candidate — " + res.stdout)
    assert "FOREIGN_SURVIVED=yes" in res.stdout, (
        "the pre-existing foreign leftover was destroyed instead of skipped — " + res.stdout)
    assert "FOREIGN_PID=attempt1_orphan_pid" in res.stdout, (
        "the pre-existing foreign leftover's content was overwritten — " + res.stdout)
    assert "FOREIGN_NESTED_COUNT=0" in res.stdout, (
        "the reclaim was nested inside the pre-existing foreign leftover instead of "
        "using its own distinct, collision-checked discard path — " + res.stdout)
    assert "STALE_DIR_COUNT=1" in res.stdout, (
        "expected only the untouched foreign leftover to remain once the matched "
        "reclaim's own discard was safely deleted — " + res.stdout)


def test_discard_path_selection_gives_up_after_five_colliding_candidates(tmp_path):
    """Tier-3 review, PR #796 round 16: the retry is bounded (5 attempts) —
    if every candidate the loop tries is already taken (in practice: never,
    since the token is high-entropy), it must give up rather than force a
    claim onto an occupied name. Stubs the token generator to always return
    the same value so every candidate collides with one pre-existing
    directory, and confirms "$lock" itself is left completely untouched."""
    body = _extract("_atomic_sync_dir")
    start = body.index('local discard="" _discard_try _discard_candidate')
    end = body.index("# No unconditional", start)
    selection_snippet = body[start:end]

    lock = tmp_path / "dst.sync.lock"
    lock.mkdir()
    (lock / "pid").write_text("live_pid", encoding="utf-8")

    script = ("set -uo pipefail\n"  # no -e: `continue` outside a loop "fails" here on purpose
              + '_new_claim_token() { printf "always-same"; }\n'
              + f'lock="{_p(lock)}"\n'
              + 'precreated="${lock}.stale.always-same.$$"\n'
              + 'mkdir -p "$precreated"\n'
              + 'empty_pid_waits=99\n'
              + "_select() {\n" + selection_snippet + "\n"
              + '    echo "DISCARD=[$discard]"\n'
              + "}\n_select\n"
              + 'echo "EMPTY_PID_WAITS_AFTER=$empty_pid_waits"\n'
              + 'echo "LOCK_EXISTS=$([ -d "$lock" ] && echo yes || echo no)"\n'
              + 'echo "LOCK_PID=$(cat "$lock/pid" 2>/dev/null || echo MISSING)"\n')
    res = _run_script(script)

    assert res.returncode == 0, res.stderr
    assert "DISCARD=[]" in res.stdout, (
        "expected an empty $discard once every candidate in the retry budget collided — " + res.stdout)
    assert "EMPTY_PID_WAITS_AFTER=0" in res.stdout, (
        "exhausting the retry budget must reset empty_pid_waits so the outer loop treats "
        "this the same as losing the reclaim race outright — " + res.stdout)
    assert "LOCK_EXISTS=yes" in res.stdout, (
        "\"$lock\" must be left untouched when no free discard path could be found — " + res.stdout)
    assert "LOCK_PID=live_pid" in res.stdout, (
        "\"$lock\"'s content was modified despite the reclaim giving up before any mv — " + res.stdout)
