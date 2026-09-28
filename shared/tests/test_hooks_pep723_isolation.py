"""PEP 723 inline script metadata as the version-independent hook isolation.

`--no-project` in hooks.json stops uv from syncing the session CWD's project,
but it does NOT stop uv honoring a CWD `.python-version` (measured on uv 0.11:
a hook without a header tried to *download* the pinned interpreter), and on
uv >= 0.12 project discovery is script-relative anyway
(astral-sh/uv#14585) — so the flag is defense-in-depth whose necessity depends
on the uv release. A script carrying a `# /// script` header never consults
any ambient project, `.venv` or `.python-version`, on any uv version.

`--no-project` STAYS in every hooks.json entry (still asserted by
test_hooks_uv_run_pinned.py); the header is the second, independent layer.

The ledger of scripts that must carry a header is DERIVED from hooks.json (every
`uv run` target), so a newly added hook without a header fails here instead of
being discovered live. Scripts reached only via `sys.executable` from an entry
point (the `run_if_cache_ready.py` fan-out chain) ignore inline metadata and
inherit the entry point's environment, so they carry no header of their own.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "shared" / "scripts" / "hooks"

_UV_RUN_TARGET = re.compile(r'uv run((?:(?!uv run)[^"])*)"([^"]+)"')
# The reference regex from PEP 723.
_BLOCK = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")
_DEP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _hook_commands() -> list[tuple[Path, str]]:
    def walk(node: object):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "command" and isinstance(value, str):
                    yield value
                else:
                    yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    out: list[tuple[Path, str]] = []
    for hooks_path in sorted(REPO_ROOT.glob("plugins/*/hooks*/hooks.json")):
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        out.extend((hooks_path.parent.parent, cmd) for cmd in walk(config))
    return out


_UNMAPPED: list[str] = []  # `uv run` commands whose target the regex could not read


def _entry_points() -> dict[Path, set[str]]:
    """Every script a hooks.json runs via `uv run`, with the `--with` packages it gets."""
    found: dict[Path, set[str]] = {}
    for plugin, cmd in _hook_commands():
        matches = _UV_RUN_TARGET.findall(cmd)
        if len(matches) != cmd.count("uv run"):
            _UNMAPPED.append(cmd)  # reported by a real test below, not a collection error
        for flags, target in matches:
            path = (plugin / target.replace("${CLAUDE_PLUGIN_ROOT}/", "")).resolve()
            found.setdefault(path, set()).update(re.findall(r"--with (\S+)", flags))
    return found


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


_ENTRY_POINTS = _entry_points()
PEP723_HOOKS: tuple[Path, ...] = tuple(sorted(_ENTRY_POINTS))


def test_ledger_reads_every_uv_run_hook_command() -> None:
    """A `uv run` command the ledger cannot map to a script (unquoted path, `python x.py`,
    unbraced variable, a target that does not exist) would let a headerless hook pass CI, so
    each one fails here by name. The floor stops a broken glob/regex passing vacuously."""
    assert not _UNMAPPED, "hooks.json `uv run` commands the ledger cannot map to a script:\n" + "\n".join(_UNMAPPED)
    missing = [str(p) for p in _ENTRY_POINTS if not p.is_file()]
    assert not missing, f"hooks.json targets that do not exist: {missing}"
    assert len(_ENTRY_POINTS) >= 30, f"only {len(_ENTRY_POINTS)} hook entry points found"


def _read_header(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    blocks = [m for m in _BLOCK.finditer(text) if m.group("type") == "script"]
    assert len(blocks) == 1, f"{path.name}: expected exactly one `# /// script` block, found {len(blocks)}"
    body = "".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in blocks[0].group("content").splitlines(keepends=True)
    )
    return tomllib.loads(body)


@pytest.mark.parametrize("path", PEP723_HOOKS, ids=_rel)
def test_hook_has_wellformed_header(path: Path) -> None:
    meta = _read_header(path)
    assert meta.get("requires-python") == ">=3.11", f"{path.name}: header must pin requires-python >=3.11"
    assert isinstance(meta.get("dependencies"), list), f"{path.name}: header must declare `dependencies` (even if [])"


@pytest.mark.parametrize("path", sorted(_ENTRY_POINTS), ids=_rel)
def test_header_deps_cover_hooks_json_with_flags(path: Path) -> None:
    """Header deps must be a superset of the `--with` flags hooks.json passes for the
    same script, so the header alone is sufficient if the flags are ever dropped."""
    declared = {m.group(0).lower() for d in _read_header(path)["dependencies"] if (m := _DEP_NAME.match(d))}
    missing = _ENTRY_POINTS[path] - declared
    assert not missing, f"{path.name}: hooks.json passes --with {sorted(missing)} but the header does not declare them"


def test_no_project_still_present_alongside_headers() -> None:
    """Precondition for the layering claim: the flag is still in every entry, so the
    header tests prove a SECOND layer rather than replacing the first."""
    commands = [c for _, c in _hook_commands() if "uv run" in c]
    assert commands, "no `uv run` hook commands found — fixture broken"
    flag_sets = [flags.strip() for c in commands for flags, _ in _UV_RUN_TARGET.findall(c)]
    assert flag_sets, "no `uv run` targets parsed — regex no longer matches hooks.json shape"
    assert all(f.startswith("--no-project") for f in flag_sets)


def _uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            raise AssertionError("uv not on PATH in CI — install it (astral-sh/setup-uv)")
        pytest.skip("uv not installed")
    return uv


@pytest.fixture()
def poisoned_cwd(tmp_path: Path) -> Path:
    """A CWD whose ambient project AND interpreter pin are both unusable."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "poison"\nversion = "0"\nrequires-python = ">=99"\n', encoding="utf-8"
    )
    (tmp_path / ".python-version").write_text("3.99\n", encoding="utf-8")
    return tmp_path


