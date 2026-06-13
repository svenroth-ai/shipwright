"""WP2/F13: the Stop-fallback's outer ``update-step`` timeout must strictly
exceed the inner compliance subprocess timeout.

If outer <= inner, the inner compliance subprocess can consume the whole outer
budget and the orchestrator is killed before ``save_run_config`` marks the
phase complete — a permanent ~30 s stall per Stop with the phase never
completing. We assert the ACTUAL timeout wired into the subprocess call (not
just two constants) by capturing the kwarg generate_handoff_on_stop passes.

Lives in the shipwright-run session: it pairs the shared Stop hook
(``generate_handoff_on_stop``) with this plugin's compliance timeout
constant, so ``orchestrator_pkg.compliance_runner`` is a native import here.
"""
import sys
from pathlib import Path

_PARENTS = Path(__file__).resolve().parents
_RUN_LIB = _PARENTS[1] / "scripts" / "lib"
_HOOKS = _PARENTS[3] / "shared" / "scripts" / "hooks"
for _p in (str(_RUN_LIB), str(_HOOKS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import generate_handoff_on_stop as gh  # noqa: E402
from orchestrator_pkg.compliance_runner import (  # noqa: E402
    COMPLIANCE_SUBPROCESS_TIMEOUT_SECONDS,
)


def test_phase_completion_outer_timeout_exceeds_compliance_inner(tmp_path, mocker):
    captured = {}

    def _fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        captured["cmd"] = args[0] if args else kwargs.get("args")

        class _Result:  # minimal subprocess.CompletedProcess stand-in
            returncode = 0

        return _Result()

    mocker.patch.object(gh.subprocess, "run", side_effect=_fake_run)

    # The orchestrator script exists in-repo, so the guard passes and
    # subprocess.run is invoked (then captured).
    gh._run_phase_completion(tmp_path, "project")

    # It is the Stop-fallback phase-completion call we are measuring, not some
    # other subprocess that happens to use a >30s timeout.
    cmd = captured.get("cmd") or []
    assert "update-step" in cmd and "complete" in cmd, f"unexpected fallback command: {cmd}"

    assert captured.get("timeout") is not None, "subprocess.run was not invoked"
    assert captured["timeout"] > COMPLIANCE_SUBPROCESS_TIMEOUT_SECONDS, (
        f"outer Stop-fallback timeout {captured['timeout']} must strictly exceed "
        f"inner compliance timeout {COMPLIANCE_SUBPROCESS_TIMEOUT_SECONDS}"
    )
