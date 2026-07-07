"""Contract lock for the ``diff-coverage-gate`` composite action.

Diff-coverage single-source-of-truth (``iterate-2026-07-07-diff-coverage-composite-action``):
the changed-line coverage GATE used to live as three hand-maintained copies (the
monorepo ``measure_diff_coverage.py`` wrapper, the WebUI ci.yml, and the vitest
adopt templates). This iterate replaces the *adopt-template* copies with a single
composite action, ``.github/actions/diff-coverage-gate/action.yml``, that the
templates (and, later, WebUI) consume via
``uses: svenroth-ai/shipwright/.github/actions/diff-coverage-gate@main``.

The action is the GATE only — coverage *production* (vitest → cobertura) stays
repo-specific, and WARN-vs-HARD is the caller's step ``continue-on-error``. This
smoke test pins the action's public contract so a consumer's ``uses:`` reference
can't silently drift: the four inputs + their defaults, the SHA-pinned setup-uv,
the pinned ``diff-cover`` invocation, and the injection-safe input plumbing
(inputs reach the shell via ``env:`` — never ``${{ inputs.* }}`` interpolated
directly into a ``run:`` body).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / ".github/actions/diff-coverage-gate/action.yml"

# A full-length commit SHA — the supply-chain-safe way to pin a third-party
# action (a mutable ``@v3`` tag can be re-pointed at malicious code).
_SHA_PIN = re.compile(r"astral-sh/setup-uv@[0-9a-f]{40}\b")


@pytest.fixture(scope="module")
def action() -> dict:
    assert ACTION_PATH.exists(), (
        f"composite action missing at {ACTION_PATH} — the diff-coverage gate's "
        f"single source of truth. Consumers reference it via "
        f"`uses: svenroth-ai/shipwright/.github/actions/diff-coverage-gate@main`."
    )
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(action: dict) -> list[dict]:
    runs = action.get("runs") or {}
    assert runs.get("using") == "composite", (
        "the diff-coverage gate must be a `composite` action so it runs as steps "
        "inside the caller's job and can read the caller's already-produced "
        "cobertura files (a reusable workflow cannot)."
    )
    return [s for s in (runs.get("steps") or []) if isinstance(s, dict)]


@pytest.fixture(scope="module")
def run_body(steps: list[dict]) -> str:
    return "\n".join(s.get("run", "") for s in steps if isinstance(s.get("run"), str))


class TestDiffCoverageActionInputs:
    def test_coverage_files_is_required(self, action: dict) -> None:
        inputs = action.get("inputs") or {}
        cov = inputs.get("coverage-files")
        assert isinstance(cov, dict) and cov.get("required") is True, (
            "`coverage-files` must be a required input — the action can't guess "
            "which cobertura report(s) to gate."
        )

    @pytest.mark.parametrize(
        "name,default",
        [
            ("compare-branch", "origin/main"),
            ("fail-under", "80"),
            ("diff-cover-version", "10.3.0"),
        ],
    )
    def test_input_defaults(self, action: dict, name: str, default: str) -> None:
        inputs = action.get("inputs") or {}
        spec = inputs.get(name)
        assert isinstance(spec, dict), f"input {name!r} missing from action.yml"
        assert str(spec.get("default")) == default, (
            f"input {name!r} default={spec.get('default')!r}, expected {default!r} "
            f"— the shipwright reference gate (warn -> prove -> flip at 80% vs "
            f"origin/main, diff-cover pinned at 10.3.0)."
        )


class TestDiffCoverageActionSteps:
    def test_setup_uv_is_sha_pinned(self, steps: list[dict]) -> None:
        uses = [s.get("uses", "") for s in steps if isinstance(s.get("uses"), str)]
        setup_uv = [u for u in uses if u.startswith("astral-sh/setup-uv@")]
        assert setup_uv, (
            "the action must install uv (adopted Node repos have no uv) via "
            "astral-sh/setup-uv before invoking uvx diff-cover."
        )
        for u in setup_uv:
            assert _SHA_PIN.search(u), (
                f"setup-uv ref {u!r} is not SHA-pinned — a third-party action "
                f"must be pinned to a full commit SHA (supply-chain hardening)."
            )

    def test_gate_threads_the_pinned_inputs(self, run_body: str) -> None:
        # The pinned version must be threaded FROM the input, adjacent to
        # `diff-cover@` — not `diff-cover@latest` with the input consumed
        # elsewhere. This ties the declared default (10.3.0) to the executed
        # command, so the two can't silently diverge.
        collapsed = run_body.replace(" ", "")
        assert "diff-cover@${INPUT_DIFF_COVER_VERSION}" in collapsed, (
            "the gate must invoke `uvx \"diff-cover@${INPUT_DIFF_COVER_VERSION}\"` — "
            "the pinned version threaded straight from the input, so a "
            "`diff-cover@latest` or hardcoded mismatch can't slip through."
        )
        # Every gate parameter flows FROM the declared input (via env), so the
        # inputs are live, not dead: a hardcoded value would let the action.yml
        # default and the effective gate silently disagree.
        for token in (
            "INPUT_COVERAGE_FILES",
            "INPUT_COMPARE_BRANCH",
            "INPUT_FAIL_UNDER",
            "INPUT_DIFF_COVER_VERSION",
        ):
            assert token in run_body, (
                f"the gate run body does not consume {token} — the corresponding "
                f"input is dead / hardcoded, so the action.yml default is a lie."
            )
        assert "--compare-branch" in run_body and "--fail-under" in run_body, (
            "the gate must pass --compare-branch and --fail-under to diff-cover."
        )

    def test_inputs_are_injection_safe(self, steps: list[dict]) -> None:
        """No ``${{ inputs.* }}`` interpolated into a ``run:`` body.

        GitHub-Actions expression injection: attacker-influenced input
        interpolated into a shell ``run:`` executes as code. Inputs must reach
        the shell via ``env:`` bindings (``$INPUT_*``) instead — the env context
        is not re-parsed as shell.
        """
        for s in steps:
            body = s.get("run")
            if not isinstance(body, str):
                continue
            assert "${{ inputs." not in body.replace(" ", ""), (
                f"step {s.get('name')!r} interpolates `${{{{ inputs.* }}}}` into its "
                f"run body — pass the input through `env:` and read `$INPUT_*` "
                f"instead (expression-injection hardening)."
            )


def _input_to_env_key(name: str) -> str:
    """`compare-branch` -> `INPUT_COMPARE_BRANCH` (the run body's convention)."""
    return "INPUT_" + name.upper().replace("-", "_")


class TestDiffCoverageActionEnvMapping:
    """The ``inputs.* -> INPUT_*`` env seam is the one surface neither the
    static run-body test nor the runtime test (which sets INPUT_* directly)
    exercises. A typo here (``inputs.compare-brnch``) or a dropped mapping
    leaves the run body reading an unbound var — ``set -u`` aborts, or
    diff-cover gets ``--compare-branch=`` — while every other test stays green.
    """

    def test_every_input_is_bound_in_env(self, action: dict, steps: list[dict]) -> None:
        inputs = action.get("inputs") or {}
        env_steps = [s for s in steps if isinstance(s.get("env"), dict)
                     and isinstance(s.get("run"), str) and "diff-cover@" in s["run"]]
        assert len(env_steps) == 1, (
            "expected exactly one composite step that both declares `env:` and "
            f"runs diff-cover; found {len(env_steps)}."
        )
        env = env_steps[0]["env"]
        # Forward: every declared input reaches the shell via its INPUT_* binding.
        for name in inputs:
            key = _input_to_env_key(name)
            assert env.get(key) == f"${{{{ inputs.{name} }}}}", (
                f"env seam broken: {key}={env.get(key)!r}, expected "
                f"`${{{{ inputs.{name} }}}}`. A dropped/typo'd mapping leaves the "
                f"run body reading an unbound var at runtime."
            )
        # Reverse: no stray INPUT_* env key without a matching declared input.
        for key, value in env.items():
            if not key.startswith("INPUT_"):
                continue
            assert any(_input_to_env_key(n) == key for n in inputs), (
                f"env key {key!r} does not correspond to any declared input — "
                f"dead binding or a renamed input the run body still expects."
            )
