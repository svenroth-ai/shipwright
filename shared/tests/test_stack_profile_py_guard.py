"""Tests of the ``*.py`` stack-profile guard (campaign stack-profile-resolver S5).

The rules, allowlists and the reasoning live in ``stack_profile_py_rules.py`` (handler heuristics in
``stack_profile_py_handlers.py``); this module runs them over the tracked tree and pins them with
planted red and green cases. Reads the git INDEX. Tagged to FR-01.06; see test_profile_resolver.py
for the FR note.
"""

from __future__ import annotations

import ast
import textwrap

import pytest

from shared.tests.stack_profile_py_rules import (
    ALLOWLIST, PINNED_WRAPPERS, RESOLVER_MODULES, SWALLOW_ALLOWLIST, _all_swallows, _is_test_file, _modules,
    module_wrappers, path_findings, swallow_findings,
)

pytestmark = pytest.mark.covers("FR-01.06")

_RERAISER = (
    "def _helper(n):\n    try:\n        return pr.resolve_profile(n)\n    except ValueError as exc:\n"
    "        raise with_hint(exc, n) from exc\n\n\n")
_RAISES_OTHER = (
    "def _wrap(n):\n    try:\n        return pr.resolve_profile(n)\n    except ValueError as e:\n"
    "        raise RuntimeError(str(e))\n\n\n")


def test_production_modules_with_a_test_prefix_are_scanned():
    mods = _modules()
    assert "plugins/shipwright-test/scripts/lib/test_runner.py" in mods
    assert "plugins/shipwright-deploy/scripts/lib/test_gate.py" in mods
    assert not any("/tests/" in n or n.endswith("conftest.py") for n in mods)
    assert _is_test_file("plugins/x/tests/test_a.py") and not _is_test_file("plugins/x/scripts/lib/test_runner.py")


def test_planting_a_swallow_in_test_runner_turns_the_guard_red():
    rel = "plugins/shipwright-test/scripts/lib/test_runner.py"
    src = _modules()[rel]
    assert not swallow_findings(src, rel), "the real test_runner.py must be clean"
    needle = "        except ValueError as exc:  # unknown / corrupt / too new: fail loud, name the file, no fallback\n            return _fail(exc)"
    assert needle in src, "test_runner.py's resolver handler moved: update this planted case"
    planted = src.replace(needle, needle.replace("return _fail(exc)", "return None"), 1)
    assert swallow_findings(planted, rel)