# A representative spread for the (slow, real-uv) poisoned-CWD run: stdlib-only and
# pyyaml+jsonschema. The static tests above cover every entry point.
_PROBED_NAMES = {"suggest_iterate.py", "audit_compliance_on_stop.py"}
_PROBED = [p for p in PEP723_HOOKS if p.name in _PROBED_NAMES]
assert {p.name for p in _PROBED} == _PROBED_NAMES, "a probed hook was renamed or is no longer a hook"


def _run_in_poisoned_cwd(flags: list[str], script: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    # Strip uv config AND the Claude/Shipwright session variables: two probed hooks write to
    # CLAUDE_ENV_FILE / resolve SHIPWRIGHT_PROJECT_ROOT, which must never point at a real session.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("UV_", "CLAUDE", "SHIPWRIGHT_")) and k != "VIRTUAL_ENV"
    }
    env["UV_PYTHON_DOWNLOADS"] = "never"  # an unsatisfiable pin must fail fast, never download
    return subprocess.run(
        [_uv(), "run", *flags, str(script)],
        input=json.dumps({"session_id": "s", "cwd": str(cwd)}),
        cwd=cwd, env=env, capture_output=True, text=True, timeout=180,
    )


@pytest.mark.parametrize("flags", [[], ["--no-project"]], ids=["plain", "no-project"])
@pytest.mark.parametrize("path", _PROBED, ids=lambda p: p.name)
def test_header_hook_ignores_poisoned_cwd_on_any_uv(path: Path, flags: list[str], poisoned_cwd: Path) -> None:
    """The invariant holds with AND without `--no-project`: the header alone isolates."""
    proc = _run_in_poisoned_cwd(flags, path, poisoned_cwd)
    assert proc.returncode == 0, f"{path.name} {flags}: rc={proc.returncode}\n{proc.stderr}"
    assert "error:" not in proc.stderr, f"{path.name} {flags}: uv error surfaced:\n{proc.stderr}"


def test_control_headerless_script_is_affected_by_cwd_python_pin(poisoned_cwd: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Negative control: without the header, `--no-project` does NOT stop uv honoring the
    CWD `.python-version` (the uninstallable-but-compatible `3.99` makes the run fail). Skipped where the
    running uv ignores the pin for out-of-tree scripts, so the vacuity is visible in the
    output instead of the header tests above silently proving nothing."""
    probe = tmp_path_factory.mktemp("headerless") / "probe.py"
    probe.write_text("pass\n", encoding="utf-8")
    assert "/// script" not in probe.read_text(encoding="utf-8"), "control must be headerless"
    proc = _run_in_poisoned_cwd(["--no-project"], probe, poisoned_cwd)
    if proc.returncode == 0:
        pytest.skip("this uv ignores a CWD .python-version for out-of-tree scripts; header adds nothing to prove here")
    assert "3.99" in proc.stderr or "interpreter" in proc.stderr.lower(), f"failed for an unrelated reason:\n{proc.stderr}"


def test_audit_compliance_header_declares_packaging() -> None:
    """The in-process SBOM version sort imports `packaging`; the ambient environment used to
    supply it, the isolated one only does if the header declares it."""
    meta = _read_header(HOOKS_DIR / "audit_compliance_on_stop.py")
    assert {"pyyaml", "jsonschema", "packaging"} <= {d.lower() for d in meta["dependencies"]}
