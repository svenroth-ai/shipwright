"""Behavioral regression tests for the top-level installer/shell scripts.

Covers WP10 (deep-audit 2026-06-10, findings F33-F38) of the recommended POSIX
install path across ``scripts/{install,update-marketplace,verify-setup}.sh``:
F33 ``((missing++))`` aborts under ``set -e``; F34 uv PATH (~/.local/bin vs
~/.cargo/bin); F35 alias omits adopt + stale-alias skip guard; F36 unquoted
``$REPO_ROOT`` splits on spaces; F37 bare ``python`` aborts where only
``python3`` exists; F38 ``source``-ing ``.env.local`` executes spaced values.

The tests drive the scripts through ``bash`` via subprocess. Per ADR-044
CI-discipline the missing-``bash`` guard hard-fails in CI (ubuntu ships bash)
and skips locally.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
UPDATE_SH = REPO_ROOT / "scripts" / "update-marketplace.sh"
VERIFY_SH = REPO_ROOT / "scripts" / "verify-setup.sh"

PLUGIN_NAMES = (
    "shipwright-run", "shipwright-project", "shipwright-design",
    "shipwright-iterate", "shipwright-plan", "shipwright-build",
    "shipwright-test", "shipwright-deploy", "shipwright-changelog",
    "shipwright-compliance", "shipwright-security", "shipwright-preview",
    "shipwright-adopt",
)


def _require_bash() -> None:
    skip_or_fail_on_missing_binary("bash", "bash ships on every CI runner; install Git Bash locally")


def _bash(script: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, **kwargs)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _alias_block(src: str) -> str:
    m = re.search(r'ALIAS_BLOCK="(.*?)\n"', src, flags=re.DOTALL)
    assert m, "could not find ALIAS_BLOCK heredoc in install.sh"
    return m.group(1)


# --------------------------------------------------------------------------- #
# F33 — prerequisite counter must not abort the loop under set -e
# --------------------------------------------------------------------------- #
def test_f33_raw_post_increment_from_zero_aborts():
    """Guard the premise: the OLD idiom really does abort (so the fix matters)."""
    _require_bash()
    res = _bash("set -e\nm=0\n((m++))\necho REACHED")
    assert res.returncode != 0, "premise broken: bare ((m++)) from 0 no longer aborts"
    assert "REACHED" not in res.stdout


def test_f33_missing_counter_does_not_abort_under_set_e():
    """The exact increment idiom install.sh uses must survive ``set -e`` from 0."""
    _require_bash()
    src = _read(INSTALL_SH)
    inc_lines = [
        ln.strip()
        for ln in src.splitlines()
        if not ln.lstrip().startswith("#")
        and re.search(r"\bmissing\b", ln)
        and ("++" in ln or "missing+1" in ln or "missing +" in ln)
    ]
    assert inc_lines, "install.sh has no `missing` increment lines to probe"
    body = "set -euo pipefail\nmissing=0\n" + "\n".join(inc_lines) + "\necho FINAL=$missing\n"
    res = _bash(body)
    assert res.returncode == 0, (
        f"missing-counter increment aborted under set -e: rc={res.returncode}\n"
        f"stderr={res.stderr!r}\nbody={body!r}"
    )
    # N increments from 0 must reach N (proves none was swallowed).
    assert f"FINAL={len(inc_lines)}" in res.stdout, (
        f"expected FINAL={len(inc_lines)}, got {res.stdout!r}"
    )


def test_f33_verify_setup_counters_do_not_abort_under_set_e():
    """verify-setup.sh shares the F33 pattern in its errors/warnings counters
    and is a documented standalone command — they must survive ``set -e`` from 0."""
    _require_bash()
    src = _read(VERIFY_SH)
    inc_lines = [
        ln.strip()
        for ln in src.splitlines()
        if not ln.lstrip().startswith("#")
        and re.search(r"\b(errors|warnings)\b", ln)
        and ("++" in ln or "errors+1" in ln or "warnings+1" in ln)
    ]
    assert inc_lines, "verify-setup.sh has no errors/warnings increment lines to probe"
    body = (
        "set -euo pipefail\nerrors=0\nwarnings=0\n"
        + "\n".join(inc_lines)
        + "\necho REACHED_SUMMARY\n"
    )
    res = _bash(body)
    assert res.returncode == 0 and "REACHED_SUMMARY" in res.stdout, (
        f"verify-setup.sh counter increment aborted under set -e: rc={res.returncode}\n"
        f"stderr={res.stderr!r}\nbody={body!r}"
    )


# --------------------------------------------------------------------------- #
# F34 — uv install must export the astral install dir (~/.local/bin)
# --------------------------------------------------------------------------- #
def test_f34_uv_install_exports_local_bin():
    src = _read(INSTALL_SH)
    assert ".local/bin" in src, (
        "install.sh does not export the real astral install dir (~/.local/bin) "
        "after installing uv — `uv sync` will be command-not-found"
    )


# --------------------------------------------------------------------------- #
# F35 — alias lists all 13 plugins incl. adopt; refresh is not blocked
# --------------------------------------------------------------------------- #
def test_f35_alias_lists_all_thirteen_plugins():
    block = _alias_block(_read(INSTALL_SH))
    for name in PLUGIN_NAMES:
        assert f"plugins/{name}" in block, f"alias block omits {name}"
    dirs = re.findall(r"--plugin-dir\s+\S*plugins/(shipwright-[a-z]+)", block)
    assert len(set(dirs)) == len(PLUGIN_NAMES), (
        f"alias has {len(set(dirs))} distinct plugins, expected {len(PLUGIN_NAMES)}: {sorted(set(dirs))}"
    )


def test_f35_alias_refresh_not_blocked_by_stale_guard():
    """A grep idempotency guard that skips on a pre-existing alias permanently
    pins a stale 12-plugin alias; the fix must rewrite the block on re-run."""
    src = _read(INSTALL_SH)
    assert 'echo "  Shell alias already exists' not in src, (
        "install.sh still has the stale-alias skip guard; a refresh cannot update "
        "a 12-plugin alias to 13"
    )


def test_f35_alias_refresh_backs_up_and_guards_empty():
    """The strip-and-rewrite must back up the rc and never overwrite it with an
    empty result (external-review HIGH: destructive rc overwrite). The actual
    strip behaviour is exercised end-to-end in the iterate's Confidence
    Calibration probe; here we pin the two structural safeguards."""
    src = _read(INSTALL_SH)
    assert ".shipwright.bak" in src, "alias refresh does not back up the shell rc"
    assert "[ -s " in src, "alias refresh does not guard the mv on non-empty output"


# --------------------------------------------------------------------------- #
# F36 — alias must quote --plugin-dir paths (space-containing clone paths)
# --------------------------------------------------------------------------- #
def test_f36_alias_quotes_plugin_dir_paths():
    block = _alias_block(_read(INSTALL_SH))
    raw_dirs = re.findall(r"--plugin-dir\s+(\S.*?)(?:\\\\| \\\\|\n|$)", block)
    assert raw_dirs, "no --plugin-dir entries found in alias block"
    for arg in raw_dirs:
        arg = arg.strip().rstrip("\\").strip()
        assert arg.startswith('\\"') or arg.startswith('"'), (
            f"--plugin-dir path not quoted (breaks on space-containing paths): {arg!r}"
        )


def test_f36_emitted_alias_survives_spaced_repo_root():
    """Render the alias under a space-containing REPO_ROOT and assert each
    --plugin-dir path tokenizes as a single argument (no split on the space)."""
    _require_bash()
    src = _read(INSTALL_SH)
    m = re.search(r'(ALIAS_BLOCK="\n.*?\n")', src, flags=re.DOTALL)
    assert m, "could not extract ALIAS_BLOCK assignment"
    probe = (
        'REPO_ROOT="/tmp/Program Files/My Projects/shipwright"\n'
        + m.group(1) + "\n"
        + 'claude() { for a in "$@"; do printf "ARG:%s\\n" "$a"; done; }\n'
        + 'eval "$ALIAS_BLOCK"\nshipwright\n'
    )
    res = _bash(probe)
    assert res.returncode == 0, f"alias eval failed: rc={res.returncode} stderr={res.stderr!r}"
    args = [ln[len("ARG:"):] for ln in res.stdout.splitlines() if ln.startswith("ARG:")]
    plugin_dirs = [a for a in args if "plugins/shipwright-" in a]
    assert len(plugin_dirs) == len(PLUGIN_NAMES), (
        f"spaced REPO_ROOT split paths: got {len(plugin_dirs)} plugin-dir args, "
        f"expected {len(PLUGIN_NAMES)}\nall args={args!r}"
    )
    for pd in plugin_dirs:
        assert pd.startswith("/tmp/Program Files/My Projects/shipwright/plugins/shipwright-"), (
            f"plugin-dir path was split on a space: {pd!r}"
        )


# --------------------------------------------------------------------------- #
# F37 — update-marketplace.sh must resolve python3/python/py, not bare `python`
# --------------------------------------------------------------------------- #
def test_f37_update_marketplace_resolves_a_python_interpreter():
    """On Ubuntu/Debian/macOS only ``python3`` exists; a bare ``python`` in a
    command substitution resolves to nothing and ``set -e`` silently aborts."""
    src = _read(UPDATE_SH)
    assert "python3" in src, (
        "update-marketplace.sh never references python3 — bare `python` aborts on "
        "Debian/Ubuntu/macOS"
    )
    bad = re.findall(r"\$\(\s*python\s+-c", src)
    assert not bad, (
        f"update-marketplace.sh still calls bare `python -c` in a substitution: {bad!r}"
    )


def test_f37_python_resolver_picks_python3_when_python_absent(tmp_path):
    """Drive the resolver with a PATH where only ``python3`` exists; it must
    resolve a non-empty interpreter without aborting."""
    _require_bash()
    src = _read(UPDATE_SH)
    m = re.search(r"(PYTHON_BIN=.*?)(?:\n\n|\necho )", src, flags=re.DOTALL)
    assert m, "could not find a PYTHON_BIN resolver block in update-marketplace.sh"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    py3 = shim_dir / "python3"
    py3.write_text("#!/usr/bin/env bash\nexec python3.real \"$@\" 2>/dev/null || echo ok\n", encoding="utf-8")
    py3.chmod(0o755)
    probe = "set -euo pipefail\n" + m.group(1) + '\necho "RESOLVED=$PYTHON_BIN"\n'
    res = subprocess.run(
        ["bash", "-c", probe],
        capture_output=True, text=True,
        env={**os.environ, "PATH": f"{shim_dir.as_posix()}:{os.environ.get('PATH', '')}"},
    )
    assert "RESOLVED=" in res.stdout, f"resolver did not set PYTHON_BIN: {res.stdout!r} / {res.stderr!r}"
    resolved = res.stdout.split("RESOLVED=", 1)[1].strip().splitlines()[0]
    assert resolved, "resolver returned an empty interpreter"


# --------------------------------------------------------------------------- #
# F39 — the python resolver must TEST-RUN each candidate, not just `command -v`
#        (Windows regression of F37: python3 is the Microsoft Store stub that
#        `command -v` finds but that exits 49 on invocation, aborting the sync
#        under set -euo pipefail at the first `$(python3 -c …)`).
# --------------------------------------------------------------------------- #
def _drive_python_resolver(block: str, varname: str, tmp_path) -> str:
    """Run a resolver ``block`` (which sets ``varname``) under a PATH where
    ``python3`` is a Microsoft-Store-style stub — present on PATH, found by
    ``command -v``, but exits 49 on ``--version`` with no real output — and
    ``python`` is a working interpreter. Returns the resolved interpreter name.
    A ``command -v``-only probe returns ``python3`` (the stub); a test-run probe
    must fall through to ``python``."""
    _require_bash()
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    stub = shim_dir / "python3"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'echo "Python was not found; install from the Microsoft Store" >&2\n'
        "exit 49\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    real = shim_dir / "python"
    real.write_text('#!/usr/bin/env bash\necho "Python 3.11.9"\n', encoding="utf-8")
    real.chmod(0o755)
    probe = "set -euo pipefail\n" + block + f'\necho "RESOLVED=${varname}"\n'
    res = subprocess.run(
        ["bash", "-c", probe],
        capture_output=True, text=True,
        # Prepend the shims so python3=stub is found first; keep the host PATH so
        # the `#!/usr/bin/env bash` shebang still resolves a real bash.
        env={**os.environ, "PATH": f"{shim_dir.as_posix()}:{os.environ.get('PATH', '')}"},
    )
    assert res.returncode == 0, (
        f"resolver aborted on a stub python3: rc={res.returncode} stderr={res.stderr!r}"
    )
    assert "RESOLVED=" in res.stdout, f"resolver did not set {varname}: {res.stdout!r} / {res.stderr!r}"
    return res.stdout.split("RESOLVED=", 1)[1].strip().splitlines()[0]


def test_f39_update_marketplace_probe_skips_failing_python3_stub(tmp_path):
    """update-marketplace.sh: a ``command -v``-only probe picks the Microsoft
    Store python3 stub, then the first ``$(python3 -c …)`` aborts the whole
    sync under ``set -euo pipefail``. The probe must test-run each candidate and
    fall through to the real ``python``."""
    src = _read(UPDATE_SH)
    m = re.search(r"(PYTHON_BIN=\"\".*?\ndone)", src, flags=re.DOTALL)
    assert m, "could not find a PYTHON_BIN resolver loop in update-marketplace.sh"
    resolved = _drive_python_resolver(m.group(1), "PYTHON_BIN", tmp_path)
    assert resolved == "python", (
        f"probe picked the failing python3 stub instead of the working interpreter: {resolved!r}"
    )


def test_f39_verify_setup_probe_skips_failing_python3_stub(tmp_path):
    """verify-setup.sh shares the python-resolution pattern and is a documented
    standalone command — it must apply the same test-run probe so a Microsoft
    Store python3 stub is skipped in favour of the real interpreter."""
    src = _read(VERIFY_SH)
    m = re.search(r"((?:SW_PYTHON|ENV_PYTHON)=\"\".*?\ndone)", src, flags=re.DOTALL)
    assert m, "could not find a python resolver loop in verify-setup.sh"
    varname = m.group(1).split("=", 1)[0]
    resolved = _drive_python_resolver(m.group(1), varname, tmp_path)
    assert resolved == "python", (
        f"verify-setup.sh probe picked the failing python3 stub: {resolved!r}"
    )


# --------------------------------------------------------------------------- #
# F38 — verify-setup.sh must parse .env.local as dotenv, not `source` it
# --------------------------------------------------------------------------- #
def test_f38_verify_setup_does_not_source_env_local():
    src = _read(VERIFY_SH)
    assert 'source "$PROJECT_ROOT/.env.local"' not in src and "source $PROJECT_ROOT/.env.local" not in src, (
        "verify-setup.sh still `source`s .env.local — a spaced/quoted value is "
        "executed as a shell command instead of parsed as dotenv"
    )
    assert any(tok in src for tok in ("env.py", "parse_env_file", "load_shipwright_env")), (
        "verify-setup.sh should parse .env.local via the canonical reader (shared/scripts/lib/env.py)"
    )


def test_f38_spaced_dotenv_value_does_not_execute_as_command(tmp_path):
    """A .env.local value with shell metacharacters must not be executed.
    Probe the canonical parser the fix delegates to."""
    env_file = tmp_path / ".env.local"
    sentinel = tmp_path / "PWNED"
    env_file.write_text(
        f'OPENROUTER_API_KEY=sk-with spaces and $(touch "{sentinel.as_posix()}")\n',
        encoding="utf-8",
    )
    parser_dir = REPO_ROOT / "shared" / "scripts" / "lib"
    res = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            + "from env import parse_env_file; from pathlib import Path; "
            + "d = parse_env_file(Path(sys.argv[2])); "
            + "print('KEY=' + repr(d.get('OPENROUTER_API_KEY')))",
            str(parser_dir), str(env_file),
        ],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, f"parser crashed on spaced value: {res.stderr!r}"
    assert not sentinel.exists(), "spaced dotenv value executed a command (source-style eval)"
    assert "KEY=" in res.stdout, f"parser did not return the key: {res.stdout!r}"


def test_f38_verify_setup_filters_malformed_keys():
    """The dotenv key emitter in verify-setup.sh must restrict keys to a
    conservative identifier pattern (external-review HIGH: a malformed key
    must not influence the shell's membership test)."""
    src = _read(VERIFY_SH)
    assert "A-Za-z_" in src and "re.fullmatch" in src, (
        "verify-setup.sh does not validate dotenv key names against an "
        "identifier pattern before handing them to the shell"
    )
    # The shell membership test must be fixed-string (-F), not regex/glob.
    assert "grep -Fxq" in src, (
        "verify-setup.sh uses a regex/glob grep for key membership instead of "
        "fixed-string exact match"
    )
