"""Hook block-channel contract test (WP4 / iterate-2026-06-13-hook-block-channel).

The acceptance criterion: a hook's block/warn reason MUST be delivered on the
channel the event *actually reads*. Claude Code's channels are per-event:

  * **PostToolUse + exit 2** -> Claude reads **stderr**; stdout is DISCARDED.
  * **SessionStart**         -> Claude reads **stdout** (additionalContext,
    exit 0); it CANNOT block a session.

Before this fix the two PostToolUse security guards (``check_secrets.sh`` and
the registered ``check_destructive_migration.sh``) emitted their block payload
as JSON on stdout then ``exit 2`` -> the warning was thrown away. The
SessionStart artifact-drift gate claimed a ``migrated`` hard-stop (JSON on
stdout + ``exit 1``) that SessionStart cannot perform -> inert. These tests pin
the reason to the readable channel per event so the bug cannot regress.

This is a sibling of ``test_hook_output_schema_compliance.py`` rather than an
appended case there, because that file is grandfathered at its bloat baseline
``current`` — appending would trip the anti-ratchet gate. It is self-contained
(no cross-test-module import) so collection order / sys.path setup cannot break
it. The SessionStart channel check mirrors that module's per-event schema map.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_hygiene import is_ci

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Mirror of test_hook_output_schema_compliance's SessionStart contract:
# hookSpecificOutput may carry only these fields, plus a small set of allowed
# top-level keys. Kept inline (not imported) for collection robustness.
_SESSIONSTART_HSO_FIELDS = {"hookEventName", "additionalContext"}
_ALLOWED_TOP_LEVEL = {
    "hookSpecificOutput", "decision", "reason",
    "suppressOutput", "continue", "stopReason", "systemMessage",
}


def _aws_example_key() -> str:
    # Built by concatenation so THIS test file does not itself carry a literal
    # ``AKIA…`` token that the runtime check_secrets.sh / gitleaks scanners
    # would flag. The fixture file written at run time gets the full key.
    return "AKIA" + "IOSFODNN7" + "EXAMPLE"


# Registered PostToolUse security guards + a triggering fixture for each.
#   (script path rel-to-repo, fixture rel-path, content, reason substring)
# The destructive-migration entry deliberately targets the REGISTERED build
# copy (wired in plugins/shipwright-build/hooks/hooks.json), where the
# stdout-channel bug lived — not the already-stderr shared copy.
_POSTTOOLUSE_GUARDS = [
    (
        "shared/scripts/hooks/check_secrets.sh",
        "leak.py",
        f'AWS_KEY = "{_aws_example_key()}"\n',
        "AWS Access Key",
    ),
    (
        "plugins/shipwright-build/scripts/hooks/check_destructive_migration.sh",
        "supabase/migrations/002_drop_old.sql",
        "DROP TABLE old_users;\n",
        "DESTRUCTIVE",
    ),
]


def _require(binary: str) -> None:
    if shutil.which(binary) is None:
        msg = f"{binary} not on PATH; cannot exercise the hook command."
        if is_ci():
            pytest.fail(msg, pytrace=False)
        pytest.skip(msg)


@pytest.mark.parametrize(
    "script_rel, fixture_rel, content, reason_substr",
    _POSTTOOLUSE_GUARDS,
    ids=[g[0].rsplit("/", 1)[-1] for g in _POSTTOOLUSE_GUARDS],
)
def test_posttooluse_guard_reason_on_stderr(
    script_rel: str, fixture_rel: str, content: str, reason_substr: str, tmp_path: Path
) -> None:
    """A PostToolUse guard that soft-blocks (exit 2) MUST put its reason on
    STDERR — the only channel Claude reads on exit 2 — never solely on the
    discarded stdout."""
    _require("bash")
    script = _REPO_ROOT / script_rel
    assert script.exists(), f"registered guard missing: {script_rel}"

    target = tmp_path / fixture_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    payload = json.dumps({"tool_input": {"file_path": str(target)}})
    result = subprocess.run(
        ["bash", str(script)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 2, (
        f"{script_rel} should soft-block (exit 2); got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # The reason reaches the model: it is on STDERR (the exit-2 channel).
    assert reason_substr in result.stderr, (
        f"{script_rel}: block reason not on stderr — the channel Claude reads "
        f"on exit 2.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # ...and it is NOT stranded on stdout, which Claude DISCARDS on exit 2.
    assert reason_substr not in result.stdout, (
        f"{script_rel}: block reason on stdout, which Claude DISCARDS on exit 2 "
        f"(regression of the hook-block-channel bug)."
    )


def _migrated_legacy_dirname() -> str:
    """A real 'migrated' legacy dirname from the registry — derived (not a
    literal) so this test carries no legacy-path string (artifact-path-canon
    clean) and tracks whatever migration is actually flipped to migrated."""
    shared_scripts = _REPO_ROOT / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    from lib.artifact_migrations import active_migrations  # type: ignore

    migrated = [m for m in active_migrations() if m["status"] == "migrated"]
    assert migrated, "expected at least one migrated artifact migration in the registry"
    return migrated[0]["legacy_dirname"]


def test_sessionstart_drift_reason_on_stdout_additionalcontext(tmp_path: Path) -> None:
    """The SessionStart artifact-drift gate cannot block a session, so it MUST
    deliver its warning to the model via the channel SessionStart reads —
    schema-valid ``additionalContext`` on stdout, exit 0 (honest warn-only) —
    never a fake ``exit 1`` 'hard-gate' the model never sees."""
    _require("uv")
    legacy_dirname = _migrated_legacy_dirname()

    # Minimal Shipwright project marker so the root resolves HERE, then recreate
    # the relocated legacy dir at its root to trigger a 'migrated' (block) finding.
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "profile": "test"}), encoding="utf-8"
    )
    legacy = tmp_path / legacy_dirname
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "leftover.txt").write_text("x", encoding="utf-8")

    script = _REPO_ROOT / "shared" / "scripts" / "hooks" / "check_artifact_drift.py"
    env = os.environ.copy()
    # The hook honors SHIPWRIGHT_PROJECT_ROOT first — pin it to tmp_path so it
    # cannot resolve to the real repo (which has no top-level legacy dir).
    env["SHIPWRIGHT_PROJECT_ROOT"] = str(tmp_path)
    result = subprocess.run(
        ["uv", "run", str(script)],
        input=json.dumps({"hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env=env,
        timeout=90,
    )

    # SessionStart cannot block: the honest contract is exit 0 (warn-only).
    assert result.returncode == 0, (
        f"SessionStart drift gate must not pretend to hard-block (exit non-zero); "
        f"got {result.returncode}.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # The reason is on the channel SessionStart reads: a schema-valid
    # additionalContext JSON object on stdout.
    payload = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            payload = json.loads(line)
            break
    assert payload is not None, (
        f"no additionalContext JSON on stdout (the SessionStart channel).\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # Schema-valid SessionStart envelope (mirror of the schema-compliance map).
    assert set(payload) <= _ALLOWED_TOP_LEVEL, f"unexpected top-level keys: {set(payload)}"
    hso = payload.get("hookSpecificOutput")
    assert isinstance(hso, dict), f"missing hookSpecificOutput: {payload!r}"
    assert set(hso) <= _SESSIONSTART_HSO_FIELDS, f"bad hookSpecificOutput fields: {set(hso)}"
    assert hso.get("hookEventName") == "SessionStart"
    ctx = hso.get("additionalContext", "")
    assert "git mv" in ctx, f"expected the git-mv remediation in additionalContext; got {ctx!r}"
    # A human-facing notice still goes to stderr.
    assert "drift" in result.stderr.lower(), (
        f"expected a stderr drift notice for the human; stderr={result.stderr!r}"
    )