def test_pinned_wrappers_still_exist():
    defined = {f.name for src in _modules().values() for f in ast.walk(ast.parse(src))
               if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not (PINNED_WRAPPERS - defined), f"pinned wrappers no longer defined: {PINNED_WRAPPERS - defined}"


def test_resolver_modules_are_excluded_by_location_and_the_allowlist_is_the_s3_family_only():
    assert RESOLVER_MODULES <= set(_modules())
    # the exclusion is load-bearing: scanned, profile_resolver.py WOULD be flagged (it catches ProfileError around
    # its own resolver calls); if it ever stops doing that the exclusion is stale. profile_model.py has no such
    # handler today and is excluded as part of the resolver family.
    assert swallow_findings(_modules()["shared/scripts/profile_resolver.py"], "shared/scripts/profile_resolver.py")
    assert set(SWALLOW_ALLOWLIST) == {
        ("plugins/shipwright-adopt/scripts/lib/profile_matcher.py", "_discover"),
        ("plugins/shipwright-adopt/scripts/lib/adopt_profile.py", "hint_warning")}


def test_no_module_builds_a_stack_profile_path_outside_the_resolver():
    bad = [f for rel, src in _modules().items() if rel not in ALLOWLIST for f in path_findings(src, rel)]
    assert not bad, "go through profile_resolver / profile_consumer, not a hand-built path:\n" + "\n".join(bad)


def test_every_path_allowlist_entry_still_excuses_a_real_finding():
    stale = [rel for rel in ALLOWLIST if not path_findings(_modules().get(rel, ""), rel)]
    assert not stale, f"allowlist entries excuse no finding: {stale}"


def test_no_caller_swallows_a_resolver_error():
    bad = [f for rel, scope, f in _all_swallows() if (rel, scope) not in SWALLOW_ALLOWLIST]
    assert not bad, (
        "an `except ValueError` around a resolver call must re-raise, exit non-zero, return a failure "
        "or branch on .kind:\n" + "\n".join(bad))


def test_every_swallow_allowlist_entry_still_excuses_a_real_finding():
    live = {(rel, scope) for rel, scope, _ in _all_swallows()}
    stale = [k for k in SWALLOW_ALLOWLIST if k not in live]
    assert not stale, f"swallow allowlist entries excuse no finding: {stale}"


def test_path_rule_is_red_on_planted_forms_and_green_on_the_neighbours():
    for planted in ('os.path.join(root, "profiles", "x.json")', 'Path(root) / "shared" / "profiles"',
                    'p = "shared/profiles/vite-hono.json"', 'join(home, ".shipwright", "profiles")',
                    'd = root + "/.shipwright/profiles/"', 'p = Path(root) / ".shipwright/profiles/my-stack.json"',
                    'p = "~/.shipwright/profiles/user-stack.json"'):
        assert path_findings(planted), planted
    for fine in ('"""Docstring about shared/profiles."""', 'x = listing["profiles"]', 'd = {"profiles": rows}',
                 '# shared/profiles in a comment', 'p = "profile_resolver"', 'p = "deploy-profile.json"',
                 'x = d.get("profiles")', 'x = d.pop("profiles", None)', 'x = d.setdefault("profiles", [])'):
        assert not path_findings(fine), fine


def _try(call: str, handler: str, exc: str = "ValueError as e", prefix: str = "") -> str:
    return (prefix + "def f():\n    try:\n        " + call + "\n    except " + exc + ":\n"
            + textwrap.indent(textwrap.dedent(handler).strip("\n"), "        ") + "\n")


def test_swallow_rule_is_red_on_planted_handlers():
    swallowed = [
        _try("pr.resolve_profile(n)", "return None"),
        _try("pc.resolve_named(n, r)", "pass", "Exception"),
        _try("load_profile_file(p)", "data = {}", ""),
        _try("pr.list_profiles(r)", "print(e)\nreturn 0"),
        _try("pr.resolve_profile(n)", "sys.exit(0)"),
        _try("pr.resolve_profile(n)", "sys.exit()"),
        _try("pr.resolve_profile(n)", "raise SystemExit(0)"),
        _try("pr.resolve_profile(n)", "raise SystemExit"),  # a bare name is a zero exit too
        _try("pr.resolve_profile(n)", "raise SystemExit from e"),
        "class C:\n    def f(self):\n        try:\n            pr.resolve_profile(n)\n"
        "        except ValueError:\n            return None\n",
        # .kind only mentioned (message / log), not branched on
        _try("pr.resolve_profile(n)", "print(e.kind)\nreturn None"),
        _try("pr.resolve_profile(n)", "return f'bad {e.kind}'"),
        _try("pr.resolve_profile(n)", "log(getattr(e, 'kind', 'x'))\nreturn None"),
        # returned calls that do not receive the exception, or only convert / log it, or are no failure builder
        _try("pr.resolve_profile(n)", "return _defaults()"),
        _try("pr.resolve_profile(n)", "return dict()"),
        _try("pr.resolve_profile(n)", "return _skipped(phase, name, 'x')"),
        _try("pr.resolve_profile(n)", "return str(e)"),
        _try("pr.resolve_profile(n)", "return log.warning(e)"),
        _try("pr.resolve_profile(n)", "return _skipped(p, n, e)"),
        # the Profile* family
        _try("pr.resolve_profile(n)", "return None", "pc.ProfileInvalid"),
        _try("pr.resolve_profile(n)", "return None", "ProfileNotFound"),
        _try("pr.resolve_profile(n)", "return None", "(OSError, pc.ProfileSchemaDrift)"),
        # newly listed resolver calls
        _try("pc.resolve_in_dir(n, d)", "return None"),
        _try("pc.config_profile(root)", "return None"),
        _try("pr.check_name(n)", "return None"),
        # wrappers: same module, a re-raising helper (still a wrapper), pinned cross-module
        _try("_resolve(root, name)", "return None", prefix="def _resolve(r, n):\n    return pr.resolve_profile(n, r)\n\n\n"),
        _try("_helper(n)", "return None", prefix=_RERAISER),
        _try("load_resolved(p, None, cwd)", "return None"),
        # the pinned dev-server wrapper, kind read into a local and then dropped
        _try("_get_services_resolved(profile, cwd)", "kind = getattr(e, 'kind', None)\nreturn {'error': str(e)}"),
        # contextlib.suppress, and try/except*
        "def f():\n    with contextlib.suppress(ValueError):\n        pr.resolve_profile(n)\n",
        _try("pr.resolve_profile(n)", "return None").replace("except ", "except* "),
        # suppress() names the same error family as a handler does
        "def f():\n    with contextlib.suppress(ProfileInvalid):\n        pr.resolve_profile(n)\n",
        "def f():\n    with contextlib.suppress(pc.ProfileNotFound):\n        pr.resolve_profile(n)\n",
        # a local helper around a PINNED cross-module wrapper is itself a wrapper
        _try("_mine(p)", "return None", prefix="def _mine(p):\n    return load_resolved(p, None, cwd)\n\n\n"),
    ]
    for src in swallowed:
        assert swallow_findings(src), src


def test_module_wrappers_are_seeded_with_the_pinned_ones():
    tree = ast.parse("def _mine(p):\n    return load_resolved(p, None, cwd)\n")
    assert module_wrappers(tree) >= {"_mine"} | PINNED_WRAPPERS


def test_modules_decode_a_bom_and_name_the_file_that_cannot_be_read(monkeypatch):
    from shared.tests import stack_profile_py_rules as rules

    monkeypatch.setattr(rules, "tracked", lambda *_: ["plugins/a.py", "plugins/b.py"])
    monkeypatch.setattr(rules, "read_index", lambda names: {"plugins/a.py": b"\xef\xbb\xbfx = 1\n", "plugins/b.py": b"\xff"})
    rules._modules.cache_clear()
    try:
        with pytest.raises(AssertionError, match="plugins/b.py"):
            rules._modules()
        monkeypatch.setattr(rules, "read_index", lambda names: {"plugins/a.py": b"\xef\xbb\xbfx = 1\n"})
        rules._modules.cache_clear()
        assert rules._modules() == {"plugins/a.py": "x = 1\n"}
    finally:
        rules._modules.cache_clear()


def test_swallow_rule_is_green_on_the_loud_handlers_and_the_neighbours():
    loud = [
        _try("pr.resolve_profile(n)", "raise"),
        _try("pr.resolve_profile(n)", "sys.exit(getattr(e, 'exit_code', 1))"),
        _try("pr.resolve_profile(n)", "return _fail(e)"),
        _try("pr.resolve_profile(n)", "return build_error(phase, exc=e)"),
        _try("pr.resolve_profile(n)", "return 3"),
        _try("pr.resolve_profile(n)", "return -1"),  # a negative exit code is a failure, not a swallow
        _try("pr.resolve_profile(n)", "if e.kind == 'not_found':\n    return None\nraise"),
        _try("pr.resolve_profile(n)", "return None if e.kind == 'not_found' else 2"),
        _try("pr.resolve_profile(n)", "return e.exit_code"),
        _try("json.loads(s)", "return None"),  # not a resolver call
        _try("check_name(entry)", "return None"),  # a plain helper named like the resolver's, not an attribute call
        # multiservice's real handler: the kind goes through one local into a test
        _try("_get_services_resolved(profile, cwd)",
             "kind = getattr(e, 'kind', None)\nif kind:\n    return {'error': str(e), 'kind': kind}\n"
             "return {'error': f'invalid services: {e}'}"),
        # a re-raise as another type protects the helper's own call, so the caller is not a wrapper caller
        _try("_wrap(n)", "return None", prefix=_RAISES_OTHER),
        # a wrapper that protects its own call is not a wrapper
        _try("_safe(root, name)", "return None", prefix=(
            "def _safe(r, n):\n    try:\n        return pr.resolve_profile(n, r)\n    except ValueError as e:\n"
            "        raise RuntimeError(str(e))\n\n\n")),
    ]
    for src in loud:
        assert not swallow_findings(src), src
